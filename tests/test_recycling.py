import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from rotmg_recycling import InputError, plan_recycling


def item(item_id, materials, *, quantity=1, locked=False):
    return {"id": item_id, "name": item_id, "materials": materials,
            "quantity": quantity, "locked": locked}


class RecyclingPlannerTests(unittest.TestCase):
    def test_minimum_number_of_items(self):
        result = plan_recycling({
            "required_materials": {"rare": 10},
            "inventory": [item("small", {"rare": 5}, quantity=2),
                          item("large", {"rare": 10})],
        })
        self.assertTrue(result["possible"])
        self.assertEqual(result["selected"], [
            {"id": "large", "name": "large", "quantity": 1}])
        self.assertEqual(result["method"], "exact")

    def test_least_waste_for_equal_count(self):
        result = plan_recycling({
            "required_materials": {"common": 10},
            "inventory": [item("a", {"common": 14}),
                          item("b", {"common": 11})],
        })
        self.assertEqual(result["selected"][0]["id"], "b")
        self.assertEqual(result["excess_materials"], {"common": 1})

    def test_locked_items_never_selected(self):
        result = plan_recycling({
            "required_materials": {"rare": 2},
            "inventory": [item("valuable", {"rare": 100}, locked=True),
                          item("spare", {"rare": 2})],
        })
        self.assertEqual(result["selected"][0]["id"], "spare")
        self.assertEqual(result["locked_units_excluded"], 1)

    def test_impossible_reports_shortfall(self):
        result = plan_recycling({
            "required_materials": {"rare": 5, "common": 8},
            "inventory": [item("only", {"rare": 3}, quantity=1)],
        })
        self.assertFalse(result["possible"])
        self.assertEqual(result["shortfall"], {"rare": 2, "common": 8})
        self.assertEqual(result["selected"], [])

    def test_quantities_select_only_needed_copies(self):
        result = plan_recycling({
            "required_materials": {"rare": 6},
            "inventory": [item("duplicate", {"rare": 2}, quantity=4)],
        })
        self.assertEqual(result["selected"][0]["quantity"], 3)

    def test_multiple_material_requirements(self):
        result = plan_recycling({
            "required_materials": {"common": 3, "rare": 4},
            "inventory": [item("mixed", {"common": 3, "rare": 4}),
                          item("rare", {"rare": 10}),
                          item("common", {"common": 10})],
        })
        self.assertEqual(result["selected"][0]["id"], "mixed")

    def test_rejects_invalid_and_duplicate_identifiers(self):
        with self.assertRaises(InputError):
            plan_recycling({"required_materials": {"rare": 1}, "inventory": [
                item("same", {"rare": 1}), item("same", {"rare": 1})]})
        with self.assertRaises(InputError):
            plan_recycling({"required_materials": {"rare": True}, "inventory": []})
        with self.assertRaises(InputError):
            plan_recycling({"required_materials": {"rare": 1}, "inventory": [
                item("a", {"rare": -1})]})

    def test_rejects_extremely_large_unlocked_inventory(self):
        with self.assertRaisesRegex(InputError, "At most 500"):
            plan_recycling({
                "required_materials": {"rare": 1},
                "inventory": [item("many", {"rare": 1}, quantity=501)],
            })

    def test_large_inputs_use_labeled_heuristic(self):
        result = plan_recycling({
            "required_materials": {"rare": 2},
            "inventory": [item(f"unit{i:02}", {"rare": 1}) for i in range(19)],
        })
        self.assertTrue(result["possible"])
        self.assertEqual(result["method"], "greedy")
        self.assertEqual(sum(x["quantity"] for x in result["selected"]), 2)

    def test_deterministic(self):
        data = {"required_materials": {"rare": 2},
                "inventory": [item("z", {"rare": 2}), item("a", {"rare": 2})]}
        self.assertEqual(plan_recycling(data), plan_recycling(data))
        self.assertEqual(plan_recycling(data)["selected"][0]["id"], "a")

    def test_cli_json_is_offline_and_machine_readable(self):
        sample = {"required_materials": {"rare": 4},
                  "inventory": [item("x", {"rare": 4})]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "inventory.json"
            path.write_text(json.dumps(sample), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-m", "rotmg_recycling", str(path)],
                text=True, capture_output=True, check=False,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(json.loads(proc.stdout)["possible"])


if __name__ == "__main__":
    unittest.main()
