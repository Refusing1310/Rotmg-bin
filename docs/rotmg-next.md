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


## Generic free-item offers (issue #12)

The coordinator now recognises probable giveaway announcements such as
`free dex`, `free gear`, `free x`, `giving away t12 weapons`,
`handing out robes`, `rings for free` and `anyone want free items?`,
in addition to the original potion expressions. The public
`is_free_potion_offer` detector remains available and unchanged.

This text-only heuristic intentionally rejects requests for freebies,
denials, sales, reports about other players, thank-you messages,
non-item phrases such as `free space`, and ambiguous questions.
Unrecognised slang or long/context-dependent messages may still be
misclassified; always confirm the offer manually before taking a trade.
The output is **only an offline trade-request intent** addressed to the
sender identified in a trusted `ChatEvent`. Nothing observes chat or
executes a game trade.

DECA's March 2026 Terms §6.2 restrict gameplay automation and automated
requests. Any client connection, trade execution, input automation,
or live adapter remains unimplemented and unapproved.
