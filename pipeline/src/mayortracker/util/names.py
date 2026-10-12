"""Name normalisation utilities for Romanian administrative units and localities."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Administrative prefixes (in ASCII-folded lowercase).
# Matched only at the very start of a name, and stripped only if text remains.
ADMIN_PREFIXES: frozenset[str] = frozenset(
    {
        "comuna",
        "com",
        "orasul",
        "oras",
        "municipiul",
        "municipiu",
        "mun",
        "judetul",
        "judet",
        "jud",
        "sectorul",
        "sector",
    }
)

_CEDILLA_MAP = str.maketrans(
    {
        "ş": "ș",
        "Ş": "Ș",
        "ţ": "ț",
        "Ţ": "Ț",
    }
)


@dataclass(frozen=True, slots=True)
class NameNormalised:
    """A pair of display-ready name and matching key."""

    display: str
    key: str


def normalise_name(text: str) -> NameNormalised:
    """Normalise Romanian names for display and search keys.

    - Display form:
      - Cedilla characters (ş/ţ/Ş/Ţ) converted to comma-below (ș/ț/Ș/Ț).
      - Unicode NFC normalised.
      - Source capitalisation preserved (not title-cased).
      - Leading, trailing, and redundant internal whitespace trimmed.
    - Matching key:
      - Lowercase.
      - ASCII-folded (diacritics removed).
      - Non-alphanumeric punctuation replaced with space.
      - Administrative prefixes removed only at the start of the name, and only if text remains.
      - Spaces collapsed and trimmed.
    """
    if not text:
        return NameNormalised(display="", key="")

    # 1. Display form
    display = text.translate(_CEDILLA_MAP)
    display = unicodedata.normalize("NFC", display)
    display = " ".join(display.split())

    # 2. Matching key
    # Lowercase & ASCII-fold
    folded = "".join(
        c for c in unicodedata.normalize("NFD", display.lower())
        if unicodedata.category(c) != "Mn"
    )
    # Replace non-alphanumeric with spaces
    cleaned = re.sub(r"[^a-z0-9\s]", " ", folded)
    tokens = cleaned.split()

    if tokens and tokens[0] in ADMIN_PREFIXES and len(tokens) > 1:
        tokens = tokens[1:]

    key = " ".join(tokens)
    return NameNormalised(display=display, key=key)
