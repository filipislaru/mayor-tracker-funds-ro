"""Shared test fixtures. All data here is synthetic (see AGENTS.md fixture rules)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

ENV_KEYS = ("CONTACT_EMAIL", "LLM_PROVIDER", "LLM_API_KEY", "MT_CONFIG")


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test without project env vars (restored/removed afterwards)."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def _block_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if any test tries to use the real network transport."""

    def _blocked(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        raise RuntimeError(f"Real network access attempted in tests: {request.url}")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _blocked)


SETTINGS_YAML = """\
project_name: TEST project
data_dir: data
pilot_county: null
http:
  min_seconds_between_requests: 1.0
  max_retries: 5
"""

ENV_EXAMPLE = """\
# TEST .env.example
CONTACT_EMAIL=
LLM_PROVIDER=
LLM_API_KEY=
"""


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """A temporary fake repo root with config/settings.yaml and .env.example."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.yaml").write_text(SETTINGS_YAML, encoding="utf-8")
    (tmp_path / ".env.example").write_text(ENV_EXAMPLE, encoding="utf-8")
    return tmp_path
