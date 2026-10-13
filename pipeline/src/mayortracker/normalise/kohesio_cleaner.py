"""Kohesio-specific name cleaning and classification helpers."""

from __future__ import annotations

import datetime as dt
import re

_PREFIX_PATTERNS = [
    r"^\s*unitate[aă]?\s+administrativ[-\s]+teritorial[aă]\b\s*(?:-\s*)?",
    r"^\s*(?:u\s*\.\s*a\s*\.\s*t\s*\.|uat\b)\s*(?:-\s*)?",
    r"^\s*prim[aă]ri(?:ei|[aei])\b\s*",
    r"^\s*consiliul\s+local\s+(?:al\s+)?",
    r"^\s*comun(?:ei|[aei])\b\s*",
    r"^\s*ora[sș](?:ului|ul)?\b\s*",
    r"^\s*municipi(?:ului|ul)?\b\s*",
    r"^\s*al\s+municipiului\b\s*",
]

_SUFFIX_PATTERNS = [
    r"\s+al\s+municipiului\s+bucure[sș]ti.*$",
    r"\s+a\s+municipiului\s+bucure[sș]ti.*$",
    r"\s+prin\s+primar.*$",
]

_OTHER_BODY_PATTERNS = [
    r"\bspital",
    r"\bliceul\b",
    r"\bcolegiul\b",
    r"\b[sș]coala\b",
    r"\buniversitatea\b",
    r"\bdirec[tț]ia\b",
    r"\bserviciul\b",
    r"\bagen[tț]ia\b",
    r"\basocia[tț]ia\b",
    r"\borganismul\b",
    r"\bcompania\b",
    r"\bsocietatea\b",
    r"\bregia\b",
    r"\bs\.?r\.?l\.?\b",
    r"\bs\.?a\.?\b",
    r"\bs\.?c\.?\b",
    r"\bong\b",
    r"\bfunda[tț]ia\b",
    r"\bparohia\b",
    r"\bepiscopia\b",
    r"\bmitropolia\b",
    r"\bmanastirea\b",
    r"\bmănăstirea\b",
    r"\bcamera\s+de\s+comer[tț]\b",
    r"\binspectoratul\b",
    r"\bclubul\s+sportiv\b",
]

_LOCAL_AUTHORITY_PATTERN = re.compile(
    r"\b(?:prim[aă]ri[aei]?|comun[aei]?|ora[sș](?:ul|ului)?|municipi(?:ul|ului)?|sector(?:ul)?|u\.?a\.?t\.?)\b",
    re.IGNORECASE,
)


def clean_kohesio_beneficiary_name(raw: str) -> str:
    """Clean Romanian beneficiary names specifically for Kohesio without altering shared helpers.

    Strips prefixes such as 'PRIMĂRIA', 'UAT', 'UNITATEA ADMINISTRATIV-TERITORIALĂ',
    and suffixes such as 'PRIN PRIMAR', 'AL MUNICIPIULUI BUCUREȘTI', and trailing / sections.
    """
    if not raw:
        return ""
    # Normalise cedillas to comma-below
    s = raw.replace("ş", "ș").replace("Ş", "Ș").replace("ţ", "ț").replace("Ţ", "Ț")
    # Take first part before slash /
    s = s.split("/")[0].strip()

    # Strip suffixes
    for suf in _SUFFIX_PATTERNS:
        s = re.sub(suf, "", s, flags=re.IGNORECASE).strip()

    # Repeatedly strip prefixes while any matches
    changed = True
    while changed:
        changed = False
        for p in _PREFIX_PATTERNS:
            m = re.match(p, s, flags=re.IGNORECASE)
            if m and len(s[m.end() :].strip()) > 0:
                s = s[m.end() :].strip()
                changed = True
                break

    return s


def is_county_council(name: str) -> bool:
    """Check if the entity is a County Council (Consiliul Județean / Județul)."""
    if not name:
        return False
    n = name.lower().replace("ş", "ș").replace("ţ", "ț")
    return bool(
        re.search(
            r"consiliul\s+jude[tț]ean|jude[tț]ul\s+[a-z]|u\.?a\.?t\.?\s+jude[tț]ul",
            n,
        )
    )


def is_other_body(name: str) -> bool:
    """Check if the entity is a commercial, educational, religious, or non-governmental body."""
    if not name:
        return False
    n = name.lower().replace("ş", "ș").replace("ţ", "ț")
    return any(bool(re.search(p, n)) for p in _OTHER_BODY_PATTERNS)


def is_local_authority(name: str) -> bool:
    """Check if the entity represents a Romanian local public administrative authority."""
    if not name:
        return False
    if is_county_council(name) or is_other_body(name):
        return False
    return bool(_LOCAL_AUTHORITY_PATTERN.search(name))


def parse_kohesio_date(raw: str | None) -> dt.date | None:
    """Strictly parse DD/MM/YYYY date strings; returns None for empty or invalid dates."""
    if not raw or not isinstance(raw, str):
        return None
    val = raw.strip()
    if not val or val.lower() == "nan":
        return None
    try:
        return dt.datetime.strptime(val, "%d/%m/%Y").date()
    except (ValueError, TypeError):
        return None
