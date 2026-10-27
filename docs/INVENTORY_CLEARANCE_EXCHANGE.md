# RotMG Bin — randomised inventory clearance (experimental)

## Intent

The player offers multiple unwanted **tradable** items and receives fewer
tradable items in return, freeing inventory slots. The *aggregate value* of
the reward is randomised: sometimes less valuable, potentially occasionally
more valuable, but with a **target expected payout slightly below the
deposited value**. The Bin retains the difference on average, not necessarily
in every exchange. The customer must see the resulting offer *before*
confirming anything.

This is not Forge dismantling, pet feeding, item destruction, or a currency
exchange. The 2018-era `trader.py` is untouched.

## Example and mathematics

Eight unwanted items are worth 10 value units each (80 total).
Available stock includes a 72-unit item and an 80-unit item.
At the default target of 95% of input value:

- Low outcome: a 72-unit item (10% haircut).
- High outcome: an 80-unit item (0% haircut).
- Each outcome has 50% probability. Expected value = 76 (95%).
- Both outcomes give the player **1 item**, clearing **7 slots**.

A stock-backed lottery can also give more than the deposited value on a
particular outcome, up to the configured cap (105% by default). The two
physical payout options are selected as the nearest achievable values
strictly below and strictly above the target. The algorithm computes the
exact rational high-outcome probability required to hit that target:

```text
P(high) = (target_expected_value - low_value) / (high_value - low_value)
P(low)  = 1 - P(high)
```

It samples the lottery with `secrets.randbelow` (integer arithmetic, no
floating point rounding). The **conditional expectation** is exactly the
configured expected payout for a *fixed manual stock and price snapshot*
when both sides of the target are available. If no pair brackets the
target, it **refuses** to quote rather than claim a false average.

Repeated quotes that are sampled independently can be rerolled for a
favourable outcome. A production service MUST bind each price/stock quote
to a user/session/offer, enforce TTL and rate limits, and atomically
reserve the chosen stock before revealing the outcome. Current code does
**none** of that.

### Item counts and inventory

- Allowed inventory-capacity settings: **8, 16, 24, 32**.
- **Default 24** reflects DECA's published backpack and Backpack Extender
  description (8+8+8). The requested 32 is supported as a **planning
  hypothesis**, not a verified live-game slot count; this must be tested
  against the current client before anyone relies on it.
- A customer may offer 2 up to the configured inventory capacity.
- Any selected payout contains **strictly fewer item units** than input.
  E.g. 8 in can give 1–7 out. A hypothetical 32-in offer can return
  fewer, but cannot be settled as an atomic in-game trade by this module.
- Offline payout planning can suggest up to **input_count − 1** output
  units (31 for a hypothetical 32-item input). It prefers the fewest
  returned item units for equal total value, maximising inventory space freed.
  Any reward with over 8 units also fails the single-trade safety check.
- The planner uses a **separate conservative limit of 8 incoming units
  per single trade**. It marks larger offers `requires_multi_trade=true`
  and `settlement=manual_design_required`. The implementation explicitly
  refuses to verify such offers as safe in one trade.
- Do NOT silently split a 32-to-fewer deal into several player-to-player
  trades. Multi-trade arrangements can expose the player to loss; a
  trustworthy escrow/atomic-settlement design would need independent
  validation and platform-rule review.

## Run

Python 3.10+; no external packages for the new offline package.

```sh
python -m rotmg_bin examples/inventory-clearance.json
python -m unittest discover -s tests -p 'test_exchange.py' -v
```

The example uses fictional prices and item names; it does not fetch current
RotMG listings or read the live client.

JSON fields:
- `price_book.version`: manual pricing snapshot identifier.
- `price_book.items.<id>`: `name`, positive integer `value`, explicitly
  boolean `tradable`.
- `offer`: list of `{"item_id":"...", "quantity":N}` lines (duplicates
  combined).
- `stock`: list of such lines, with distinct item IDs.
- `policy.inventory_capacity`: 8, 16, 24 (default), or 32.
- `policy.expected_payout_bps`: default 9500 = 95%; must be below 10000.
- `policy.minimum_payout_bps`: default 8500 = 85%.
- `policy.maximum_payout_bps`: default 10500 = 105%.

A selected quote contains `payout` (one or multiple item lines),
`payout_units`, `payout_value`, actual `retained_value`,
`inventory_slots_freed`, a rational lottery description,
`requires_multi_trade`, and a policy snapshot.

## Safety / robustness

1. Output item stock and values are supplied by the caller: there is no
   trustworthy market-price oracle, account inventory or stock reservation.
2. This is strictly **read-only** analysis. No game-client input, account
   access, credentials, auto-confirmation, deposits or settlement.
3. `verify_trade` can compare human-observed item counts against a
   structurally identical quote and current price/stock inputs. The public
   random `draw` is **not authenticated**; anyone controlling the input
   can spoof the draw or quote. This helper is **not** transaction security,
   a quote signature, or evidence of any actual game transfer.
4. An exact two-sided lottery is not always possible with physical
   inventory. If no in-range lower and upper value exists, return
   `unavailable` and take nothing; no guaranteed output is manufactured.
5. Selection uses bounded subset-value dynamic programming to find one
   representative bundle per payout value, not exhaustive listing of all
   bundles. Eligible stock is limited to 128 units and intermediate states
   to 50,000. Input validation fails closed above those limits.
6. Market manipulation, stale prices, high-value goods, variations in
   liquidity, player account modes (seasonal/nonseasonal), trade UI rules,
   cross-trade arbitrage and game sanctions remain unresolved. These
   must be examined before any real operation.
7. The official 2023 Backpack Extender statement explicitly describes
   expanding inventory from 16 to 24, not to 32. Treat 32 as unconfirmed.

References:
- [Official 2023 backpack extension](https://remaster.realmofthemadgod.com/?p=3995)
- [Legacy trade-system mechanics](https://wildshadow.fandom.com/wiki/Trade_System)

## Next engineering decisions / gates

1. Agree a **target average payout** (95% proposed), maximum downside
   (85% proposed), and maximum upside (105% proposed). Randomisation
   is transparent; expected value does not mean every individual trade
   is profitable.
2. Decide whether players can reroll quotes and whether a small,
   non-jackpot range is preferable. Production needs binding and
   replay protections to prevent adverse selection.
3. Establish a sourced, timestamped item-value and tradability data feed,
   including manual overrides and manipulation detection.
4. Design inventory/stock ledger with durable quote IDs, reservation
   expiry and idempotent settlement, plus independent reconciliation.
5. Confirm client capacities and game rules with DECA; never deploy
   unattended in-game trading without an approved compliance route.
