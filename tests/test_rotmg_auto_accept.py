"""Offline auto-accept policy tests; no game client or account required."""

import unittest

from rotmg_next.auto_accept_policy import (
    AcceptIntent,
    AutoAcceptPolicy,
    AutoAcceptSettings,
    FinalOfferSnapshot,
    IncomingTradeInvitation,
)
from rotmg_next.inventory_policy import InventorySnapshot


def invitation(**kw):
    return IncomingTradeInvitation(
        request_id=kw.get("request_id", "invite-1"),
        recipient_player_id=kw.get("recipient_player_id", "my-account"),
        sender_player_id=kw.get("sender_player_id", "friend"),
        sender_name=kw.get("sender_name", "MyFriend"),
        observed_at=kw.get("observed_at", 1.0),
    )


def offer(**kw):
    return FinalOfferSnapshot(
        trade_id=kw.get("trade_id", "trade-1"),
        owner_player_id=kw.get("owner_player_id", "my-account"),
        counterparty_player_id=kw.get("counterparty_player_id", "friend"),
        revision=kw.get("revision", 3),
        incoming_item_ids=kw.get("incoming_item_ids", ("dex_pot",)),
        outgoing_item_ids=kw.get("outgoing_item_ids", ()),
        observed_at=kw.get("observed_at", 1.0),
    )


class SettingsTests(unittest.TestCase):
    def test_default_disabled(self):
        policy = AutoAcceptPolicy("my-account")
        snapshot = InventorySnapshot(8, 7)
        self.assertEqual(
            policy.consider_invitation(invitation(), snapshot, now=1).reason,
            "invitation_auto_accept_disabled",
        )
        self.assertEqual(
            policy.consider_final_offer(
                offer(), offer(), snapshot, now=1,
                active_trade_id="trade-1",
                active_counterparty_player_id="friend",
                trade_active=True,
            ).reason,
            "final_auto_accept_disabled",
        )

    def test_invalid_modes_and_config(self):
        for kwargs in (
            {"invitation_mode": "maybe"},
            {"final_mode": "always"},
            {"invitation_ttl_seconds": float("inf")},
            {"offer_ttl_seconds": float("nan")},
            {"player_cooldown_seconds": -5},
            {"allowed_player_ids": {"friend"}},
            {"allowed_incoming_item_ids": {"dex_pot"}},
            {"offer_ttl_seconds": 0},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    AutoAcceptSettings(**kwargs)


class InvitationTests(unittest.TestCase):
    def setUp(self):
        self.invites = AutoAcceptPolicy(
            "my-account", AutoAcceptSettings(invitation_mode="all")
        )
        self.inventory = InventorySnapshot(8, 7)

    def test_accept_any_incoming_invitation_when_opted_in(self):
        decision = self.invites.consider_invitation(invitation(), self.inventory, now=1)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.intent.stage, "incoming_invitation")
        self.assertEqual(decision.intent.counterparty_player_id, "friend")
        self.assertEqual(decision.intent.reference_id, "invite-1")

    def test_duplicate_and_sender_cooldown(self):
        self.assertTrue(self.invites.consider_invitation(invitation(), self.inventory, now=1).allowed)
        self.assertEqual(
            self.invites.consider_invitation(invitation(), self.inventory, now=2).reason,
            "duplicate_invitation",
        )
        self.assertEqual(
            self.invites.consider_invitation(
                invitation(request_id="invite-2", observed_at=3), self.inventory, now=3,
            ).reason,
            "sender_cooldown",
        )
        self.assertTrue(
            self.invites.consider_invitation(
                invitation(request_id="invite-3", observed_at=32), self.inventory, now=32,
            ).allowed
        )

    def test_allowlist_and_identity(self):
        policy = AutoAcceptPolicy(
            "my-account",
            AutoAcceptSettings(
                invitation_mode="allowlist", allowed_player_ids=frozenset({"friend"})
            ),
        )
        disguised = invitation(sender_player_id="stranger", sender_name="friend")
        self.assertEqual(
            policy.consider_invitation(disguised, self.inventory, now=1).reason,
            "sender_not_allowlisted",
        )
        self.assertTrue(
            policy.consider_invitation(invitation(), self.inventory, now=1).allowed
        )

    def test_busy_full_and_stale_requests(self):
        self.assertEqual(
            self.invites.consider_invitation(
                invitation(), self.inventory, now=1, trade_active=True,
            ).reason, "trade_or_request_already_pending"
        )
        self.assertEqual(
            self.invites.consider_invitation(
                invitation(), self.inventory, now=1, request_pending=True,
            ).reason, "trade_or_request_already_pending"
        )
        self.assertEqual(
            self.invites.consider_invitation(
                invitation(), InventorySnapshot(8, 8), now=1,
            ).reason, "inventory_full"
        )
        self.assertEqual(
            self.invites.consider_invitation(invitation(), self.inventory, now=10).reason,
            "stale_or_future_invitation",
        )
        self.assertEqual(
            self.invites.consider_invitation(invitation(), self.inventory, now=0).reason,
            "stale_or_future_invitation",
        )

    def test_wrong_account_and_self_request(self):
        self.assertEqual(
            self.invites.consider_invitation(
                invitation(recipient_player_id="other"), self.inventory, now=1,
            ).reason, "wrong_recipient"
        )
        self.assertEqual(
            self.invites.consider_invitation(
                invitation(sender_player_id="my-account"), self.inventory, now=1,
            ).reason, "self_trade_not_allowed"
        )


class FinalGiftTests(unittest.TestCase):
    def setUp(self):
        self.policy = AutoAcceptPolicy(
            "my-account",
            AutoAcceptSettings(
                final_mode="gift_only",
                allowed_incoming_item_ids=frozenset({"dex_pot", "atk_pot"}),
            ),
        )
        self.inventory = InventorySnapshot(8, 6)

    def check(self, initial=None, rechecked=None, **kwargs):
        return self.policy.consider_final_offer(
            initial or offer(),
            rechecked or offer(observed_at=1.5),
            kwargs.get("inventory", self.inventory),
            now=kwargs.get("now", 1.5),
            active_trade_id=kwargs.get("active_trade_id", "trade-1"),
            active_counterparty_player_id=kwargs.get(
                "active_counterparty_player_id", "friend"
            ),
            trade_active=kwargs.get("trade_active", True),
        )

    def test_receiving_permitted_gift_emits_only_intent(self):
        decision = self.check(
            initial=offer(incoming_item_ids=("dex_pot", "atk_pot")),
            rechecked=offer(incoming_item_ids=("dex_pot", "atk_pot"), observed_at=1.5),
        )
        self.assertTrue(decision.allowed)
        self.assertIsInstance(decision.intent, AcceptIntent)
        self.assertEqual(decision.intent.offer_revision, 3)
        self.assertEqual(decision.intent.stage, "final_gift")

    def test_outgoing_items_never_allowed(self):
        self.assertEqual(
            self.check(
                initial=offer(outgoing_item_ids=("valuable_sword",)),
                rechecked=offer(outgoing_item_ids=("valuable_sword",), observed_at=1.5),
            ).reason,
            "outgoing_items_forbidden",
        )

    def test_final_offer_is_not_approved_twice(self):
        self.assertTrue(self.check().allowed)
        self.assertEqual(self.check().reason, "duplicate_final_offer")

    def test_missing_or_unknown_incoming_items_rejected(self):
        self.assertEqual(
            self.check(
                initial=offer(incoming_item_ids=()),
                rechecked=offer(incoming_item_ids=(), observed_at=1.5),
            ).reason, "no_incoming_items"
        )
        self.assertEqual(
            self.check(
                initial=offer(incoming_item_ids=("unknown",)),
                rechecked=offer(incoming_item_ids=("unknown",), observed_at=1.5),
            ).reason, "unknown_incoming_item"
        )

    def test_offer_switching_and_revision_changes_rejected(self):
        self.assertEqual(
            self.check(
                initial=offer(revision=3),
                rechecked=offer(revision=4, observed_at=1.5),
            ).reason, "offer_changed"
        )
        self.assertEqual(
            self.check(
                initial=offer(incoming_item_ids=("dex_pot",)),
                rechecked=offer(incoming_item_ids=("atk_pot",), observed_at=1.5),
            ).reason, "offer_changed"
        )

    def test_inventory_capacity_and_pending_trade_context(self):
        self.assertEqual(
            self.check(inventory=InventorySnapshot(8, 8)).reason,
            "insufficient_inventory",
        )
        self.assertEqual(self.check(trade_active=False).reason, "not_trading")
        self.assertEqual(
            self.check(active_trade_id="other-trade").reason,
            "trade_changed",
        )
        self.assertEqual(
            self.check(active_counterparty_player_id="stranger").reason,
            "counterparty_changed",
        )

    def test_snapshot_identity_order_and_freshness(self):
        self.assertEqual(
            self.check(
                initial=offer(owner_player_id="someone_else"),
                rechecked=offer(owner_player_id="someone_else", observed_at=1.5),
            ).reason, "wrong_owner"
        )
        self.assertEqual(
            self.check(
                initial=offer(observed_at=2),
                rechecked=offer(observed_at=1.5),
            ).reason, "invalid_snapshot_order"
        )
        self.assertEqual(
            self.check(now=10).reason,
            "stale_offer",
        )

    def test_all_items_must_be_allowlisted(self):
        policy = AutoAcceptPolicy(
            "my-account", AutoAcceptSettings(final_mode="gift_only")
        )
        decision = policy.consider_final_offer(
            offer(), offer(observed_at=1.5), self.inventory,
            now=1.5, active_trade_id="trade-1",
            active_counterparty_player_id="friend", trade_active=True,
        )
        self.assertEqual(decision.reason, "no_permitted_items")

    def test_invalid_event_fields(self):
        with self.assertRaises(ValueError):
            invitation(request_id="")
        with self.assertRaises(ValueError):
            invitation(observed_at=float("inf"))
        with self.assertRaises(ValueError):
            offer(revision=True)
        with self.assertRaises(ValueError):
            offer(incoming_item_ids=["dex_pot"])
        with self.assertRaises(ValueError):
            offer(observed_at=10**400)
        with self.assertRaises(ValueError):
            self.check(now=float("nan"))


if __name__ == "__main__":
    unittest.main()
