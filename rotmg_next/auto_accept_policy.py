"""Offline-only acceptance policies for *synthetic* ROTMG trade events.

No game integration, account access, input automation, or real acceptance exists.
The outputs are advisory intents, never sent to a game client.
"""

from collections import deque
from dataclasses import dataclass, field
from math import isfinite
from typing import FrozenSet, Optional, Tuple

from .inventory_policy import InventorySnapshot


def _identity(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")


def _clock(value: float, label: str) -> None:
    if type(value) not in (float, int):
        raise ValueError(f"{label} must be a finite nonnegative number")
    try:
        valid = isfinite(value) and value >= 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{label} must be a finite nonnegative number")


@dataclass(frozen=True)
class AutoAcceptSettings:
    """Both actions opt-in separately; defaults authorize nothing."""

    invitation_mode: str = "off"  # off, allowlist, all
    final_mode: str = "off"  # off, gift_only
    allowed_player_ids: FrozenSet[str] = field(default_factory=frozenset)
    allowed_incoming_item_ids: FrozenSet[str] = field(default_factory=frozenset)
    invitation_ttl_seconds: float = 5.0
    offer_ttl_seconds: float = 2.0
    player_cooldown_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.invitation_mode not in ("off", "allowlist", "all"):
            raise ValueError("invalid invitation_mode")
        if self.final_mode not in ("off", "gift_only"):
            raise ValueError("invalid final_mode")
        if type(self.allowed_player_ids) is not frozenset:
            raise ValueError("allowed_player_ids must be a frozenset")
        if type(self.allowed_incoming_item_ids) is not frozenset:
            raise ValueError("allowed_incoming_item_ids must be a frozenset")
        for player in self.allowed_player_ids:
            _identity(player, "allowed_player_id")
        for item in self.allowed_incoming_item_ids:
            _identity(item, "allowed_incoming_item_id")
        for label in ("invitation_ttl_seconds", "offer_ttl_seconds", "player_cooldown_seconds"):
            value = getattr(self, label)
            _clock(value, label)
        if self.invitation_ttl_seconds == 0 or self.offer_ttl_seconds == 0:
            raise ValueError("request/offer TTL must be positive")


@dataclass(frozen=True)
class IncomingTradeInvitation:
    """Caller-supplied metadata, not obtained from game chat strings."""

    request_id: str
    recipient_player_id: str
    sender_player_id: str
    sender_name: str
    observed_at: float

    def __post_init__(self) -> None:
        for label in ("request_id", "recipient_player_id", "sender_player_id", "sender_name"):
            _identity(getattr(self, label), label)
        _clock(self.observed_at, "observed_at")


@dataclass(frozen=True)
class FinalOfferSnapshot:
    """Immutable representation of an observed offer for local testing.

    The tuple lists are item *unit IDs*, one per unit, not stack counts.
    A real integration would have to authenticate and reread them independently.
    """

    trade_id: str
    owner_player_id: str
    counterparty_player_id: str
    revision: int
    incoming_item_ids: Tuple[str, ...]
    outgoing_item_ids: Tuple[str, ...]
    observed_at: float

    def __post_init__(self) -> None:
        for label in ("trade_id", "owner_player_id", "counterparty_player_id"):
            _identity(getattr(self, label), label)
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError("revision must be a nonnegative integer")
        for label in ("incoming_item_ids", "outgoing_item_ids"):
            items = getattr(self, label)
            if type(items) is not tuple:
                raise ValueError(f"{label} must be a tuple")
            for item in items:
                _identity(item, label)
        _clock(self.observed_at, "observed_at")


@dataclass(frozen=True)
class AcceptIntent:
    stage: str  # incoming_invitation, final_gift
    reference_id: str
    counterparty_player_id: str
    created_at: float
    offer_revision: Optional[int] = None


@dataclass(frozen=True)
class AcceptDecision:
    reason: str
    intent: Optional[AcceptIntent] = None

    @property
    def allowed(self) -> bool:
        return self.intent is not None


class AutoAcceptPolicy:
    """Never performs actions; decisions are for mock/simulation consumers only."""

    def __init__(self, self_player_id: str, settings: AutoAcceptSettings = AutoAcceptSettings()):
        _identity(self_player_id, "self_player_id")
        self.self_player_id = self_player_id
        self.settings = settings
        self._seen_invitation_ids = set()
        self._invitation_order = deque()
        self._seen_final_offers = set()
        self._final_order = deque()
        self._max_seen = 2048
        self._sender_request_at = {}

    def consider_invitation(
        self,
        invitation: IncomingTradeInvitation,
        inventory: InventorySnapshot,
        *,
        now: float,
        trade_active: bool = False,
        request_pending: bool = False,
    ) -> AcceptDecision:
        _clock(now, "now")
        if self.settings.invitation_mode == "off":
            return AcceptDecision("invitation_auto_accept_disabled")
        if invitation.recipient_player_id != self.self_player_id:
            return AcceptDecision("wrong_recipient")
        if invitation.sender_player_id == self.self_player_id:
            return AcceptDecision("self_trade_not_allowed")
        if invitation.observed_at > now or now - invitation.observed_at > self.settings.invitation_ttl_seconds:
            return AcceptDecision("stale_or_future_invitation")
        if invitation.request_id in self._seen_invitation_ids:
            return AcceptDecision("duplicate_invitation")
        if self.settings.invitation_mode == "allowlist" and invitation.sender_player_id not in self.settings.allowed_player_ids:
            return AcceptDecision("sender_not_allowlisted")
        if trade_active or request_pending:
            return AcceptDecision("trade_or_request_already_pending")
        if not inventory.can_receive:
            return AcceptDecision("inventory_full")
        last = self._sender_request_at.get(invitation.sender_player_id)
        if last is not None and now - last < self.settings.player_cooldown_seconds:
            return AcceptDecision("sender_cooldown")

        if len(self._invitation_order) >= self._max_seen:
            self._seen_invitation_ids.discard(self._invitation_order.popleft())
        self._seen_invitation_ids.add(invitation.request_id)
        self._invitation_order.append(invitation.request_id)
        self._sender_request_at[invitation.sender_player_id] = now
        self._sender_request_at = {
            sender: when for sender, when in self._sender_request_at.items()
            if now - when < self.settings.player_cooldown_seconds
        }
        return AcceptDecision(
            "eligible_invitation",
            AcceptIntent(
                stage="incoming_invitation",
                reference_id=invitation.request_id,
                counterparty_player_id=invitation.sender_player_id,
                created_at=now,
            ),
        )

    def consider_final_offer(
        self,
        initial: FinalOfferSnapshot,
        rechecked: FinalOfferSnapshot,
        inventory: InventorySnapshot,
        *,
        now: float,
        active_trade_id: str,
        active_counterparty_player_id: str,
        trade_active: bool,
    ) -> AcceptDecision:
        _clock(now, "now")
        if self.settings.final_mode != "gift_only":
            return AcceptDecision("final_auto_accept_disabled")
        if not trade_active:
            return AcceptDecision("not_trading")
        if initial.trade_id != active_trade_id or rechecked.trade_id != active_trade_id:
            return AcceptDecision("trade_changed")
        if initial.counterparty_player_id != active_counterparty_player_id:
            return AcceptDecision("counterparty_changed")
        if initial.owner_player_id != self.self_player_id:
            return AcceptDecision("wrong_owner")
        if active_counterparty_player_id == self.self_player_id:
            return AcceptDecision("self_trade_not_allowed")
        # Exact snapshots must match except the second observation time.
        first = (
            initial.trade_id, initial.owner_player_id, initial.counterparty_player_id,
            initial.revision, initial.incoming_item_ids, initial.outgoing_item_ids
        )
        second = (
            rechecked.trade_id, rechecked.owner_player_id, rechecked.counterparty_player_id,
            rechecked.revision, rechecked.incoming_item_ids, rechecked.outgoing_item_ids
        )
        if first != second:
            return AcceptDecision("offer_changed")
        if initial.observed_at > rechecked.observed_at or rechecked.observed_at > now:
            return AcceptDecision("invalid_snapshot_order")
        if now - rechecked.observed_at > self.settings.offer_ttl_seconds:
            return AcceptDecision("stale_offer")
        if initial.outgoing_item_ids or rechecked.outgoing_item_ids:
            return AcceptDecision("outgoing_items_forbidden")
        if not initial.incoming_item_ids:
            return AcceptDecision("no_incoming_items")
        if not self.settings.allowed_incoming_item_ids:
            return AcceptDecision("no_permitted_items")
        if any(item not in self.settings.allowed_incoming_item_ids for item in initial.incoming_item_ids):
            return AcceptDecision("unknown_incoming_item")
        if len(initial.incoming_item_ids) > inventory.free_slots:
            return AcceptDecision("insufficient_inventory")
        reference = (initial.trade_id, initial.revision)
        if reference in self._seen_final_offers:
            return AcceptDecision("duplicate_final_offer")
        if len(self._final_order) >= self._max_seen:
            self._seen_final_offers.discard(self._final_order.popleft())
        self._seen_final_offers.add(reference)
        self._final_order.append(reference)
        return AcceptDecision(
            "verified_gift_intent",
            AcceptIntent(
                stage="final_gift",
                reference_id=initial.trade_id,
                counterparty_player_id=active_counterparty_player_id,
                created_at=now,
                offer_revision=initial.revision,
            ),
        )
