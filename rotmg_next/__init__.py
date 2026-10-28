"""Offline-only ROTMG trade-planning primitives.

Nothing in this package connects to a game client or sends a trade.
"""
from .chat_detector import ChatEvent, is_free_potion_offer
from .inventory_policy import InventorySnapshot
from .trade_coordinator import TradeCoordinator, TradeRequestIntent

__all__ = [
    "ChatEvent",
    "InventorySnapshot",
    "TradeCoordinator",
    "TradeRequestIntent",
    "is_free_potion_offer",
]
