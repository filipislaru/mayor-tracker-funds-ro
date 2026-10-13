"""Normalise official mayoral election results (2020 and 2024).

Implements parsing of polling-station records, aggregation to UAT race level,
candidate ranking, tiebreaks with Round 2 runoff data, date assignments,
uncontested race handling, party alias standardisation, and county x party reconciliation.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from mayortracker.schemas.elections import (
    MayorCandidateRecord,
    MayorRaceRecord,
    MayorTermRecord,
    PollingStationMayorRecord,
)
from mayortracker.util.names import normalise_name

if TYPE_CHECKING:
    from mayortracker.util.config import Settings

logger = logging.getLogger(__name__)

SOURCE_ID = "aep_local"
BUCHAREST_SIRUTA = 179132


def load_party_aliases(config_path: Path) -> dict[int, dict[str, dict[str, Any]]]:
    """Load config/party_aliases.yaml mapping (year -> party_raw -> info)."""
    if not config_path.is_file():
        logger.warning("Party aliases config missing at %s", config_path)
        return {2020: {}, 2024: {}}
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    result: dict[int, dict[str, dict[str, Any]]] = {2020: {}, 2024: {}}
    for yr in (2020, 2024):
        for entry in data.get("parties", {}).get(yr, []):
            raw = entry.get("party_raw", "").strip()
            if raw:
                result[yr][raw] = entry
    return result


def _standardise_diacritics(s: str) -> str:
    trans = str.maketrans({"ş": "ș", "Ş": "Ș", "ţ": "ț", "Ţ": "Ț"})
    return re.sub(r"\s+", " ", s.translate(trans)).strip()


def parse_competitor_2024(
    raw_comp: str,
    known_parties: set[str],
    alias_map: dict[str, dict[str, Any]],
) -> tuple[str | None, str, str | None, bool, bool]:
    """Parse 2024 competitor string.

    Returns:
        (cand_name, party_raw, party_normalised, is_indep, is_alliance)
    """
    s = raw_comp.strip()
    if s.endswith("-voturi"):
        s = s[:-7].strip()
    if s.startswith("g-"):
        s = s[2:].strip()

    if s.endswith("--CI"):
        raw_name = s[:-4].strip()
        norm_name = normalise_name(raw_name).display if raw_name else None
        return norm_name, "CANDIDAT INDEPENDENT", None, True, False
    if s.endswith("-CI"):
        raw_name = s[:-3].strip()
        norm_name = normalise_name(raw_name).display if raw_name else None
        return norm_name, "CANDIDAT INDEPENDENT", None, True, False

    # Try matching known party suffixes from longest to shortest
    for p in sorted(known_parties, key=len, reverse=True):
        if s.endswith("-" + p):
            raw_name = s[: -(len(p) + 1)].strip()
            norm_name = normalise_name(raw_name).display if raw_name else None
            party_info = alias_map.get(p)
            party_norm = (
                party_info.get("party_normalised")
                if party_info
                else _standardise_diacritics(p)
            )
            is_alliance = (
                party_info.get("is_alliance", False)
                if party_info
                else (p.upper().startswith("ALIAN") or p.upper().startswith("ALIN"))
            )
            return norm_name, p, party_norm, False, is_alliance

    # Fallback right split
    parts = s.rsplit("-", 1)
    if len(parts) == 2:
        raw_name, p = parts[0].strip(), parts[1].strip()
        norm_name = normalise_name(raw_name).display if raw_name else None
        party_info = alias_map.get(p)
        party_norm = (
            party_info.get("party_normalised") if party_info else _standardise_diacritics(p)
        )
        is_alliance = (
            party_info.get("is_alliance", False)
            if party_info
            else (p.upper().startswith("ALIAN") or p.upper().startswith("ALIN"))
        )
        return norm_name, p, party_norm, False, is_alliance

    norm_name = normalise_name(s).display if s else None
    return norm_name, s, _standardise_diacritics(s), False, False


def get_manifest_provenance(
    raw_dir: Path, source_id: str
) -> dict[str, tuple[str, datetime, str]]:
    """Scan data/raw/<source_id>/<date>/manifest.json for file provenance details."""
    prov: dict[str, tuple[str, datetime, str]] = {}
    base = raw_dir / source_id
    if not base.is_dir():
        return prov
    for mpath in base.rglob("manifest.json"):
        try:
            entries = json.loads(mpath.read_text(encoding="utf-8"))
            for entry in entries:
                fname = entry.get("filename", "")
                url = entry.get("url", "")
                sha = entry.get("sha256", "")
                dt_str = entry.get("retrieved_at", "")
                dt = (
                    datetime.fromisoformat(dt_str)
                    if dt_str
                    else datetime.now()
                )
                if fname:
                    prov[fname] = (url, dt, sha)
        except Exception as e:
            logger.warning("Error reading manifest %s: %e", mpath, e)
    return prov


def normalise_elections(settings: Settings, year: int | None = None) -> dict[str, Any]:
    """Execute mayoral elections normalisation pipeline for 2020, 2024, or both."""
    data_dir = settings.data_dir
    raw_dir = data_dir / "raw"
    interim_dir = data_dir / "interim"
    processed_dir = data_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    cfg_dir = settings.config_path.parent if settings.config_path else Path("config")
    config_path = cfg_dir / "party_aliases.yaml"
    party_aliases = load_party_aliases(config_path)

    # Load valid UATs
    uat_path = processed_dir / "uat.parquet"
    if not uat_path.is_file():
        raise FileNotFoundError(f"Missing required UAT reference table: {uat_path}")

    conn = duckdb.connect()
    uat_records = conn.execute(
        'SELECT siruta FROM "data/processed/uat.parquet"'
    ).fetchall()
    valid_sirutas = {r[0] for r in uat_records}

    prov = get_manifest_provenance(raw_dir, SOURCE_ID)

    years_to_run = [year] if year in (2020, 2024) else [2020, 2024]

    all_candidates: list[dict[str, Any]] = []
    all_races: list[dict[str, Any]] = []
    all_terms: list[dict[str, Any]] = []
    all_stations: list[dict[str, Any]] = []

    metrics: dict[str, Any] = {}

    for yr in years_to_run:
        logger.info("Processing election year %d...", yr)
        if yr == 2020:
            cands, races, terms, stations, m = _process_2020(
                raw_dir, interim_dir, valid_sirutas, party_aliases[2020], prov
            )
        else:
            cands, races, terms, stations, m = _process_2024(
                raw_dir, interim_dir, valid_sirutas, party_aliases[2024], prov
            )
        all_candidates.extend(cands)
        all_races.extend(races)
        all_terms.extend(terms)
        all_stations.extend(stations)
        metrics[yr] = m

    # Save to Parquet tables
    _write_parquet_tables(
        processed_dir, all_candidates, all_races, all_terms, all_stations, years_to_run
    )

    return metrics


ProcessResult = tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]


def _process_2020(
    raw_dir: Path,
    interim_dir: Path,
    valid_sirutas: set[int],
    alias_map: dict[str, dict[str, Any]],
    prov: dict[str, tuple[str, datetime, str]],
) -> ProcessResult:
    conn = duckdb.connect()

    # Find raw files
    raw_files = list((raw_dir / "aep_local").rglob("bd_sectii_27.09.2020+24.01.2021.csv"))
    if not raw_files:
        raise FileNotFoundError("Missing 2020 raw file: bd_sectii_27.09.2020+24.01.2021.csv")
    main_csv = raw_files[0]
    runoff_csv = main_csv.parent / "bd_p_11.10.2020.csv"

    default_prov = (
        "https://www.roaep.ro/prezentare/wp-content/uploads/2025/02/Alegeri-locale-2020.zip",
        datetime.now(),
        "",
    )
    url, dt, sha = prov.get(main_csv.name, default_prov)
    r_url, r_dt, r_sha = prov.get(runoff_csv.name, (url, dt, sha))

    # Read distinct polling station voter totals for Round 1
    # Note: For PG, stations in sectors vote for Bucharest General Mayor (siruta 179132)
    # For P, stations vote for local mayor
    # Polling station records query
    # Quote='"' ensures school names with semicolons are parsed cleanly
    main_df = conn.execute(f"""
        SELECT 
            Tip,
            county_nce,
            county_name,
            nr_sv,
            uat_siruta,
            cast(a as bigint) as a,
            cast(b as bigint) as b,
            cast(c as bigint) as c,
            Competitor,
            cast(VVE as bigint) as votes
        FROM read_csv('{main_csv}', delim=';', header=True, quote='"', all_varchar=True)
        WHERE Tip IN ('P', 'PG')
    """).fetchall()

    runoff_df = conn.execute(f"""
        SELECT 
            county_nce,
            county_name,
            nr_sv,
            uat_siruta,
            cast(a as bigint) as a,
            cast(b as bigint) as b,
            cast(c as bigint) as c,
            Competitor,
            cast(TVVE as bigint) as votes
        FROM read_csv('{runoff_csv}', delim=';', header=True, quote='"', all_varchar=True)
    """).fetchall()

    # Organize Round 1 votes
    # races: siruta -> {
    #   'stations': dict (station_id -> {a, b, c}),
    #   'candidates': dict (comp -> votes)
    # }
    races_r1: dict[int, dict[str, Any]] = {}
    stations_out: list[dict[str, Any]] = []

    for row in main_df:
        tip, c_nce, c_name, nr_sv, uat_siruta_raw, a_val, b_val, c_val, comp, votes = row
        siruta = BUCHAREST_SIRUTA if tip == "PG" else int(uat_siruta_raw)
        station_id = f"{c_nce}-{nr_sv}"

        if siruta not in races_r1:
            races_r1[siruta] = {"stations": {}, "candidates": {}}
        if station_id not in races_r1[siruta]["stations"]:
            races_r1[siruta]["stations"][station_id] = (a_val, b_val, c_val)
        races_r1[siruta]["candidates"][comp] = races_r1[siruta]["candidates"].get(comp, 0) + votes

    # Organize Round 2 votes
    # tied UATs: 151996 (Balaci), 34262 (Rebra), 158010 (Orțișoara)
    races_r2: dict[int, dict[str, Any]] = {}
    for row in runoff_df:
        c_nce, c_name, nr_sv, uat_siruta_raw, a_val, b_val, c_val, comp, votes = row
        siruta = int(uat_siruta_raw)
        station_id = f"{c_nce}-{nr_sv}"
        if siruta not in races_r2:
            races_r2[siruta] = {"stations": {}, "candidates": {}}
        if station_id not in races_r2[siruta]["stations"]:
            races_r2[siruta]["stations"][station_id] = (a_val, b_val, c_val)
        races_r2[siruta]["candidates"][comp] = races_r2[siruta]["candidates"].get(comp, 0) + votes

    # Build candidates, races, and terms
    candidates_out: list[dict[str, Any]] = []
    races_out: list[dict[str, Any]] = []
    terms_out: list[dict[str, Any]] = []

    # Map candidate_id to candidate row for station linking
    cand_id_map: dict[tuple[int, int, str], str] = {}  # (siruta, round, comp) -> cand_id

    discrepancy_count = 0
    max_discrepancy = 0
    uncontested_count = 0
    named_candidates_count = 0
    named_winners_count = 0

    for siruta, r1_info in sorted(races_r1.items()):
        is_tied_r1 = siruta in races_r2
        decided_in_round = 2 if is_tied_r1 else 1

        # Sum station totals
        reg_r1 = sum(st[0] for st in r1_info["stations"].values())
        cast_r1 = sum(st[1] for st in r1_info["stations"].values())
        valid_r1 = sum(st[2] for st in r1_info["stations"].values())

        # Sort Round 1 candidates
        sorted_comps_r1 = sorted(r1_info["candidates"].items(), key=lambda x: x[1], reverse=True)
        sum_cand_votes_r1 = sum(v for _, v in sorted_comps_r1)
        disc_r1 = abs(sum_cand_votes_r1 - valid_r1)
        if disc_r1 > 0:
            discrepancy_count += 1
            if disc_r1 > max_discrepancy:
                max_discrepancy = disc_r1

        n_cands_r1 = len(sorted_comps_r1)
        is_uncontested = n_cands_r1 == 1

        # Round 1 margin
        if is_uncontested:
            round1_margin_pp = None
        elif is_tied_r1:
            round1_margin_pp = 0.0
        else:
            rank1_v = sorted_comps_r1[0][1]
            rank2_v = sorted_comps_r1[1][1]
            round1_margin_pp = (
                round((rank1_v - rank2_v) / valid_r1 * 100.0, 4)
                if valid_r1 > 0
                else 0.0
            )

        # Build candidate records for Round 1
        for rank, (comp, votes) in enumerate(sorted_comps_r1, start=1):
            cand_id = f"2020-{siruta}-r1-{rank}"
            cand_id_map[(siruta, 1, comp)] = cand_id
            v_share = round(votes / valid_r1 * 100.0, 4) if valid_r1 > 0 else 0.0

            # 2020 names: party nominees have null, independents have name
            is_indep = comp.startswith("CANDIDAT INDEPENDENT-")
            if is_indep:
                raw_name = comp[21:].strip()
                n = normalise_name(raw_name)
                cand_name, name_key = n.display, n.key
                party_raw = comp
                party_norm = None
                is_alliance = False
                named_candidates_count += 1
            else:
                cand_name = None
                name_key = None
                party_raw = comp
                p_info = alias_map.get(comp)
                party_norm = (
                    p_info.get("party_normalised")
                    if p_info
                    else _standardise_diacritics(comp)
                )
                is_alliance = (
                    p_info.get("is_alliance", False)
                    if p_info
                    else (comp.upper().startswith("ALIAN") or comp.upper().startswith("ALIN"))
                )

            is_winner = (decided_in_round == 1) and (rank == 1)
            candidates_out.append({
                "year": 2020,
                "siruta": siruta,
                "round": 1,
                "candidate_id": cand_id,
                "candidate_name": cand_name,
                "name_key": name_key,
                "party_raw": party_raw,
                "party_normalised": party_norm,
                "is_independent": is_indep,
                "is_alliance": is_alliance,
                "votes": votes,
                "vote_share": v_share,
                "rank": rank,
                "is_winner": is_winner,
                "source_id": SOURCE_ID,
                "source_url": url,
                "retrieved_at": dt,
                "raw_sha256": sha,
            })

        # If decided in Round 2: process Round 2 candidates
        if is_tied_r1:
            r2_info = races_r2[siruta]
            reg_r2 = sum(st[0] for st in r2_info["stations"].values())
            cast_r2 = sum(st[1] for st in r2_info["stations"].values())
            valid_r2 = sum(st[2] for st in r2_info["stations"].values())

            sorted_comps_r2 = sorted(
                r2_info["candidates"].items(), key=lambda x: x[1], reverse=True
            )
            for rank, (comp, votes) in enumerate(sorted_comps_r2, start=1):
                cand_id = f"2020-{siruta}-r2-{rank}"
                cand_id_map[(siruta, 2, comp)] = cand_id
                v_share = round(votes / valid_r2 * 100.0, 4) if valid_r2 > 0 else 0.0

                is_indep = comp.startswith("CANDIDAT INDEPENDENT-")
                if is_indep:
                    raw_name = comp[21:].strip()
                    n = normalise_name(raw_name)
                    cand_name, name_key = n.display, n.key
                    party_raw = comp
                    party_norm = None
                    is_alliance = False
                    named_candidates_count += 1
                else:
                    cand_name = None
                    name_key = None
                    party_raw = comp
                    p_info = alias_map.get(comp)
                    party_norm = (
                        p_info.get("party_normalised")
                        if p_info
                        else _standardise_diacritics(comp)
                    )
                    is_alliance = (
                        p_info.get("is_alliance", False)
                        if p_info
                        else (comp.upper().startswith("ALIAN") or comp.upper().startswith("ALIN"))
                    )

                is_winner = rank == 1
                candidates_out.append({
                    "year": 2020,
                    "siruta": siruta,
                    "round": 2,
                    "candidate_id": cand_id,
                    "candidate_name": cand_name,
                    "name_key": name_key,
                    "party_raw": party_raw,
                    "party_normalised": party_norm,
                    "is_independent": is_indep,
                    "is_alliance": is_alliance,
                    "votes": votes,
                    "vote_share": v_share,
                    "rank": rank,
                    "is_winner": is_winner,
                    "source_id": SOURCE_ID,
                    "source_url": r_url,
                    "retrieved_at": r_dt,
                    "raw_sha256": r_sha,
                })

            deciding_sorted = sorted_comps_r2
            deciding_valid = valid_r2
            deciding_reg = reg_r2
            deciding_cast = cast_r2
            deciding_url = r_url
            deciding_dt = r_dt
            deciding_sha = r_sha
            election_date = date(2020, 10, 11)
            is_repeated = False
        else:
            deciding_sorted = sorted_comps_r1
            deciding_valid = valid_r1
            deciding_reg = reg_r1
            deciding_cast = cast_r1
            deciding_url = url
            deciding_dt = dt
            deciding_sha = sha
            if siruta == 51056:  # Moldova Nouă
                election_date = date(2021, 1, 24)
                is_repeated = True
            else:
                election_date = date(2020, 9, 27)
                is_repeated = False

        # Compute deciding round margins and winner
        winner_comp, winner_votes = deciding_sorted[0]
        winner_cand_id = f"2020-{siruta}-r{decided_in_round}-1"
        winner_share = (
            round(winner_votes / deciding_valid * 100.0, 4)
            if deciding_valid > 0
            else 0.0
        )

        if is_uncontested:
            uncontested_count += 1
            runner_up_share = None
            margin_pp = None
        else:
            runner_up_comp, runner_up_votes = deciding_sorted[1]
            runner_up_share = (
                round(runner_up_votes / deciding_valid * 100.0, 4)
                if deciding_valid > 0
                else 0.0
            )
            margin_pp = (
                round((winner_votes - runner_up_votes) / deciding_valid * 100.0, 4)
                if deciding_valid > 0
                else 0.0
            )

        races_out.append({
            "year": 2020,
            "siruta": siruta,
            "election_date": election_date,
            "decided_in_round": decided_in_round,
            "is_uncontested": is_uncontested,
            "registered_voters": deciding_reg,
            "votes_cast": deciding_cast,
            "valid_votes": deciding_valid,
            "n_candidates": len(deciding_sorted),
            "winner_candidate_id": winner_cand_id,
            "winner_vote_share": winner_share,
            "runner_up_vote_share": runner_up_share,
            "round1_margin_pp": round1_margin_pp,
            "margin_pp": margin_pp,
            "is_repeated_or_annulled": is_repeated,
            "source_id": SOURCE_ID,
            "source_url": deciding_url,
            "retrieved_at": deciding_dt,
            "raw_sha256": deciding_sha,
        })

        # Mayor term
        winner_is_indep = winner_comp.startswith("CANDIDAT INDEPENDENT-")
        if winner_is_indep:
            mayor_name = normalise_name(winner_comp[21:].strip()).display
            winner_p_norm = None
            named_winners_count += 1
        else:
            mayor_name = None
            winner_p_info = alias_map.get(winner_comp)
            winner_p_norm = (
                winner_p_info.get("party_normalised")
                if winner_p_info
                else _standardise_diacritics(winner_comp)
            )

        terms_out.append({
            "term_id": f"2020-{siruta}",
            "siruta": siruta,
            "election_year": 2020,
            "term_start": None,
            "planned_term_end": None,
            "candidate_id": winner_cand_id,
            "mayor_name": mayor_name,
            "party_normalised": winner_p_norm,
            "margin_pp": margin_pp,
        })

    # Build polling station table for 2020
    for row in main_df:
        tip, c_nce, c_name, nr_sv, uat_siruta_raw, _, _, _, comp, votes = row
        siruta = BUCHAREST_SIRUTA if tip == "PG" else int(uat_siruta_raw)
        station_id = f"{c_nce}-{nr_sv}"
        cand_id = cand_id_map.get((siruta, 1, comp), "")
        cand_name = comp[21:].strip() if comp.startswith("CANDIDAT INDEPENDENT-") else None
        norm_cand_name = normalise_name(cand_name).display if cand_name else None
        stations_out.append({
            "year": 2020,
            "siruta": siruta,
            "round": 1,
            "station_id": station_id,
            "candidate_id": cand_id,
            "candidate_name": norm_cand_name,
            "party_raw": comp,
            "votes": votes,
            "source_id": SOURCE_ID,
            "source_url": url,
            "retrieved_at": dt,
            "raw_sha256": sha,
        })

    for row in runoff_df:
        c_nce, c_name, nr_sv, uat_siruta_raw, _, _, _, comp, votes = row
        siruta = int(uat_siruta_raw)
        station_id = f"{c_nce}-{nr_sv}"
        cand_id = cand_id_map.get((siruta, 2, comp), "")
        cand_name = comp[21:].strip() if comp.startswith("CANDIDAT INDEPENDENT-") else None
        norm_cand_name = normalise_name(cand_name).display if cand_name else None
        stations_out.append({
            "year": 2020,
            "siruta": siruta,
            "round": 2,
            "station_id": station_id,
            "candidate_id": cand_id,
            "candidate_name": norm_cand_name,
            "party_raw": comp,
            "votes": votes,
            "source_id": SOURCE_ID,
            "source_url": r_url,
            "retrieved_at": r_dt,
            "raw_sha256": r_sha,
        })

    metrics = {
        "year": 2020,
        "total_races": len(races_out),
        "uncontested_races": uncontested_count,
        "discrepancy_races": discrepancy_count,
        "max_discrepancy": max_discrepancy,
        "named_candidates": named_candidates_count,
        "named_winners": named_winners_count,
        "candidates_count": len(candidates_out),
    }
    return candidates_out, races_out, terms_out, stations_out, metrics


def _process_2024(
    raw_dir: Path,
    interim_dir: Path,
    valid_sirutas: set[int],
    alias_map: dict[str, dict[str, Any]],
    prov: dict[str, tuple[str, datetime, str]],
) -> ProcessResult:
    conn = duckdb.connect()

    # Find 2024 files in interim (extracted from 7z)
    i_dir = interim_dir / "aep_local/2024/Alegeri locale 2024"
    main_csv = i_dir / "bd_sectii_09.06.2024+07.07.2024.csv"
    runoff_csv = i_dir / "bd_p_23.06.2024.csv"
    if not main_csv.is_file():
        raise FileNotFoundError(f"Missing 2024 file: {main_csv}")

    default_prov = (
        "https://www.roaep.ro/prezentare/wp-content/uploads/2025/02/Alegeri_locale_2024.7z",
        datetime.now(),
        "",
    )
    url, dt, sha = prov.get("Alegeri_locale_2024.7z", default_prov)

    # Known parties from pv_final headers
    known_parties: set[str] = set()
    for fname in ["pv_final_cntry_p.csv", "pv_final_cntry_cl.csv", "pv_final_cntry_cj.csv"]:
        fpath = interim_dir / f"aep_local/2024/Alegeri locale 2024/{fname}"
        if fpath.is_file():
            with open(fpath, encoding="utf-8") as f:
                r = csv.reader(f)
                h = next(r, [])
                for col in h:
                    if col.endswith("-voturi"):
                        p = col[:-7].strip()
                        if p != "Candidat Independent" and not p.startswith("Candidat Independent"):
                            known_parties.add(p)

    # Query Round 1 polling station records
    main_df = conn.execute(f"""
        SELECT 
            tip_alegeri,
            cod,
            nr_sv,
            siruta,
            cast(a as bigint) as a,
            cast(b as bigint) as b,
            cast(c as bigint) as c,
            Competitor,
            cast(VVE as bigint) as votes
        FROM read_csv('{main_csv}', delim=';', header=True, quote='"', all_varchar=True)
        WHERE tip_alegeri IN ('P', 'PG')
    """).fetchall()

    runoff_df = conn.execute(f"""
        SELECT 
            county_nce,
            nr_sv,
            uat_siruta,
            cast(a as bigint) as a,
            cast(b as bigint) as b,
            cast(c as bigint) as c,
            Competitor,
            cast(TVVE as bigint) as votes
        FROM read_csv('{runoff_csv}', delim=';', header=True, quote='"', all_varchar=True)
    """).fetchall()

    races_r1: dict[int, dict[str, Any]] = {}
    for row in main_df:
        tip, cod, nr_sv, siruta_raw, a_val, b_val, c_val, comp, votes = row
        siruta = BUCHAREST_SIRUTA if tip == "PG" else int(siruta_raw)
        station_id = f"{cod}-{nr_sv}"

        if siruta not in races_r1:
            races_r1[siruta] = {"stations": {}, "candidates": {}}
        if station_id not in races_r1[siruta]["stations"]:
            races_r1[siruta]["stations"][station_id] = (a_val, b_val, c_val)
        races_r1[siruta]["candidates"][comp] = races_r1[siruta]["candidates"].get(comp, 0) + votes

    races_r2: dict[int, dict[str, Any]] = {}
    for row in runoff_df:
        c_nce, nr_sv, uat_siruta_raw, a_val, b_val, c_val, comp, votes = row
        siruta = int(uat_siruta_raw)
        station_id = f"{c_nce}-{nr_sv}"
        if siruta not in races_r2:
            races_r2[siruta] = {"stations": {}, "candidates": {}}
        if station_id not in races_r2[siruta]["stations"]:
            races_r2[siruta]["stations"][station_id] = (a_val, b_val, c_val)
        races_r2[siruta]["candidates"][comp] = races_r2[siruta]["candidates"].get(comp, 0) + votes

    candidates_out: list[dict[str, Any]] = []
    races_out: list[dict[str, Any]] = []
    terms_out: list[dict[str, Any]] = []
    stations_out: list[dict[str, Any]] = []

    cand_id_map: dict[tuple[int, int, str], tuple[str, str | None, str]] = {}

    discrepancy_count = 0
    max_discrepancy = 0
    uncontested_count = 0
    named_candidates_count = 0
    named_winners_count = 0

    for siruta, r1_info in sorted(races_r1.items()):
        is_tied_r1 = siruta in races_r2
        decided_in_round = 2 if is_tied_r1 else 1

        reg_r1 = sum(st[0] for st in r1_info["stations"].values())
        cast_r1 = sum(st[1] for st in r1_info["stations"].values())
        valid_r1 = sum(st[2] for st in r1_info["stations"].values())

        # For Costinesti station 417: sum candidate votes as valid votes
        # if station reported duplicate counts
        sum_cand_votes_r1 = sum(r1_info["candidates"].values())
        if siruta == 63286:
            valid_r1 = sum_cand_votes_r1

        sorted_comps_r1 = sorted(
            r1_info["candidates"].items(), key=lambda x: x[1], reverse=True
        )
        disc_r1 = abs(sum_cand_votes_r1 - valid_r1)
        if disc_r1 > 0:
            discrepancy_count += 1
            if disc_r1 > max_discrepancy:
                max_discrepancy = disc_r1

        n_cands_r1 = len(sorted_comps_r1)
        is_uncontested = n_cands_r1 == 1

        if is_uncontested:
            round1_margin_pp = None
        elif is_tied_r1:
            round1_margin_pp = 0.0
        else:
            rank1_v = sorted_comps_r1[0][1]
            rank2_v = sorted_comps_r1[1][1]
            round1_margin_pp = (
                round((rank1_v - rank2_v) / valid_r1 * 100.0, 4)
                if valid_r1 > 0
                else 0.0
            )

        # Build candidate records for Round 1
        for rank, (comp, votes) in enumerate(sorted_comps_r1, start=1):
            cand_id = f"2024-{siruta}-r1-{rank}"
            c_name, p_raw, p_norm, is_indep, is_alliance = parse_competitor_2024(
                comp, known_parties, alias_map
            )
            cand_id_map[(siruta, 1, comp)] = (cand_id, c_name, p_raw)

            name_key = normalise_name(c_name).key if c_name else None
            if c_name:
                named_candidates_count += 1

            v_share = round(votes / valid_r1 * 100.0, 4) if valid_r1 > 0 else 0.0
            is_winner = (decided_in_round == 1) and (rank == 1)

            candidates_out.append({
                "year": 2024,
                "siruta": siruta,
                "round": 1,
                "candidate_id": cand_id,
                "candidate_name": c_name,
                "name_key": name_key,
                "party_raw": p_raw,
                "party_normalised": p_norm,
                "is_independent": is_indep,
                "is_alliance": is_alliance,
                "votes": votes,
                "vote_share": v_share,
                "rank": rank,
                "is_winner": is_winner,
                "source_id": SOURCE_ID,
                "source_url": url,
                "retrieved_at": dt,
                "raw_sha256": sha,
            })

        if is_tied_r1:
            r2_info = races_r2[siruta]
            reg_r2 = sum(st[0] for st in r2_info["stations"].values())
            cast_r2 = sum(st[1] for st in r2_info["stations"].values())
            valid_r2 = sum(st[2] for st in r2_info["stations"].values())

            sorted_comps_r2 = sorted(
                r2_info["candidates"].items(), key=lambda x: x[1], reverse=True
            )
            for rank, (comp, votes) in enumerate(sorted_comps_r2, start=1):
                cand_id = f"2024-{siruta}-r2-{rank}"
                c_name, p_raw, p_norm, is_indep, is_alliance = parse_competitor_2024(
                    comp, known_parties, alias_map
                )
                cand_id_map[(siruta, 2, comp)] = (cand_id, c_name, p_raw)
                name_key = normalise_name(c_name).key if c_name else None
                if c_name:
                    named_candidates_count += 1

                v_share = round(votes / valid_r2 * 100.0, 4) if valid_r2 > 0 else 0.0
                is_winner = rank == 1

                candidates_out.append({
                    "year": 2024,
                    "siruta": siruta,
                    "round": 2,
                    "candidate_id": cand_id,
                    "candidate_name": c_name,
                    "name_key": name_key,
                    "party_raw": p_raw,
                    "party_normalised": p_norm,
                    "is_independent": is_indep,
                    "is_alliance": is_alliance,
                    "votes": votes,
                    "vote_share": v_share,
                    "rank": rank,
                    "is_winner": is_winner,
                    "source_id": SOURCE_ID,
                    "source_url": url,
                    "retrieved_at": dt,
                    "raw_sha256": sha,
                })

            deciding_sorted = sorted_comps_r2
            deciding_valid = valid_r2
            deciding_reg = reg_r2
            deciding_cast = cast_r2
            election_date = date(2024, 6, 23)
            is_repeated = False
        else:
            deciding_sorted = sorted_comps_r1
            deciding_valid = valid_r1
            deciding_reg = reg_r1
            deciding_cast = cast_r1
            if siruta == 63286:  # Costinești
                election_date = date(2024, 7, 7)
                is_repeated = True
            else:
                election_date = date(2024, 6, 9)
                is_repeated = False

        winner_comp, winner_votes = deciding_sorted[0]
        winner_cand_id = f"2024-{siruta}-r{decided_in_round}-1"
        winner_c_name, winner_p_raw, winner_p_norm, _, _ = parse_competitor_2024(
            winner_comp, known_parties, alias_map
        )
        if winner_c_name:
            named_winners_count += 1
        winner_share = (
            round(winner_votes / deciding_valid * 100.0, 4)
            if deciding_valid > 0
            else 0.0
        )

        if is_uncontested:
            uncontested_count += 1
            runner_up_share = None
            margin_pp = None
        else:
            runner_up_comp, runner_up_votes = deciding_sorted[1]
            runner_up_share = (
                round(runner_up_votes / deciding_valid * 100.0, 4)
                if deciding_valid > 0
                else 0.0
            )
            margin_pp = (
                round((winner_votes - runner_up_votes) / deciding_valid * 100.0, 4)
                if deciding_valid > 0
                else 0.0
            )

        races_out.append({
            "year": 2024,
            "siruta": siruta,
            "election_date": election_date,
            "decided_in_round": decided_in_round,
            "is_uncontested": is_uncontested,
            "registered_voters": deciding_reg,
            "votes_cast": deciding_cast,
            "valid_votes": deciding_valid,
            "n_candidates": len(deciding_sorted),
            "winner_candidate_id": winner_cand_id,
            "winner_vote_share": winner_share,
            "runner_up_vote_share": runner_up_share,
            "round1_margin_pp": round1_margin_pp,
            "margin_pp": margin_pp,
            "is_repeated_or_annulled": is_repeated,
            "source_id": SOURCE_ID,
            "source_url": url,
            "retrieved_at": dt,
            "raw_sha256": sha,
        })

        terms_out.append({
            "term_id": f"2024-{siruta}",
            "siruta": siruta,
            "election_year": 2024,
            "term_start": None,
            "planned_term_end": None,
            "candidate_id": winner_cand_id,
            "mayor_name": winner_c_name,
            "party_normalised": winner_p_norm,
            "margin_pp": margin_pp,
        })

    # Build polling station records for 2024
    for row in main_df:
        tip, cod, nr_sv, siruta_raw, _, _, _, comp, votes = row
        siruta = BUCHAREST_SIRUTA if tip == "PG" else int(siruta_raw)
        station_id = f"{cod}-{nr_sv}"
        cid_info = cand_id_map.get((siruta, 1, comp))
        cand_id = cid_info[0] if cid_info else ""
        c_name = cid_info[1] if cid_info else None
        p_raw = cid_info[2] if cid_info else comp
        stations_out.append({
            "year": 2024,
            "siruta": siruta,
            "round": 1,
            "station_id": station_id,
            "candidate_id": cand_id,
            "candidate_name": c_name,
            "party_raw": p_raw,
            "votes": votes,
            "source_id": SOURCE_ID,
            "source_url": url,
            "retrieved_at": dt,
            "raw_sha256": sha,
        })

    for row in runoff_df:
        c_nce, nr_sv, uat_siruta_raw, _, _, _, comp, votes = row
        siruta = int(uat_siruta_raw)
        station_id = f"{c_nce}-{nr_sv}"
        cid_info = cand_id_map.get((siruta, 2, comp))
        cand_id = cid_info[0] if cid_info else ""
        c_name = cid_info[1] if cid_info else None
        p_raw = cid_info[2] if cid_info else comp
        stations_out.append({
            "year": 2024,
            "siruta": siruta,
            "round": 2,
            "station_id": station_id,
            "candidate_id": cand_id,
            "candidate_name": c_name,
            "party_raw": p_raw,
            "votes": votes,
            "source_id": SOURCE_ID,
            "source_url": url,
            "retrieved_at": dt,
            "raw_sha256": sha,
        })

    metrics = {
        "year": 2024,
        "total_races": len(races_out),
        "uncontested_races": uncontested_count,
        "discrepancy_races": discrepancy_count,
        "max_discrepancy": max_discrepancy,
        "named_candidates": named_candidates_count,
        "named_winners": named_winners_count,
        "candidates_count": len(candidates_out),
    }
    return candidates_out, races_out, terms_out, stations_out, metrics


def _write_parquet_tables(
    processed_dir: Path,
    candidates: list[dict[str, Any]],
    races: list[dict[str, Any]],
    terms: list[dict[str, Any]],
    stations: list[dict[str, Any]],
    years: list[int],
) -> None:
    """Write validated records to Parquet with explicit schemas."""
    # Validate records against Pydantic models
    validated_cands = [MayorCandidateRecord(**c).model_dump() for c in candidates]
    validated_races = [MayorRaceRecord(**r).model_dump() for r in races]
    validated_terms = [MayorTermRecord(**t).model_dump() for t in terms]
    validated_stations = [PollingStationMayorRecord(**s).model_dump() for s in stations]

    cand_schema = pa.schema([
        ("year", pa.int64()),
        ("siruta", pa.int64()),
        ("round", pa.int64()),
        ("candidate_id", pa.string()),
        ("candidate_name", pa.string()),
        ("name_key", pa.string()),
        ("party_raw", pa.string()),
        ("party_normalised", pa.string()),
        ("is_independent", pa.bool_()),
        ("is_alliance", pa.bool_()),
        ("votes", pa.int64()),
        ("vote_share", pa.float64()),
        ("rank", pa.int64()),
        ("is_winner", pa.bool_()),
        ("source_id", pa.string()),
        ("source_url", pa.string()),
        ("retrieved_at", pa.timestamp("us", tz="UTC")),
        ("raw_sha256", pa.string()),
    ])

    race_schema = pa.schema([
        ("year", pa.int64()),
        ("siruta", pa.int64()),
        ("election_date", pa.date32()),
        ("decided_in_round", pa.int64()),
        ("is_uncontested", pa.bool_()),
        ("registered_voters", pa.int64()),
        ("votes_cast", pa.int64()),
        ("valid_votes", pa.int64()),
        ("n_candidates", pa.int64()),
        ("winner_candidate_id", pa.string()),
        ("winner_vote_share", pa.float64()),
        ("runner_up_vote_share", pa.float64()),
        ("round1_margin_pp", pa.float64()),
        ("margin_pp", pa.float64()),
        ("is_repeated_or_annulled", pa.bool_()),
        ("source_id", pa.string()),
        ("source_url", pa.string()),
        ("retrieved_at", pa.timestamp("us", tz="UTC")),
        ("raw_sha256", pa.string()),
    ])

    term_schema = pa.schema([
        ("term_id", pa.string()),
        ("siruta", pa.int64()),
        ("election_year", pa.int64()),
        ("term_start", pa.date32()),
        ("planned_term_end", pa.date32()),
        ("candidate_id", pa.string()),
        ("mayor_name", pa.string()),
        ("party_normalised", pa.string()),
        ("margin_pp", pa.float64()),
    ])

    station_schema = pa.schema([
        ("year", pa.int64()),
        ("siruta", pa.int64()),
        ("round", pa.int64()),
        ("station_id", pa.string()),
        ("candidate_id", pa.string()),
        ("candidate_name", pa.string()),
        ("party_raw", pa.string()),
        ("votes", pa.int64()),
        ("source_id", pa.string()),
        ("source_url", pa.string()),
        ("retrieved_at", pa.timestamp("us", tz="UTC")),
        ("raw_sha256", pa.string()),
    ])

    # Convert to Arrow tables
    t_cands = pa.Table.from_pylist(validated_cands, schema=cand_schema)
    t_races = pa.Table.from_pylist(validated_races, schema=race_schema)
    t_terms = pa.Table.from_pylist(validated_terms, schema=term_schema)
    t_stations = pa.Table.from_pylist(validated_stations, schema=station_schema)

    pq.write_table(t_cands, processed_dir / "mayor_candidates.parquet")
    pq.write_table(t_races, processed_dir / "mayor_races.parquet")
    pq.write_table(t_terms, processed_dir / "mayor_terms.parquet")
    pq.write_table(t_stations, processed_dir / "mayor_results_polling_station.parquet")

    logger.info("Saved 4 Parquet files to %s", processed_dir)


def reconcile_county_party(settings: Settings, year: int) -> list[dict[str, Any]]:
    """Compare aggregated race totals with pv_final_cntry_p.csv at county x party level."""
    data_dir = settings.data_dir
    conn = duckdb.connect()

    uat_df = conn.execute(
        'SELECT siruta, county_name FROM "data/processed/uat.parquet"'
    ).fetchdf()
    siruta_to_county = dict(
        zip(
            uat_df["siruta"],
            uat_df["county_name"].apply(lambda x: normalise_name(x).key),
            strict=True,
        )
    )

    if year == 2020:
        pv_path = data_dir / "raw/aep_local/2026-10-13/pv_final_cntry_p.csv"
        delim = ";"
    else:
        pv_path = data_dir / "interim/aep_local/2024/Alegeri locale 2024/pv_final_cntry_p.csv"
        delim = ","

    if not pv_path.is_file():
        return []

    # Read pv_final_cntry_p
    csv_sql = (
        f"SELECT * FROM read_csv('{pv_path}', delim='{delim}', header=True, "
        f"quote='\"', all_varchar=True)"
    )
    pv_data = conn.execute(csv_sql).fetchdf()
    pv_data["c_key"] = pv_data["county_name"].apply(
        lambda x: normalise_name(x).key if x else ""
    )

    # Read candidates parquet
    cands_path = data_dir / "processed/mayor_candidates.parquet"
    if not cands_path.is_file():
        return []

    cands_df = conn.execute(f"""
        SELECT siruta, round, party_raw, party_normalised, is_independent, votes
        FROM '{cands_path}'
        WHERE year = {year} AND round = 1
    """).fetchdf()

    cands_df["c_key"] = cands_df["siruta"].map(siruta_to_county)

    discrepancies: list[dict[str, Any]] = []
    party_cols = [c for c in pv_data.columns if c.endswith("-voturi")]

    for _, row in pv_data.iterrows():
        ck = row["c_key"]
        c_name = row["county_name"].strip().upper()
        if not ck:
            continue
        county_cands = cands_df[cands_df["c_key"] == ck]
        for pcol in party_cols:
            pv_v = int(row[pcol]) if row[pcol] and str(row[pcol]).isdigit() else 0
            if pv_v == 0:
                continue
            pname = pcol[:-7].strip()
            pname_clean = pname.strip('"')

            if pname_clean == "Candidat Independent" or "independent" in pname_clean.lower():
                agg_v = int(
                    county_cands[county_cands["is_independent"] == True]["votes"].sum()  # noqa: E712
                )
            else:
                p_cands = county_cands[
                    (county_cands["party_raw"] == pname)
                    | (county_cands["party_raw"].str.strip('"') == pname_clean)
                    | (county_cands["party_normalised"].str.strip('"') == pname_clean)
                ]
                agg_v = int(p_cands["votes"].sum())

            if agg_v != pv_v:
                discrepancies.append({
                    "year": year,
                    "county": c_name,
                    "party": pname_clean,
                    "pv_votes": pv_v,
                    "agg_votes": agg_v,
                    "diff": agg_v - pv_v,
                })

    return discrepancies
