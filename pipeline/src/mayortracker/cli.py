"""The ``mt`` command-line interface."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

import typer

from mayortracker import __version__
from mayortracker.util.config import Settings, find_repo_root, load_settings

app = typer.Typer(
    name="mt",
    help="Romania Mayor Tracker pipeline.",
    no_args_is_help=True,
    add_completion=False,
)

_ENV_KEY_RE = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)\s*=")


def env_example_keys(path: Path) -> list[str]:
    """Return variable names declared in an ``.env.example`` file (values are ignored)."""
    if not path.is_file():
        return []
    keys: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _ENV_KEY_RE.match(line)
        if match and match.group(1) not in keys:
            keys.append(match.group(1))
    return keys


def _uv_version() -> str | None:
    exe = shutil.which("uv")
    if exe is None:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def _status(ok: bool, yes: str = "ok", no: str = "missing") -> str:
    return yes if ok else no


@app.command()
def doctor() -> None:
    """Report environment health: Python, uv environment, data folders, .env keys.

    Never prints the value of any environment variable, only whether it is set.
    """
    settings = load_settings()
    repo_root = settings.config_path.parent.parent if settings.config_path else find_repo_root()

    typer.echo(f"mayortracker {__version__}")
    typer.echo(f"Python: {platform.python_version()} ({sys.executable})")

    typer.echo("uv environment:")
    venv = (repo_root / ".venv").resolve()
    in_project_venv = Path(sys.prefix).resolve() == venv
    typer.echo(f"  project .venv active: {_status(in_project_venv, 'yes', 'no')}")
    typer.echo(f"  uv.lock: {_status((repo_root / 'uv.lock').is_file())}")
    uv_version = _uv_version()
    typer.echo(f"  uv executable: {uv_version or 'not on PATH'}")

    typer.echo(f"Config: {settings.config_path}")
    typer.echo(f"Data directory: {settings.data_dir}")
    for name, path in settings.data_dirs().items():
        typer.echo(f"  {name:<10} {_status(path.is_dir(), 'exists', 'missing')}  {path}")

    typer.echo("Environment keys (from .env.example):")
    keys = env_example_keys(repo_root / ".env.example")
    if not keys:
        typer.echo("  (no .env.example found)")
    for key in keys:
        is_set = bool(os.environ.get(key, "").strip())
        typer.echo(f"  {key:<16} {_status(is_set, 'set', 'missing')}")


def _init_data(settings: Settings) -> list[tuple[Path, bool]]:
    results: list[tuple[Path, bool]] = []
    for path in settings.data_dirs().values():
        existed = path.is_dir()
        path.mkdir(parents=True, exist_ok=True)
        results.append((path, not existed))
    return results


@app.command("init-data")
def init_data() -> None:
    """Create the data folders (raw, interim, processed, export, cache/http) if missing."""
    settings = load_settings()
    for path, created in _init_data(settings):
        typer.echo(f"{'created' if created else 'exists ':<8} {path}")


if __name__ == "__main__":  # pragma: no cover
    app()
