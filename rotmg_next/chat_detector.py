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
