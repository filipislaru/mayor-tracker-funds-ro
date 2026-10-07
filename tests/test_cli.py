from __future__ import annotations

from pathlib import Path

import pytest
from mayortracker.cli import app
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def cli_env(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("MT_CONFIG", str(project_dir / "config" / "settings.yaml"))
    return project_dir


def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "doctor" in result.output
    assert "init-data" in result.output


def test_doctor_reports_set_and_missing_without_values(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONTACT_EMAIL", "TEST-SECRET-EMAIL@example.invalid")
    monkeypatch.setenv("LLM_API_KEY", "TEST-SECRET-KEY-123")
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    lines = {line.split()[0]: line.split()[1] for line in result.output.splitlines()
             if line.strip().startswith(("CONTACT_EMAIL", "LLM_"))}
    assert lines == {"CONTACT_EMAIL": "set", "LLM_PROVIDER": "missing", "LLM_API_KEY": "set"}
    assert "TEST-SECRET-EMAIL" not in result.output
    assert "TEST-SECRET-KEY-123" not in result.output
    assert "Python:" in result.output
    assert "uv.lock" in result.output


def test_doctor_reports_data_dirs(cli_env: Path) -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert result.output.count("missing  ") >= 5  # five data dirs, none created yet

    assert runner.invoke(app, ["init-data"]).exit_code == 0
    result = runner.invoke(app, ["doctor"])
    assert result.output.count("exists  ") == 5


def test_init_data_creates_folders_idempotently(cli_env: Path) -> None:
    first = runner.invoke(app, ["init-data"])
    assert first.exit_code == 0, first.output
    for rel in ("raw", "interim", "processed", "export", "cache/http"):
        assert (cli_env / "data" / rel).is_dir()
    assert first.output.count("created") == 5

    second = runner.invoke(app, ["init-data"])
    assert second.exit_code == 0
    assert "created" not in second.output
    assert second.output.count("exists") == 5
