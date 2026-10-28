"""Deterministic offline JSON-lines simulator.

Consumes supplied fixtures only. No network, keyboard, game memory, or trade I/O.
The source of chat sender metadata is hypothetical for testing and is not
authentication; production ingestion is intentionally unsupported.
"""

import argparse
import json
import math
import sys
from typing import Any, Iterable, Mapping, Optional

from .chat_detector import ChatEvent
from .inventory_policy import InventorySnapshot
from .trade_coordinator import TradeCoordinator


class ReplayError(ValueError):
    """Invalid fixture or ordering."""


class ReplaySimulator:
    """Process synthetic events in increasing monotonic-time order."""

    def __init__(
        self,
        self_player_id: str,
        inventory: InventorySnapshot,
        *,
        sender_cooldown_seconds: float = 30.0,
        request_timeout_seconds: float = 10.0,
    ) -> None:
        self.coordinator = TradeCoordinator(
            self_player_id,
            sender_cooldown_seconds=sender_cooldown_seconds,
            request_timeout_seconds=request_timeout_seconds,
        )
        self.inventory = inventory
        self.currently_trading = False
        self._last_at: Optional[float] = None

    def handle(self, record: Mapping[str, Any]) -> Optional[dict]:
        if not isinstance(record, dict):
            raise ReplayError("each event must be a JSON object")
        at = record.get("at")
        if type(at) not in (float, int) or not math.isfinite(at) or at < 0:
            raise ReplayError("'at' must be a finite nonnegative number")
        if self._last_at is not None and at < self._last_at:
            raise ReplayError("events must be in nondecreasing 'at' order")
        self._last_at = at
        self.coordinator.expire(at)

        kind = record.get("kind")
        if kind == "chat":
            try:
                chat = ChatEvent(
                    event_id=record["event_id"],
                    sender_id=record["sender_id"],
                    sender_name=record["sender_name"],
                    text=record["text"],
                    channel=record.get("channel", "public"),
                )
            except (KeyError, ValueError, TypeError) as exc:
                raise ReplayError(f"invalid chat fixture: {exc}") from exc
            intent = self.coordinator.process(
                chat, self.inventory, now=at, currently_trading=self.currently_trading
            )
            if intent is None:
                return None
            return {
                "kind": "trade_request_intent",
                "at": at,
                "event_id": intent.event_id,
                "target_player_id": intent.target_player_id,
                "target_player_name": intent.target_player_name,
            }
        if kind == "inventory":
            try:
                self.inventory = InventorySnapshot(
                    record["capacity"], record["occupied"], record.get("reserved", 0)
                )
            except (KeyError, ValueError, TypeError) as exc:
                raise ReplayError(f"invalid inventory fixture: {exc}") from exc
            return None
        if kind == "trading":
            active = record.get("active")
            if type(active) is not bool:
                raise ReplayError("trading.active must be a boolean")
            self.currently_trading = active
            return None
        if kind == "finish":
            player_id = record.get("target_player_id")
            if not isinstance(player_id, str) or not player_id.strip():
                raise ReplayError("finish.target_player_id must be a nonempty string")
            return {
                "kind": "finish_result",
                "at": at,
                "target_player_id": player_id,
                "cleared": self.coordinator.finish(player_id),
            }
        raise ReplayError(f"unsupported fixture kind: {kind!r}")


def replay(records: Iterable[Mapping[str, Any]], simulator: ReplaySimulator):
    """Yield only simulated intents and finish acknowledgements."""
    for record in records:
        result = simulator.handle(record)
        if result is not None:
            yield result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay synthetic RotMG chat events locally; never sends trades."
    )
    parser.add_argument("--self-player-id", required=True)
    parser.add_argument("--capacity", type=int, default=8)
    parser.add_argument("--occupied", type=int, default=7)
    parser.add_argument("--file", help="JSON Lines fixture path; default: standard input")
    args = parser.parse_args(argv)

    try:
        simulator = ReplaySimulator(
            args.self_player_id, InventorySnapshot(args.capacity, args.occupied)
        )
        source = open(args.file, encoding="utf-8") if args.file else sys.stdin
        try:
            for line_num, line in enumerate(source, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line, parse_constant=lambda token: (_ for _ in ()).throw(
                        ValueError("nonfinite constant " + token)
                    ))
                    result = simulator.handle(record)
                except (ValueError, TypeError) as exc:
                    raise ReplayError(f"line {line_num}: {exc}") from exc
                if result is not None:
                    print(json.dumps(result, sort_keys=True))
        finally:
            if args.file:
                source.close()
    except (OSError, ReplayError, ValueError) as exc:
        print(f"Offline replay error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
