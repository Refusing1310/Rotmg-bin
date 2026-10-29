"""Hermetic unit tests: no game client, network, UI or account access."""

import unittest

from rotmg_next import (
    ChatEvent,
    InventorySnapshot,
    TradeCoordinator,
    is_free_potion_offer,
    is_free_item_offer,
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


class FreeItemOfferTests(unittest.TestCase):
    def test_positive_generic_offers(self):
        cases = [
            "free", " FREE ", "FREE!", "free!!!", "free.",
            "free pots", "free dex", "free life pots", "free gear",
            "free items", "free t12", "free 3 rings",
            "giving away robes", "giving away some weapons",
            "giving out spare equipment", "handing out gear",
            "rings for free", "I want to give away free dex",
            "I am giving away free rings", "I have free rings",
            "anyone want free gear?",
            "anyone need free items?", "Free wis - trade me",
        ]
        for message in cases:
            with self.subTest(message=message):
                self.assertTrue(is_free_item_offer(message))

    def test_negative_and_ambiguous_generic(self):
        cases = [
            "anyone giving free pots?", "anyone got free gear?",
            "can i get free dex?", "who has free items?",
            "looking for free rings", "i want free armor",
            "not giving away free gear", "no free x",
            "I don't have free gear", "selling free items",
            "buying free gear", "wtb free rings", "free to play",
            "free space", "free slots", "free game",
            "thanks for free dex", "I got free gear",
            "someone is giving away rings", "they are giving out pots",
            "free gear?", "free?", "free ?", "anyone free?",
            "free please", "free to play", "", "pots are expensive",
            "free hugs", "free heals", "free here", "free x",
            "free gear was a scam", "Alice is giving away free dex",
            "someone's giving away pots", "Bob was handing out free gear",
            "free diamonds", "free tomorrow",
            "I wanted free pots yesterday",
        ]
        for message in cases:
            with self.subTest(message=message):
                self.assertFalse(is_free_item_offer(message))

    def test_bare_free_intent_sender_and_existing_guards(self):
        for text in ("free", " FREE ", "FREE!", "free!!!", "free."):
            with self.subTest(text=text):
                bot = TradeCoordinator("bot", sender_cooldown_seconds=30)
                inventory = InventorySnapshot(8, 7)
                first = bot.process(
                    event("bare-1", sender_id="giver", sender_name="RealSender", text=text),
                    inventory, now=1,
                )
                self.assertIsNotNone(first)
                self.assertEqual(first.target_player_id, "giver")
                self.assertEqual(first.target_player_name, "RealSender")
                # One pending intent, regardless of how many others advertise.
                self.assertIsNone(bot.process(
                    event("bare-2", sender_id="other", text="free"),
                    inventory, now=2,
                ))
                self.assertTrue(bot.finish("giver"))
                # Clearing the pending intent does not bypass cooldown.
                self.assertIsNone(bot.process(
                    event("bare-3", sender_id="giver", text="free"),
                    inventory, now=3,
                ))
                self.assertIsNone(bot.process(
                    event("bare-1", sender_id="giver", text="free"),
                    inventory, now=32,
                ))
                self.assertIsNotNone(bot.process(
                    event("bare-4", sender_id="giver", text="free"),
                    inventory, now=32,
                ))

        # Exact-message matching is mandatory, including with misleading text.
        for text in ("free?", "free please", "free here", "free to play",
                     "anyone free?", "free gear?", "no free", "free now"):
            with self.subTest(rejected=text):
                self.assertFalse(is_free_item_offer(text))
        full = InventorySnapshot(8, 8)
        room = InventorySnapshot(8, 7)
        self.assertIsNone(TradeCoordinator("bot").process(
            event("full", text="free"), full, now=1,
        ))
        self.assertIsNone(TradeCoordinator("bot").process(
            event("busy", text="free"), room, now=1, currently_trading=True,
        ))
        self.assertIsNone(TradeCoordinator("bot").process(
            event("self", sender_id="bot", text="free"), room, now=1,
        ))
        self.assertIsNone(TradeCoordinator("bot").process(
            event("system", text="free", channel="system"), room, now=1,
        ))

    def test_generic_intent_sender_and_guards(self):
        bot = TradeCoordinator("bot", sender_cooldown_seconds=30)
        inventory = InventorySnapshot(8, 6)
        first = bot.process(
            event("g1", sender_id="actual", sender_name="ActualSender",
                  text="free gear - whisper FakeSender"),
            inventory, now=1,
        )
        self.assertIsNotNone(first)
        self.assertEqual(first.target_player_id, "actual")
        self.assertIsNone(bot.process(
            event("g2", sender_id="other", text="free dex"),
            inventory, now=2,
        ))
        self.assertTrue(bot.finish("actual"))
        self.assertIsNone(bot.process(
            event("g3", sender_id="actual", text="free rings"),
            inventory, now=3,
        ))
        self.assertIsNotNone(bot.process(
            event("g4", sender_id="other", text="free rings"),
            inventory, now=4,
        ))
        self.assertFalse(is_free_item_offer(None))
        self.assertFalse(is_free_item_offer(123))


    def test_custom_aliases_are_opt_in(self):
        self.assertFalse(is_free_item_offer("free x"))
        self.assertTrue(is_free_item_offer("free x", additional_item_aliases=("x",)))
        self.assertTrue(is_free_item_offer(
            "Free Shiny Ancient Orb", additional_item_aliases=("shiny ancient orb",)
        ))
        self.assertFalse(is_free_item_offer(
            "free hugs", additional_item_aliases=("shiny ancient orb",)
        ))
        self.assertFalse(is_free_item_offer(
            "Alice is giving away free x", additional_item_aliases=("x",)
        ))


    def test_many_custom_aliases_do_not_exceed_default_vocabulary_limit(self):
        aliases = tuple(f"customitem{i}" for i in range(128))
        bot = TradeCoordinator("bot", additional_item_aliases=aliases)
        intent = bot.process(
            event("many", sender_id="giver", text="free customitem127"),
            InventorySnapshot(8, 7), now=1,
        )
        self.assertIsNotNone(intent)
        self.assertEqual(intent.target_player_id, "giver")
        with self.assertRaises(ValueError):
            TradeCoordinator("bot", additional_item_aliases=aliases + ("too_many",))

    def test_reject_invalid_alias_configuration(self):
        for aliases in ("x", (None,), ("",), ("a" * 70,), range(2), ("^x.*",)):
            with self.subTest(aliases=aliases):
                with self.assertRaises(ValueError):
                    is_free_item_offer("free dex", additional_item_aliases=aliases)
        with self.assertRaises(ValueError):
            TradeCoordinator("bot", additional_item_aliases=("^x.*",))

    def test_third_party_messages_never_target_reporter(self):
        for text in (
            "Alice is giving away free dex",
            "somebody's giving away pots",
            "someone is giving away rings",
            "they're handing out free gear",
        ):
            with self.subTest(text=text):
                coordinator = TradeCoordinator("bot")
                self.assertIsNone(coordinator.process(
                    event("third-party", sender_id="reporter", text=text),
                    InventorySnapshot(8, 5), now=1,
                ))

    def test_configured_item_requests_preserve_coordinator_guards(self):
        bot = TradeCoordinator("bot", additional_item_aliases=("x",))
        inventory = InventorySnapshot(8, 7)
        request = bot.process(
            event("custom", sender_id="giver", sender_name="Giver", text="free x"),
            inventory, now=2,
        )
        self.assertIsNotNone(request)
        self.assertEqual(request.target_player_id, "giver")
        self.assertIsNone(bot.process(
            event("custom-repeat", sender_id="other", text="free dex"),
            inventory, now=3,
        ))
        self.assertTrue(bot.finish("giver"))
        self.assertIsNone(bot.process(
            event("other-report", sender_id="reporter",
                  text="Alice is giving away free dex"),
            inventory, now=4,
        ))


if __name__ == "__main__":
    unittest.main()
