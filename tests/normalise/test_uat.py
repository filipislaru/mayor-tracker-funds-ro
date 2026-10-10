"""Tests for UAT and locality normalisation with synthetic fixtures."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from mayortracker.normalise.uat import (
    RawSourceInfo,
    load_and_verify_counties,
    parse_siruta_records,
    process_boundaries,
    read_siruta_csv,
    write_parquet_tables,
)
from mayortracker.schemas.geo import LocalityRecord, UatRecord, UatType
from mayortracker.util.config import find_repo_root
from shapely.geometry import Polygon


@pytest.fixture
def repo_root() -> Path:
    return find_repo_root()


@pytest.fixture
def synthetic_county_records() -> list[dict[str, str]]:
    """Synthetic level 1 SIRUTA records covering all 42 real counties."""
    root = find_repo_root()
    import yaml

    counties_yaml = yaml.safe_load((root / "config" / "counties.yaml").read_text())["counties"]
    records = []
    for idx, c in enumerate(counties_yaml, start=1):
        # Synthetic codes >= 900000
        siruta_code = 900000 + idx
        records.append(
            {
                "siruta": str(siruta_code),
                "niv": "1",
                "sirsup": "1",
                "tip": "40",
                "denloc": f"JUDETUL {c['name'].upper()}",
                "ult": "0",
                "med": "0",
                "jud": str(idx),
                "prefix": "0",
                "regiune": "7",
                "codp": "0",
                "fsj": "1",
                "fs2": "",
                "fs3": "",
                "fsl": "1",
                "fictiv": "0",
            }
        )
    return records


def test_load_and_verify_counties_success(
    repo_root: Path, synthetic_county_records: list[dict[str, str]]
) -> None:
    matched = load_and_verify_counties(repo_root, synthetic_county_records)
    assert len(matched) == 42


def test_load_and_verify_counties_failure_on_missing(
    repo_root: Path, synthetic_county_records: list[dict[str, str]]
) -> None:
    # Remove one county to force mismatch
    partial_records = synthetic_county_records[:-1]
    with pytest.raises(RuntimeError, match="Failed to match all 42 counties"):
        load_and_verify_counties(repo_root, partial_records)


def test_parse_siruta_records(
    tmp_path: Path, repo_root: Path, synthetic_county_records: list[dict[str, str]]
) -> None:
    counties_by_siruta = load_and_verify_counties(repo_root, synthetic_county_records)

    # Find Alba (jud 1)
    alba_jud = [c["ins_jud"] for c in counties_by_siruta.values() if c["county_code"] == "AB"][0]

    # Create synthetic SIRUTA CSV
    siruta_rows = [
        # County records
        *synthetic_county_records,
        # UAT commune in Alba
        {
            "siruta": "910001",
            "niv": "2",
            "sirsup": "900001",
            "tip": "3",
            "denloc": "TEST COMUNA EXEMPLU",
            "ult": "0",
            "med": "0",
            "jud": str(alba_jud),
            "prefix": "0",
            "regiune": "7",
            "codp": "0",
            "fsj": "1",
            "fs2": "1",
            "fs3": "",
            "fsl": "1",
            "fictiv": "0",
        },
        # Locality seat for the commune
        {
            "siruta": "920001",
            "niv": "3",
            "sirsup": "910001",
            "tip": "22",
            "denloc": "TEST SAT EXEMPLU RESEDINTA",
            "ult": "1",
            "med": "0",
            "jud": str(alba_jud),
            "prefix": "0",
            "regiune": "7",
            "codp": "0",
            "fsj": "1",
            "fs2": "1",
            "fs3": "1",
            "fsl": "2",
            "fictiv": "0",
        },
        # Component locality (non-seat)
        {
            "siruta": "920002",
            "niv": "3",
            "sirsup": "910001",
            "tip": "23",
            "denloc": "TEST SAT SECUNDAR",
            "ult": "1",
            "med": "0",
            "jud": str(alba_jud),
            "prefix": "0",
            "regiune": "7",
            "codp": "0",
            "fsj": "1",
            "fs2": "1",
            "fs3": "2",
            "fsl": "3",
            "fictiv": "0",
        },
        # Bucharest level 2
        {
            "siruta": "179132",
            "niv": "2",
            "sirsup": "900042",
            "tip": "9",
            "denloc": "TEST MUNICIPIUL BUCURESTI",
            "ult": "0",
            "med": "1",
            "jud": "40",
            "prefix": "0",
            "regiune": "8",
            "codp": "0",
            "fsj": "42",
            "fs2": "11681",
            "fs3": "",
            "fsl": "16972",
            "fictiv": "0",
        },
        # Bucharest Sector 1 (tip 6)
        {
            "siruta": "179141",
            "niv": "3",
            "sirsup": "179132",
            "tip": "6",
            "denloc": "TEST BUCURESTI SECTORUL 1",
            "ult": "1",
            "med": "1",
            "jud": "40",
            "prefix": "0",
            "regiune": "8",
            "codp": "0",
            "fsj": "42",
            "fs2": "11681",
            "fs3": "1001759",
            "fsl": "16973",
            "fictiv": "0",
        },
    ]

    csv_path = tmp_path / "siruta.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(siruta_rows[0].keys()))
        writer.writeheader()
        writer.writerows(siruta_rows)

    prov = RawSourceInfo(
        file_path=csv_path,
        url="https://test.example.com/siruta.csv",
        retrieved_at=datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC),
        sha256="abc12345",
    )

    uats, localities = parse_siruta_records(csv_path, prov, counties_by_siruta)

    # 1 commune + 1 bucharest + 1 sector = 3 UATs
    assert len(uats) == 3
    commune_uat = [u for u in uats if u.siruta == 910001][0]
    assert commune_uat.uat_type == UatType.COMUNA
    assert commune_uat.county_code == "AB"

    sector_uat = [u for u in uats if u.siruta == 179141][0]
    assert sector_uat.uat_type == UatType.SECTOR
    assert sector_uat.county_code == "B"

    # Localities
    assert len(localities) == 2
    seat_loc = [loc for loc in localities if loc.siruta == 920001][0]
    assert seat_loc.is_uat_seat is True
    assert seat_loc.locality_type == "sat_resedinta_comuna"

    non_seat_loc = [loc for loc in localities if loc.siruta == 920002][0]
    assert non_seat_loc.is_uat_seat is False
    assert non_seat_loc.locality_type == "sat_comuna"


def test_parse_siruta_records_unknown_tip_raises(
    tmp_path: Path, repo_root: Path, synthetic_county_records: list[dict[str, str]]
) -> None:
    counties_by_siruta = load_and_verify_counties(repo_root, synthetic_county_records)
    siruta_rows = [
        *synthetic_county_records,
        {
            "siruta": "910099",
            "niv": "2",
            "sirsup": "900001",
            "tip": "99",  # Unknown tip code
            "denloc": "TEST INVALID",
            "ult": "0",
            "med": "0",
            "jud": "1",
            "prefix": "0",
            "regiune": "7",
            "codp": "0",
            "fsj": "1",
            "fs2": "1",
            "fs3": "",
            "fsl": "1",
            "fictiv": "0",
        },
    ]
    csv_path = tmp_path / "siruta_invalid.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(siruta_rows[0].keys()))
        writer.writeheader()
        writer.writerows(siruta_rows)

    prov = RawSourceInfo(
        file_path=csv_path,
        url="https://test.example.com/siruta.csv",
        retrieved_at=datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC),
        sha256="abc12345",
    )

    with pytest.raises(ValueError, match="Unknown SIRUTA level 2 tip code 99"):
        parse_siruta_records(csv_path, prov, counties_by_siruta)


def test_write_parquet_tables_and_process_boundaries(tmp_path: Path) -> None:
    dt = datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC)
    uats = [
        UatRecord(
            siruta=910001,
            name="TEST Comuna A",
            name_key="comuna a",
            uat_type=UatType.COMUNA,
            county_code="AB",
            county_name="Alba",
            county_siruta=900001,
            source_id="siruta",
            source_url="https://test.example.com",
            retrieved_at=dt,
            raw_sha256="sha123",
        ),
        UatRecord(
            siruta=910002,
            name="TEST Comuna B (Unmatched)",
            name_key="comuna b",
            uat_type=UatType.COMUNA,
            county_code="AB",
            county_name="Alba",
            county_siruta=900001,
            source_id="siruta",
            source_url="https://test.example.com",
            retrieved_at=dt,
            raw_sha256="sha123",
        ),
    ]
    localities = [
        LocalityRecord(
            siruta=920001,
            name="TEST Sat A",
            name_key="sat a",
            parent_uat_siruta=910001,
            locality_type="sat_comuna",
            is_uat_seat=True,
            source_id="siruta",
            source_url="https://test.example.com",
            retrieved_at=dt,
            raw_sha256="sha123",
        )
    ]

    processed_dir = tmp_path / "processed"
    write_parquet_tables(uats, localities, processed_dir)

    # Check parquet output and schema
    uat_parquet = processed_dir / "uat.parquet"
    assert uat_parquet.is_file()
    t_uat = pq.read_table(uat_parquet)
    assert t_uat.num_rows == 2
    # Verify retrieved_at is a timestamp with UTC timezone
    retrieved_col = t_uat.schema.field("retrieved_at")
    assert retrieved_col.type == pa.timestamp("us", tz="UTC")

    loc_parquet = processed_dir / "locality.parquet"
    assert loc_parquet.is_file()
    t_loc = pq.read_table(loc_parquet)
    assert t_loc.num_rows == 1

    # Synthetic GeoDataFrame
    poly = Polygon([(23.0, 46.0), (23.1, 46.0), (23.1, 46.1), (23.0, 46.1), (23.0, 46.0)])
    gdf = gpd.GeoDataFrame(
        [
            {"GISCO_ID": "RO_910001", "CNTR_CODE": "RO", "geometry": poly},
            {"GISCO_ID": "HU_999999", "CNTR_CODE": "HU", "geometry": poly},
        ],
        crs="EPSG:4326",
    )
    lau_file = tmp_path / "lau.geojson"
    gdf.to_file(lau_file, driver="GeoJSON")

    prov = RawSourceInfo(
        file_path=lau_file,
        url="https://test.example.com/lau.zip",
        retrieved_at=dt,
        sha256="sha456",
    )

    geo_proc_dir = processed_dir / "geo"
    geo_export_dir = tmp_path / "export" / "geo"
    matched_count, total_count, unmatched, size_mb = process_boundaries(
        lau_file, prov, uats, geo_proc_dir, geo_export_dir
    )

    assert matched_count == 1
    assert total_count == 2
    assert unmatched == [910002]
    assert (geo_proc_dir / "uat_boundaries.parquet").is_file()

    geojson_path = geo_export_dir / "uat_boundaries.geojson"
    assert geojson_path.is_file()
    data = json.loads(geojson_path.read_text(encoding="utf-8"))
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 1
    assert data["features"][0]["properties"]["siruta"] == 910001


def test_read_siruta_csv_strict_decoding(tmp_path: Path) -> None:
    csv_file = tmp_path / "TEST_valid.csv"
    # Write UTF-8 with BOM and diacritics
    content = "\ufeffsiruta,niv,denloc\n900001,1,TEST Județ\n"
    csv_file.write_text(content, encoding="utf-8")

    rows = read_siruta_csv(csv_file)
    assert len(rows) == 1
    assert rows[0]["siruta"] == "900001"
    assert rows[0]["denloc"] == "TEST Județ"

    # Write corrupt byte sequence that is invalid UTF-8
    bad_csv = tmp_path / "TEST_bad.csv"
    bad_csv.write_bytes(b"\xff\xfe\x00\x00siruta,niv\n")

    with pytest.raises(ValueError, match="Strict decoding failed without replacement"):
        read_siruta_csv(bad_csv)
