"""Regression tests for bounded, stock-backed, randomised offline exchanges."""
import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

from rotmg_bin import QuoteInputError, quote_exchange, verify_trade


def example(count=8, capacity=24, stock=None):
    return {
        "price_book": {
            "version": "TEST-ONLY",
            "items": {
                "junk": {"name": "Junk", "value": 10, "tradable": True},
                "low": {"name": "Lower payout", "value": 72, "tradable": True},
                "high": {"name": "Higher payout", "value": 80, "tradable": True},
                "too_low": {"name": "Unsuitable", "value": 10, "tradable": True},
                "jackpot": {"name": "Jackpot", "value": 84, "tradable": True},
                "mega_jackpot": {"name": "Mega jackpot", "value": 160, "tradable": True},
                "triple_jackpot": {"name": "Triple jackpot", "value": 240, "tradable": True},
                "deep_low": {"name": "Deep lower", "value": 68, "tradable": True},
                "quarter": {"name": "Quarter", "value": 20, "tradable": True},
                "untradable": {"name": "Bound", "value": 80, "tradable": False},
            },
        },
        "offer": [{"item_id": "junk", "quantity": count}],
        "stock": [{"item_id": "low", "quantity": 1},
                  {"item_id": "high", "quantity": 1}] if stock is None else stock,
        "policy": {"inventory_capacity": capacity},
    }


def upper(n):
    return 0


def lower(n):
    return n - 1


class QuoteTests(unittest.TestCase):
    def test_randomised_upper_draw(self):
        result = quote_exchange(example(), randbelow=upper)
        self.assertEqual(result["payout_value"], 80)
        self.assertEqual(result["payout_units"], 1)
        self.assertEqual(result["inventory_slots_freed"], 7)
        self.assertEqual(result["retained_value"], 0)
        self.assertFalse(result["requires_multi_trade"])
        self.assertEqual(result["lottery"]["lower_value"], 72)
        self.assertEqual(result["lottery"]["upper_value"], 80)

    def test_randomised_lower_draw(self):
        result = quote_exchange(example(), randbelow=lower)
        self.assertEqual(result["payout_value"], 72)
        self.assertEqual(result["retained_value"], 8)
        self.assertEqual(result["inventory_slots_freed"], 7)

    def test_lottery_expected_value_is_exactly_ninety_five_percent(self):
        result = quote_exchange(example(), randbelow=upper)
        pool = result["lottery"]
        chance_high = Fraction(pool["upper_probability_numerator"],
                               pool["probability_denominator"])
        expectation = (chance_high * pool["upper_value"] +
                       (1 - chance_high) * pool["lower_value"])
        self.assertEqual(expectation, Fraction(80 * 9500, 10000))
        self.assertEqual(result["expected_payout_value_numerator"], 80 * 9500)

    def test_jackpot_can_exceed_input_without_exceeding_expected_value(self):
        data = example(stock=[{"item_id": "deep_low", "quantity": 1},
                              {"item_id": "jackpot", "quantity": 1}])
        high = quote_exchange(data, randbelow=upper)
        low = quote_exchange(data, randbelow=lower)
        self.assertEqual(high["payout_value"], 84)
        self.assertEqual(low["payout_value"], 68)
        self.assertEqual(high["lottery"]["upper_probability_numerator"] * 2,
                         high["lottery"]["probability_denominator"])

    def test_rare_big_win_but_same_ninety_five_percent_expected_value(self):
        data = example(stock=[
            {"item_id": "low", "quantity": 1},
            {"item_id": "mega_jackpot", "quantity": 1},
        ])
        win = quote_exchange(data, randbelow=upper)
        loss = quote_exchange(data, randbelow=lower)
        self.assertEqual(win["payout_value"], 160)
        self.assertTrue(win["is_profit_for_player"])
        self.assertTrue(win["is_jackpot"])
        self.assertFalse(loss["is_jackpot"])
        self.assertEqual(loss["payout_value"], 72)
        p = win["lottery"]
        chance = Fraction(p["upper_probability_numerator"],
                          p["probability_denominator"])
        self.assertEqual(chance, Fraction(1, 22))
        self.assertEqual(chance * 160 + (1 - chance) * 72, 76)

    def test_three_times_value_jackpot_is_stock_dependent(self):
        data = example(stock=[
            {"item_id": "low", "quantity": 1},
            {"item_id": "mega_jackpot", "quantity": 1},
            {"item_id": "triple_jackpot", "quantity": 1},
        ])
        jackpot = quote_exchange(data, randbelow=upper)
        self.assertEqual(jackpot["payout_value"], 240)
        self.assertEqual(jackpot["lottery"]["upper_value"], 240)
        self.assertEqual(jackpot["lottery"]["lower_value"], 72)
        p = jackpot["lottery"]
        chance = Fraction(p["upper_probability_numerator"],
                          p["probability_denominator"])
        self.assertEqual(chance, Fraction(1, 42))
        self.assertEqual(chance * 240 + (1 - chance) * 72, 76)

    def test_custom_maximum_caps_jackpot(self):
        data = example(stock=[
            {"item_id": "low", "quantity": 1},
            {"item_id": "mega_jackpot", "quantity": 1},
            {"item_id": "high", "quantity": 1},
        ])
        data["policy"]["maximum_payout_bps"] = 11_000
        data["policy"]["jackpot_threshold_bps"] = 10_500
        quote = quote_exchange(data, randbelow=upper)
        self.assertEqual(quote["payout_value"], 80)
        self.assertFalse(quote["is_jackpot"])

    def test_fewer_output_items_in_multi_item_payout(self):
        data = example(stock=[
            {"item_id": "low", "quantity": 1},
            {"item_id": "quarter", "quantity": 4},
        ])
        # Upper outcome: 4x quarter = 80; lower outcome: 72.
        high = quote_exchange(data, randbelow=upper)
        self.assertEqual(high["payout_units"], 4)
        self.assertEqual(high["inventory_slots_freed"], 4)
        self.assertEqual(high["payout"][0]["quantity"], 4)

    def test_24_input_items_plannable_when_character_is_upgraded(self):
        data = example(count=24, capacity=24)
        data["price_book"]["items"]["low"]["value"] = 224
        data["price_book"]["items"]["high"]["value"] = 232
        result = quote_exchange(data, randbelow=upper)
        self.assertEqual(result["offer_units"], 24)
        self.assertEqual(result["inventory_slots_freed"], 23)
        self.assertTrue(result["requires_multi_trade"])
        self.assertEqual(result["settlement"], "manual_design_required")

    def test_offline_24_item_offer_can_return_more_than_eight_items(self):
        data = example(
            count=24, capacity=24,
            stock=[{"item_id": "quarter", "quantity": 12}],
        )
        # Total offered 240, target 228, with 11x20=220 or 12x20=240.
        high = quote_exchange(data, randbelow=upper)
        low = quote_exchange(data, randbelow=lower)
        self.assertEqual(high["payout_units"], 12)
        self.assertEqual(low["payout_units"], 11)
        self.assertEqual(high["inventory_slots_freed"], 12)
        self.assertTrue(high["requires_multi_trade"])
        p = high["lottery"]
        chance = Fraction(p["upper_probability_numerator"],
                          p["probability_denominator"])
        self.assertEqual(chance * 240 + (1 - chance) * 220, 228)

    def test_expected_payout_cannot_exceed_deposit(self):
        data = example()
        data["policy"]["expected_payout_bps"] = 10_500
        with self.assertRaises(QuoteInputError):
            quote_exchange(data)

    def test_capacity_24_does_not_imply_atomic_trade(self):
        data = example(count=24, capacity=24)
        data["price_book"]["items"]["low"]["value"] = 224
        data["price_book"]["items"]["high"]["value"] = 232
        quote = quote_exchange(data, randbelow=upper)
        check = verify_trade(data, quote, data["offer"],
                             [{"item_id": "high", "quantity": 1}])
        self.assertEqual(check["reason"], "multi_trade_not_supported")

    def test_capacity_24_rejects_25_items(self):
        with self.assertRaises(QuoteInputError):
            quote_exchange(example(count=25, capacity=24))

    def test_capacity_8_rejects_16_item_offer(self):
        with self.assertRaises(QuoteInputError):
            quote_exchange(example(count=16, capacity=8))

    def test_capacity_16_accepts_partial_inventory(self):
        data = example(count=6, capacity=16)
        data["price_book"]["items"]["low"]["value"] = 52
        data["price_book"]["items"]["high"]["value"] = 60
        quote = quote_exchange(data, randbelow=upper)
        self.assertEqual(quote["offer_units"], 6)
        self.assertEqual(quote["inventory_slots_freed"], 5)

    def test_default_character_capacity_is_eight(self):
        data = example()
        del data["policy"]["inventory_capacity"]
        quote = quote_exchange(data, randbelow=upper)
        self.assertEqual(quote["policy"]["inventory_capacity"], 8)
        self.assertEqual(quote["offer_units"], 8)

    def test_32_is_not_supported(self):
        with self.assertRaises(QuoteInputError):
            quote_exchange(example(count=24, capacity=32))

    def test_supported_capacities_only(self):
        with self.assertRaises(QuoteInputError):
            quote_exchange(example(capacity=30))

    def test_one_input_item_cannot_clear_slots(self):
        with self.assertRaises(QuoteInputError):
            quote_exchange(example(count=1))

    def test_scarce_stock_is_declined_without_fake_randomisation(self):
        data = example(stock=[{"item_id": "low", "quantity": 1}])
        result = quote_exchange(data, randbelow=upper)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "no_two_sided_stock_lottery_at_target_value")

    def test_only_upper_outcome_unavailable(self):
        data = example(stock=[{"item_id": "high", "quantity": 1}])
        self.assertEqual(quote_exchange(data)["status"], "unavailable")

    def test_favours_largest_available_upper_outcome(self):
        data = example(stock=[
            {"item_id": "deep_low", "quantity": 1},
            {"item_id": "low", "quantity": 1},
            {"item_id": "high", "quantity": 1},
            {"item_id": "jackpot", "quantity": 1},
        ])
        quote = quote_exchange(data, randbelow=upper)
        self.assertEqual(quote["lottery"]["lower_value"], 72)
        self.assertEqual(quote["lottery"]["upper_value"], 84)

    def test_untradable_stock_is_excluded(self):
        data = example(stock=[
            {"item_id": "low", "quantity": 1},
            {"item_id": "untradable", "quantity": 1},
        ])
        self.assertEqual(quote_exchange(data)["status"], "unavailable")

    def test_untradable_input_rejected(self):
        data = example()
        data["offer"] = [{"item_id": "untradable", "quantity": 3}]
        with self.assertRaises(QuoteInputError):
            quote_exchange(data)

    def test_missing_price_rejected(self):
        data = example()
        data["offer"] = [{"item_id": "does-not-exist", "quantity": 3}]
        with self.assertRaises(QuoteInputError):
            quote_exchange(data)

    def test_duplicate_incoming_items_combined(self):
        data = example()
        data["offer"] = [
            {"item_id": "junk", "quantity": 3},
            {"item_id": "junk", "quantity": 5},
        ]
        result = quote_exchange(data, randbelow=lower)
        self.assertEqual(result["offer"], [{"item_id": "junk", "quantity": 8}])

    def test_duplicate_stock_rows_rejected(self):
        data = example(stock=[
            {"item_id": "low", "quantity": 1},
            {"item_id": "low", "quantity": 1},
        ])
        with self.assertRaises(QuoteInputError):
            quote_exchange(data)

    def test_boolean_cannot_be_price_or_quantity(self):
        data = example()
        data["price_book"]["items"]["junk"]["value"] = True
        with self.assertRaises(QuoteInputError):
            quote_exchange(data)
        data = example()
        data["offer"][0]["quantity"] = True
        with self.assertRaises(QuoteInputError):
            quote_exchange(data)

    def test_invalid_probability_bounds_rejected(self):
        data = example()
        data["policy"]["minimum_payout_bps"] = 9600
        with self.assertRaises(QuoteInputError):
            quote_exchange(data)

    def test_unbounded_eligible_stock_rejected(self):
        data = example()
        data["stock"] = [{"item_id": "quarter", "quantity": 129}]
        with self.assertRaises(QuoteInputError):
            quote_exchange(data)

    def test_bad_random_draw_rejected(self):
        with self.assertRaises(QuoteInputError):
            quote_exchange(example(), randbelow=lambda n: n)

    def test_verify_same_upper_quote_and_observed_items(self):
        data = example()
        quote = quote_exchange(data, randbelow=upper)
        result = verify_trade(data, quote, data["offer"],
                              [{"item_id": "high", "quantity": 1}])
        self.assertEqual(result, {
            "valid": True, "reason": "manual_review_matches_quote",
        })

    def test_verify_same_lower_quote_and_observed_items(self):
        data = example()
        quote = quote_exchange(data, randbelow=lower)
        result = verify_trade(data, quote, data["offer"],
                              [{"item_id": "low", "quantity": 1}])
        self.assertTrue(result["valid"])

    def test_verify_rejects_changed_offer(self):
        data = example()
        quote = quote_exchange(data, randbelow=upper)
        self.assertEqual(verify_trade(
            data, quote, [{"item_id": "junk", "quantity": 7}],
            [{"item_id": "high", "quantity": 1}],
        )["reason"], "incoming_items_changed")

    def test_verify_rejects_changed_payout(self):
        data = example()
        quote = quote_exchange(data, randbelow=upper)
        self.assertEqual(verify_trade(
            data, quote, data["offer"],
            [{"item_id": "low", "quantity": 1}],
        )["reason"], "outgoing_items_changed")

    def test_verify_rejects_changed_prices(self):
        data = example()
        quote = quote_exchange(data, randbelow=upper)
        newer = deepcopy(data)
        newer["price_book"]["items"]["low"]["value"] = 60
        self.assertFalse(verify_trade(
            newer, quote, data["offer"],
            [{"item_id": "high", "quantity": 1}],
        )["valid"])

    def test_verify_rejects_changed_version(self):
        data = example()
        quote = quote_exchange(data, randbelow=upper)
        newer = deepcopy(data)
        newer["price_book"]["version"] = "newer"
        self.assertEqual(verify_trade(
            newer, quote, data["offer"],
            [{"item_id": "high", "quantity": 1}],
        )["reason"], "quote_outdated_or_modified")

    def test_verify_rejects_tampered_payout_value(self):
        data = example()
        quote = quote_exchange(data, randbelow=upper)
        quote["payout_value"] = 999
        self.assertEqual(verify_trade(
            data, quote, data["offer"],
            [{"item_id": "high", "quantity": 1}],
        )["reason"], "quote_outdated_or_modified")

    def test_cli_smoke_test(self):
        with tempfile.TemporaryDirectory() as dirname:
            path = Path(dirname) / "exchange.json"
            path.write_text(json.dumps(example()), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-m", "rotmg_bin", str(path)],
                capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "quoted")


if __name__ == "__main__":
    unittest.main()
