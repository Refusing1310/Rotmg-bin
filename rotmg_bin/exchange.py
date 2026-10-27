"""Offline, randomised multi-item inventory-clearance exchange quotes.

All prices are manually supplied integer value units. This module neither
reads the game client nor performs in-game trades.
"""
from collections import Counter
import secrets

BPS = 10_000
DEFAULT_EXPECTED_PAYOUT_BPS = 9_500   # Long-run target: 95% of deposited value
DEFAULT_MIN_PAYOUT_BPS = 7_000       # Ordinary losses may return as little as 70%
DEFAULT_MAX_PAYOUT_BPS = 30_000      # Rare stock-backed wins may return up to 300%
DEFAULT_JACKPOT_THRESHOLD_BPS = 15_000  # At least 150% is a jackpot
SUPPORTED_CAPACITIES = (8, 16, 24)   # Backpack upgrades vary by character
SINGLE_TRADE_LIMIT = 8              # Conservative, not a verified current UI contract
MAX_STOCK_UNITS = 128
MAX_STATES = 50_000


class QuoteInputError(ValueError):
    """Invalid or unsupported manual quote input."""


def _integer(value, field, minimum=1, maximum=None):
    if type(value) is not int or value < minimum or (
        maximum is not None and value > maximum
    ):
        limit = f", at most {maximum}" if maximum is not None else ""
        raise QuoteInputError(f"{field} must be an integer >= {minimum}{limit}")
    return value


def _catalog(price_book):
    if not isinstance(price_book, dict):
        raise QuoteInputError("price_book must be an object")
    version = price_book.get("version")
    if not isinstance(version, str) or not version.strip():
        raise QuoteInputError("price_book.version must be a nonempty string")
    items = price_book.get("items")
    if not isinstance(items, dict) or not items:
        raise QuoteInputError("price_book.items must be a nonempty object")
    for item_id, item in items.items():
        if not isinstance(item_id, str) or not item_id.strip():
            raise QuoteInputError("item IDs must be nonempty strings")
        if not isinstance(item, dict):
            raise QuoteInputError(f"item {item_id!r} must be an object")
        if not isinstance(item.get("name"), str) or not item["name"].strip():
            raise QuoteInputError(f"item {item_id!r} must have a display name")
        _integer(item.get("value"), f"item {item_id!r} value")
        if type(item.get("tradable")) is not bool:
            raise QuoteInputError(f"item {item_id!r} needs explicit tradable boolean")
    return version, items


def _lines(raw, field, *, allow_duplicates=True):
    if not isinstance(raw, list):
        raise QuoteInputError(f"{field} must be an array")
    result = Counter()
    for index, line in enumerate(raw):
        if not isinstance(line, dict):
            raise QuoteInputError(f"{field}[{index}] must be an object")
        item_id = line.get("item_id")
        if not isinstance(item_id, str) or not item_id.strip():
            raise QuoteInputError(f"{field}[{index}].item_id is required")
        qty = _integer(line.get("quantity"), f"{field}[{index}].quantity", maximum=128)
        if not allow_duplicates and item_id in result:
            raise QuoteInputError(f"duplicate {field} item ID: {item_id}")
        result[item_id] += qty
    return result


def _policy(raw):
    raw = {} if raw is None else raw
    if not isinstance(raw, dict):
        raise QuoteInputError("policy must be an object")
    target = _integer(raw.get("expected_payout_bps", DEFAULT_EXPECTED_PAYOUT_BPS),
                      "expected_payout_bps", maximum=BPS - 1)
    lower = _integer(raw.get("minimum_payout_bps", DEFAULT_MIN_PAYOUT_BPS),
                     "minimum_payout_bps", maximum=20_000)
    upper = _integer(raw.get("maximum_payout_bps", DEFAULT_MAX_PAYOUT_BPS),
                     "maximum_payout_bps", maximum=100_000)
    if not lower < target < upper:
        raise QuoteInputError("minimum_payout_bps must be < expected_payout_bps "
                              "< maximum_payout_bps")
    jackpot = _integer(raw.get("jackpot_threshold_bps", DEFAULT_JACKPOT_THRESHOLD_BPS),
                       "jackpot_threshold_bps", minimum=BPS + 1, maximum=upper)
    capacity = raw.get("inventory_capacity", 8)
    if type(capacity) is not int or capacity not in SUPPORTED_CAPACITIES:
        raise QuoteInputError("inventory_capacity must be one of 8, 16, 24")
    return target, lower, upper, jackpot, capacity


def _normalise(counts):
    return [{"item_id": item_id, "quantity": counts[item_id]}
            for item_id in sorted(counts)]


def _get_candidates(stock, items, input_count, input_value, minimum_bps,
                    maximum_bps):
    """Represent each reachable (units, value) by its stable best bundle.

    The dynamic-programming frontier is explicitly bounded, preventing an
    adversarially enormous stock/price book from exhausting memory.
    """
    minimum_value = (input_value * minimum_bps + BPS - 1) // BPS
    maximum_value = input_value * maximum_bps // BPS
    # Model all physically smaller reward bundles offline. The separate
    # single-trade limit is enforced only at settlement verification.
    max_count = input_count - 1
    if max_count <= 0:
        return []
    available = []
    for item_id in sorted(stock):
        item = items[item_id]
        if not item["tradable"] or item["value"] > maximum_value:
            continue
        available.extend([(item_id, item["value"])] *
                         min(stock[item_id], max_count))
    if len(available) > MAX_STOCK_UNITS:
        raise QuoteInputError(f"at most {MAX_STOCK_UNITS} eligible stock units supported")
    # key: (item count, total value). Same valuation -> prefer fewer
    # physical items and deterministic lexicographic tie-breaks.
    states = {(0, 0): ()}
    for item_id, value in available:
        next_states = dict(states)
        for (count, total), bundle in states.items():
            if count >= max_count or total + value > maximum_value:
                continue
            key = (count + 1, total + value)
            candidate = bundle + (item_id,)
            if key not in next_states or candidate < next_states[key]:
                next_states[key] = candidate
        if len(next_states) > MAX_STATES:
            raise QuoteInputError("stock combinations exceed safe planning limit")
        states = next_states
    # A single representative per distinct payout value, minimising item
    # count: the user receives fewer items for equivalent value.
    by_value = {}
    for (count, value), bundle in states.items():
        if count and minimum_value <= value <= maximum_value:
            if value not in by_value or (count, bundle) < (
                len(by_value[value]), by_value[value]
            ):
                by_value[value] = bundle
    return sorted(by_value.items())


def _prepare(request):
    if not isinstance(request, dict):
        raise QuoteInputError("request must be an object")
    version, catalog = _catalog(request.get("price_book"))
    expected, minimum, maximum, jackpot, capacity = _policy(request.get("policy"))
    incoming = _lines(request.get("offer"), "offer")
    input_count = sum(incoming.values())
    if not 2 <= input_count <= capacity:
        raise QuoteInputError(f"offer must contain 2 to {capacity} item units")
    stock = _lines(request.get("stock"), "stock", allow_duplicates=False)
    for item_id in incoming:
        if item_id not in catalog:
            raise QuoteInputError(f"offered item {item_id!r} has no known price")
        if not catalog[item_id]["tradable"]:
            raise QuoteInputError(f"offered item {item_id!r} is not tradable")
    for item_id in stock:
        if item_id not in catalog:
            raise QuoteInputError(f"stock item {item_id!r} has no known price")
    input_value = sum(catalog[item_id]["value"] * qty
                      for item_id, qty in incoming.items())
    outcomes = _get_candidates(stock, catalog, input_count, input_value,
                               minimum, maximum)
    target_numerator = input_value * expected
    below = [c for c in outcomes if c[0] * BPS < target_numerator]
    above = [c for c in outcomes if c[0] * BPS > target_numerator]
    base = {
        "price_book_version": version,
        "offer": _normalise(incoming),
        "offer_units": input_count,
        "offer_value": input_value,
        "value_unit": "user_defined",
        "policy": {
            "inventory_capacity": capacity,
            "expected_payout_bps": expected,
            "minimum_payout_bps": minimum,
            "maximum_payout_bps": maximum,
            "jackpot_threshold_bps": jackpot,
        },
    }
    # Require a genuine two-sided, nondegenerate lottery. This ensures the
    # configured average is *actually achievable* with physical stock items.
    if not below or not above:
        return base, None
    # Ordinary outcome: as valuable as stock permits below the expected value.
    # Rare outcome: highest physical reward within the allowed payout band.
    # Its probability automatically falls as the upper payout becomes bigger.
    # Without stock worth >100% of the deposit a genuine win isn't possible.
    low_value, low_bundle = below[-1]
    high_value, high_bundle = above[-1]
    span = (high_value - low_value) * BPS
    upper_wins = target_numerator - low_value * BPS
    return base, (low_value, low_bundle, high_value, high_bundle,
                  span, upper_wins, catalog)


def quote_exchange(request, *, randbelow=None):
    """Random payout with exact conditional expected value on given stock.

    randbelow(n) is injectable solely for reproducible offline tests. In
    normal use, unpredictability comes from secrets.randbelow.
    """
    base, lottery = _prepare(request)
    if lottery is None:
        return {
            **base,
            "status": "unavailable",
            "reason": "no_two_sided_stock_lottery_at_target_value",
            "payout": None,
        }
    low_value, low_bundle, high_value, high_bundle, span, upper_wins, catalog = lottery
    generator = secrets.randbelow if randbelow is None else randbelow
    draw = generator(span)
    if type(draw) is not int or not 0 <= draw < span:
        raise QuoteInputError("random draw must be an integer within lottery range")
    choose_upper = draw < upper_wins
    value, bundle = ((high_value, high_bundle) if choose_upper
                     else (low_value, low_bundle))
    selected = Counter(bundle)
    payout = [{**line, "name": catalog[line["item_id"]]["name"]}
              for line in _normalise(selected)]
    payout_units = len(bundle)
    return {
        **base,
        "status": "quoted",
        "draw": draw,  # Reproducibility only; NOT signed or fraud-resistant.
        "lottery": {
            "lower_value": low_value,
            "upper_value": high_value,
            "upper_probability_numerator": upper_wins,
            "probability_denominator": span,
            "upper_outcome_is_profitable": high_value > base["offer_value"],
            "upper_outcome_is_jackpot": (high_value * BPS >= base["offer_value"] *
                                         base["policy"]["jackpot_threshold_bps"]),
        },
        "payout": payout,
        "payout_units": payout_units,
        "payout_value": value,
        "is_profit_for_player": value > base["offer_value"],
        "is_jackpot": (value * BPS >= base["offer_value"] *
                       base["policy"]["jackpot_threshold_bps"]),
        "retained_value": base["offer_value"] - value,
        "inventory_slots_freed": base["offer_units"] - payout_units,
        "expected_payout_value_numerator": base["offer_value"] *
                                            base["policy"]["expected_payout_bps"],
        "expected_payout_value_denominator": BPS,
        "requires_multi_trade": (base["offer_units"] > SINGLE_TRADE_LIMIT or
                                 payout_units > SINGLE_TRADE_LIMIT),
        "settlement": ("manual_design_required" if base["offer_units"] >
                       SINGLE_TRADE_LIMIT else "single_trade_candidate"),
    }


def verify_trade(request, quote, observed_offer, observed_payout):
    """Check manual observations against the identical random-draw quote.

    The draw is untrusted client-supplied data. This is only a structural
    consistency check, NOT authentication, stock reservation or settlement.
    """
    if type(quote) is not dict or type(quote.get("draw")) is not int:
        return {"valid": False, "reason": "invalid_quote"}
    try:
        current = quote_exchange(request, randbelow=lambda _: quote["draw"])
    except QuoteInputError:
        return {"valid": False, "reason": "quote_outdated_or_invalid"}
    if current["status"] != "quoted" or quote != current:
        return {"valid": False, "reason": "quote_outdated_or_modified"}
    try:
        incoming = _normalise(_lines(observed_offer, "observed_offer"))
        outgoing = _normalise(_lines(observed_payout, "observed_payout"))
    except QuoteInputError:
        return {"valid": False, "reason": "invalid_trade_observation"}
    if incoming != quote["offer"]:
        return {"valid": False, "reason": "incoming_items_changed"}
    expected_outgoing = [
        {"item_id": line["item_id"], "quantity": line["quantity"]}
        for line in quote["payout"]
    ]
    if outgoing != expected_outgoing:
        return {"valid": False, "reason": "outgoing_items_changed"}
    if quote["requires_multi_trade"]:
        return {"valid": False, "reason": "multi_trade_not_supported"}
    return {"valid": True, "reason": "manual_review_matches_quote"}
