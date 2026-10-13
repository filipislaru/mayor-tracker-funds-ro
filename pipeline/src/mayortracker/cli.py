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
    entries = ingest_siruta(settings)
    for entry in entries:
        typer.echo(
            f"Downloaded {entry.filename} ({entry.bytes} bytes, sha256={entry.sha256[:8]}...)"
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


@ingest_app.command("kohesio")
def ingest_kohesio_cmd() -> None:
    """Download official Kohesio datasets for Romania (projects, beneficiaries, NUTS)."""
    from mayortracker.ingest.kohesio import ingest_kohesio

    settings = load_settings()
    entries = ingest_kohesio(settings)
    for entry in entries:
        typer.echo(
            f"Downloaded {entry.filename} ({entry.bytes} bytes, sha256={entry.sha256[:8]}...)"
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


@normalise_app.command("elections")
def normalise_elections_cmd(
    year: Annotated[
        int | None,
        typer.Option(
            "--year",
            help="Election year to normalise (2020 or 2024). Defaults to both.",
        ),
    ] = None,
) -> None:
    """Normalise mayoral election results into clean candidate, race, and term tables."""
    from mayortracker.normalise.elections import normalise_elections, reconcile_county_party

    settings = load_settings()
    metrics = normalise_elections(settings, year=year)
    for yr, m in metrics.items():
        typer.echo(
            f"Year {yr}: {m['total_races']} races ({m['uncontested_races']} uncontested), "
            f"{m['candidates_count']} candidate entries, "
            f"named candidates: {m['named_candidates']}, named winners: {m['named_winners']}."
        )
        if m["discrepancy_races"] > 0:
            typer.echo(
                f"  Vote-sum discrepancies: {m['discrepancy_races']} races "
                f"(max discrepancy: {m['max_discrepancy']} votes)."
            )
        if m.get("unmatched_races"):
            typer.echo(
                f"  UAT reference match: {m['matched_count']}/{m['total_races']} matched, "
                f"unmatched races: {m['unmatched_races']}, missing UATs: {m['missing_uats']}."
            )
        else:
            matched_c = m.get("matched_count", m["total_races"])
            typer.echo(f"  UAT reference match: {matched_c}/{m['total_races']} matched (100.00%).")
        recs = reconcile_county_party(settings, yr)
        if recs:
            typer.echo(f"  County reconciliation discrepancies vs pv_final: {len(recs)} entries.")
        else:
            typer.echo("  County reconciliation: 100% match against pv_final.")


@normalise_app.command("kohesio")
def normalise_kohesio_cmd() -> None:
    """Normalise Kohesio projects, beneficiaries, and link local authorities to UATs."""
    from mayortracker.normalise.kohesio import normalise_kohesio

    settings = load_settings()
    metrics = normalise_kohesio(settings)
    typer.echo(
        f"Projects: {metrics.total_projects:,} total ({metrics.projects_14_20:,} for 2014-2020, "
        f"{metrics.projects_21_27:,} for 2021-2027)."
    )
    typer.echo(
        f"Projects with local-authority beneficiaries: {metrics.projects_with_la:,} "
        f"({metrics.la_project_share_pct:.2f}%)."
    )
    typer.echo(
        f"Beneficiaries: {metrics.total_beneficiaries:,} unique "
        f"({metrics.local_authority_beneficiaries:,} local authorities)."
    )
    typer.echo(
        f"  Matched cleanly: {metrics.matched_local_authorities:,} "
        f"(exact: {metrics.matches_by_method.get('name_county_exact', 0)}, "
        f"normalised: {metrics.matches_by_method.get('name_county_normalised', 0)})."
    )
    ambig_count = metrics.ambiguous_or_unmatched_local_authorities
    cand_count = metrics.matches_by_method.get('locality_candidate', 0)
    unmatched_count = metrics.matches_by_method.get('unmatched_local_authority', 0)
    typer.echo(
        f"  Ambiguous / unmatched local authorities: {ambig_count:,} "
        f"(locality candidates: {cand_count}, unmatched/disagreements: {unmatched_count})."
    )
    typer.echo(
        f"Fiscal codes: crosswalk built. Flags: {metrics.multi_uat_fiscal_codes_count} "
        f"multi-UAT fiscal codes, {metrics.multi_fiscal_code_uats_count} multi-fiscal-code UATs."
    )
    typer.echo("Top 5 UATs by EU co-financing (total / shared):")
    for u in metrics.top_20_uats[:5]:
        amt = u["total_eu_budget_eur"]
        shared = u.get("shared_eu_budget_eur", 0.0)
        typer.echo(
            f"  {u['siruta']} {u['uat_name']} ({u['county_code']}): €{amt:,.2f} "
            f"(shared: €{shared:,.2f})"
        )



if __name__ == "__main__":  # pragma: no cover
    app()

