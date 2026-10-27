import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from rotmg_bin import QuoteInputError, quote_exchange, verify_trade


def request(offer_qty=8, stock=None):
    return {
        "price_book": {
            "version": "test-v1",
            "items": {
                "junk": {"name": "Junk", "value": 10, "tradable": True},
                "reward": {"name": "Reward", "value": 76, "tradable": True},
                "cheap": {"name": "Cheap", "value": 71, "tradable": True},
                "best": {"name": "Best", "value": 75, "tradable": True},
                "expensive": {"name": "Expensive", "value": 79, "tradable": True},
                "bound": {"name": "Bound", "value": 76, "tradable": False},
            },
        },
        "offer": [{"item_id": "junk", "quantity": offer_qty}],
        "stock": [{"item_id": "reward", "quantity": 1}] if stock is None else stock,
    }


class ExchangeQuoteTests(unittest.TestCase):
    def test_eight_to_one_quote_and_savings(self):
        result = quote_exchange(request())
        self.assertEqual(result["status"], "quoted")
        self.assertEqual(result["offer_value"], 80)
        self.assertEqual(result["payout"]["value"], 76)
        self.assertEqual(result["inventory_slots_freed"], 7)
        self.assertEqual(result["retained_value"], 4)
        self.assertEqual(result["effective_margin_bps_floor"], 500)

    def test_selects_best_customer_value_within_margin_band(self):
        data = request(stock=[
            {"item_id": "cheap", "quantity": 1},
            {"item_id": "best", "quantity": 1},
            {"item_id": "reward", "quantity": 1},
        ])
        self.assertEqual(quote_exchange(data)["payout"]["item_id"], "reward")

    def test_declines_instead_of_underpaying(self):
        data = request(stock=[{"item_id": "junk", "quantity": 5}])
        self.assertEqual(quote_exchange(data)["status"], "unavailable")
        self.assertEqual(quote_exchange(data)["payout"], None)

    def test_declines_instead_of_overpaying(self):
        data = request(stock=[{"item_id": "expensive", "quantity": 1}])
        self.assertEqual(quote_exchange(data)["status"], "unavailable")

    def test_declines_soulbound_stock(self):
        data = request(stock=[{"item_id": "bound", "quantity": 1}])
        self.assertEqual(quote_exchange(data)["status"], "unavailable")

    def test_rejects_soulbound_offers(self):
        data = request()
        data["offer"] = [{"item_id": "bound", "quantity": 3}]
        with self.assertRaises(QuoteInputError):
            quote_exchange(data)

    def test_rejects_one_input_item(self):
        with self.assertRaises(QuoteInputError):
            quote_exchange(request(offer_qty=1))

    def test_rejects_more_than_eight_incoming_items(self):
        with self.assertRaises(QuoteInputError):
            quote_exchange(request(offer_qty=9))

    def test_duplicate_offer_ids_are_counted(self):
        data = request()
        data["offer"] = [
            {"item_id": "junk", "quantity": 4},
            {"item_id": "junk", "quantity": 4},
        ]
        result = quote_exchange(data)
        self.assertEqual(result["offer"], [{"item_id": "junk", "quantity": 8}])

    def test_unknown_price_is_rejected(self):
        data = request()
        data["offer"] = [{"item_id": "unknown", "quantity": 2}]
        with self.assertRaises(QuoteInputError):
            quote_exchange(data)

    def test_boolean_is_not_accepted_as_price_or_quantity(self):
        data = request()
        data["price_book"]["items"]["junk"]["value"] = True
        with self.assertRaises(QuoteInputError):
            quote_exchange(data)
        data = request()
        data["offer"][0]["quantity"] = True
        with self.assertRaises(QuoteInputError):
            quote_exchange(data)

    def test_explicit_tradable_flag_is_required(self):
        data = request()
        del data["price_book"]["items"]["junk"]["tradable"]
        with self.assertRaises(QuoteInputError):
            quote_exchange(data)

    def test_duplicate_stock_entries_are_rejected(self):
        data = request(stock=[
            {"item_id": "reward", "quantity": 1},
            {"item_id": "reward", "quantity": 2},
        ])
        with self.assertRaises(QuoteInputError):
            quote_exchange(data)

    def test_bad_margin_policy_is_rejected(self):
        data = request()
        data["policy"] = {"minimum_margin_bps": 1200, "maximum_margin_bps": 500}
        with self.assertRaises(QuoteInputError):
            quote_exchange(data)

    def test_custom_margin_range(self):
        data = request(stock=[{"item_id": "best", "quantity": 1}])
        data["policy"] = {"minimum_margin_bps": 600, "maximum_margin_bps": 700}
        self.assertEqual(quote_exchange(data)["payout"]["item_id"], "best")

    def test_verify_exact_trade(self):
        data = request()
        quote = quote_exchange(data)
        self.assertEqual(verify_trade(
            data, quote, [{"item_id": "junk", "quantity": 8}],
            [{"item_id": "reward", "quantity": 1}]
        ), {"valid": True, "reason": "manual_review_matches_quote"})

    def test_verify_rejects_change_to_offer(self):
        data = request()
        quote = quote_exchange(data)
        result = verify_trade(
            data, quote, [{"item_id": "junk", "quantity": 7}],
            [{"item_id": "reward", "quantity": 1}],
        )
        self.assertEqual(result["reason"], "incoming_items_changed")

    def test_verify_rejects_change_to_reward(self):
        data = request()
        quote = quote_exchange(data)
        result = verify_trade(
            data, quote, [{"item_id": "junk", "quantity": 8}],
            [{"item_id": "expensive", "quantity": 1}],
        )
        self.assertEqual(result["reason"], "outgoing_item_changed")

    def test_verify_rejects_stale_pricebook(self):
        data = request()
        quote = quote_exchange(data)
        newer = deepcopy(data)
        newer["price_book"]["version"] = "test-v2"
        self.assertEqual(
            verify_trade(newer, quote, data["offer"], [{"item_id": "reward", "quantity": 1}])["reason"],
            "quote_outdated_or_modified",
        )

    def test_verify_rejects_stock_change(self):
        data = request()
        quote = quote_exchange(data)
        empty = deepcopy(data)
        empty["stock"] = []
        self.assertEqual(
            verify_trade(empty, quote, data["offer"], [{"item_id": "reward", "quantity": 1}])["reason"],
            "no_current_quote",
        )

    def test_verify_rejects_tampered_quote(self):
        data = request()
        quote = quote_exchange(data)
        quote["retained_value"] = 0
        self.assertEqual(
            verify_trade(data, quote, data["offer"], [{"item_id": "reward", "quantity": 1}])["reason"],
            "quote_outdated_or_modified",
        )

    def test_cli_smoke_test(self):
        data = request()
        with tempfile.TemporaryDirectory() as dirname:
            path = Path(dirname) / "sample.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-m", "rotmg_bin", str(path)],
                text=True, capture_output=True, check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "quoted")


if __name__ == "__main__":
    unittest.main()
