"""Tests for budget execution ingestion."""

from __future__ import annotations

from pathlib import Path

import httpx
from mayortracker.ingest.budget_exec import BUDGET_EXEC_2024_URL, ingest_budget_exec
from mayortracker.util.config import Settings
from mayortracker.util.http import PoliteClient


def test_ingest_budget_exec_mocked(tmp_path: Path) -> None:
    settings = Settings(
        project_name="TEST project",
        data_dir=tmp_path / "data",
        contact_email="test@example.com",
    )
    fake_content = b"TEST EXCEL CONTENT"

    def handle(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if request.url.path.endswith("robots.txt"):
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if url_str == BUDGET_EXEC_2024_URL:
            return httpx.Response(
                200,
                content=fake_content,
                headers={"Content-Type": "application/octet-stream"},
            )
        return httpx.Response(404)

    client = PoliteClient(settings, transport=httpx.MockTransport(handle))
    entries = ingest_budget_exec(settings, client=client)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.filename == "situaia-veniturilor-i-cheltuielilor-2024.xlsx"
    assert entry.http_status == 200

    raw_dir = tmp_path / "data" / "raw" / "budget_exec" / entry.retrieved_at[:10]
    target_file = raw_dir / entry.filename
    assert target_file.is_file()
    assert target_file.read_bytes() == fake_content
