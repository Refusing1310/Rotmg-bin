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
is_free_item_offer(text)     [bare "free", known items or configured aliases]
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

The offline coordinator's `is_free_item_offer` classifier recognises
**self-advertised** giveaways using a controlled ROTMG item vocabulary.
It does not turn arbitrary `free <word>` text into a trade intent.

| Chat input | Default decision | Reason |
| --- | --- | --- |
| `free`, `FREE!`, `free.` | Match | Common short giveaway announcement; item unspecified |
| `free?`, `anyone free?` | Ignore | Ambiguous question, not a self-advertised item offer |
| `free pots`, `free dex`, `free gear` | Match | Known item/term, sender advertises it |
| `giving away rings`, `I want to give away free dex` | Match | Self-advertised giveaway |
| `anyone want free gear?` | Match | Offer to the audience, not a request |
| `free x` | Ignore by default | Unknown name; add `x` as an explicit item alias |
| `free hugs`, `free here`, `free gear was a scam` | Ignore | Non-item / non-offer context |
| `Alice is giving away free dex` | Ignore | Third-party report, not the sender's offer |
| `anyone giving free pots?` | Ignore | Request to others |

An optional, validated `additional_item_aliases` iterable extends the known
vocabulary for custom, event-specific, or new ROTMG item names:

```python
from rotmg_next import TradeCoordinator, is_free_item_offer

assert not is_free_item_offer("free x")
assert is_free_item_offer("free x", additional_item_aliases=("x",))
bot = TradeCoordinator("my-player-id", additional_item_aliases=("x",))
```

Aliases must contain 1-64 characters (letters, digits, spaces, hyphens
and apostrophes), and are limited to 128 additional names per coordinator.
Unknown **item names** are deliberately not treated as outgoing requests. As an
exception, a whole-message `free` (case-insensitive, optional `!` or final `.`)
produces an intent even without an item name (issue #16). This is a higher
false-positive risk: a player may mean that they are available, rather than
offering an item. `free?` and additional words are not covered by this exception.
The user accepted that trade-off for the offline detector. Existing trusted
sender metadata, cooldown, busy, capacity and deduplication guards still apply.
Phrase recognition remains heuristic and may miss valid advertisements;
for live contexts, manual review is preferable to an overbroad detector.

The existing `is_free_potion_offer` public API is unchanged.
`TradeCoordinator.process` emits **offline-only intentions**, never
an actual request, click, trade confirmation, payment or inventory change.
Sender identification uses trusted `ChatEvent` metadata, not chat text.
The pending-request, sender-cooldown, duplicate, busy and inventory guards
remain in force. No game-client integration or packet access exists.

DECA's current Terms restrict third-party automation used to play the
game and automated requests. Live trade submission requires documented
platform permission, not merely passing tests.
