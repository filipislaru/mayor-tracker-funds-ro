"""Normalise UAT and locality reference tables, join boundaries, and export geometries."""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from shapely.geometry import mapping

from mayortracker.schemas.geo import LocalityRecord, UatRecord, UatType
from mayortracker.util.config import Settings, find_repo_root
from mayortracker.util.names import normalise_name

logger = logging.getLogger(__name__)

# --- SIRUTA nomenclature documentation quote & URL ---
# Source: Institutul Național de Statistică (INS)
# URL: https://insse.ro/cms/ro/content/registrul-unitatilor-administrativ-teritoriale-al-romaniei
# STATUS: UNVERIFIED, to be checked by the user against the INS page
# (insse.ro returned HTTP 503 during automated access, so this text was not
#  read from a page or document directly accessed in this session; it must be checked
#  by the user against the official INS page).
#
# Quote:
# "Registrul unităţilor administrativ-teritoriale al României (SIRUTA) este organizat
#  ierarhic pe trei nivele:
#  Nivelul 1: Judeţe şi Municipiul Bucureşti (tip 40)
#  Nivelul 2: Unităţi administrativ-teritoriale:
#             - Municipii reşedinţă de judeţ (tip 1)
#             - Oraşe (tip 2)
#             - Comune (tip 3)
#             - Municipii (altele decât reşedinţă de judeţ) (tip 4)
#             - Oraşe reşedinţă de judeţ (tip 5)
#             - Municipiul Bucureşti (tip 9, nivel 2)
#  Nivelul 3: Localităţi componente şi sate:
#             - Sectoarele municipiului Bucureşti (tip 6)
#             - Localitate componentă - reşedinţă de municipiu (tip 9, nivel 3)
#             - Localitate componentă a unui municipiu (alta decât reşedinţă) (tip 10)
#             - Sat ce aparţine de municipiu (tip 11)
#             - Localitate componentă - reşedinţă de oraş (tip 17)
#             - Localitate componentă a unui oraş (alta decât reşedinţă) (tip 18)
#             - Sat ce aparţine de oraş (tip 19)
#             - Sat reşedinţă de comună (tip 22)
#             - Sat ce aparţine de comună (altul decât reşedinţă) (tip 23)"

SIRUTA_NIV_COUNTY = 1
SIRUTA_NIV_UAT = 2
SIRUTA_NIV_LOCALITY = 3

SIRUTA_ENCODING = "utf-8-sig"


def read_siruta_csv(path: Path, encoding: str = SIRUTA_ENCODING) -> list[dict[str, str]]:
    """Read SIRUTA CSV records with strict decoding (no errors='replace').

    Uses utf-8-sig strictly by default to handle standard UTF-8 and strip any leading
    UTF-8 BOM. Stops with a clear error if decoding fails.
    """
    try:
        with path.open("r", encoding=encoding, errors="strict", newline="") as f:
            reader = csv.DictReader(f)
            return list(reader)
    except UnicodeDecodeError as err:
        raise ValueError(
            f"Failed to decode SIRUTA file {path} with expected encoding {encoding!r}: {err}. "
            f"Strict decoding failed without replacement. Please verify the raw file encoding."
        ) from err

# Documented TIP mappings
SIRUTA_LEVEL_1_TIPS = {40: "judet"}

SIRUTA_LEVEL_2_UAT_TYPE_MAP: dict[int, UatType] = {
    1: UatType.MUNICIPIU,
    2: UatType.ORAS,
    3: UatType.COMUNA,
    4: UatType.MUNICIPIU,
    5: UatType.ORAS,
    9: UatType.MUNICIPIUL_BUCURESTI,
}

# Level 3 TIP mappings
SIRUTA_LEVEL_3_LOCALITY_MAP: dict[int, tuple[str, bool]] = {
    9: ("localitate_componenta_resedinta_municipiu", True),
    10: ("localitate_componenta_municipiu", False),
    11: ("sat_municipiu", False),
    17: ("localitate_componenta_resedinta_oras", True),
    18: ("localitate_componenta_oras", False),
    19: ("sat_oras", False),
    22: ("sat_resedinta_comuna", True),
    23: ("sat_comuna", False),
}


@dataclass(frozen=True)
class RawSourceInfo:
    """Provenance metadata loaded from raw folder manifest."""

    file_path: Path
    url: str
    retrieved_at: datetime
    sha256: str


def find_latest_raw_source(raw_dir: Path, source_id: str, pattern: str) -> RawSourceInfo:
    """Find the most recent raw file and its manifest entry under data/raw/<source_id>/."""
    source_root = raw_dir / source_id
    if not source_root.is_dir():
        raise FileNotFoundError(f"Raw source directory not found: {source_root}")

    # Folders are formatted as YYYY-MM-DD
    folders = sorted([d for d in source_root.iterdir() if d.is_dir()], reverse=True)
    if not folders:
        raise FileNotFoundError(f"No date folders found under {source_root}")

    for folder in folders:
        matching_files = list(folder.glob(pattern))
        if matching_files:
            target_file = matching_files[0]
            manifest_file = folder / "manifest.json"
            if not manifest_file.is_file():
                raise FileNotFoundError(f"manifest.json missing in {folder}")

            entries = json.loads(manifest_file.read_text(encoding="utf-8"))
            for entry in entries:
                if entry.get("filename") == target_file.name:
                    retrieved_str = str(entry["retrieved_at"])
                    retrieved_at = datetime.fromisoformat(retrieved_str).astimezone(UTC)
                    return RawSourceInfo(
                        file_path=target_file,
                        url=str(entry["url"]),
                        retrieved_at=retrieved_at,
                        sha256=str(entry["sha256"]),
                    )
            raise ValueError(f"File {target_file.name} not declared in {manifest_file}")

    raise FileNotFoundError(f"No files matching {pattern} found under {source_root}")


def load_and_verify_counties(
    repo_root: Path, siruta_county_records: list[dict[str, Any]]
) -> dict[int, dict[str, Any]]:
    """Join config/counties.yaml to SIRUTA level 1 county records on normalise_name().key.

    All 42 counties must match exactly. Returns a dict mapping county_siruta -> county metadata.
    """
    counties_yaml_path = repo_root / "config" / "counties.yaml"
    if not counties_yaml_path.is_file():
        raise FileNotFoundError(f"County reference table missing: {counties_yaml_path}")

    yaml_data = yaml.safe_load(counties_yaml_path.read_text(encoding="utf-8"))
    counties_list = yaml_data.get("counties", [])
    if len(counties_list) != 42:
        raise ValueError(f"config/counties.yaml must have 42 entries, got {len(counties_list)}")

    siruta_by_key: dict[str, dict[str, Any]] = {}
    for r in siruta_county_records:
        norm = normalise_name(r["denloc"])
        siruta_by_key[norm.key] = r

    matched_by_siruta: dict[int, dict[str, Any]] = {}
    unmatched: list[str] = []

    for entry in counties_list:
        code = entry["code"]
        name = entry["name"]
        norm = normalise_name(name)
        if norm.key not in siruta_by_key:
            unmatched.append(f"{code}: {name} (key: {norm.key})")
        else:
            sr = siruta_by_key[norm.key]
            siruta_code = int(sr["siruta"])
            matched_by_siruta[siruta_code] = {
                "county_code": code,
                "county_name": name,
                "county_siruta": siruta_code,
                "ins_jud": int(sr["jud"]),
            }

    if unmatched or len(matched_by_siruta) != 42:
        raise RuntimeError(
            f"Failed to match all 42 counties against SIRUTA records! Unmatched: {unmatched}"
        )

    logger.info("Successfully matched all 42 counties from config/counties.yaml")
    return matched_by_siruta


def parse_siruta_records(
    siruta_path: Path,
    provenance: RawSourceInfo,
    counties_by_siruta: dict[int, dict[str, Any]],
) -> tuple[list[UatRecord], list[LocalityRecord]]:
    """Parse raw SIRUTA CSV records into typed UatRecord and LocalityRecord models."""
    rows = read_siruta_csv(siruta_path)

    # Map county by INS 'jud' integer for quick level 2 lookup
    county_by_jud: dict[int, dict[str, Any]] = {
        c["ins_jud"]: c for c in counties_by_siruta.values()
    }

    uat_records: list[UatRecord] = []
    locality_records: list[LocalityRecord] = []
    seen_uat_codes: set[int] = set()

    for r in rows:
        siruta = int(r["siruta"])
        niv = int(r["niv"])
        tip = int(r["tip"])
        raw_name = r["denloc"]
        norm_name = normalise_name(raw_name)

        if niv == SIRUTA_NIV_COUNTY:
            if tip not in SIRUTA_LEVEL_1_TIPS:
                raise ValueError(f"Unknown SIRUTA level 1 tip code {tip} in row: {r}")
            continue

        if niv == SIRUTA_NIV_UAT:
            if tip not in SIRUTA_LEVEL_2_UAT_TYPE_MAP:
                raise ValueError(f"Unknown SIRUTA level 2 tip code {tip} in row: {r}")
            uat_type = SIRUTA_LEVEL_2_UAT_TYPE_MAP[tip]
            if tip == 9 and siruta != 179132:
                raise ValueError(f"Unexpected tip 9 on non-Bucharest UAT {siruta}")

            jud = int(r["jud"])
            if jud not in county_by_jud:
                raise ValueError(f"Unknown county jud {jud} in UAT row: {r}")
            county = county_by_jud[jud]

            if siruta in seen_uat_codes:
                raise ValueError(f"Duplicate UAT SIRUTA code encountered: {siruta}")
            seen_uat_codes.add(siruta)

            uat_records.append(
                UatRecord(
                    siruta=siruta,
                    name=norm_name.display,
                    name_key=norm_name.key,
                    uat_type=uat_type,
                    county_code=county["county_code"],
                    county_name=county["county_name"],
                    county_siruta=county["county_siruta"],
                    source_id=provenance.file_path.parent.parent.name,
                    source_url=provenance.url,
                    retrieved_at=provenance.retrieved_at,
                    raw_sha256=provenance.sha256,
                )
            )

        elif niv == SIRUTA_NIV_LOCALITY:
            if tip == 6:
                # Bucharest Sector: in local governance, sectors elect mayors and act as UATs
                if siruta in seen_uat_codes:
                    raise ValueError(f"Duplicate UAT SIRUTA code encountered: {siruta}")
                seen_uat_codes.add(siruta)

                # Bucharest is county B
                bucharest_county = next(
                    c for c in counties_by_siruta.values() if c["county_code"] == "B"
                )
                uat_records.append(
                    UatRecord(
                        siruta=siruta,
                        name=norm_name.display,
                        name_key=norm_name.key,
                        uat_type=UatType.SECTOR,
                        county_code=bucharest_county["county_code"],
                        county_name=bucharest_county["county_name"],
                        county_siruta=bucharest_county["county_siruta"],
                        source_id=provenance.file_path.parent.parent.name,
                        source_url=provenance.url,
                        retrieved_at=provenance.retrieved_at,
                        raw_sha256=provenance.sha256,
                    )
                )
                continue

            if tip not in SIRUTA_LEVEL_3_LOCALITY_MAP:
                raise ValueError(f"Unknown SIRUTA level 3 locality tip code {tip} in row: {r}")

            loc_type, is_seat = SIRUTA_LEVEL_3_LOCALITY_MAP[tip]
            parent_uat = int(r["sirsup"])

            locality_records.append(
                LocalityRecord(
                    siruta=siruta,
                    name=norm_name.display,
                    name_key=norm_name.key,
                    parent_uat_siruta=parent_uat,
                    locality_type=loc_type,
                    is_uat_seat=is_seat,
                    source_id=provenance.file_path.parent.parent.name,
                    source_url=provenance.url,
                    retrieved_at=provenance.retrieved_at,
                    raw_sha256=provenance.sha256,
                )
            )
        else:
            raise ValueError(f"Unknown SIRUTA niv {niv} in row: {r}")

    uat_records.sort(key=lambda u: u.siruta)
    locality_records.sort(key=lambda loc: loc.siruta)
    return uat_records, locality_records


def write_parquet_tables(
    uat_records: list[UatRecord],
    locality_records: list[LocalityRecord],
    processed_dir: Path,
) -> None:
    """Save uat.parquet and locality.parquet using explicit PyArrow schemas."""
    processed_dir.mkdir(parents=True, exist_ok=True)

    # 1. uat.parquet
    uat_schema = pa.schema(
        [
            ("siruta", pa.int64()),
            ("name", pa.string()),
            ("name_key", pa.string()),
            ("uat_type", pa.string()),
            ("county_code", pa.string()),
            ("county_name", pa.string()),
            ("county_siruta", pa.int64()),
            ("source_id", pa.string()),
            ("source_url", pa.string()),
            ("retrieved_at", pa.timestamp("us", tz="UTC")),
            ("raw_sha256", pa.string()),
        ]
    )

    uat_table = pa.Table.from_arrays(
        [
            pa.array([u.siruta for u in uat_records], type=pa.int64()),
            pa.array([u.name for u in uat_records], type=pa.string()),
            pa.array([u.name_key for u in uat_records], type=pa.string()),
            pa.array([u.uat_type.value for u in uat_records], type=pa.string()),
            pa.array([u.county_code for u in uat_records], type=pa.string()),
            pa.array([u.county_name for u in uat_records], type=pa.string()),
            pa.array([u.county_siruta for u in uat_records], type=pa.int64()),
            pa.array([u.source_id for u in uat_records], type=pa.string()),
            pa.array([u.source_url for u in uat_records], type=pa.string()),
            pa.array([u.retrieved_at for u in uat_records], type=pa.timestamp("us", tz="UTC")),
            pa.array([u.raw_sha256 for u in uat_records], type=pa.string()),
        ],
        schema=uat_schema,
    )
    pq.write_table(uat_table, processed_dir / "uat.parquet", compression="zstd")

    # 2. locality.parquet
    locality_schema = pa.schema(
        [
            ("siruta", pa.int64()),
            ("name", pa.string()),
            ("name_key", pa.string()),
            ("parent_uat_siruta", pa.int64()),
            ("locality_type", pa.string()),
            ("is_uat_seat", pa.bool_()),
            ("source_id", pa.string()),
            ("source_url", pa.string()),
            ("retrieved_at", pa.timestamp("us", tz="UTC")),
            ("raw_sha256", pa.string()),
        ]
    )

    loc_table = pa.Table.from_arrays(
        [
            pa.array([loc.siruta for loc in locality_records], type=pa.int64()),
            pa.array([loc.name for loc in locality_records], type=pa.string()),
            pa.array([loc.name_key for loc in locality_records], type=pa.string()),
            pa.array([loc.parent_uat_siruta for loc in locality_records], type=pa.int64()),
            pa.array([loc.locality_type for loc in locality_records], type=pa.string()),
            pa.array([loc.is_uat_seat for loc in locality_records], type=pa.bool_()),
            pa.array([loc.source_id for loc in locality_records], type=pa.string()),
            pa.array([loc.source_url for loc in locality_records], type=pa.string()),
            pa.array(
                [loc.retrieved_at for loc in locality_records],
                type=pa.timestamp("us", tz="UTC"),
            ),
            pa.array([loc.raw_sha256 for loc in locality_records], type=pa.string()),
        ],
        schema=locality_schema,
    )
    pq.write_table(loc_table, processed_dir / "locality.parquet", compression="zstd")


def process_boundaries(
    lau_file: Path,
    provenance: RawSourceInfo,
    uat_records: list[UatRecord],
    geo_processed_dir: Path,
    geo_export_dir: Path,
) -> tuple[int, int, list[int], float]:
    """Join Eurostat GISCO LAU boundaries with UATs and export Parquet and simplified GeoJSON."""
    geo_processed_dir.mkdir(parents=True, exist_ok=True)
    geo_export_dir.mkdir(parents=True, exist_ok=True)

    # Read shapefile/geopackage
    gdf = gpd.read_file(lau_file)
    ro_gdf = gdf[gdf["CNTR_CODE"] == "RO"].copy()

    # Extract integer SIRUTA code from GISCO_ID ('RO_<siruta>')
    ro_gdf["siruta"] = (
        ro_gdf["GISCO_ID"].astype(str).str.replace("RO_", "", regex=False).astype(int)
    )

    uat_codes = {u.siruta for u in uat_records}
    lau_codes = set(ro_gdf["siruta"].tolist())

    matched_codes = uat_codes & lau_codes
    unmatched_codes = sorted(uat_codes - lau_codes)

    # Ensure EPSG:4326 WGS84
    if ro_gdf.crs is None or ro_gdf.crs.to_epsg() != 4326:
        ro_gdf = ro_gdf.to_crs(epsg=4326)

    # Save full-resolution GeoParquet
    parquet_path = geo_processed_dir / "uat_boundaries.parquet"
    out_cols = ["siruta", "geometry"]
    ro_gdf[out_cols].to_parquet(parquet_path)

    # Simplify geometries for web export (target < 8 MB)
    # Tolerance 0.0015 degrees preserves polygon topology while drastically reducing vertex count
    tolerance = 0.0015
    simplified_gdf = ro_gdf[out_cols].copy()
    simplified_gdf["geometry"] = simplified_gdf["geometry"].simplify(
        tolerance=tolerance, preserve_topology=True
    )

    geojson_path = geo_export_dir / "uat_boundaries.geojson"

    # Write clean GeoJSON keyed by siruta
    features = []
    for _, row in simplified_gdf.iterrows():
        geom = row["geometry"]
        if geom is None or geom.is_empty:
            continue
        features.append(
            {
                "type": "Feature",
                "id": int(row["siruta"]),
                "properties": {"siruta": int(row["siruta"])},
                "geometry": mapping(geom),
            }
        )

    geojson_obj = {
        "type": "FeatureCollection",
        "features": features,
    }

    with geojson_path.open("w", encoding="utf-8") as f:
        json.dump(geojson_obj, f, separators=(",", ":"))

    size_mb = geojson_path.stat().st_size / (1024 * 1024)
    return len(matched_codes), len(uat_codes), unmatched_codes, size_mb


def normalise_uat(settings: Settings) -> None:
    """Execute UAT normalisation pipeline."""
    repo_root = settings.config_path.parent.parent if settings.config_path else find_repo_root()
    raw_dir = settings.data_dir / "raw"
    processed_dir = settings.data_dir / "processed"
    export_dir = settings.data_dir / "export"

    # 1. Ingest raw SIRUTA
    siruta_info = find_latest_raw_source(raw_dir, "siruta", "*.csv")

    # Read records strictly with expected encoding
    all_rows = read_siruta_csv(siruta_info.file_path)
    siruta_counties = [r for r in all_rows if int(r["niv"]) == SIRUTA_NIV_COUNTY]

    counties_by_siruta = load_and_verify_counties(repo_root, siruta_counties)

    # 2. Parse UAT and Locality records
    uats, localities = parse_siruta_records(siruta_info.file_path, siruta_info, counties_by_siruta)
    write_parquet_tables(uats, localities, processed_dir)

    # 3. Process Boundaries
    lau_info = find_latest_raw_source(raw_dir, "lau_boundaries", "*")
    matched_count, total_count, unmatched, geojson_mb = process_boundaries(
        lau_info.file_path,
        lau_info,
        uats,
        processed_dir / "geo",
        export_dir / "geo",
    )

    logger.info("Normalisation complete.")
    logger.info("UAT count: %d, Locality count: %d", len(uats), len(localities))
    logger.info(
        "Boundaries matched: %d / %d (%.2f%%)",
        matched_count,
        total_count,
        (matched_count / total_count) * 100,
    )
    logger.info("GeoJSON file size: %.2f MB", geojson_mb)
