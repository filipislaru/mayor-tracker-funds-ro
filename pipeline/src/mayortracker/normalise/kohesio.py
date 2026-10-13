"""Normalise Kohesio projects, beneficiaries, and UAT matches."""

from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from mayortracker.normalise.kohesio_cleaner import (
    clean_kohesio_beneficiary_name,
    is_county_council,
    is_local_authority,
    is_other_body,
    parse_kohesio_date,
)
from mayortracker.schemas.kohesio import MatchConfidence, MatchMethod
from mayortracker.util.config import Settings
from mayortracker.util.names import normalise_name

logger = logging.getLogger(__name__)

SOURCE_ID = "kohesio"


@dataclass(frozen=True, slots=True)
class KohesioMetrics:
    """Metrics and diagnostics produced during Kohesio normalisation."""

    total_projects: int
    projects_14_20: int
    projects_21_27: int
    projects_with_la: int
    la_project_share_pct: float
    total_beneficiaries: int
    local_authority_beneficiaries: int
    matched_local_authorities: int
    ambiguous_or_unmatched_local_authorities: int
    matches_by_method: dict[str, int]
    fund_totals_before_dedup: dict[str, dict[str, float]]
    fund_totals_after_dedup: dict[str, dict[str, float]]
    top_20_uats: list[dict[str, Any]]
    unparseable_dates_count: int
    multi_uat_fiscal_codes_count: int
    multi_fiscal_code_uats_count: int


def find_latest_raw_folder(raw_dir: Path, source_id: str) -> Path:
    """Find the latest date folder under data/raw/<source_id>/."""
    source_path = raw_dir / source_id
    if not source_path.is_dir():
        raise FileNotFoundError(
            f"Raw directory for source '{source_id}' not found at {source_path}"
        )
    subdirs = sorted([p for p in source_path.iterdir() if p.is_dir()], key=lambda p: p.name)
    if not subdirs:
        raise FileNotFoundError(f"No date subdirectories found under {source_path}")
    return subdirs[-1]


def load_manifest(folder: Path) -> dict[str, dict[str, Any]]:
    """Load manifest.json from a raw folder indexed by filename."""
    manifest_file = folder / "manifest.json"
    if not manifest_file.is_file():
        return {}
    entries = json.loads(manifest_file.read_text(encoding="utf-8"))
    return {e["filename"]: e for e in entries if "filename" in e}


def normalise_kohesio(
    settings: Settings,
    *,
    raw_folder: Path | None = None,
) -> KohesioMetrics:
    """Normalise Kohesio projects, beneficiaries, and link local authorities to UATs.

    Parameters
    ----------
    settings : Settings
        Application settings.
    raw_folder : Path | None
        Optional explicit folder containing raw Kohesio CSVs and manifest.json.

    Returns
    -------
    KohesioMetrics
        Comprehensive metrics and summary statistics.
    """
    raw_dir = settings.data_dir / "raw"
    folder = raw_folder or find_latest_raw_folder(raw_dir, SOURCE_ID)
    manifest = load_manifest(folder)

    # 1. Load reference UAT and Locality tables
    uat_path = settings.data_dir / "processed" / "uat.parquet"
    loc_path = settings.data_dir / "processed" / "locality.parquet"
    if not uat_path.is_file():
        raise FileNotFoundError(
            f"UAT reference table not found at {uat_path}. Run 'mt normalise uat' first."
        )

    conn = duckdb.connect()
    uats_df = conn.execute(
        "SELECT siruta, name, name_key, county_code, county_name, uat_type FROM '"
        + str(uat_path)
        + "'"
    ).fetchdf()

    locs_df = pd.DataFrame()
    if loc_path.is_file():
        locs_df = conn.execute(
            """
            SELECT l.siruta as loc_siruta, l.name as loc_name, l.name_key as loc_key,
                   l.parent_uat_siruta, u.county_code, u.name as uat_name
            FROM '"""
            + str(loc_path)
            + """' l
            JOIN '"""
            + str(uat_path)
            + """' u ON l.parent_uat_siruta = u.siruta
            """
        ).fetchdf()

    # 2. Build NUTS3 to County mapping from RO-nuts-latest.csv
    nuts_file = folder / "RO-nuts-latest.csv"
    nuts_map: dict[str, str] = {}
    if nuts_file.is_file():
        df_nuts = pd.read_csv(nuts_file)
        for _, r in df_nuts.iterrows():
            n_code = str(r["nuts3code"]).strip()
            lbl = str(r["nuts3Label"]).strip()
            if n_code == "RO414":
                nuts_map[n_code] = "OT"
            else:
                k = normalise_name(lbl).key
                match = uats_df[
                    uats_df["county_name"].apply(lambda x, key=k: normalise_name(x).key == key)
                ]
                if not match.empty:
                    nuts_map[n_code] = str(match.iloc[0]["county_code"])

    uat_by_name_county = {(r["name_key"], r["county_code"]): r for _, r in uats_df.iterrows()}
    loc_by_name_county = (
        {(r["loc_key"], r["county_code"]): r for _, r in locs_df.iterrows()}
        if not locs_df.empty
        else {}
    )

    # 3. Read and parse raw project files
    p14_file = folder / "RO-pp14-20-latest.csv"
    p21_file = folder / "RO-pp21-27-latest.csv"
    p14_manifest = manifest.get("RO-pp14-20-latest.csv", {})
    p21_manifest = manifest.get("RO-pp21-27-latest.csv", {})

    df14 = pd.read_csv(p14_file, low_memory=False)
    df21 = pd.read_csv(p21_file, low_memory=False)

    total_rows_14 = len(df14)
    total_rows_21 = len(df21)

    # Budget totals before de-duplication
    def compute_fund_totals(df: pd.DataFrame, period: str) -> dict[str, dict[str, float]]:
        totals: dict[str, dict[str, float]] = {}
        for fund, sub in df.groupby("Fund_Code", dropna=False):
            fund_key = f"{period}:{fund or 'UNKNOWN'}"
            totals[fund_key] = {
                "count": float(len(sub)),
                "total_eligible": float(sub["Total_Eligible_Expenditure_amount"].sum()),
                "eu_budget": float(sub["Project_EU_Budget"].sum()),
            }
        return totals

    fund_totals_before: dict[str, dict[str, float]] = {}
    fund_totals_before.update(compute_fund_totals(df14, "2014-2020"))
    fund_totals_before.update(compute_fund_totals(df21, "2021-2027"))

    # Parse dates strictly
    unparseable_dates = 0

    def parse_dates_col(series: pd.Series) -> list[Any]:
        nonlocal unparseable_dates
        out = []
        for val in series:
            if pd.isna(val) or val is None or not str(val).strip():
                out.append(None)
            else:
                d = parse_kohesio_date(str(val))
                if d is None:
                    unparseable_dates += 1
                out.append(d)
        return out

    # Standardize records
    projects_rows: list[dict[str, Any]] = []
    beneficiaries_rows: list[dict[str, Any]] = []

    def process_projects_df(
        df: pd.DataFrame,
        period: str,
        m_entry: dict[str, Any],
    ) -> None:
        start_dates = parse_dates_col(df["Operation_Start_Date"])
        end_dates = parse_dates_col(df["Operation_End_Date"])
        retrieved_at = m_entry.get("retrieved_at", "2026-10-13T00:00:00Z")
        sha256_val = m_entry.get("sha256", "")
        source_url = m_entry.get("url", "")

        for i, row in df.iterrows():
            proj_id = str(row["Operation_Unique_Identifier"]).strip()
            loc_id = str(row["Operation_Local_Identifier"]).strip()
            title = str(row["Operation_Name_Programme_Language"]).strip()
            title_en = (
                str(row["Operation_Name_English"]).strip()
                if pd.notna(row.get("Operation_Name_English"))
                else None
            )
            prog_code = str(row["Programme_Code"]).strip()
            prog_name = str(row["Programme_Name"]).strip()
            fund_code = (
                str(row["Fund_Code"]).strip() if pd.notna(row.get("Fund_Code")) else "UNKNOWN"
            )
            fund_name = (
                str(row["Fund_Name"]).strip() if pd.notna(row.get("Fund_Name")) else "UNKNOWN"
            )
            total_amt = float(row["Total_Eligible_Expenditure_amount"])
            curr = str(row["Total_Eligible_Expenditure_Currency"]).strip()
            eu_budget = float(row["Project_EU_Budget"])
            cofin_rate = (
                float(row["Cofinancing_Rate"]) if pd.notna(row.get("Cofinancing_Rate")) else None
            )

            lau_ids = str(row["LAU_IDs"]).strip() if pd.notna(row.get("LAU_IDs")) else None
            lau_labels = str(row["LAU_Labels"]).strip() if pd.notna(row.get("LAU_Labels")) else None
            nuts3_code = str(row["NUTS3_Code"]).strip() if pd.notna(row.get("NUTS3_Code")) else None
            nuts3_label = (
                str(row["NUTS3_Label"]).strip() if pd.notna(row.get("NUTS3_Label")) else None
            )
            raw_coords = row.get("Coordinates", row.get("Location_Indicator_latitude_longitude"))
            coords = (
                str(raw_coords).strip()
                if pd.notna(raw_coords)
                else None
            )

            # Check multiple beneficiaries / partners in project
            bene_id = str(row["Beneficiary_Unique_Identifier"]).strip()
            bene_name = str(row["Beneficiary_Name"]).strip()
            bene_local_id_raw = (
                str(row["Beneficiary_Local_Identifier"]).strip()
                if pd.notna(row.get("Beneficiary_Local_Identifier"))
                else None
            )

            has_mult_bene = False
            local_ids_list = [bene_local_id_raw] if bene_local_id_raw else [None]
            if bene_local_id_raw and ("|" in bene_local_id_raw or ";" in bene_local_id_raw):
                has_mult_bene = True
                local_ids_list = [
                    x.strip()
                    for x in re.split(r"[|;]", bene_local_id_raw)
                    if x.strip()
                ]

            is_la = is_local_authority(bene_name)

            projects_rows.append({
                "project_id": proj_id,
                "local_id": loc_id,
                "title": title,
                "title_en": title_en,
                "programme_code": prog_code,
                "programme_name": prog_name,
                "fund_code": fund_code,
                "fund_name": fund_name,
                "programming_period": period,
                "total_eligible_expenditure_amount": total_amt,
                "total_eligible_expenditure_currency": curr,
                "eu_budget": eu_budget,
                "cofinancing_rate": cofin_rate,
                "start_date": start_dates[i],
                "end_date": end_dates[i],
                "has_multiple_beneficiaries": has_mult_bene,
                "lau_ids": lau_ids,
                "lau_labels": lau_labels,
                "nuts3_code": nuts3_code,
                "nuts3_label": nuts3_label,
                "coordinates": coords,
                "source_id": SOURCE_ID,
                "source_url": source_url,
                "retrieved_at": retrieved_at,
                "raw_sha256": sha256_val,
            })

            # Record each project-beneficiary pair
            for lid in local_ids_list:
                beneficiaries_rows.append({
                    "project_id": proj_id,
                    "beneficiary_id": bene_id,
                    "beneficiary_name": bene_name,
                    "beneficiary_local_id": lid,
                    "is_local_authority": is_la,
                    "source_id": SOURCE_ID,
                    "source_url": source_url,
                    "retrieved_at": retrieved_at,
                    "raw_sha256": sha256_val,
                })

    process_projects_df(df14, "2014-2020", p14_manifest)
    process_projects_df(df21, "2021-2027", p21_manifest)

    projects_df = pd.DataFrame(projects_rows)
    # De-duplicate projects by project_id
    dedup_projects_df = projects_df.drop_duplicates(subset=["project_id"])

    fund_totals_after: dict[str, dict[str, float]] = {}
    for (period, fund), sub in dedup_projects_df.groupby(["programming_period", "fund_code"]):
        fund_key = f"{period}:{fund}"
        fund_totals_after[fund_key] = {
            "count": float(len(sub)),
            "total_eligible": float(sub["total_eligible_expenditure_amount"].sum()),
            "eu_budget": float(sub["eu_budget"].sum()),
        }

    # 4. Beneficiary-to-UAT Matching
    beneficiaries_df = pd.DataFrame(beneficiaries_rows)

    # Map project details per unique beneficiary entity
    bene_project_map: dict[str, list[dict[str, Any]]] = {}
    for _, p_row in dedup_projects_df.iterrows():
        # Get beneficiary id and details from beneficiaries_df for this project
        pairs = beneficiaries_df[beneficiaries_df["project_id"] == p_row["project_id"]]
        for _, b_row in pairs.iterrows():
            bid = b_row["beneficiary_id"]
            if bid not in bene_project_map:
                bene_project_map[bid] = []
            bene_project_map[bid].append({
                "project_id": p_row["project_id"],
                "beneficiary_name": b_row["beneficiary_name"],
                "beneficiary_local_id": b_row["beneficiary_local_id"],
                "nuts3_code": p_row["nuts3_code"],
                "lau_ids": p_row["lau_ids"],
                "eu_budget": p_row["eu_budget"],
                "total_eligible": p_row["total_eligible_expenditure_amount"],
            })

    unique_benes = beneficiaries_df[
        ["beneficiary_id", "beneficiary_name", "beneficiary_local_id"]
    ].drop_duplicates(subset=["beneficiary_id"])

    match_records: list[dict[str, Any]] = []
    review_records: list[dict[str, Any]] = []
    confirmed_uat_matches: list[dict[str, Any]] = []

    matches_by_method_counts: dict[str, int] = {
        MatchMethod.NAME_COUNTY_EXACT.value: 0,
        MatchMethod.NAME_COUNTY_NORMALISED.value: 0,
        MatchMethod.LOCALITY_CANDIDATE.value: 0,
        MatchMethod.UNMATCHED_LOCAL_AUTHORITY.value: 0,
        MatchMethod.COUNTY_COUNCIL.value: 0,
        MatchMethod.OTHER_BODY.value: 0,
    }

    retrieved_now = pd.Timestamp.now(tz="UTC")

    for _, b_row in unique_benes.iterrows():
        b_id = b_row["beneficiary_id"]
        b_name = b_row["beneficiary_name"]
        b_local_id = b_row["beneficiary_local_id"]
        p_list = bene_project_map.get(b_id, [])

        # Gather counties from associated projects
        nuts_codes: list[str] = []
        lau_sirutas: list[int] = []
        for p in p_list:
            if p.get("nuts3_code"):
                for piece in str(p["nuts3_code"]).split("|"):
                    piece = piece.strip()
                    if piece in nuts_map:
                        nuts_codes.append(nuts_map[piece])
            if p.get("lau_ids"):
                for piece in str(p["lau_ids"]).split("|"):
                    piece = piece.strip()
                    if piece.startswith("RO_") and piece[3:].isdigit():
                        lau_sirutas.append(int(piece[3:]))

        counties = sorted(list(set(nuts_codes)))
        lau_sirutas = sorted(list(set(lau_sirutas)))

        # Classification
        if is_county_council(b_name):
            matches_by_method_counts[MatchMethod.COUNTY_COUNCIL.value] += 1
            match_records.append({
                "beneficiary_id": b_id,
                "beneficiary_name": b_name,
                "beneficiary_local_id": b_local_id,
                "siruta": None,
                "uat_name": None,
                "county_code": counties[0] if counties else None,
                "match_method": MatchMethod.COUNTY_COUNCIL.value,
                "match_confidence": MatchConfidence.NONE.value,
                "evidence": "Identified as County Council / Județ entity",
                "source_id": SOURCE_ID,
                "retrieved_at": retrieved_now,
            })
            continue

        if is_other_body(b_name):
            matches_by_method_counts[MatchMethod.OTHER_BODY.value] += 1
            match_records.append({
                "beneficiary_id": b_id,
                "beneficiary_name": b_name,
                "beneficiary_local_id": b_local_id,
                "siruta": None,
                "uat_name": None,
                "county_code": counties[0] if counties else None,
                "match_method": MatchMethod.OTHER_BODY.value,
                "match_confidence": MatchConfidence.NONE.value,
                "evidence": "Identified as commercial company / non-UAT public or private body",
                "source_id": SOURCE_ID,
                "retrieved_at": retrieved_now,
            })
            continue

        if not is_local_authority(b_name):
            matches_by_method_counts[MatchMethod.OTHER_BODY.value] += 1
            match_records.append({
                "beneficiary_id": b_id,
                "beneficiary_name": b_name,
                "beneficiary_local_id": b_local_id,
                "siruta": None,
                "uat_name": None,
                "county_code": counties[0] if counties else None,
                "match_method": MatchMethod.OTHER_BODY.value,
                "match_confidence": MatchConfidence.NONE.value,
                "evidence": "Unclassified entity (no local authority keywords)",
                "source_id": SOURCE_ID,
                "retrieved_at": retrieved_now,
            })
            continue

        # Local authority candidate matching
        cleaned = clean_kohesio_beneficiary_name(b_name)
        key = normalise_name(cleaned).key

        # Special Bucharest sector resolution
        m_sec = re.match(r"^(?:sector(?:ul)?\s*)?([1-6])$", cleaned.strip(), re.IGNORECASE)
        if m_sec:
            sec_num = m_sec.group(1)
            key = f"bucuresti sectorul {sec_num}"
            if "B" not in counties:
                counties.append("B")

        found_uat = None
        method_used = MatchMethod.NAME_COUNTY_EXACT

        # 1. Exact match on (name_key, county)
        for c in counties:
            if (key, c) in uat_by_name_county:
                found_uat = uat_by_name_county[(key, c)]
                break

        # 2. Orthographic vowel variation (singeorz <-> sangeorz, sinmartin <-> sanmartin, tg/tirgu)
        if found_uat is None:
            key_alt = (
                key.replace("singeorz", "sangeorz")
                .replace("sangeorz", "singeorz")
                .replace("sinmartin", "sanmartin")
                .replace("sanmartin", "sinmartin")
                .replace("tg ", "targu ")
                .replace("tirgu ", "targu ")
                .replace("birlad", "barlad")
                .replace("vilcelele", "valcelele")
            )
            for c in counties:
                if (key_alt, c) in uat_by_name_county:
                    found_uat = uat_by_name_county[(key_alt, c)]
                    method_used = MatchMethod.NAME_COUNTY_NORMALISED
                    break

        if found_uat is not None:
            # Check LAU code disagreement
            # Where LAU_IDs is present and disagrees with name-plus-county match, send to review
            lau_disagreement = False
            if lau_sirutas and found_uat["siruta"] not in lau_sirutas:
                # If LAU siruta points to a different UAT altogether
                lau_disagreement = True

            if lau_disagreement:
                matches_by_method_counts[MatchMethod.UNMATCHED_LOCAL_AUTHORITY.value] += 1
                evidence_text = (
                    f"Name-county matched {found_uat['name']} ({found_uat['county_code']}) "
                    f"but project LAU_IDs {lau_sirutas} disagrees"
                )
                match_records.append({
                    "beneficiary_id": b_id,
                    "beneficiary_name": b_name,
                    "beneficiary_local_id": b_local_id,
                    "siruta": None,
                    "uat_name": found_uat["name"],
                    "county_code": found_uat["county_code"],
                    "match_method": MatchMethod.UNMATCHED_LOCAL_AUTHORITY.value,
                    "match_confidence": MatchConfidence.LOW.value,
                    "evidence": evidence_text,
                    "source_id": SOURCE_ID,
                    "retrieved_at": retrieved_now,
                })
                review_records.append({
                    "beneficiary_id": b_id,
                    "beneficiary_name": b_name,
                    "beneficiary_local_id": b_local_id,
                    "candidate_siruta": found_uat["siruta"],
                    "candidate_uat_name": found_uat["name"],
                    "county_code": found_uat["county_code"],
                    "reason": "lau_disagreement",
                    "evidence": evidence_text,
                })
            else:
                matches_by_method_counts[method_used.value] += 1
                evidence_text = (
                    f"Matched {found_uat['name']} in county {found_uat['county_code']} "
                    f"via {method_used.value}"
                    + (f", verified by LAU_IDs {lau_sirutas}" if lau_sirutas else "")
                )
                conf = (
                    MatchConfidence.HIGH.value
                    if method_used == MatchMethod.NAME_COUNTY_EXACT
                    else MatchConfidence.MEDIUM.value
                )
                match_records.append({
                    "beneficiary_id": b_id,
                    "beneficiary_name": b_name,
                    "beneficiary_local_id": b_local_id,
                    "siruta": found_uat["siruta"],
                    "uat_name": found_uat["name"],
                    "county_code": found_uat["county_code"],
                    "match_method": method_used.value,
                    "match_confidence": conf,
                    "evidence": evidence_text,
                    "source_id": SOURCE_ID,
                    "retrieved_at": retrieved_now,
                })
                confirmed_uat_matches.append({
                    "siruta": found_uat["siruta"],
                    "fiscal_code": b_local_id,
                    "beneficiary_id": b_id,
                    "uat_name": found_uat["name"],
                    "county_code": found_uat["county_code"],
                    "project_count": len(p_list),
                    "evidence": evidence_text,
                })
        else:
            # Check if name matches a component locality (village)
            loc_candidate = None
            for c in counties:
                if (key, c) in loc_by_name_county:
                    loc_candidate = loc_by_name_county[(key, c)]
                    break

            if loc_candidate is not None:
                matches_by_method_counts[MatchMethod.LOCALITY_CANDIDATE.value] += 1
                evidence_text = (
                    f"Matched component locality '{loc_candidate['loc_name']}' under parent UAT "
                    f"'{loc_candidate['uat_name']}' (SIRUTA {loc_candidate['parent_uat_siruta']}) "
                    f"in county {loc_candidate['county_code']}"
                )
                match_records.append({
                    "beneficiary_id": b_id,
                    "beneficiary_name": b_name,
                    "beneficiary_local_id": b_local_id,
                    "siruta": None,
                    "uat_name": loc_candidate["uat_name"],
                    "county_code": loc_candidate["county_code"],
                    "match_method": MatchMethod.LOCALITY_CANDIDATE.value,
                    "match_confidence": MatchConfidence.LOW.value,
                    "evidence": evidence_text,
                    "source_id": SOURCE_ID,
                    "retrieved_at": retrieved_now,
                })
                review_records.append({
                    "beneficiary_id": b_id,
                    "beneficiary_name": b_name,
                    "beneficiary_local_id": b_local_id,
                    "candidate_siruta": loc_candidate["parent_uat_siruta"],
                    "candidate_uat_name": loc_candidate["uat_name"],
                    "county_code": loc_candidate["county_code"],
                    "reason": "locality_candidate",
                    "evidence": evidence_text,
                })
            else:
                matches_by_method_counts[MatchMethod.UNMATCHED_LOCAL_AUTHORITY.value] += 1
                evidence_text = (
                    f"Unmatched local authority; cleaned='{cleaned}', key='{key}', "
                    f"counties={counties}"
                )
                match_records.append({
                    "beneficiary_id": b_id,
                    "beneficiary_name": b_name,
                    "beneficiary_local_id": b_local_id,
                    "siruta": None,
                    "uat_name": None,
                    "county_code": counties[0] if counties else None,
                    "match_method": MatchMethod.UNMATCHED_LOCAL_AUTHORITY.value,
                    "match_confidence": MatchConfidence.NONE.value,
                    "evidence": evidence_text,
                    "source_id": SOURCE_ID,
                    "retrieved_at": retrieved_now,
                })
                review_records.append({
                    "beneficiary_id": b_id,
                    "beneficiary_name": b_name,
                    "beneficiary_local_id": b_local_id,
                    "candidate_siruta": None,
                    "candidate_uat_name": None,
                    "county_code": counties[0] if counties else None,
                    "reason": "unmatched_name_county",
                    "evidence": evidence_text,
                })

    matches_df = pd.DataFrame(match_records)
    review_df = pd.DataFrame(review_records)

    # 5. Build uat_fiscal_codes.parquet from confirmed matches ONLY
    fiscal_codes_records: list[dict[str, Any]] = []
    # Collect all (siruta, fiscal_code) pairs
    fc_pairs: list[dict[str, Any]] = []
    for m in confirmed_uat_matches:
        raw_fc = str(m.get("fiscal_code") or "").strip()
        if raw_fc and raw_fc.isdigit():
            fc_pairs.append({
                "siruta": m["siruta"],
                "fiscal_code": raw_fc,
                "project_count": m["project_count"],
                "evidence": m["evidence"],
            })

    fc_df = pd.DataFrame(fc_pairs)
    multi_uat_fc_count = 0
    multi_fc_uat_count = 0

    if not fc_df.empty:
        grouped_fc = (
            fc_df.groupby(["siruta", "fiscal_code"])
            .agg(number_of_projects=("project_count", "sum"))
            .reset_index()
        )

        # Count multi-mappings
        fc_to_siruta = grouped_fc.groupby("fiscal_code")["siruta"].nunique()
        multi_uat_fcs = set(fc_to_siruta[fc_to_siruta > 1].index)
        multi_uat_fc_count = len(multi_uat_fcs)

        siruta_to_fc = grouped_fc.groupby("siruta")["fiscal_code"].nunique()
        multi_fc_uats = set(siruta_to_fc[siruta_to_fc > 1].index)
        multi_fc_uat_count = len(multi_fc_uats)

        for _, r in grouped_fc.iterrows():
            s_code = int(r["siruta"])
            fc_val = str(r["fiscal_code"])
            n_proj = int(r["number_of_projects"])
            is_multi_uat = fc_val in multi_uat_fcs
            is_multi_fc = s_code in multi_fc_uats
            flags = []
            if is_multi_uat:
                flags.append("FLAG: fiscal code maps to multiple UATs")
            if is_multi_fc:
                flags.append("FLAG: UAT has multiple fiscal codes")
            evidence_str = (
                f"Confirmed UAT match across {n_proj} project(s)"
                + (f" [{'; '.join(flags)}]" if flags else "")
            )
            fiscal_codes_records.append({
                "siruta": s_code,
                "fiscal_code": fc_val,
                "number_of_projects": n_proj,
                "is_multi_uat_fiscal_code": is_multi_uat,
                "is_multi_fiscal_code_uat": is_multi_fc,
                "evidence": evidence_str,
            })

    fiscal_codes_df = pd.DataFrame(fiscal_codes_records)

    # 6. Top 20 UATs ranked by EU co-financing
    # Join confirmed UAT matches to projects
    confirmed_siruta_map = {
        m["beneficiary_id"]: m["siruta"] for m in confirmed_uat_matches if m["siruta"] is not None
    }
    # Map project to set of distinct confirmed UAT SIRUTAs
    proj_to_uats: dict[str, set[int]] = {}
    for _, b_row in beneficiaries_df.iterrows():
        bid = b_row["beneficiary_id"]
        pid = b_row["project_id"]
        if bid in confirmed_siruta_map:
            s_id = confirmed_siruta_map[bid]
            if pid not in proj_to_uats:
                proj_to_uats[pid] = set()
            proj_to_uats[pid].add(s_id)

    # Calculate EU co-financing per UAT and shared amount (projects involving >1 UAT)
    uat_funds: dict[int, float] = {}
    uat_shared_funds: dict[int, float] = {}
    for _, p_row in dedup_projects_df.iterrows():
        pid = p_row["project_id"]
        uats_in_proj = proj_to_uats.get(pid, set())
        is_shared_proj = len(uats_in_proj) > 1
        b_pairs = beneficiaries_df[beneficiaries_df["project_id"] == pid]
        seen_sirutas_in_p = set()
        for _, b_row in b_pairs.iterrows():
            bid = b_row["beneficiary_id"]
            if bid in confirmed_siruta_map:
                s_id = confirmed_siruta_map[bid]
                if s_id not in seen_sirutas_in_p:
                    seen_sirutas_in_p.add(s_id)
                    amt = float(p_row["eu_budget"])
                    uat_funds[s_id] = uat_funds.get(s_id, 0.0) + amt
                    if is_shared_proj:
                        uat_shared_funds[s_id] = uat_shared_funds.get(s_id, 0.0) + amt

    top_20_list = []
    siruta_to_name = {r["siruta"]: (r["name"], r["county_code"]) for _, r in uats_df.iterrows()}
    for s_id, amt in sorted(uat_funds.items(), key=lambda x: x[1], reverse=True)[:20]:
        u_name, c_code = siruta_to_name.get(s_id, ("UNKNOWN", "UNKNOWN"))
        top_20_list.append({
            "siruta": s_id,
            "uat_name": u_name,
            "county_code": c_code,
            "total_eu_budget_eur": amt,
            "shared_eu_budget_eur": uat_shared_funds.get(s_id, 0.0),
        })

    # 7. Write Parquet and CSV Deliverables
    proc_dir = settings.data_dir / "processed"
    interim_dir = settings.data_dir / "interim" / "kohesio"
    proc_dir.mkdir(parents=True, exist_ok=True)
    interim_dir.mkdir(parents=True, exist_ok=True)

    # Schema definitions for parquet writes
    projects_schema = pa.schema([
        ("project_id", pa.string()),
        ("local_id", pa.string()),
        ("title", pa.string()),
        ("title_en", pa.string()),
        ("programme_code", pa.string()),
        ("programme_name", pa.string()),
        ("fund_code", pa.string()),
        ("fund_name", pa.string()),
        ("programming_period", pa.string()),
        ("total_eligible_expenditure_amount", pa.float64()),
        ("total_eligible_expenditure_currency", pa.string()),
        ("eu_budget", pa.float64()),
        ("cofinancing_rate", pa.float64()),
        ("start_date", pa.date32()),
        ("end_date", pa.date32()),
        ("has_multiple_beneficiaries", pa.bool_()),
        ("lau_ids", pa.string()),
        ("lau_labels", pa.string()),
        ("nuts3_code", pa.string()),
        ("nuts3_label", pa.string()),
        ("coordinates", pa.string()),
        ("source_id", pa.string()),
        ("source_url", pa.string()),
        ("retrieved_at", pa.timestamp("us", tz="UTC")),
        ("raw_sha256", pa.string()),
    ])
    projects_table = pa.Table.from_pandas(
        dedup_projects_df, schema=projects_schema, preserve_index=False
    )
    pq.write_table(projects_table, proc_dir / "kohesio_projects.parquet")

    beneficiaries_schema = pa.schema([
        ("project_id", pa.string()),
        ("beneficiary_id", pa.string()),
        ("beneficiary_name", pa.string()),
        ("beneficiary_local_id", pa.string()),
        ("is_local_authority", pa.bool_()),
        ("source_id", pa.string()),
        ("source_url", pa.string()),
        ("retrieved_at", pa.timestamp("us", tz="UTC")),
        ("raw_sha256", pa.string()),
    ])
    beneficiaries_table = pa.Table.from_pandas(
        beneficiaries_df, schema=beneficiaries_schema, preserve_index=False
    )
    pq.write_table(beneficiaries_table, proc_dir / "kohesio_beneficiaries.parquet")

    matches_schema = pa.schema([
        ("beneficiary_id", pa.string()),
        ("beneficiary_name", pa.string()),
        ("beneficiary_local_id", pa.string()),
        ("siruta", pa.int64()),
        ("uat_name", pa.string()),
        ("county_code", pa.string()),
        ("match_method", pa.string()),
        ("match_confidence", pa.string()),
        ("evidence", pa.string()),
        ("source_id", pa.string()),
        ("retrieved_at", pa.timestamp("us", tz="UTC")),
    ])
    matches_table = pa.Table.from_pandas(
        matches_df, schema=matches_schema, preserve_index=False
    )
    pq.write_table(matches_table, proc_dir / "beneficiary_uat_matches.parquet")

    fc_schema = pa.schema([
        ("siruta", pa.int64()),
        ("fiscal_code", pa.string()),
        ("number_of_projects", pa.int64()),
        ("is_multi_uat_fiscal_code", pa.bool_()),
        ("is_multi_fiscal_code_uat", pa.bool_()),
        ("evidence", pa.string()),
    ])
    if not fiscal_codes_df.empty:
        fc_table = pa.Table.from_pandas(fiscal_codes_df, schema=fc_schema, preserve_index=False)
        pq.write_table(fc_table, proc_dir / "uat_fiscal_codes.parquet")
    else:
        pq.write_table(
            pa.Table.from_arrays([[], [], [], [], [], []], schema=fc_schema),
            proc_dir / "uat_fiscal_codes.parquet",
        )

    # CSV write for review file
    review_csv_path = interim_dir / "match_review.csv"
    review_df.to_csv(review_csv_path, index=False, quoting=csv.QUOTE_NONNUMERIC)

    # Calculate metrics
    total_projects = len(dedup_projects_df)
    la_project_count = dedup_projects_df["project_id"].isin(
        beneficiaries_df[beneficiaries_df["is_local_authority"]]["project_id"]
    ).sum()
    share_pct = (la_project_count / total_projects * 100.0) if total_projects else 0.0

    la_beneficiaries = (
        matches_by_method_counts[MatchMethod.NAME_COUNTY_EXACT.value]
        + matches_by_method_counts[MatchMethod.NAME_COUNTY_NORMALISED.value]
        + matches_by_method_counts[MatchMethod.LOCALITY_CANDIDATE.value]
        + matches_by_method_counts[MatchMethod.UNMATCHED_LOCAL_AUTHORITY.value]
    )
    matched_la = (
        matches_by_method_counts[MatchMethod.NAME_COUNTY_EXACT.value]
        + matches_by_method_counts[MatchMethod.NAME_COUNTY_NORMALISED.value]
    )
    unmatched_la = (
        matches_by_method_counts[MatchMethod.LOCALITY_CANDIDATE.value]
        + matches_by_method_counts[MatchMethod.UNMATCHED_LOCAL_AUTHORITY.value]
    )

    metrics = KohesioMetrics(
        total_projects=total_projects,
        projects_14_20=total_rows_14,
        projects_21_27=total_rows_21,
        projects_with_la=int(la_project_count),
        la_project_share_pct=share_pct,
        total_beneficiaries=len(unique_benes),
        local_authority_beneficiaries=la_beneficiaries,
        matched_local_authorities=matched_la,
        ambiguous_or_unmatched_local_authorities=unmatched_la,
        matches_by_method=matches_by_method_counts,
        fund_totals_before_dedup=fund_totals_before,
        fund_totals_after_dedup=fund_totals_after,
        top_20_uats=top_20_list,
        unparseable_dates_count=unparseable_dates,
        multi_uat_fiscal_codes_count=multi_uat_fc_count,
        multi_fiscal_code_uats_count=multi_fc_uat_count,
    )

    return metrics
