"""Tests for LAU boundaries ingestion."""

from __future__ import annotations

from pathlib import Path

import httpx
from mayortracker.ingest.boundaries import SOURCE_ID, SOURCE_URL, ingest_lau_boundaries
from mayortracker.util.config import Settings
from mayortracker.util.http import PoliteClient


def test_ingest_lau_boundaries_mocked(tmp_path: Path) -> None:
    settings = Settings(
        project_name="TEST project",
        data_dir=tmp_path / "data",
        contact_email="test@example.com",
    )
    raw_zip = b"PK\x05\x06" + b"\x00" * 18  # Empty zip bytes

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("robots.txt"):
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if str(request.url) == SOURCE_URL:
            return httpx.Response(
                200, content=raw_zip, headers={"Content-Type": "application/zip"}
            )
        return httpx.Response(404)

    client = PoliteClient(settings, transport=httpx.MockTransport(handle))
    entry = ingest_lau_boundaries(settings, client=client)

    assert entry.filename == "ref-lau-2024-01m.shp.zip"
    assert entry.bytes == len(raw_zip)
    assert entry.http_status == 200

    target = (
        tmp_path / "data" / "raw" / SOURCE_ID / entry.retrieved_at[:10] / "ref-lau-2024-01m.shp.zip"
    )
    assert target.is_file()
    assert target.read_bytes() == raw_zip
