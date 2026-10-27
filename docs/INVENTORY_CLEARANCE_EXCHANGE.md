# RotMG Bin — randomised item-for-item inventory clearance (experimental)

## User-confirmed product model

The player deposits **at least two** unwanted, tradable items and receives
**strictly fewer** tradable items in return. This releases inventory space.
The **value of the payout is random**, not guaranteed to be slightly lower
on each attempt. Most outcomes can lose some item-market value, while rare
outcomes can be **substantially more valuable** than the deposit.

The *expected* reward remains slightly below the input value (provisional
default: **95%**). A negative expected margin does not mean every trade
loses value for the player; the Bin can lose on a jackpot and recover its
edge across many independent, fairly priced trades. Quotes require real
stock, but this prototype uses **manually supplied, illustrative valuations**.

This is an item-for-item lottery with in-game assets, not Forge
dismantling, pet feeding, item destruction, or a real-money transaction.
The existing 2018-era `trader.py` is untouched.

## Illustration: ordinary loss, occasional 3x jackpot

Player inventory capacity: 16 slots (backpack enabled), with **only 8
items deposited**. Eight deposited items are worth 10 arbitrary value
units each; combined input value = 80. Stock contains one 72-value
reward and one 240-value reward.

| Outcome | Payout | Probability | Change vs input |
| --- | ---: | ---: | ---: |
| Ordinary | 1 item worth 72 | 41/42 ≈ 97.62% | -10% |
| Jackpot | 1 item worth 240 | 1/42 ≈ 2.38% | +200% |

Expected payout:
`(41/42 × 72) + (1/42 × 240) = 76`, exactly **95%** of 80.
Both outcomes free **seven** inventory slots.

**These odds are conditional on this illustrative stock and price
snapshot.** Different stock and prices produce different jackpots and
probabilities. It is not a promised universal 1-in-42 win rate.

## Implemented probability and selection

1. Determine offered value using the manually supplied versioned price book.
2. Find physically available bundles with **fewer item units than the
   deposited quantity**, bounded by the configured relative-value band.
3. Choose the highest-value feasible ordinary payout below the target
   expectation; choose the **highest-value feasible winning bundle**
   above that expectation, favouring large potential jackpots.
4. Assign the upper outcome its precise probability:

```text
P(upper) = (target expected payout - lower payout value)
           / (upper payout value - lower payout value)
P(lower) = 1 - P(upper)
```

5. Use `secrets.randbelow` to draw the outcome with exact integer
   weights (no floating point), and show the selected item bundle
   **before** a human confirms a trade.

The default parameters are:

| Parameter | Default |
| --- | --- |
| Expected reward | 95% of deposited value |
| Lower allowed reward | 70% |
| Upper allowed reward | 300% |
| Jackpot label threshold | 150% |
| Inventory capacity | 8 slots unless explicitly configured as 16 or 24 |

The lower and upper bounds are *allowed* outcomes, not promised outcomes.
A 3x win is only possible if actual in-stock items can form one, without
giving back as many units as were deposited. If stock cannot create
outcomes on both sides of the expected value, the quote is unavailable
and no exchange should proceed. The engine's selected upper value may
be less than the player's deposit if no suitably valuable item bundle
exists; the `is_profit_for_player` and `is_jackpot` indicators distinguish
these cases.

A quote's expected payout is mathematically correct **for a fixed
input/stock snapshot**. It is not a guarantee of profitability for the
actual Bin: real price errors, changes in stock, valuation manipulation
and customer rerolls all change the realised results. Display odds and
value uncertainty clearly.

## Variable character capacity: 8, 16, or 24

- **Maximum supported character inventory** is 24 slots: 8 ordinary,
  another 8 with a backpack, and another 8 with an extender.
- Not everyone has all upgrades; each offer supplies the particular
  character's **8/16/24-slot capacity**. Default is conservatively **8**.
- The player does **not** have to submit the entire inventory. A
  16-slot player can deposit 3, 8, 12, or any other supported quantity
  from 2–16 items. Return is **always at least one item fewer** than
  deposit (e.g., 8 in → 1–7 out, 24 in → at most 23 out).
- The 32-slot planning option has been **removed**.
- **Inventory capacity is not a trade-window limit**. A conservative
  eight-incoming-item single-trade safeguard is implemented, but current
  client mechanics need independent confirmation. A 24-item quote is
  only a *planning scenario*; the system returns
  `requires_multi_trade=true` and refuses to claim such a quote is safe
  to settle in one transaction. Do not turn this into unsecured partial
  deposits.

The engine currently has no concept of occupied slots, inventory rows,
backpack ownership proof, or player inventory scraping. It simply accepts
user-supplied item quantities up to the configured capacity.

## Offline usage

Python 3.10+; the new module has no external dependencies.

```sh
python -m rotmg_bin examples/inventory-clearance.json
python -m unittest discover -s tests -p 'test_exchange.py' -v
```

The example contains **fictional** item IDs and prices. JSON includes a
versioned `price_book`, `offer`, `stock`, and a `policy` with
`inventory_capacity`, `expected_payout_bps`,
`minimum_payout_bps`, `maximum_payout_bps`, and
`jackpot_threshold_bps` (where 10,000 basis points = 100%).

The output includes both potential payout values, exact integer
probabilities, actual payout item counts, slots freed, a realisation
flag for profits and jackpots, and expected-value metadata.

## Security and operational limitations

1. **No game interaction:** No automated clicks, live account access,
   credentials, item transfers, or client injection. The legacy trading
   bot is not used.
2. **No durable quote:** The quote's published random draw is
   **forgeable**, and `verify_trade` only checks structural consistency
   of supplied observations. This is not authentication or a secure
   settlement receipt.
3. **Reroll/selection exploit:** Running new independent quotes for
   the same offered items until a jackpot appears destroys the expected
   margin. Before deployment, enforce an immutable offer fingerprint,
   a server-generated one-time result, rate limits and stock reservation
   that cannot be bypassed by cancelling and resubmitting.
4. **One-sided stock failure:** If physical inventory cannot support
   both payout values, refuse the lottery. Do not quietly replace
   a jackpot with fake goods or vary expected value unnoticed.
5. **Trade safety:** Bundles are planned using bounded dynamic
   programming (up to 128 eligible stock units and 50,000 intermediate
   states). Payout unit count is strictly below deposit unit count.
   A quote exceeding the conservative single-trade allowance is
   **not** suitable for automatic settlement.
6. **Economics, fairness and game policy:** Manual prices can be wrong,
   stale or illiquid; valuable inventory may be lost. Game rules,
   market manipulation, age suitability, user-facing probability
   disclosures, and whether such a lottery is allowed by DECA
   require assessment before any public launch or actual transfers.
7. **External security review:** The production service needs
   independent prelaunch red-team/security testing, ledger/escrow
   review, operational controls, and fraud/race-condition tests.

## Next milestones

- Product owner agrees provisional house edge, rare-jackpot volatility,
  pricing sources, eligible item classes and reroll policy.
- Implement an auditable, authenticated quote/stock reservation ledger,
  expiry and idempotent settlement.
- Validate character inventory and trade-window mechanics.
- Check platform and applicable gambling/commercial regulations before
  putting real player items at risk.

Official capacity reference: [DECA's Backpack Extender announcement
describing 16 to 24 slots](https://remaster.realmofthemadgod.com/?p=3995).
