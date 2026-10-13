"""Tests for Kohesio normalisation and UAT matching using synthetic fixtures."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from mayortracker.normalise.kohesio import normalise_kohesio
from mayortracker.schemas.kohesio import MatchConfidence, MatchMethod
from mayortracker.util.config import Settings


def test_normalise_kohesio_synthetic(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw" / "kohesio" / "2026-10-13"
    proc_dir = data_dir / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    proc_dir.mkdir(parents=True, exist_ok=True)

    settings = Settings(
        project_name="TEST project",
        data_dir=data_dir,
        contact_email="test@example.com",
    )

    # 1. Synthetic UAT and locality tables (SIRUTA >= 900000, TEST prefix)
    uats_data = [
        {
            "siruta": 900001,
            "name": "TEST EXEMPLU",
            "name_key": "test exemplu",
            "uat_type": "comuna",
            "county_code": "AB",
            "county_name": "Alba",
            "county_siruta": 900000,
        },
        {
            "siruta": 900002,
            "name": "TEST MODEL",
            "name_key": "test model",
            "uat_type": "oras",
            "county_code": "CJ",
            "county_name": "Cluj",
            "county_siruta": 900010,
        },
        {
            "siruta": 900003,
            "name": "TEST PARINTE",
            "name_key": "test parinte",
            "uat_type": "comuna",
            "county_code": "AB",
            "county_name": "Alba",
            "county_siruta": 900000,
        },
    ]
    uats_df = pd.DataFrame(uats_data)
    pq.write_table(pa.Table.from_pandas(uats_df, preserve_index=False), proc_dir / "uat.parquet")

    locs_data = [
        {
            "siruta": 900101,
            "name": "TEST SAT COMPONENT",
            "name_key": "test sat component",
            "parent_uat_siruta": 900003,
            "locality_type": "sat",
            "is_uat_seat": False,
        }
    ]
    locs_df = pd.DataFrame(locs_data)
    locs_tbl = pa.Table.from_pandas(locs_df, preserve_index=False)
    pq.write_table(locs_tbl, proc_dir / "locality.parquet")

    # 2. Synthetic NUTS table
    nuts_data = [
        {"nuts3code": "RO121", "nuts3Label": "Alba"},
        {"nuts3code": "RO113", "nuts3Label": "Cluj"},
    ]
    with (raw_dir / "RO-nuts-latest.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["nuts3code", "nuts3Label"])
        writer.writeheader()
        writer.writerows(nuts_data)

    # 3. Synthetic projects 2014-2020
    p14_headers = [
        "Operation_Unique_Identifier",
        "Operation_Local_Identifier",
        "Operation_Name_English",
        "Operation_Name_Programme_Language",
        "Country",
        "Operation_Start_Date",
        "Operation_End_Date",
        "Cofinancing_Rate",
        "Total_Eligible_Expenditure_amount",
        "Total_Eligible_Expenditure_Currency",
        "Project_EU_Budget",
        "Beneficiary_Unique_Identifier",
        "Beneficiary_Name",
        "Beneficiary_Local_Identifier",
        "Fund_Code",
        "Fund_Name",
        "Programme_Code",
        "Programme_Name",
        "Coordinates",
        "LAU_IDs",
        "LAU_Labels",
        "NUTS3_Code",
        "NUTS3_Label",
    ]
    p14_rows = [
        # Match 1: Exact match on Comuna Exemplu (AB)
        {
            "Operation_Unique_Identifier": "TEST_PROJ_1",
            "Operation_Local_Identifier": "TEST_L1",
            "Operation_Name_English": "TEST Project 1",
            "Operation_Name_Programme_Language": "TEST Proiect 1",
            "Country": "Romania",
            "Operation_Start_Date": "01/01/2018",
            "Operation_End_Date": "31/12/2019",
            "Cofinancing_Rate": 85.0,
            "Total_Eligible_Expenditure_amount": 100000.0,
            "Total_Eligible_Expenditure_Currency": "EUR",
            "Project_EU_Budget": 85000.0,
            "Beneficiary_Unique_Identifier": "TEST_BENE_1",
            "Beneficiary_Name": "PRIMĂRIA COMUNA TEST EXEMPLU",
            "Beneficiary_Local_Identifier": "123456",
            "Fund_Code": "ERDF",
            "Fund_Name": "European Regional Development Fund",
            "Programme_Code": "TEST_PROG",
            "Programme_Name": "TEST Programme",
            "Coordinates": "Point(23.5 46.1)",
            "LAU_IDs": "RO_900001",
            "LAU_Labels": "TEST Comuna Exemplu",
            "NUTS3_Code": "RO121",
            "NUTS3_Label": "Alba",
        },
        # Match 2: Multi-beneficiary project on Oraș Model (CJ)
        {
            "Operation_Unique_Identifier": "TEST_PROJ_2",
            "Operation_Local_Identifier": "TEST_L2",
            "Operation_Name_English": "TEST Project 2",
            "Operation_Name_Programme_Language": "TEST Proiect 2",
            "Country": "Romania",
            "Operation_Start_Date": "01/06/2019",
            "Operation_End_Date": "30/06/2021",
            "Cofinancing_Rate": 85.0,
            "Total_Eligible_Expenditure_amount": 200000.0,
            "Total_Eligible_Expenditure_Currency": "EUR",
            "Project_EU_Budget": 170000.0,
            "Beneficiary_Unique_Identifier": "TEST_BENE_2",
            "Beneficiary_Name": "UAT ORAȘUL TEST MODEL",
            "Beneficiary_Local_Identifier": "654321|999999",
            "Fund_Code": "CF",
            "Fund_Name": "Cohesion Fund",
            "Programme_Code": "TEST_PROG",
            "Programme_Name": "TEST Programme",
            "Coordinates": "Point(23.6 46.7)",
            "LAU_IDs": "RO_900002",
            "LAU_Labels": "TEST Oras Model",
            "NUTS3_Code": "RO113",
            "NUTS3_Label": "Cluj",
        },
        # Non-UAT: County Council
        {
            "Operation_Unique_Identifier": "TEST_PROJ_3",
            "Operation_Local_Identifier": "TEST_L3",
            "Operation_Name_English": "TEST Project 3",
            "Operation_Name_Programme_Language": "TEST Proiect 3",
            "Country": "Romania",
            "Operation_Start_Date": "01/01/2019",
            "Operation_End_Date": "31/12/2020",
            "Cofinancing_Rate": 85.0,
            "Total_Eligible_Expenditure_amount": 500000.0,
            "Total_Eligible_Expenditure_Currency": "EUR",
            "Project_EU_Budget": 425000.0,
            "Beneficiary_Unique_Identifier": "TEST_BENE_CJ",
            "Beneficiary_Name": "CONSILIUL JUDEȚEAN ALBA",
            "Beneficiary_Local_Identifier": "777777",
            "Fund_Code": "ERDF",
            "Fund_Name": "European Regional Development Fund",
            "Programme_Code": "TEST_PROG",
            "Programme_Name": "TEST Programme",
            "Coordinates": "Point(23.5 46.1)",
            "LAU_IDs": "RO_900001",
            "LAU_Labels": "TEST Comuna Exemplu",
            "NUTS3_Code": "RO121",
            "NUTS3_Label": "Alba",
        },
        # LAU Disagreement: Names Comuna Exemplu (AB), but LAU_IDs points to RO_900002 (CJ)
        {
            "Operation_Unique_Identifier": "TEST_PROJ_4",
            "Operation_Local_Identifier": "TEST_L4",
            "Operation_Name_English": "TEST Project 4",
            "Operation_Name_Programme_Language": "TEST Proiect 4",
            "Country": "Romania",
            "Operation_Start_Date": "01/01/2018",
            "Operation_End_Date": "invalid_date",  # Unparseable date
            "Cofinancing_Rate": 85.0,
            "Total_Eligible_Expenditure_amount": 50000.0,
            "Total_Eligible_Expenditure_Currency": "EUR",
            "Project_EU_Budget": 42500.0,
            "Beneficiary_Unique_Identifier": "TEST_BENE_DISAGREE",
            "Beneficiary_Name": "COMUNA TEST EXEMPLU",
            "Beneficiary_Local_Identifier": "888888",
            "Fund_Code": "ESF",
            "Fund_Name": "European Social Fund",
            "Programme_Code": "TEST_PROG",
            "Programme_Name": "TEST Programme",
            "Coordinates": "Point(23.5 46.1)",
            "LAU_IDs": "RO_900002",
            "LAU_Labels": "TEST Oras Model",
            "NUTS3_Code": "RO121",
            "NUTS3_Label": "Alba",
        },
        # Village candidate: Names TEST SAT COMPONENT
        {
            "Operation_Unique_Identifier": "TEST_PROJ_5",
            "Operation_Local_Identifier": "TEST_L5",
            "Operation_Name_English": "TEST Project 5",
            "Operation_Name_Programme_Language": "TEST Proiect 5",
            "Country": "Romania",
            "Operation_Start_Date": "01/01/2019",
            "Operation_End_Date": "31/12/2020",
            "Cofinancing_Rate": 85.0,
            "Total_Eligible_Expenditure_amount": 60000.0,
            "Total_Eligible_Expenditure_Currency": "EUR",
            "Project_EU_Budget": 51000.0,
            "Beneficiary_Unique_Identifier": "TEST_BENE_VILLAGE",
            "Beneficiary_Name": "COMUNA TEST SAT COMPONENT",
            "Beneficiary_Local_Identifier": "555555",
            "Fund_Code": "ERDF",
            "Fund_Name": "European Regional Development Fund",
            "Programme_Code": "TEST_PROG",
            "Programme_Name": "TEST Programme",
            "Coordinates": "Point(23.5 46.1)",
            "LAU_IDs": None,
            "LAU_Labels": None,
            "NUTS3_Code": "RO121",
            "NUTS3_Label": "Alba",
        },
    ]

    with (raw_dir / "RO-pp14-20-latest.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=p14_headers)
        writer.writeheader()
        writer.writerows(p14_rows)

    # 4. Synthetic projects 2021-2027 (1 project)
    p21_headers = p14_headers
    p21_rows = [
        {
            "Operation_Unique_Identifier": "TEST_PROJ_6",
            "Operation_Local_Identifier": "TEST_L6",
            "Operation_Name_English": "TEST Project 6",
            "Operation_Name_Programme_Language": "TEST Proiect 6",
            "Country": "Romania",
            "Operation_Start_Date": "01/01/2022",
            "Operation_End_Date": "31/12/2024",
            "Cofinancing_Rate": 85.0,
            "Total_Eligible_Expenditure_amount": 150000.0,
            "Total_Eligible_Expenditure_Currency": "EUR",
            "Project_EU_Budget": 127500.0,
            "Beneficiary_Unique_Identifier": "TEST_BENE_1",
            "Beneficiary_Name": "PRIMĂRIA COMUNA TEST EXEMPLU",
            "Beneficiary_Local_Identifier": "123456",
            "Fund_Code": "ERDF",
            "Fund_Name": "European Regional Development Fund",
            "Programme_Code": "TEST_PROG",
            "Programme_Name": "TEST Programme",
            "Coordinates": "Point(23.5 46.1)",
            "LAU_IDs": None,
            "LAU_Labels": None,
            "NUTS3_Code": "RO121",
            "NUTS3_Label": "Alba",
        }
    ]
    with (raw_dir / "RO-pp21-27-latest.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=p21_headers)
        writer.writeheader()
        writer.writerows(p21_rows)

    # 5. Manifest
    manifest_data = [
        {
            "filename": "RO-pp14-20-latest.csv",
            "url": "https://example.com/p14",
            "sha256": "fake14",
            "retrieved_at": "2026-10-13T00:00:00Z",
        },
        {
            "filename": "RO-pp21-27-latest.csv",
            "url": "https://example.com/p21",
            "sha256": "fake21",
            "retrieved_at": "2026-10-13T00:00:00Z",
        },
    ]
    (raw_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    # Run normalise_kohesio
    metrics = normalise_kohesio(settings, raw_folder=raw_dir)

    assert metrics.total_projects == 6
    assert metrics.projects_14_20 == 5
    assert metrics.projects_21_27 == 1
    assert metrics.unparseable_dates_count == 1

    # Verify output parquet files exist
    assert (proc_dir / "kohesio_projects.parquet").is_file()
    assert (proc_dir / "kohesio_beneficiaries.parquet").is_file()
    assert (proc_dir / "beneficiary_uat_matches.parquet").is_file()
    assert (proc_dir / "uat_fiscal_codes.parquet").is_file()
    assert (data_dir / "interim" / "kohesio" / "match_review.csv").is_file()

    # Verify projects table
    proj_pq = pq.read_table(proc_dir / "kohesio_projects.parquet").to_pandas()
    assert len(proj_pq) == 6
    multi_p = proj_pq[proj_pq["project_id"] == "TEST_PROJ_2"]
    assert multi_p["has_multiple_beneficiaries"].iloc[0]

    # Verify beneficiaries table
    bene_pq = pq.read_table(proc_dir / "kohesio_beneficiaries.parquet").to_pandas()
    assert len(bene_pq) >= 7  # Multi-beneficiary expanded

    # Verify match table
    matches_pq = pq.read_table(proc_dir / "beneficiary_uat_matches.parquet").to_pandas()
    # TEST_BENE_1 matched cleanly
    b1 = matches_pq[matches_pq["beneficiary_id"] == "TEST_BENE_1"]
    assert len(b1) == 1
    assert b1["siruta"].iloc[0] == 900001
    assert b1["match_method"].iloc[0] == MatchMethod.NAME_COUNTY_EXACT.value
    assert b1["match_confidence"].iloc[0] == MatchConfidence.HIGH.value

    # County council classified as county_council
    b_cj = matches_pq[matches_pq["beneficiary_id"] == "TEST_BENE_CJ"]
    assert b_cj["match_method"].iloc[0] == MatchMethod.COUNTY_COUNCIL.value
    assert pd.isna(b_cj["siruta"].iloc[0])

    # Village candidate routed to review
    b_vil = matches_pq[matches_pq["beneficiary_id"] == "TEST_BENE_VILLAGE"]
    assert b_vil["match_method"].iloc[0] == MatchMethod.LOCALITY_CANDIDATE.value

    # LAU disagreement routed to review
    b_dis = matches_pq[matches_pq["beneficiary_id"] == "TEST_BENE_DISAGREE"]
    assert b_dis["match_method"].iloc[0] == MatchMethod.UNMATCHED_LOCAL_AUTHORITY.value

    # Review CSV checks
    review_df = pd.read_csv(data_dir / "interim" / "kohesio" / "match_review.csv")
    assert "lau_disagreement" in review_df["reason"].values
    assert "locality_candidate" in review_df["reason"].values

    # Fiscal code crosswalk
    fc_pq = pq.read_table(proc_dir / "uat_fiscal_codes.parquet").to_pandas()
    assert 900001 in fc_pq["siruta"].values
    assert "123456" in fc_pq["fiscal_code"].values
    assert "is_multi_uat_fiscal_code" in fc_pq.columns
    assert "is_multi_fiscal_code_uat" in fc_pq.columns
