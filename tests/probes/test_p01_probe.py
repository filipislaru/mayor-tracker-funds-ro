"""Unit tests for P01 probe notice parser and runner using synthetic fixtures."""

from __future__ import annotations

from mayortracker.probes.p01_probe import (
    SAMPLE_NOTICES,
    ProbeRunner,
    parse_ted_notice_xml,
)
from mayortracker.util.config import Settings


def test_sample_notices_composition() -> None:
    """Verify that sample notices contain 20 items: 10 standard and 10 eForms."""
    assert len(SAMPLE_NOTICES) == 20
    standard = [n for n in SAMPLE_NOTICES if n["format"] == "standard"]
    eforms = [n for n in SAMPLE_NOTICES if n["format"] == "eforms"]
    assert len(standard) == 10
    assert len(eforms) == 10

    # Ensure coverage of authority types
    for group in [standard, eforms]:
        types = {n["authority_type"] for n in group}
        assert "Comună" in types
        assert "Oraș" in types
        assert "Municipiu" in types
        assert "Consiliu Județean" in types


def test_parse_standard_form_synthetic_xml() -> None:
    """Verify parsing of synthetic standard form TED notice XML."""
    synthetic_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <TED_EXPORT>
        <LEFTI>
            <SUITABILITY>TEST Ofertantul va face dovada inregistrarii...</SUITABILITY>
            <TECHNICAL_PROFESSIONAL_INFO>
                TEST Experienta similara in lucrari de drumuri...
            </TECHNICAL_PROFESSIONAL_INFO>
            <TECHNICAL_PROFESSIONAL_MIN_LEVEL>
                TEST Minim 1 contract finalizat...
            </TECHNICAL_PROFESSIONAL_MIN_LEVEL>
        </LEFTI>
        <OBJECT_CONTRACT>
            <SHORT_DESCR>TEST Lucrari de modernizare</SHORT_DESCR>
        </OBJECT_CONTRACT>
        <COMPLEMENTARY_INFO>
            <URL_DOCUMENT>https://e-licitatie.ro/pub/notices/c-notice/v2/view/999999</URL_DOCUMENT>
        </COMPLEMENTARY_INFO>
    </TED_EXPORT>
    """

    meta = {
        "pub_number": "TEST-01-2021",
        "format": "standard",
        "authority_type": "Comună",
        "buyer_name": "TEST Comuna Exemplu",
        "contract_nature": "works",
        "year": 2021,
    }

    result = parse_ted_notice_xml(synthetic_xml, meta)
    assert result.pub_number == "TEST-01-2021"
    assert result.format == "standard"
    assert result.sicap_notice_id == "999999"
    assert "SUITABILITY" in result.criteria_fields
    assert "TECHNICAL_PROFESSIONAL_INFO" in result.criteria_fields
    assert result.total_criteria_chars > 0
    assert result.sample_excerpt is not None
    assert "TEST" in result.sample_excerpt


def test_parse_eforms_synthetic_xml() -> None:
    """Verify parsing of synthetic eForms TED notice XML."""
    synthetic_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <ContractNotice
        xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
        xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
        <cac:CallForTendersDocumentReference>
            <cac:Attachment>
                <cac:ExternalReference>
                    <cbc:URI>https://e-licitatie.ro/pub/notices/c-notice/v2/view/888888</cbc:URI>
                </cac:ExternalReference>
            </cac:Attachment>
        </cac:CallForTendersDocumentReference>
        <cac:TendererQualificationRequest>
            <cbc:Description>TEST Conditii de participare DUAE</cbc:Description>
        </cac:TendererQualificationRequest>
        <cac:SelectionCriteria>
            <cbc:ID>sui-act</cbc:ID>
            <cbc:Description>TEST Capacitatea tehnica si profesionala de executie</cbc:Description>
        </cac:SelectionCriteria>
        <cac:SubordinateAwardingCriterion>
            <cbc:Description>TEST Factor tehnic garantie 60 luni</cbc:Description>
        </cac:SubordinateAwardingCriterion>
    </ContractNotice>
    """

    meta = {
        "pub_number": "TEST-02-2024",
        "format": "eforms",
        "authority_type": "Municipiu",
        "buyer_name": "TEST Municipiul Exemplu",
        "contract_nature": "services",
        "year": 2024,
    }

    result = parse_ted_notice_xml(synthetic_xml, meta)
    assert result.pub_number == "TEST-02-2024"
    assert result.format == "eforms"
    assert result.sicap_notice_id == "888888"
    assert "SelectionCriteria_sui-act" in result.criteria_fields
    assert "AwardingCriterion_Technical" in result.criteria_fields
    assert result.total_criteria_chars > 0
    assert result.sample_excerpt is not None


def test_probe_runner_records_requests(tmp_path) -> None:
    """Verify ProbeRunner request counting functionality."""
    settings = Settings(
        project_name="mayor-tracker-ro",
        data_dir=tmp_path / "data",
        contact_email="test@example.com",
    )
    runner = ProbeRunner(settings)
    runner._record_request("ted.europa.eu")
    runner._record_request("ted.europa.eu")
    runner._record_request("e-licitatie.ro")

    assert runner.request_counts["ted.europa.eu"] == 2
    assert runner.request_counts["e-licitatie.ro"] == 1
