"""Configuration loading: ``config/settings.yaml`` plus environment variables from ``.env``.

Secrets (for example ``CONTACT_EMAIL``) are read from the environment only, never from YAML.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

CONFIG_ENV_VAR = "MT_CONFIG"
DEFAULT_CONFIG_RELPATH = Path("config") / "settings.yaml"

# Data sub-directories, relative to ``data_dir``.
DATA_SUBDIRS: dict[str, Path] = {
    "raw": Path("raw"),
    "interim": Path("interim"),
    "processed": Path("processed"),
    "export": Path("export"),
    "cache_http": Path("cache") / "http",
}


class HttpSettings(BaseModel):
    """Politeness settings for the shared HTTP helper."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    min_seconds_between_requests: float = Field(default=1.0, ge=1.0)
    max_retries: int = Field(default=5, ge=1, le=5)


class Settings(BaseModel):
    """Validated project settings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_name: str
    data_dir: Path = Path("data")
    pilot_county: str | None = None
    http: HttpSettings = HttpSettings()

    # Not read from YAML; filled from the environment by ``load_settings``.
    contact_email: str | None = Field(default=None, exclude=True, repr=False)
    # File the settings were loaded from (informational).
    config_path: Path | None = Field(default=None, exclude=True)

    def data_dirs(self) -> dict[str, Path]:
        """Return the absolute data sub-directories keyed by short name."""
        return {name: self.data_dir / rel for name, rel in DATA_SUBDIRS.items()}


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from ``start`` (default: cwd) to the folder containing ``pyproject.toml``."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise FileNotFoundError(f"No pyproject.toml found in {current} or its parents")


def resolve_config_path(path: Path | None = None) -> Path:
    """Explicit path, then ``$MT_CONFIG``, then ``<repo_root>/config/settings.yaml``."""
    if path is not None:
        return Path(path)
    env_value = os.environ.get(CONFIG_ENV_VAR)
    if env_value:
        return Path(env_value)
    return find_repo_root() / DEFAULT_CONFIG_RELPATH


def load_settings(path: Path | None = None, env_file: Path | None = None) -> Settings:
    """Load settings from YAML and environment variables.

    ``.env`` values never override variables already set in the environment. A relative
    ``data_dir`` is resolved against the repository root, taken to be the parent of the
    config file's directory, so results do not depend on the working directory.
    """
    config_path = resolve_config_path(path).resolve()
    if env_file is not None:
        load_dotenv(env_file, override=False)
    else:
        default_env = config_path.parent.parent / ".env"
        if default_env.is_file():
            load_dotenv(default_env, override=False)

    with config_path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{config_path}: top level must be a mapping")

    settings = Settings.model_validate(raw)
    data_dir = settings.data_dir
    if not data_dir.is_absolute():
        data_dir = (config_path.parent.parent / data_dir).resolve()

    contact_email = os.environ.get("CONTACT_EMAIL", "").strip() or None
    logger.debug("Loaded settings from %s", config_path)
    return settings.model_copy(
        update={
            "data_dir": data_dir,
            "contact_email": contact_email,
            "config_path": config_path,
        }
    )
