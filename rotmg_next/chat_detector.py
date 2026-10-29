"""Conservative recognition of free-potion announcements in *supplied* chat events."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ChatEvent:
    """A chat event provided by a trusted caller; no sender is parsed from text."""

    event_id: str
    sender_id: str
    sender_name: str
    text: str
    channel: str = "public"

    def __post_init__(self) -> None:
        for name in ("event_id", "sender_id", "sender_name"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.text, str) or not isinstance(self.channel, str):
            raise ValueError("text and channel must be strings")


_POT = r"(?:stat\s+)?(?:pots?|potions?)"
_OFFER = re.compile(
    rf"(?:\bfree\s+{_POT}\b"
    rf"|\b{_POT}\s+(?:for\s+)?free\b"
    rf"|\b(?:giving\s+(?:away|out)|handing\s+out)\s+"
    rf"(?:(?:my|some|free)\s+)*{_POT}\b)",
    flags=re.IGNORECASE,
)
_REQUEST = re.compile(
    r"\b(?:anyone\s+(?:got|have|has|giving|selling|offering)"
    r"|who\s+(?:has|got|is\s+giving)"
    r"|(?:can|could)\s+(?:someone|anyone|i)\s+(?:give|have|get|trade)"
    r"|looking\s+for|i\s+(?:need|want)"
    r"|\A\s*(?:need|want|lf|buying)\s+free)\b",
    flags=re.IGNORECASE,
)
_DENIAL = re.compile(
    rf"\b(?:no|not|never|don't|dont|do\s+not|without)\s+"
    rf"(?:\w+\s+){{0,4}}(?:free\s+)?{_POT}\b"
    r"|\bselling\s+free\s+(?:stat\s+)?(?:pots?|potions?)\b",
    flags=re.IGNORECASE,
)
_OFFER_QUESTION = re.compile(r"\b(?:anyone|who)\s+(?:wants?|needs?)\b", re.IGNORECASE)


def is_free_potion_offer(message: str) -> bool:
    """Recognise likely offers, intentionally preferring false negatives to spam.

    This is not a semantic classifier: indirect offers, jokes and sarcasm can
    still be ambiguous. Never use this result to accept or settle a trade.
    """
    if not isinstance(message, str) or not message.strip():
        return False
    if not _OFFER.search(message):
        return False
    if _REQUEST.search(message) or _DENIAL.search(message):
        return False
    if "?" in message and not _OFFER_QUESTION.search(message):
        return False
    return True


# Broader giveaway announcements (issue #12). These are heuristics over supplied
# chat text, not an interface to the game. Sender identity always comes from
# trusted ChatEvent metadata, never from this content.
_GENERIC_GIVEAWAY = re.compile(
    r"\bfree\s+(?:(?:some|any|a|an|my|extra|spare|\d+)\s+)*"
    r"(?P<free_item>[a-z][\w'-]*)\b"
    r"|\b(?:giving\s+(?:away|out)|handing\s+out)\s+"
    r"(?:(?:some|any|a|an|my|extra|spare|free|\d+)\s+)*"
    r"(?P<given_item>[a-z][\w'-]*)\b"
    r"|\b(?P<for_free_item>[a-z][\w'-]*)\s+for\s+free\b",
    flags=re.IGNORECASE,
)
# Common non-item uses of "free"; deliberately keep the list conservative.
_NON_ITEM_WORDS = frozenset({
    "to", "for", "of", "with", "from", "if", "when", "as", "the",
    "me", "you", "us", "them", "him", "her", "myself", "yourself",
    "now", "today", "tomorrow", "later", "time", "times",
    "space", "spaces", "slot", "slots", "room", "rooms", "spot", "spots",
    "game", "games", "play", "account", "accounts", "trial", "version",
    "server", "servers", "chat", "guild", "discord", "entry", "access",
    "help", "run", "runs", "carry", "carrying", "trade", "trades",
    "is", "are", "was", "were", "be", "being", "been",
})
_GENERIC_DENIAL = re.compile(
    r"\b(?:not|no|never|don't|dont|do\s+not|without|can't|cannot|"
    r"won't|wont|isn't|wasn't)\s+(?:[\w'-]+\s+){0,4}"
    r"(?:free|giving\s+(?:away|out)|handing\s+out)\b",
    flags=re.IGNORECASE,
)
_SALE = re.compile(r"\b(?:selling|buying|wts|wtb|lf)\b", re.IGNORECASE)
_THIRD_PARTY = re.compile(
    r"\b(?:someone|somebody|anyone|they|he|she|my\s+friend|that\s+guy)"
    r"\s+(?:(?:is|was|are|were)\s+)?"
    r"(?:giving\s+(?:away|out)|handing\s+out)\b",
    re.IGNORECASE,
)
_PAST_OR_THANKS = re.compile(
    r"^\s*(?:thanks?|thank\s+you|ty|thx|"
    r"i\s+(?:got|received|found|saw|heard)|"
    r"we\s+(?:got|received|found|saw|heard)|"
    r"just\s+(?:got|received))\b",
    flags=re.IGNORECASE,
)


def is_free_item_offer(message: str) -> bool:
    """Recognise probable item giveaways, including 'free <item>' phrases.

    A conservative text heuristic; arbitrary item names may be falsely
    recognised. Its output is suitable only for offline trade-request intents,
    never for an automated trade, payment or settlement.
    """
    if not isinstance(message, str) or not message.strip():
        return False
    if (_REQUEST.search(message) or _GENERIC_DENIAL.search(message)
            or _SALE.search(message) or _THIRD_PARTY.search(message)
            or _PAST_OR_THANKS.search(message)):
        return False
    if "?" in message and not _OFFER_QUESTION.search(message):
        return False
    for candidate in _GENERIC_GIVEAWAY.finditer(message):
        word = next((w for w in candidate.groupdict().values() if w), "").lower()
        if word and word not in _NON_ITEM_WORDS:
            return True
    return is_free_potion_offer(message)
