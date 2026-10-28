# ROTMG Next: isolated offline core

## Why a new package?

This issue #6 implementation does not inherit the forked `trader.py` or its
screen coordinates, client automation, Python dependencies or legacy state.
Existing code and history are preserved for audit only. No existing live bot
behaviour is changed.

## Data flow

```text
synthetic / recorded ChatEvent
        |
        v
is_free_potion_offer(text)   [conservative, heuristic]
        |
        v
TradeCoordinator.process(event, inventory, now)
        |
        v
TradeRequestIntent or None
        |
        v
mock sink / local test only
```

No live ingestion adapter or trade gateway exists. The sender identity
(`sender_id`) **must** be taken from a trusted event transport, not parsed
from player-controlled chat text. `created_at` and `now` use a caller-supplied
monotonic clock. Passing deliberately false metadata is outside this offline
core's trust model.

The coordinator's only output is a *proposed* outgoing trade request. It
never accepts a trade, moves a potion, transfers an item, sends a network
request, reads memory, or clicks the client. It enforces one outstanding
request, sender cooldown, timeout, bounded event-ID deduplication and
available receiving space.

## Offline usage

```python
from rotmg_next import ChatEvent, InventorySnapshot, TradeCoordinator

coordinator = TradeCoordinator(self_player_id="my-player-id")
event = ChatEvent(
    event_id="msg-123",
    sender_id="sender-456",
    sender_name="OtherPlayer",
    text="free pots",
)
intent = coordinator.process(event, InventorySnapshot(8, 7), now=10.0)
assert intent is not None
assert intent.target_player_id == "sender-456"

# Local simulation only: never forward to a live game client.
assert coordinator.finish("sender-456")
```

Run the self-contained tests with `python -m unittest discover -s tests -p 'test_rotmg_next.py' -v`.

## Limitations

The announcement detector is deliberately conservative. Missed announcements
and occasional ambiguous matches are possible; actual game/chat slang must
be reviewed from permitted, non-sensitive sample data. There is no account
login, game integration, automated trade, automatic acceptance or inventory
synchronisation. No external dependencies or credentials are required.

Live game automation is **out of scope** unless game-platform permission and
security requirements are separately validated and authorised.

## Synthetic-event replay (no game integration)

Use the supplied local fixture to inspect the request intents the offline engine
would create. No game client, screenshot capture, network connection, credentials,
clicks or actual requests are involved:

```sh
python -m rotmg_next.replay --self-player-id my-player-id --file examples/free-pot-replay.jsonl
python -m unittest discover -s tests -p 'test_rotmg_*.py' -v
```

Input is one JSON object per line, each with a finite nonnegative `at` value
in nondecreasing monotonic-time order. The synthetic kinds are `chat` (requires
`event_id`, `sender_id`, `sender_name`, `text`; optional `channel`),
`inventory` (requires `capacity`, `occupied`, optional `reserved`),
`trading` (requires Boolean `active`) and `finish` (requires
`target_player_id`). The output is only JSON summaries of offline
`trade_request_intent` and `finish_result` events. A `finish` record
simulates a manual completion acknowledgement; it is **not** an in-game
trade settlement.

A fixture's `sender_id` is trusted **only for the simulation**; there is no
authenticated live event source. Do not connect this replay module to client
automation, and do not treat emitted intents as permission to trade.
