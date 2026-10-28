"""Deterministic, offline trade-request intent coordinator.

The coordinator does not call an API, inject into a client or click any UI.
A separate, currently *unimplemented*, permitted adapter would be needed
to translate an intent into a live request.
"""

from collections import deque
from dataclasses import dataclass
from math import isfinite
from typing import Deque, Dict, Optional, Protocol, Set

from .chat_detector import ChatEvent, is_free_potion_offer
from .inventory_policy import InventorySnapshot


@dataclass(frozen=True)
class TradeRequestIntent:
    event_id: str
    target_player_id: str
    target_player_name: str
    created_at: float


class TradeIntentSink(Protocol):
    """Non-game interface for downstream mock/simulator consumers."""

    def submit(self, intent: TradeRequestIntent) -> None:
        ...


class TradeCoordinator:
    """At most one outstanding request; duplicate and repeat-announcement guard."""

    ALLOWED_CHANNELS = frozenset({"public", "local", "realm"})

    def __init__(
        self,
        self_player_id: str,
        *,
        sender_cooldown_seconds: float = 30.0,
        request_timeout_seconds: float = 10.0,
        max_seen_events: int = 2048,
    ) -> None:
        if not self_player_id or not self_player_id.strip():
            raise ValueError("self_player_id is required")
        for label, value in (
            ("sender_cooldown_seconds", sender_cooldown_seconds),
            ("request_timeout_seconds", request_timeout_seconds),
        ):
            if type(value) not in (int, float) or not isfinite(value):
                raise ValueError(f"{label} must be a finite number")
        if sender_cooldown_seconds < 0 or request_timeout_seconds <= 0:
            raise ValueError("invalid timing configuration")
        if type(max_seen_events) is not int or max_seen_events < 1:
            raise ValueError("max_seen_events must be positive")
        self.self_player_id = self_player_id
        self.sender_cooldown_seconds = sender_cooldown_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.max_seen_events = max_seen_events
        self.pending: Optional[TradeRequestIntent] = None
        self._seen_ids: Set[str] = set()
        self._seen_order: Deque[str] = deque()
        self._last_request: Dict[str, float] = {}

    def _mark_seen(self, event_id: str) -> bool:
        if event_id in self._seen_ids:
            return False
        if len(self._seen_order) == self.max_seen_events:
            self._seen_ids.remove(self._seen_order.popleft())
        self._seen_ids.add(event_id)
        self._seen_order.append(event_id)
        return True

    def expire(self, now: float) -> bool:
        """Clear an expired intent; caller supplies monotonic, numeric time."""
        if type(now) not in (int, float) or not isfinite(now):
            raise ValueError("now must be a finite number")
        if self.pending and now - self.pending.created_at >= self.request_timeout_seconds:
            self.pending = None
            return True
        return False

    def finish(self, target_player_id: str) -> bool:
        """Manually acknowledge completion, rejection, or cancellation."""
        if self.pending is None or self.pending.target_player_id != target_player_id:
            return False
        self.pending = None
        return True

    def process(
        self,
        event: ChatEvent,
        inventory: InventorySnapshot,
        *,
        now: float,
        currently_trading: bool = False,
    ) -> Optional[TradeRequestIntent]:
        """Return a request intent immediately when a valid event can be handled.

        The method has no side effects outside memory; callers must use a mock
        sink. A returned intent never authorises an item transfer or acceptance.
        """
        self.expire(now)
        if not self._mark_seen(event.event_id):
            return None
        if event.channel.lower() not in self.ALLOWED_CHANNELS:
            return None
        if event.sender_id == self.self_player_id:
            return None
        if self.pending is not None or currently_trading or not inventory.can_receive:
            return None
        if not is_free_potion_offer(event.text):
            return None

        last = self._last_request.get(event.sender_id)
        if last is not None and now - last < self.sender_cooldown_seconds:
            return None
        # Keep cooldown bookkeeping bounded by removing old entries.
        for player, when in list(self._last_request.items()):
            if now - when >= self.sender_cooldown_seconds:
                del self._last_request[player]

        intent = TradeRequestIntent(
            event_id=event.event_id,
            target_player_id=event.sender_id,
            target_player_name=event.sender_name,
            created_at=now,
        )
        self._last_request[event.sender_id] = now
        self.pending = intent
        return intent
