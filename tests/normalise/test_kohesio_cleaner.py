"""Tests for Kohesio-specific name cleaning and classification."""

from __future__ import annotations

import datetime as dt

from mayortracker.normalise.kohesio_cleaner import (
    clean_kohesio_beneficiary_name,
    is_county_council,
    is_local_authority,
    is_other_body,
    parse_kohesio_date,
)


def test_clean_kohesio_beneficiary_name_prefixes() -> None:
    cases = [
        ("PRIMĂRIA COMUNA SCHITU GOLESTI", "SCHITU GOLESTI"),
        ("PRIMARIA COMUNEI VORTA", "VORTA"),
        ("UAT ORAŞUL DĂRMĂNEŞTI", "DĂRMĂNEȘTI"),
        ("U.A.T. MUNICIPIUL MEDGIDIA", "MEDGIDIA"),
        ("UNITATEA ADMINISTRATIV-TERITORIALĂ MUNICIPIUL CALARASI", "CALARASI"),
        (
            "Unitatea Administrativ Teritoriala Municipiului Râmnicu Vâlcea",
            "Râmnicu Vâlcea",
        ),
        ("UNITATE ADMINISTRATIV TERITORIALA - COMUNA PALTINIS", "PALTINIS"),
        ("COMUNA OCNA SUGATAG/PRIMARIA OCNA SUGATAG", "OCNA SUGATAG"),
        ("COMUNA BELCIUGATELE/Primarie", "BELCIUGATELE"),
        ("CONSILIUL LOCAL AL MUNICIPIULUI CRAIOVA", "CRAIOVA"),
        ("UAT COMUNA VALEA MARE PRIN PRIMAR", "VALEA MARE"),
        ("SECTORUL 1 AL MUNICIPIULUI BUCURESTI", "SECTORUL 1"),
        ("PRIMARIA SECTORUL 3", "SECTORUL 3"),
    ]
    for raw, expected in cases:
        assert clean_kohesio_beneficiary_name(raw) == expected


def test_classify_beneficiary_types() -> None:
    # County councils
    assert is_county_council("CONSILIUL JUDETEAN CLUJ")
    assert is_county_council("JUDETUL ILFOV")
    assert is_county_council("UAT JUDETUL TULCEA")
    assert not is_local_authority("CONSILIUL JUDETEAN CLUJ")

    # Other bodies
    assert is_other_body("SPITALUL ORASENESC BECLEAN")
    assert is_other_body("LICEUL TEORETIC TEST")
    assert is_other_body("FLEXON-ALL SRL")
    assert is_other_body("COMPANIA DE APA SOMES SA")
    assert is_other_body("ASOCIATIA DE DEZVOLTARE INTERCOMUNITARA ALBA IULIA")
    assert not is_local_authority("SPITALUL ORASENESC BECLEAN")
    assert not is_local_authority("FLEXON-ALL SRL")

    # Local authorities
    assert is_local_authority("COMUNA VORTA")
    assert is_local_authority("ORAS TITU")
    assert is_local_authority("MUNICIPIUL SIBIU")
    assert is_local_authority("PRIMARIA COMUNA SCHITU GOLESTI")
    assert is_local_authority("SECTORUL 1 AL MUNICIPIULUI BUCURESTI")


def test_parse_kohesio_date_strict() -> None:
    assert parse_kohesio_date("01/08/2018") == dt.date(2018, 8, 1)
    assert parse_kohesio_date("29/11/2019") == dt.date(2019, 11, 29)
    assert parse_kohesio_date("31/12/2026") == dt.date(2026, 12, 31)

    # Invalid and null formats
    assert parse_kohesio_date(None) is None
    assert parse_kohesio_date("") is None
    assert parse_kohesio_date("   ") is None
    assert parse_kohesio_date("NaN") is None
    assert parse_kohesio_date("2018-08-01") is None  # ISO format rejected by strict DD/MM/YYYY
    assert parse_kohesio_date("32/01/2020") is None  # Invalid day
    assert parse_kohesio_date("invalid") is None
