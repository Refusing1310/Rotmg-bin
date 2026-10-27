"""Read-only RotMG Bin exchange pricing and final-trade verification.

All prices are user-supplied integers in an arbitrary, consistent unit. This
module never reads the game client, controls input, or performs a trade.
"""
from collections import Counter

BASIS_POINTS = 10_000
DEFAULT_MIN_MARGIN_BPS = 500
DEFAULT_MAX_MARGIN_BPS = 1_000
TRADE_ITEM_LIMIT = 8


class QuoteInputError(ValueError):
    """Invalid or unsupported manual trade input."""


def _positive_int(value, field, maximum=None):
    if type(value) is not int or value < 1 or (
        maximum is not None and value > maximum
    ):
        limit = f" and at most {maximum}" if maximum is not None else ""
        raise QuoteInputError(f"{field} must be a positive integer{limit}")
    return value


def _catalog(price_book):
    if not isinstance(price_book, dict):
        raise QuoteInputError("price_book must be an object")
    version = price_book.get("version")
    if not isinstance(version, str) or not version.strip():
        raise QuoteInputError("price_book.version must be a nonempty string")
    raw = price_book.get("items")
    if not isinstance(raw, dict) or not raw:
        raise QuoteInputError("price_book.items must be a nonempty object")
    for item_id, info in raw.items():
        if not isinstance(item_id, str) or not item_id.strip():
            raise QuoteInputError("item identifiers must be nonempty strings")
        if not isinstance(info, dict):
            raise QuoteInputError(f"item {item_id!r} must be an object")
        if not isinstance(info.get("name"), str) or not info["name"].strip():
            raise QuoteInputError(f"item {item_id!r} needs a display name")
        _positive_int(info.get("value"), f"item {item_id!r} value")
        if type(info.get("tradable")) is not bool:
            raise QuoteInputError(f"item {item_id!r} needs explicit tradable boolean")
    return version, raw


def _lines(raw, field, *, allow_duplicates):
    if not isinstance(raw, list):
        raise QuoteInputError(f"{field} must be an array")
    counts = Counter()
    for i, line in enumerate(raw):
        if not isinstance(line, dict):
            raise QuoteInputError(f"{field}[{i}] must be an object")
        item_id = line.get("item_id")
        if not isinstance(item_id, str) or not item_id.strip():
            raise QuoteInputError(f"{field}[{i}].item_id must be a nonempty string")
        count = _positive_int(line.get("quantity"), f"{field}[{i}].quantity", 10_000)
        if not allow_duplicates and item_id in counts:
            raise QuoteInputError(f"duplicate {field} item_id {item_id!r}")
        counts[item_id] += count
    return counts


def _policy(raw):
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise QuoteInputError("policy must be an object")
    minimum = raw.get("minimum_margin_bps", DEFAULT_MIN_MARGIN_BPS)
    maximum = raw.get("maximum_margin_bps", DEFAULT_MAX_MARGIN_BPS)
    _positive_int(minimum, "minimum_margin_bps", BASIS_POINTS - 1)
    _positive_int(maximum, "maximum_margin_bps", BASIS_POINTS - 1)
    if minimum > maximum:
        raise QuoteInputError("minimum_margin_bps cannot exceed maximum_margin_bps")
    return minimum, maximum


def _normalise(counts):
    return [{"item_id": k, "quantity": counts[k]} for k in sorted(counts)]


def quote_exchange(request):
    """Quote one stock item for 2–8 incoming, tradable item units.

    The price book is manual, not a live-market oracle. An eligible payout must
    fall between the minimum and maximum margin, inclusive. Among eligible
    stock entries, the customer receives the most valuable; ties prefer the
    lexical item id. No match means no trade rather than a poor-value trade.
    """
    if not isinstance(request, dict):
        raise QuoteInputError("request must be an object")
    version, catalog = _catalog(request.get("price_book"))
    minimum, maximum = _policy(request.get("policy"))
    incoming = _lines(request.get("offer"), "offer", allow_duplicates=True)
    units = sum(incoming.values())
    if not 2 <= units <= TRADE_ITEM_LIMIT:
        raise QuoteInputError(f"offer must contain 2 to {TRADE_ITEM_LIMIT} item units")
    stock = _lines(request.get("stock"), "stock", allow_duplicates=False)
    for item_id in incoming:
        if item_id not in catalog:
            raise QuoteInputError(f"offered item {item_id!r} has no price")
        if not catalog[item_id]["tradable"]:
            raise QuoteInputError(f"offered item {item_id!r} is not marked tradable")
    for item_id in stock:
        if item_id not in catalog:
            raise QuoteInputError(f"stock item {item_id!r} has no price")
    offer_value = sum(catalog[item_id]["value"] * qty
                      for item_id, qty in incoming.items())
    # Use exact integer arithmetic: ceil(lower bound), floor(upper bound).
    lower = (offer_value * (BASIS_POINTS - maximum) + BASIS_POINTS - 1) // BASIS_POINTS
    upper = offer_value * (BASIS_POINTS - minimum) // BASIS_POINTS
    candidates = [
        (catalog[item_id]["value"], item_id)
        for item_id, count in stock.items()
        if count > 0 and catalog[item_id]["tradable"]
        and lower <= catalog[item_id]["value"] <= upper
    ]
    base = {
        "price_book_version": version,
        "offer": _normalise(incoming),
        "offer_value": offer_value,
        "value_unit": "user_defined",
        "inventory_slots_freed": units - 1,
        "policy": {"minimum_margin_bps": minimum, "maximum_margin_bps": maximum},
    }
    if not candidates:
        return {
            **base,
            "status": "unavailable",
            "reason": "no_tradable_stock_item_within_margin_band",
            "payout": None,
        }
    payout_value, payout_id = sorted(candidates, key=lambda row: (-row[0], row[1]))[0]
    retained = offer_value - payout_value
    return {
        **base,
        "status": "quoted",
        "payout": {
            "item_id": payout_id,
            "name": catalog[payout_id]["name"],
            "quantity": 1,
            "value": payout_value,
        },
        "retained_value": retained,
        "effective_margin_bps_floor": retained * BASIS_POINTS // offer_value,
    }


def verify_trade(request, quote, observed_offer, observed_payout):
    """Requote from the latest manual price book/stock and compare exact items.

    The observed inventories must be entered by a human or a separately
    reviewed trusted interface. This cannot attest to actual game state and
    never authorises an automatic click or transfer.
    """
    expected = quote_exchange(request)
    if expected["status"] != "quoted":
        return {"valid": False, "reason": "no_current_quote"}
    if type(quote) is not dict or quote != expected:
        return {"valid": False, "reason": "quote_outdated_or_modified"}
    try:
        actual_incoming = _lines(observed_offer, "observed_offer", allow_duplicates=True)
        actual_outgoing = _lines(observed_payout, "observed_payout", allow_duplicates=False)
    except QuoteInputError:
        return {"valid": False, "reason": "invalid_trade_observation"}
    if _normalise(actual_incoming) != quote["offer"]:
        return {"valid": False, "reason": "incoming_items_changed"}
    if actual_outgoing != Counter({quote["payout"]["item_id"]: 1}):
        return {"valid": False, "reason": "outgoing_item_changed"}
    return {"valid": True, "reason": "manual_review_matches_quote"}
