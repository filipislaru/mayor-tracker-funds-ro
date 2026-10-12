"""Tests for manual file registration (register-file command)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from mayortracker.cli import app
from mayortracker.ingest.register import register_file
from mayortracker.normalise.uat import find_latest_raw_source
from mayortracker.util.config import Settings
from typer.testing import CliRunner

runner = CliRunner()


def test_register_file_success(tmp_path: Path) -> None:
    settings = Settings(
        project_name="TEST project",
        data_dir=tmp_path / "data",
        contact_email="test@example.com",
    )
    src_file = tmp_path / "TEST_siruta.csv"
    content = b"siruta,niv,denloc\n900001,1,TEST Jude\xc5\xa3\n"
    src_file.write_bytes(content)

    frozen_time = datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC)
    entry = register_file(
        src_file,
        source_id="siruta",
        source_url="https://data.gov.ro/dataset/siruta",
        settings=settings,
        now=lambda: frozen_time,
    )

    expected_folder = tmp_path / "data" / "raw" / "siruta" / "2026-10-10"
    target = expected_folder / "TEST_siruta.csv"
    assert target.is_file()
    assert target.read_bytes() == content

    assert entry.filename == "TEST_siruta.csv"
    assert entry.size == len(content)
    assert entry.bytes == len(content)
    assert entry.sha256 == hashlib.sha256(content).hexdigest()
    assert entry.retrieval_method == "manual"
    assert entry.retrieved_by == "user"

    manifest_path = expected_folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest) == 1
    assert manifest[0] == {
        "url": "https://data.gov.ro/dataset/siruta",
        "filename": "TEST_siruta.csv",
        "retrieved_at": "2026-10-10T12:00:00Z",
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
        "bytes": len(content),
        "retrieval_method": "manual",
        "retrieved_by": "user",
    }


def test_register_file_refuses_to_overwrite(tmp_path: Path) -> None:
    settings = Settings(
        project_name="TEST project",
        data_dir=tmp_path / "data",
        contact_email="test@example.com",
    )
    src_file = tmp_path / "TEST_data.csv"
    src_file.write_bytes(b"TEST content 1")

    frozen_time = datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC)
    register_file(
        src_file,
        source_id="siruta",
        source_url="https://data.gov.ro/dataset/siruta",
        settings=settings,
        now=lambda: frozen_time,
    )

    # Attempt to overwrite must raise FileExistsError
    with pytest.raises(FileExistsError, match="Raw files are immutable"):
        register_file(
            src_file,
            source_id="siruta",
            source_url="https://data.gov.ro/dataset/siruta",
            settings=settings,
            now=lambda: frozen_time,
        )


def test_register_file_validations(tmp_path: Path) -> None:
    settings = Settings(
        project_name="TEST project",
        data_dir=tmp_path / "data",
        contact_email="test@example.com",
    )
    non_existent = tmp_path / "does_not_exist.csv"

    with pytest.raises(FileNotFoundError):
        register_file(
            non_existent,
            source_id="siruta",
            source_url="https://example.com",
            settings=settings,
        )

    src_file = tmp_path / "test.csv"
    src_file.write_bytes(b"content")

    with pytest.raises(ValueError, match="Invalid source_id"):
        register_file(
            src_file,
            source_id="invalid/id",
            source_url="https://example.com",
            settings=settings,
        )

    with pytest.raises(ValueError, match="source_url must not be empty"):
        register_file(
            src_file,
            source_id="siruta",
            source_url="",
            settings=settings,
        )


def test_normalise_uat_reads_registered_siruta(tmp_path: Path) -> None:
    """Verify that find_latest_raw_source in normalise.uat successfully reads registered file."""
    settings = Settings(
        project_name="TEST project",
        data_dir=tmp_path / "data",
        contact_email="test@example.com",
    )
    src_file = tmp_path / "siruta.csv"
    content = b"siruta,niv,denloc\n900001,1,TEST Jude\xc5\xa3\n"
    src_file.write_bytes(content)

    register_file(
        src_file,
        source_id="siruta",
        source_url="https://data.gov.ro/dataset/siruta",
        settings=settings,
    )

    raw_info = find_latest_raw_source(settings.data_dir / "raw", "siruta", "*.csv")
    assert raw_info.file_path.name == "siruta.csv"
    assert raw_info.url == "https://data.gov.ro/dataset/siruta"
    assert raw_info.sha256 == hashlib.sha256(content).hexdigest()
    assert raw_info.file_path.read_bytes() == content


def test_cli_register_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_settings = Settings(
        project_name="TEST project",
        data_dir=tmp_path / "data",
        contact_email="test@example.com",
    )
    monkeypatch.setattr("mayortracker.cli.load_settings", lambda: fake_settings)

    src_file = tmp_path / "TEST_manual.csv"
    src_file.write_bytes(b"TEST manual data")

    result = runner.invoke(
        app,
        [
            "ingest",
            "register-file",
            str(src_file),
            "--source-id",
            "siruta",
            "--source-url",
            "https://data.gov.ro/dataset/siruta",
        ],
    )
    assert result.exit_code == 0
    assert "Registered TEST_manual.csv" in result.output
    assert "under data/raw/siruta/" in result.output
