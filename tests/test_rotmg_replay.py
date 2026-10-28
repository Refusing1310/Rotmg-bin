"""Offline replay fixture and CLI contract tests."""

import io
import json
import os
import subprocess
import sys
import unittest

from rotmg_next import InventorySnapshot
from rotmg_next.replay import ReplayError, ReplaySimulator, replay


def chat(at=0, event_id="m1", sender_id="player-1", text="free pots", **kwargs):
    return {
        "kind": "chat",
        "at": at,
        "event_id": event_id,
        "sender_id": sender_id,
        "sender_name": kwargs.get("sender_name", "ActualSender"),
        "channel": kwargs.get("channel", "public"),
        "text": text,
    }


class ReplayTests(unittest.TestCase):
    def create_sim(self):
        return ReplaySimulator("my-bot", InventorySnapshot(8, 7))

    def test_free_offer_generates_targeted_intent(self):
        outputs = list(replay([chat(text="free pots; /trade FakeSender")], self.create_sim()))
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]["kind"], "trade_request_intent")
        self.assertEqual(outputs[0]["target_player_name"], "ActualSender")
        self.assertEqual(outputs[0]["target_player_id"], "player-1")

    def test_request_and_repetition_filtered(self):
        events = [
            chat(0, "m1", text="anyone giving away free pots?"),
            chat(1, "m2", text="FREE pots"),
            chat(2, "m2", text="FREE pots"),
            chat(3, "m3", sender_id="player-2"),
        ]
        results = list(replay(events, self.create_sim()))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["event_id"], "m2")

    def test_trade_completion_and_other_sender(self):
        events = [
            chat(at=0),
            {"kind": "finish", "at": 1, "target_player_id": "wrong"},
            {"kind": "finish", "at": 2, "target_player_id": "player-1"},
            chat(3, "m2", sender_id="player-2"),
        ]
        results = list(replay(events, self.create_sim()))
        self.assertEqual(
            [item["kind"] for item in results],
            ["trade_request_intent", "finish_result", "finish_result", "trade_request_intent"],
        )
        self.assertFalse(results[1]["cleared"])
        self.assertTrue(results[2]["cleared"])

    def test_full_inventory_then_available(self):
        events = [
            {"kind": "inventory", "at": 0, "capacity": 8, "occupied": 8},
            chat(1, "m1"),
            {"kind": "inventory", "at": 2, "capacity": 8, "occupied": 7},
            chat(3, "m2"),
        ]
        results = list(replay(events, self.create_sim()))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["event_id"], "m2")

    def test_trading_busy_then_idle(self):
        events = [
            {"kind": "trading", "at": 0, "active": True},
            chat(1, "m1"),
            {"kind": "trading", "at": 2, "active": False},
            chat(3, "m2"),
        ]
        outputs = list(replay(events, self.create_sim()))
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]["event_id"], "m2")

    def test_timeout_allows_other_sender(self):
        outputs = list(replay([
            chat(0, "m1"),
            chat(11, "m2", sender_id="player-2"),
        ], self.create_sim()))
        self.assertEqual([x["target_player_id"] for x in outputs], ["player-1", "player-2"])

    def test_invalid_sequence_rejected(self):
        cases = [
            [chat(3), chat(2, "m2")],
            [{"kind": "chat", "at": 0, "event_id": "m1", "sender_id": "u1"}],
            [{"kind": "chat", "at": 0, "event_id": "m1", "sender_name": "x", "text": "free pots"}],
            [{"kind": "unknown", "at": 0}],
            [{"kind": "trading", "at": 0, "active": "yes"}],
            [{"kind": "inventory", "at": 0, "capacity": 8, "occupied": 9}],
            [{"kind": "finish", "at": 0, "target_player_id": ""}],
            [{"kind": "chat", "at": float("nan")}],
            [{"kind": "chat", "at": float("inf")}],
            [{"kind": "chat", "at": -1}],
            [{"kind": "chat", "at": True}],
        ]
        for records in cases:
            with self.subTest(records=records):
                with self.assertRaises(ReplayError):
                    list(replay(records, self.create_sim()))

    def test_cli_stdin_is_offline_jsonl(self):
        lines = [
            chat(0, "m1", text="anyone got free pots?"),
            chat(1, "m2", text="giving away pots"),
        ]
        proc = subprocess.run(
            [sys.executable, "-m", "rotmg_next.replay", "--self-player-id", "bot"],
            input="\n".join(json.dumps(line) for line in lines) + "\n",
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        outputs = [json.loads(line) for line in proc.stdout.splitlines()]
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]["target_player_id"], "player-1")

    def test_cli_malformed_input_fails(self):
        proc = subprocess.run(
            [sys.executable, "-m", "rotmg_next.replay", "--self-player-id", "bot"],
            input='{"kind":"chat","at":NaN}\n',
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("line 1", proc.stderr)


if __name__ == "__main__":
    unittest.main()
