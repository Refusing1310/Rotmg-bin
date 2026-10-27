# RotMG Bin — inventory-clearance exchange (experimental)

## What it does

Players offer **2–8 unwanted tradable items** in one exchange and receive
**one tradable item** with a market-value estimate slightly below the sum
of the offered items. For example, eight input items at 10 arbitrary value
units each and one output item at 76 units clears seven inventory slots
and retains four value units (5%) for the bin.

This is not Forge dismantling, item destruction, pet feeding, a drop-bag
collector, or cash-for-game-item trading.

The legacy browser-era `trader.py` trading bot is not used or modified.
The v0 implementation only computes **offline quotes** and validates a
human-observed trade against a fresh quote. It cannot read inventory or
execute a trade. Never assume that a quote means a trade has happened.

## Run locally

Python 3.10+; no external packages required for this standalone package.

```sh
python -m rotmg_bin examples/inventory-clearance.json
python -m unittest discover -s tests -p 'test_exchange.py' -v
```

The example contains **invented placeholder item names and prices**.
No current RotMG item price/eligibility database is included.

## JSON input

- `price_book.version`: nonempty string identifying a manual pricing snapshot.
- `price_book.items`: mapping of item ID to `name`, positive integer
  `value`, and explicit boolean `tradable`.
- `offer`: 2–8 item units, each `{"item_id":"...","quantity":1}`;
  duplicate IDs are combined. Untradable or unknown offers are rejected.
- `stock`: unique entries with positive `quantity`; item IDs must
  exist in the price book; untradable stock is never selected.
- `policy.minimum_margin_bps`: default 500 (= 5%).
- `policy.maximum_margin_bps`: default 1000 (= 10%).

For an offered total value of 100, the default payout range is **90–95**
value units. The bin chooses the available eligible item with the
**highest** value in that band, with a deterministic ID tie-break.
It declines if nothing suitable is in stock. A payout outside the band
is never silently substituted. Rounding is calculated with integers.

The output includes the payout, captured margin, price-book version, and
number of slots freed. There are no fees beyond the quoted haircut.

## Safeguards and unresolved limitations

1. A quote is advisory. `verify_trade` performs a fresh quote and compares
   the exact observed incoming item counts and single outgoing item. It
   refuses modified/outdated quotes. **It is not proof of in-game state.**
2. No unilateral item acceptance: the trade must show the agreed payout,
   and the human must independently recheck the in-game trade window.
3. Trades beyond eight incoming items are rejected rather than splitting
   into unsecured multi-step transfers. This conservative constraint should
   be checked against the current client.
4. Price estimates and tradability are manually supplied. Incorrect,
   outdated, manipulated, or illiquid prices can cause losses. A live
   production service needs robust pricing, audit history, stale-price
   cutoff, protected high-value items, liquidity/volatility controls,
   risk limits, and human approval for exceptional quotes.
5. Stock is an input snapshot, **not an actual reservation**. Simultaneous
   quotes can promise the same item. Production requires atomic inventory
   reservations, TTL/expiry, settlement ledger, idempotency, and reconciliation.
6. Do not connect this code to the game client or enable unattended
   trading without resolving platform rules, account-security concerns,
   and gameplay fairness. The official account-safety guidance warns
   against third-party software used to play Realm.
7. No real-money transactions, credential collection, gameplay injection,
   automation, anti-detection, or bypass mechanisms are implemented.

Sources to review before any live rollout:

- Official [Things to avoid](https://support.rotmg.com/hc/en-us/articles/360058621572-Things-to-avoid)
- Official [Fair Play Updates (2026)](https://hub.realmofthemadgod.com/news0/news1/guardians)
- Community [legacy trade mechanics](https://wildshadow.fandom.com/wiki/Trade_System)

## Next milestones

- Approve exchange economics and inventory classes/accepted-item policy.
- Establish sourced, date-stamped game item tradability and manual pricebook.
- Implement an offline audit ledger and atomic stock reservation service.
- Build a manual-approval operator interface (no game-client controls).
- Obtain explicit permission or confirmation of compliant deployment
  path before considering any live in-game integration.
