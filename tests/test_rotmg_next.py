"""Hermetic unit tests: no game client, network, UI or account access."""

import unittest

from rotmg_next import (
    ChatEvent,
    InventorySnapshot,
    TradeCoordinator,
    is_free_potion_offer,
)


def event(event_id="e1", sender_id="u1", text="free pots", **kwargs):
    return ChatEvent(
        event_id=event_id,
        sender_id=sender_id,
        sender_name=kwargs.get("sender_name", "PotionSeller"),
        text=text,
        channel=kwargs.get("channel", "public"),
    )


class ChatDetectorTests(unittest.TestCase):
    def test_offer_phrases(self):
        offers = [
            "free pots",
            "FREE STAT POTIONS",
            "giving away pots",
            "giving out some pots",
            "handing out free potions",
            "pots for free",
            "anyone want free pots?",
            "anyone need free pots?",
            "Giving away stat pots",
        ]
        for message in offers:
            with self.subTest(message=message):
                self.assertTrue(is_free_potion_offer(message))

    def test_negative_and_ambiguous_phrases(self):
        not_offers = [
            "anyone got free pots?",
            "anyone giving away free pots?",
            "can someone give me free pots?",
            "who has free pots?",
            "looking for free pots",
            "i need free pots",
            "need free pots",
            "want free pots",
            "not giving away free pots",
            "I don't have free pots",
            "selling free pots",
            "free pots?",
            "buying free pots",
            "I have pots",
            "",
        ]
        for message in not_offers:
            with self.subTest(message=message):
                self.assertFalse(is_free_potion_offer(message))

    def test_invalid_event_metadata(self):
        for kw in ({"event_id": ""}, {"sender_id": ""}, {"sender_name": ""}):
            with self.subTest(kw=kw):
                with self.assertRaises(ValueError):
                    ChatEvent(
                        event_id=kw.get("event_id", "e1"),
                        sender_id=kw.get("sender_id", "u1"),
                        sender_name=kw.get("sender_name", "User"),
                        text="free pots",
                    )


class InventoryTests(unittest.TestCase):
    def test_reserved_slots(self):
        self.assertEqual(InventorySnapshot(8, 6, 1).free_slots, 1)
        self.assertTrue(InventorySnapshot(8, 6, 1).can_receive)
        self.assertFalse(InventorySnapshot(8, 6, 2).can_receive)

    def test_invalid_snapshot(self):
        for values in ((8, 9, 0), (8, 7, 2), (-1, 0, 0), (8, True, 0)):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    InventorySnapshot(*values)


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.bot = TradeCoordinator("bot", sender_cooldown_seconds=30, request_timeout_seconds=10)
        self.space = InventorySnapshot(8, 7)

    def test_immediate_intent_uses_metadata_identity(self):
        intent = self.bot.process(
            event(text="free pots — trade OtherGuy", sender_name="ActualSender"),
            self.space,
            now=1,
        )
        self.assertIsNotNone(intent)
        self.assertEqual(intent.target_player_id, "u1")
        self.assertEqual(intent.target_player_name, "ActualSender")
        self.assertEqual(intent.created_at, 1)

    def test_duplicate_does_not_restart_trade(self):
        first = self.bot.process(event(), self.space, now=1)
        self.assertIsNotNone(first)
        self.assertIsNone(self.bot.process(event(), self.space, now=2))
        self.assertEqual(self.bot.pending, first)

    def test_self_message_rejected(self):
        self.assertIsNone(self.bot.process(event(sender_id="bot"), self.space, now=1))

    def test_non_chat_channels_rejected(self):
        self.assertIsNone(
            self.bot.process(event(channel="system"), self.space, now=1)
        )

    def test_full_inventory_rejected(self):
        self.assertIsNone(
            self.bot.process(event(), InventorySnapshot(8, 8), now=1)
        )

    def test_existing_trade_blocks_request(self):
        self.assertIsNone(
            self.bot.process(event(), self.space, now=1, currently_trading=True)
        )

    def test_single_pending_request(self):
        self.assertIsNotNone(self.bot.process(event(), self.space, now=1))
        self.assertIsNone(self.bot.process(
            event("e2", sender_id="u2"), self.space, now=2
        ))

    def test_timeout_frees_pending_but_preserves_cooldown(self):
        self.assertIsNotNone(self.bot.process(event(), self.space, now=1))
        self.assertFalse(self.bot.expire(10))
        self.assertTrue(self.bot.expire(11))
        self.assertIsNone(self.bot.pending)
        self.assertIsNone(self.bot.process(event("e2"), self.space, now=12))
        self.assertIsNotNone(self.bot.process(event("e3", sender_id="u2"), self.space, now=13))

    def test_cooldown_elapsed(self):
        self.assertIsNotNone(self.bot.process(event(), self.space, now=1))
        self.assertTrue(self.bot.finish("u1"))
        self.assertIsNone(self.bot.process(event("e2"), self.space, now=30))
        self.assertIsNotNone(self.bot.process(event("e3"), self.space, now=31))

    def test_wrong_sender_cannot_complete_request(self):
        self.assertIsNotNone(self.bot.process(event(), self.space, now=1))
        self.assertFalse(self.bot.finish("u2"))
        self.assertIsNotNone(self.bot.pending)

    def test_seen_events_are_bounded(self):
        bot = TradeCoordinator("bot", max_seen_events=2, sender_cooldown_seconds=0)
        for i in range(3):
            self.assertIsNone(
                bot.process(event(f"e{i}", text="anyone got free pots?"), self.space, now=i)
            )
        self.assertEqual(len(bot._seen_ids), 2)
        self.assertEqual(len(bot._seen_order), 2)

    def test_bad_configuration(self):
        with self.assertRaises(ValueError):
            TradeCoordinator("bot", max_seen_events=0)
        with self.assertRaises(ValueError):
            TradeCoordinator("bot", request_timeout_seconds=0)


if __name__ == "__main__":
    unittest.main()
