"""The ``mt`` command-line interface."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated

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


ingest_app = typer.Typer(
    name="ingest",
    help="Ingest raw datasets from external sources.",
    no_args_is_help=True,
)
app.add_typer(ingest_app, name="ingest")


@ingest_app.command("siruta")
def ingest_siruta_cmd() -> None:
    """Download official SIRUTA nomenclature CSV from data.gov.ro."""
    from mayortracker.ingest.siruta import ingest_siruta

    settings = load_settings()
    entry = ingest_siruta(settings)
    typer.echo(
        f"Downloaded SIRUTA: {entry.filename} ({entry.bytes} bytes, sha256={entry.sha256[:8]}...)"
    )


@ingest_app.command("lau-boundaries")
def ingest_lau_boundaries_cmd() -> None:
    """Download Eurostat GISCO LAU boundaries shapefile zip."""
    from mayortracker.ingest.boundaries import ingest_lau_boundaries

    settings = load_settings()
    entry = ingest_lau_boundaries(settings)
    typer.echo(
        f"Downloaded LAU boundaries: {entry.filename} ({entry.bytes} bytes, "
        f"sha256={entry.sha256[:8]}...)"
    )


@ingest_app.command("register-file")
def register_file_cmd(
    path: Annotated[
        Path,
        typer.Argument(
            help="Path to local file to register into data/raw/<source_id>/<date>/.",
        ),
    ],
    source_id: Annotated[
        str,
        typer.Option(
            "--source-id",
            help="Source ID matching data source, e.g. 'siruta'.",
        ),
    ],
    source_url: Annotated[
        str,
        typer.Option(
            "--source-url",
            help="Exact URL where the file was obtained.",
        ),
    ],
) -> None:
    """Register a manually acquired raw file into data/raw/ with a manifest entry."""
    from mayortracker.ingest.register import register_file

    settings = load_settings()
    entry = register_file(
        path,
        source_id=source_id,
        source_url=source_url,
        settings=settings,
    )
    typer.echo(
        f"Registered {entry.filename} ({entry.bytes} bytes, sha256={entry.sha256[:8]}...) "
        f"under data/raw/{source_id}/"
    )


normalise_app = typer.Typer(
    name="normalise",
    help="Normalise raw datasets into processed reference tables.",
    no_args_is_help=True,
)
app.add_typer(normalise_app, name="normalise")


@normalise_app.command("uat")
def normalise_uat_cmd() -> None:
    """Normalise UAT and locality reference tables, join boundaries, and export geometries."""
    from mayortracker.normalise.uat import normalise_uat

    settings = load_settings()
    normalise_uat(settings)
    typer.echo("Normalised UAT and locality tables and geometries successfully.")


if __name__ == "__main__":  # pragma: no cover
    app()

