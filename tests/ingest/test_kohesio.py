"""Tests for Kohesio ingestion."""

from __future__ import annotations

from pathlib import Path

import httpx
from mayortracker.ingest.kohesio import (
    BENEFICIARIES_URL,
    NUTS_URL,
    PROJECTS_2014_2020_URL,
    PROJECTS_2021_2027_URL,
    SOURCE_ID,
    ingest_kohesio,
)
from mayortracker.util.config import Settings
from mayortracker.util.http import PoliteClient


def test_ingest_kohesio_mocked(tmp_path: Path) -> None:
    settings = Settings(
        project_name="TEST project",
        data_dir=tmp_path / "data",
        contact_email="test@example.com",
    )
    raw_p14_20 = b"project_id,title,fund\nTEST1,TEST Project 1,ERDF\n"
    raw_p21_27 = b"project_id,title,fund\nTEST2,TEST Project 2,CF\n"
    raw_bene = b"beneficiary_id,name\nTESTB1,TEST Beneficiary 1\n"
    raw_nuts = b"nuts3,nuts3Label,nuts3code\nTESTN1,TEST County,RO111\n"

    def handle(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if request.url.path.endswith("robots.txt"):
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if url_str == PROJECTS_2014_2020_URL:
            return httpx.Response(200, content=raw_p14_20, headers={"Content-Type": "text/csv"})
        if url_str == PROJECTS_2021_2027_URL:
            return httpx.Response(200, content=raw_p21_27, headers={"Content-Type": "text/csv"})
        if url_str == BENEFICIARIES_URL:
            return httpx.Response(200, content=raw_bene, headers={"Content-Type": "text/csv"})
        if url_str == NUTS_URL:
            return httpx.Response(200, content=raw_nuts, headers={"Content-Type": "text/csv"})
        return httpx.Response(404)

    client = PoliteClient(settings, transport=httpx.MockTransport(handle))
    entries = ingest_kohesio(settings, client=client)

    assert len(entries) == 4
    filenames = [e.filename for e in entries]
    assert filenames == [
        "RO-pp14-20-latest.csv",
        "RO-pp21-27-latest.csv",
        "RO-beneficiaries-latest.csv",
        "RO-nuts-latest.csv",
    ]

    for entry in entries:
        assert entry.http_status == 200
        raw_dir = tmp_path / "data" / "raw" / SOURCE_ID / entry.retrieved_at[:10]
        target = raw_dir / entry.filename
        assert target.is_file()
        assert target.stat().st_size == entry.bytes
