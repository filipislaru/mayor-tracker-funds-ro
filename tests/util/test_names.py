"""Tests for the normalise_name helper."""

from __future__ import annotations

import pytest
from mayortracker.util.names import normalise_name


@pytest.mark.parametrize(
    ("input_text", "expected_display", "expected_key"),
    [
        # Cedilla to comma-below conversion and capitalisation preservation
        ("COMUNA ŞTEFAN CEL MARE", "COMUNA ȘTEFAN CEL MARE", "stefan cel mare"),
        ("Oraşul Odorheiu Secuiesc", "Orașul Odorheiu Secuiesc", "odorheiu secuiesc"),
        ("judeţul braşov", "județul brașov", "brasov"),
        ("MUNICIPIUL CLUJ-NAPOCA", "MUNICIPIUL CLUJ-NAPOCA", "cluj napoca"),
        # Orașu Nou must keep 'orasu' because 'orasu' is not a prefix
        ("Orașu Nou", "Orașu Nou", "orasu nou"),
        ("ORAŞU NOU", "ORAȘU NOU", "orasu nou"),
        # Prefix removal only at the start and only if text remains
        ("Comuna", "Comuna", "comuna"),
        ("Oraș", "Oraș", "oras"),
        ("Sector", "Sector", "sector"),
        ("Județul", "Județul", "judetul"),
        ("orașul", "orașul", "orasul"),
        # Prefix in the middle must NOT be stripped
        ("Satul din Oraș", "Satul din Oraș", "satul din oras"),
        # Punctuation and whitespace handling
        ("  com.   Bistrița - Năsăud  ", "com. Bistrița - Năsăud", "bistrita nasaud"),
        ("Câmpulung la Tisa", "Câmpulung la Tisa", "campulung la tisa"),
        ("București Sectorul 1", "București Sectorul 1", "bucuresti sectorul 1"),
        # Empty string
        ("", "", ""),
    ],
)
def test_normalise_name(input_text: str, expected_display: str, expected_key: str) -> None:
    res = normalise_name(input_text)
    assert res.display == expected_display
    assert res.key == expected_key
