# Trade auto-acceptance policy — offline prototype

Tracked by [issue #9](https://github.com/Refusing1310/Rotmg-bin/issues/9).
This is a **local policy simulator only**. It never logs in, listens to live
messages, sends trade requests, accepts offers, clicks the game, or transfers items.

There are **two independent opt-in stages**:

1. **Incoming invitation:** `invitation_mode="off"` (default), `"allowlist"`,
   or `"all"`. If enabled, a fresh, correctly addressed invitation may produce
   an *accept-invitation intent* when no trade/request is active and the player
   has inventory room. Duplicate invitations and repeat senders are throttled.
2. **Final confirmation:** `final_mode="off"` (default), or `"gift_only"`.
   This is deliberately narrower than arbitrary automatic trade acceptance.
   It generates a final-confirmation *intent* only for verified incoming gifts:
   no outgoing item units, at least one incoming item, all item IDs on the
   opt-in allowlist, enough free slots, matching identity, matching trade ID,
   and two identical immutable offer snapshots with a fresh recheck.

For example:

```python
from rotmg_next.auto_accept_policy import (
    AutoAcceptPolicy, AutoAcceptSettings, IncomingTradeInvitation,
    FinalOfferSnapshot,
)
from rotmg_next.inventory_policy import InventorySnapshot

policy = AutoAcceptPolicy(
    "account-1",
    AutoAcceptSettings(
        invitation_mode="allowlist",
        final_mode="gift_only",
        allowed_player_ids=frozenset({"friend-1"}),
        allowed_incoming_item_ids=frozenset({"dex_pot"}),
    ),
)
invitation = IncomingTradeInvitation(
    request_id="request-1",
    recipient_player_id="account-1",
    sender_player_id="friend-1",
    sender_name="Friend",
    observed_at=1.0,
)
decision = policy.consider_invitation(
    invitation, InventorySnapshot(capacity=8, occupied=7), now=1.2
)
assert decision.allowed
assert decision.intent.stage == "incoming_invitation"

# Simulated offers, not obtained from a real game client.
first = FinalOfferSnapshot(
    trade_id="trade-1", owner_player_id="account-1",
    counterparty_player_id="friend-1", revision=1,
    incoming_item_ids=("dex_pot",), outgoing_item_ids=(), observed_at=2.0
)
rechecked = FinalOfferSnapshot(
    trade_id="trade-1", owner_player_id="account-1",
    counterparty_player_id="friend-1", revision=1,
    incoming_item_ids=("dex_pot",), outgoing_item_ids=(), observed_at=2.1
)
final = policy.consider_final_offer(
    first, rechecked, InventorySnapshot(8, 7),
    now=2.2, active_trade_id="trade-1",
    active_counterparty_player_id="friend-1", trade_active=True
)
assert final.allowed
assert final.intent.stage == "final_gift"

# There is no function that actually transmits or accepts anything.
```

All event metadata is synthetic or caller-supplied. A real sender identity,
trade-state snapshot, or revision number cannot be validated by this package.
Even a matching recheck is **not a guarantee** that the live trade remains
unchanged; there is an unavoidable time-of-check/time-of-use problem unless
supported by an authorised atomic game API.

The policy is fail-closed but **not sufficient to authorise real trade
automation**, and its opt-in flags must not be wired to a game client without
written permission from the platform and separate implementation review.
DECA's current terms prohibit gameplay automation and scripts:
https://decagames.com/tos.html

Run tests:

```sh
python -m unittest discover -s tests -p 'test_rotmg_*.py' -v
```
