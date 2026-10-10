"""Tests for SIRUTA ingestion."""

from __future__ import annotations

from pathlib import Path

import httpx
from mayortracker.ingest.siruta import SOURCE_ID, SOURCE_URL, ingest_siruta
from mayortracker.util.config import Settings
from mayortracker.util.http import PoliteClient


def test_ingest_siruta_mocked(tmp_path: Path) -> None:
    settings = Settings(
        project_name="TEST project",
        data_dir=tmp_path / "data",
        contact_email="test@example.com",
    )
    raw_csv = (
        b"siruta,niv,sirsup,tip,denloc,ult,med,jud,prefix,regiune,codp,fsj,fs2,fs3,fsl,fictiv\n"
        b"900001,1,1,40,\"TEST ALBA\",0,0,1,0,7,0,1,\"\",\"\",1,0\n"
    )

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("robots.txt"):
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if str(request.url) == SOURCE_URL:
            return httpx.Response(200, content=raw_csv, headers={"Content-Type": "text/csv"})
        return httpx.Response(404)

    client = PoliteClient(settings, transport=httpx.MockTransport(handle))
    entry = ingest_siruta(settings, client=client)

    assert entry.filename == "siruta.csv"
    assert entry.bytes == len(raw_csv)
    assert entry.http_status == 200

    target = tmp_path / "data" / "raw" / SOURCE_ID / entry.retrieved_at[:10] / "siruta.csv"
    assert target.is_file()
    assert target.read_bytes() == raw_csv
