# Offline item recycling planner — experimental

This is a **separate read-only module**. The repository's original 2018–2019
`trader.py` potion-trading bot has not been modified and is not used here.

## Why

RotMG has a Forge/Blacksmith dismantling system. The game has changed since
the old browser-era trading bot: notably, official game notes describe
dismantling equipment into stored forge materials. Values and eligibility are
subject to patches. This project **does not ship an item database** and
makes no assertion that an item is dismantleable today.

Provide your own known values in a local JSON file, then run:

```sh
python -m rotmg_recycling examples/recycling_inventory.json
python -m unittest discover -s tests -p 'test_recycling.py'
```

Python 3.10+; **no external dependencies** for this module.

## Input format

`required_materials` is a map of user-defined material type to the amount
needed. `inventory` is an array of entries with unique `id`, display
`name`, a `materials` yield map, optional `quantity` (default 1), and
optional `locked` (default false). Lock items you do not want suggested
for dismantling. Zero material yields will never be selected.

## Output and important limits

- `possible` is based **only on supplied material amounts**, not live recipes.
- Up to 18 eligible units: exact search minimizing item count, then total
  material excess (raw material units, not an economic valuation).
- From 19 to 500 eligible units: a deterministic greedy **approximation**,
  explicitly labeled `method: greedy`; it may not find the best selection.
- More than 500 unlocked eligible units is rejected to prevent excessive processing.
- A shortfall means even dismantling every unlocked eligible supplied item
  would not meet the specified material requirements.
- Nothing is deleted, sent to servers, clicked or traded. Data stay local.
- Item eligibility, restricted ingredient requirements, marks, Forgefire,
  blueprint unlocks, actual game interface changes and preservation value
  **are not modeled**. Always verify in-game before dismantling; dismantling
  is irreversible.

## Next work (requires game-specific validation)

1. Decide whether to model Forge material recycling, pet feeding, or another
   unwanted-item workflow; these are not interchangeable.
2. Curate a versioned, sourced item-yield and eligibility dataset.
3. Add Forgefire/recipe-specific restrictions and keep-value optimization.
4. Validate against current game UI without automated item destruction.

Sources: [Official Forge description](https://support.rotmg.com/hc/en-us/articles/360059243411-PT-all-about-Item-Forge),
[official later forge-material storage notes](https://remaster.realmofthemadgod.com/?p=4052).
