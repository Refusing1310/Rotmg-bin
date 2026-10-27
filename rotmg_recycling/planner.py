"""Offline, conservative planning for dismantling unwanted RotMG items.

This module consumes caller-supplied item and material values. It intentionally
does not claim to know live item data, interact with the game, or approve a craft.
"""
from collections import Counter
from itertools import combinations

EXACT_LIMIT = 18


class InputError(ValueError):
    """The supplied inventory or required materials are invalid."""


def _materials(value, context, *, require_positive=False):
    if not isinstance(value, dict):
        raise InputError(f"{context} must be an object mapping material names to integers")
    result = {}
    for name, count in value.items():
        if not isinstance(name, str) or not name.strip():
            raise InputError(f"{context} contains an invalid material name")
        if type(count) is not int or count < 0:
            raise InputError(f"{context}[{name!r}] must be a non-negative integer")
        if count:
            result[name] = count
    if require_positive and not result:
        raise InputError(f"{context} must contain at least one positive requirement")
    return result


def _validate(data):
    if not isinstance(data, dict):
        raise InputError("Input must be a JSON object")
    required = _materials(data.get("required_materials"), "required_materials", require_positive=True)
    inventory = data.get("inventory")
    if not isinstance(inventory, list):
        raise InputError("inventory must be an array")
    seen_ids = set()
    units = []
    locked_count = 0
    for index, item in enumerate(inventory):
        context = f"inventory[{index}]"
        if not isinstance(item, dict):
            raise InputError(f"{context} must be an object")
        item_id = item.get("id")
        name = item.get("name")
        quantity = item.get("quantity", 1)
        locked = item.get("locked", False)
        if not isinstance(item_id, str) or not item_id.strip():
            raise InputError(f"{context}.id must be a non-empty string")
        if item_id in seen_ids:
            raise InputError(f"Duplicate item id: {item_id}")
        seen_ids.add(item_id)
        if not isinstance(name, str) or not name.strip():
            raise InputError(f"{context}.name must be a non-empty string")
        if type(quantity) is not int or quantity < 1 or quantity > 10000:
            raise InputError(f"{context}.quantity must be an integer between 1 and 10000")
        if type(locked) is not bool:
            raise InputError(f"{context}.locked must be a boolean")
        yields = _materials(item.get("materials"), f"{context}.materials")
        if locked:
            locked_count += quantity
        elif yields:
            for copy_number in range(quantity):
                units.append((item_id, name, copy_number, yields))
    units.sort(key=lambda unit: (unit[0], unit[2]))
    return required, units, locked_count


def _totals(units):
    counts = Counter()
    for _, _, _, yields in units:
        counts.update(yields)
    return dict(sorted(counts.items()))


def _meets(total, required):
    return all(total.get(material, 0) >= count for material, count in required.items())


def _waste(total, required):
    return sum(max(0, count - required.get(material, 0)) for material, count in total.items())


def _exact(units, required):
    for size in range(1, len(units) + 1):
        best = None
        best_score = None
        for indices in combinations(range(len(units)), size):
            chosen = [units[i] for i in indices]
            total = _totals(chosen)
            if _meets(total, required):
                score = (_waste(total, required), indices)
                if best_score is None or score < best_score:
                    best_score, best = score, chosen
        if best is not None:
            return best
    return []


def _greedy(units, required):
    """Deterministic approximation for large inventories; not globally optimal."""
    available = list(units)
    chosen = []
    current = Counter()
    while not _meets(current, required):
        best_index = None
        best_score = None
        for i, unit in enumerate(available):
            yields = unit[3]
            coverage = sum(
                min(max(count - current.get(name, 0), 0), yields.get(name, 0)) / count
                for name, count in required.items()
            )
            if coverage == 0:
                continue
            spill = sum(max(0, current.get(name, 0) + value - required.get(name, 0))
                        for name, value in yields.items())
            score = (-coverage, spill, unit[0], unit[2])
            if best_score is None or score < best_score:
                best_score, best_index = score, i
        if best_index is None:
            return []
        item = available.pop(best_index)
        chosen.append(item)
        current.update(item[3])
    return chosen


def plan_recycling(data):
    """Return a read-only dismantling suggestion from user-supplied values.

    Selection minimizes item count then total excess material for inventories
    of up to EXACT_LIMIT unlocked units. Larger inputs use a labeled heuristic.
    Locked entries are never selected. This does not model forgefire, marks,
    recipes, item-specific eligibility, or the value of keeping an item.
    """
    required, units, locked_count = _validate(data)
    potential = _totals(units)
    shortfall = {
        name: max(0, count - potential.get(name, 0))
        for name, count in required.items()
        if potential.get(name, 0) < count
    }
    method = "exact" if len(units) <= EXACT_LIMIT else "greedy"
    if shortfall:
        return {
            "possible": False,
            "method": method,
            "selected": [],
            "obtained_materials": {},
            "shortfall": shortfall,
            "excess_materials": {},
            "locked_units_excluded": locked_count,
        }
    selected = _exact(units, required) if method == "exact" else _greedy(units, required)
    if not selected:
        raise RuntimeError("Planning failed despite sufficient total eligible materials")
    amounts = Counter(unit[0] for unit in selected)
    names = {unit[0]: unit[1] for unit in selected}
    obtained = _totals(selected)
    return {
        "possible": True,
        "method": method,
        "selected": [
            {"id": item_id, "name": names[item_id], "quantity": amounts[item_id]}
            for item_id in sorted(amounts)
        ],
        "obtained_materials": obtained,
        "shortfall": {},
        "excess_materials": {
            material: quantity - required.get(material, 0)
            for material, quantity in obtained.items()
            if quantity > required.get(material, 0)
        },
        "locked_units_excluded": locked_count,
    }
