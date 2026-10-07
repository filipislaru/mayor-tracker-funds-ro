from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from mayortracker.util.config import find_repo_root, load_settings
from pydantic import ValidationError


def test_loads_temporary_yaml(project_dir: Path) -> None:
    settings = load_settings(project_dir / "config" / "settings.yaml")
    assert settings.project_name == "TEST project"
    assert settings.pilot_county is None
    assert settings.http.min_seconds_between_requests == 1.0
    assert settings.http.max_retries == 5
    assert settings.data_dir == (project_dir / "data").resolve()
    assert settings.contact_email is None


def test_data_dirs(project_dir: Path) -> None:
    settings = load_settings(project_dir / "config" / "settings.yaml")
    dirs = settings.data_dirs()
    base = (project_dir / "data").resolve()
    assert dirs == {
        "raw": base / "raw",
        "interim": base / "interim",
        "processed": base / "processed",
        "export": base / "export",
        "cache_http": base / "cache" / "http",
    }


def test_defaults_when_optional_keys_missing(tmp_path: Path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text("project_name: TEST minimal\n", encoding="utf-8")
    settings = load_settings(path)
    assert settings.data_dir == (tmp_path.parent / "data").resolve()
    assert settings.http.min_seconds_between_requests == 1.0
    assert settings.http.max_retries == 5


def test_absolute_data_dir_kept(tmp_path: Path) -> None:
    path = tmp_path / "settings.yaml"
    target = tmp_path / "elsewhere"
    path.write_text(f"project_name: TEST\ndata_dir: {target}\n", encoding="utf-8")
    assert load_settings(path).data_dir == target


def test_unknown_key_rejected(tmp_path: Path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text("project_name: TEST\nhtp: {}\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_settings(path)


def test_rate_limit_cannot_be_below_one_second(tmp_path: Path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text(
        "project_name: TEST\nhttp: {min_seconds_between_requests: 0.5}\n", encoding="utf-8"
    )
    with pytest.raises(ValidationError):
        load_settings(path)


def test_contact_email_from_env_file(project_dir: Path) -> None:
    env_file = project_dir / ".env"
    env_file.write_text("CONTACT_EMAIL=TEST@example.invalid\n", encoding="utf-8")
    settings = load_settings(project_dir / "config" / "settings.yaml")  # default .env lookup
    assert settings.contact_email == "TEST@example.invalid"


def test_explicit_env_file_does_not_override_environment(
    project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = project_dir / "other.env"
    env_file.write_text("CONTACT_EMAIL=TEST-from-file@example.invalid\n", encoding="utf-8")
    monkeypatch.setenv("CONTACT_EMAIL", "TEST-from-env@example.invalid")
    settings = load_settings(project_dir / "config" / "settings.yaml", env_file=env_file)
    assert settings.contact_email == "TEST-from-env@example.invalid"


def test_mt_config_env_var(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MT_CONFIG", str(project_dir / "config" / "settings.yaml"))
    assert load_settings().project_name == "TEST project"


def test_repository_settings_file_matches_brief() -> None:
    path = find_repo_root(Path(__file__).parent) / "config" / "settings.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert raw["data_dir"] == "data"
    assert raw["pilot_county"] is None
    assert raw["http"] == {"min_seconds_between_requests": 1.0, "max_retries": 5}
    assert raw["project_name"]
