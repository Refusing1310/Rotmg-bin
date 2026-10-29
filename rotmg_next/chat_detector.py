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


# Offline-only giveaway matcher. A known item vocabulary is safer than
# interpreting arbitrary words following "free" as a tradable item.
from typing import Iterable

_DEFAULT_ITEM_ALIASES = frozenset({
    "pot", "pots", "potion", "potions", "stat pot", "stat pots",
    "stat potion", "stat potions", "life", "life pot", "life pots",
    "life potion", "life potions", "mana", "mana pot", "mana pots",
    "mana potion", "mana potions", "dex", "dexterity", "dex pots",
    "wis", "wisdom", "wis pots", "vit", "vitality", "vit pots",
    "def", "defense", "defence", "def pots", "att", "attack",
    "att pots", "spd", "speed", "spd pots", "hp", "mp",
    "item", "items", "gear", "equipment", "weapon", "weapons",
    "armor", "armour", "robe", "robes", "ring", "rings",
    "sword", "swords", "bow", "bows", "dagger", "daggers",
    "staff", "staves", "wand", "wands", "katana", "katanas",
    "tome", "tomes", "spell", "spells", "shield", "shields",
    "seal", "seals", "cloak", "cloaks", "quiver", "quivers",
    "helm", "helms", "skull", "skulls", "orb", "orbs",
    "trap", "traps", "prism", "prisms", "poison", "poisons",
    "star", "stars", "scepter", "scepters", "mace", "maces",
    "lute", "lutes", "ut", "uts", "tops", "top", "t12 weapons",
}) | frozenset(f"t{tier}" for tier in range(0, 16))

# Whole-message patterns prevent a third party's report from becoming an
# outgoing request to the reporter. Capture the claimed items, not names.
_CTA = r"(?:\s*[-—:|]\s*(?:trade|trd|whisper|pm|dm|msg)\s+[\w-]+)?(?:\s+(?:in|at)\s+(?:nexus|vault))?[.!]*"
_PREFIX = r"(?:(?:some|a|an|my|extra|spare|free|\d+)\s+)*"
_GIVEAWAY_PATTERNS = (
    re.compile(rf"^free\s+(?:(?:some|a|an|my|extra|spare|\d+)\s+)*(?P<item>.+?){_CTA}$", re.I),
    re.compile(
        rf"^(?:(?:giving\s+(?:away|out)|handing\s+out|"
        rf"i(?:'m| am)\s+giving\s+(?:away|out)|"
        rf"i\s+(?:want\s+to|will)\s+give\s+away))\s+"
        rf"{_PREFIX}(?P<item>.+?){_CTA}$",
        re.I,
    ),
    re.compile(rf"^i\s+have\s+(?:(?:some|extra|spare)\s+)?free\s+(?P<item>.+?){_CTA}$", re.I),
    re.compile(rf"^(?P<item>.+?)\s+for\s+free{_CTA}$", re.I),
    re.compile(r"^anyone\s+(?:wants?|needs?)\s+(?:some\s+)?free\s+(?P<item>.+?)\?$", re.I),
)
_ITEM_ALIAS_PATTERN = re.compile(r"[a-z0-9][a-z0-9 '-]{0,63}\Z")


def _normalise_item_aliases(additional_item_aliases: Iterable[str]) -> frozenset[str]:
    """Fail closed on misconfigured item names and pathological alias sets."""
    if isinstance(additional_item_aliases, (str, bytes)):
        raise ValueError("additional_item_aliases must be an iterable of item names")
    try:
        aliases = tuple(additional_item_aliases)
    except TypeError as exc:
        raise ValueError("additional_item_aliases must be iterable") from exc
    if len(aliases) > 128:
        raise ValueError("too many additional item aliases")
    normalised = set(_DEFAULT_ITEM_ALIASES)
    for alias in aliases:
        if not isinstance(alias, str):
            raise ValueError("item aliases must be strings")
        name = " ".join(alias.casefold().split())
        if not _ITEM_ALIAS_PATTERN.fullmatch(name):
            raise ValueError(f"invalid item alias: {alias!r}")
        normalised.add(name)
    return frozenset(normalised)


def is_free_item_offer(
    message: str, *, additional_item_aliases: Iterable[str] = ()
) -> bool:
    """Conservatively classify self-advertised item giveaways (offline only).

    Arbitrary 'free X' text is *not* trusted as a game item. Supply custom
    aliases for item names not included in the default ROTMG vocabulary.
    Results never authorise trade execution, settlement or payment.
    """
    aliases = _normalise_item_aliases(additional_item_aliases)
    if not isinstance(message, str) or not message.strip():
        return False
    message = " ".join(message.split())
    for pattern in _GIVEAWAY_PATTERNS:
        match = pattern.fullmatch(message)
        if match and " ".join(match.group("item").casefold().split()) in aliases:
            return True
    return False
