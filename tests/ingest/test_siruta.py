"""Tests for SIRUTA ingestion."""

from __future__ import annotations

from pathlib import Path

import httpx
from mayortracker.ingest.siruta import DOC_URL, SOURCE_ID, SOURCE_URL, ingest_siruta
from mayortracker.util.config import Settings
from mayortracker.util.http import PoliteClient


def test_ingest_siruta_mocked(tmp_path: Path) -> None:
    settings = Settings(
        project_name="TEST project",
        data_dir=tmp_path / "data",
        contact_email="test@example.com",
    )
    raw_csv = (
        b"SIRUTA;DENLOC;CODP;JUD;SIRSUP;TIP;NIV;MED;REGIUNE;FSJ;NUTS;LAU\n"
        b"900001;TEST ALBA;0;1;1;40;1;0;7;1;RO111;RO011\n"
    )
    raw_xml = b"<?xml version=\"1.0\"?><root><doc>TEST Legenda</doc></root>\n"

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("robots.txt"):
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if str(request.url) == SOURCE_URL:
            return httpx.Response(200, content=raw_csv, headers={"Content-Type": "text/csv"})
        if str(request.url) == DOC_URL:
            return httpx.Response(200, content=raw_xml, headers={"Content-Type": "text/xml"})
        return httpx.Response(404)

    client = PoliteClient(settings, transport=httpx.MockTransport(handle))
    entries = ingest_siruta(settings, client=client)

    assert len(entries) == 2
    csv_entry, doc_entry = entries

    assert csv_entry.filename == "siruta_s1_2026.csv"
    assert csv_entry.bytes == len(raw_csv)
    assert csv_entry.http_status == 200

    assert doc_entry.filename == "legenda-siruta.xml"
    assert doc_entry.bytes == len(raw_xml)
    assert doc_entry.http_status == 200

    raw_dir = tmp_path / "data" / "raw" / SOURCE_ID / csv_entry.retrieved_at[:10]
    csv_target = raw_dir / "siruta_s1_2026.csv"
    doc_target = raw_dir / "legenda-siruta.xml"

    assert csv_target.is_file()
    assert csv_target.read_bytes() == raw_csv
    assert doc_target.is_file()
    assert doc_target.read_bytes() == raw_xml
