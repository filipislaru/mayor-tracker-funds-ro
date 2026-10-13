"""Tests for mayoral election normalisation with synthetic fixtures.

All fixtures strictly adhere to AGENTS.md:
- Synthetic names prefixed TEST (e.g. 'TEST Comuna Exemplu', 'TEST Ion Popescu')
- SIRUTA codes >= 900000
- No real-world data inside tests
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pyarrow as pa
from mayortracker.normalise.elections import (
    _standardise_diacritics,
    load_party_aliases,
    parse_competitor_2024,
)
from mayortracker.schemas.elections import (
    MayorCandidateRecord,
    MayorRaceRecord,
    MayorTermRecord,
    PollingStationMayorRecord,
)


def test_standardise_diacritics() -> None:
    # Cedilla to comma-below conversion
    raw = "PARTIDUL NAŢIONAL LIBERAL ŞI DEMOCRAT"
    norm = _standardise_diacritics(raw)
    assert norm == "PARTIDUL NAȚIONAL LIBERAL ȘI DEMOCRAT"
    assert "ş" not in norm and "ţ" not in norm and "Ş" not in norm and "Ţ" not in norm


def test_parse_competitor_2024_independent() -> None:
    known_parties = {"TEST PARTIDUL UNU", "TEST PARTIDUL DOI"}
    alias_map = {
        "TEST PARTIDUL UNU": {
            "party_normalised": "TEST PARTIDUL UNU",
            "is_alliance": False,
        }
    }

    # Format g-NAME--CI
    name, party_raw, party_norm, is_indep, is_alliance = parse_competitor_2024(
        "g-TEST ION POPESCU--CI", known_parties, alias_map
    )
    assert name == "TEST ION POPESCU"
    assert party_raw == "CANDIDAT INDEPENDENT"
    assert is_indep is True
    assert is_alliance is False

    # Format g-NAME-CI
    name, party_raw, party_norm, is_indep, is_alliance = parse_competitor_2024(
        "g-TEST VASILE IONESCU-CI", known_parties, alias_map
    )
    assert name == "TEST VASILE IONESCU"
    assert party_raw == "CANDIDAT INDEPENDENT"
    assert is_indep is True
    assert is_alliance is False


def test_parse_competitor_2024_party_with_hyphens() -> None:
    known_parties = {
        "TEST PARTIDUL SOCIAL DEMOCRAT",
        "TEST ALIANȚA DREAPTA UNITĂ",
    }
    alias_map = {
        "TEST PARTIDUL SOCIAL DEMOCRAT": {
            "party_normalised": "TEST PARTIDUL SOCIAL DEMOCRAT",
            "is_alliance": False,
        },
        "TEST ALIANȚA DREAPTA UNITĂ": {
            "party_normalised": "TEST ALIANȚA DREAPTA UNITĂ",
            "is_alliance": True,
        },
    }

    # Candidate with hyphenated Romanian first name
    raw_comp = "g-TEST ANA-MARIA POPESCU-TEST PARTIDUL SOCIAL DEMOCRAT"
    name, party_raw, party_norm, is_indep, is_alliance = parse_competitor_2024(
        raw_comp, known_parties, alias_map
    )
    assert name == "TEST ANA-MARIA POPESCU"
    assert party_raw == "TEST PARTIDUL SOCIAL DEMOCRAT"
    assert party_norm == "TEST PARTIDUL SOCIAL DEMOCRAT"
    assert is_indep is False
    assert is_alliance is False

    # Alliance competitor
    raw_comp_all = "g-TEST GHEORGHE IONESCU-TEST ALIANȚA DREAPTA UNITĂ"
    name, party_raw, party_norm, is_indep, is_alliance = parse_competitor_2024(
        raw_comp_all, known_parties, alias_map
    )
    assert name == "TEST GHEORGHE IONESCU"
    assert party_raw == "TEST ALIANȚA DREAPTA UNITĂ"
    assert is_alliance is True


def test_load_party_aliases(tmp_path: Path) -> None:
    yaml_content = """
parties:
  2020:
    - party_raw: "TEST PARTIDUL ALFA"
      party_normalised: "TEST PARTIDUL ALFA"
      is_alliance: false
      abbreviation: ""
    - party_raw: "TEST ALIANȚA BETA"
      party_normalised: "TEST ALIANȚA BETA"
      is_alliance: true
      abbreviation: ""
      members: []
  2024:
    - party_raw: "TEST PARTIDUL GAMA"
      party_normalised: "TEST PARTIDUL GAMA"
      is_alliance: false
      abbreviation: ""
"""
    cfg_file = tmp_path / "party_aliases.yaml"
    cfg_file.write_text(yaml_content, encoding="utf-8")

    loaded = load_party_aliases(cfg_file)
    assert 2020 in loaded and 2024 in loaded
    assert "TEST PARTIDUL ALFA" in loaded[2020]
    assert loaded[2020]["TEST PARTIDUL ALFA"]["is_alliance"] is False
    assert loaded[2020]["TEST ALIANȚA BETA"]["is_alliance"] is True
    assert loaded[2020]["TEST ALIANȚA BETA"]["members"] == []


def test_mayor_candidate_schema() -> None:
    rec = MayorCandidateRecord(
        year=2024,
        siruta=900001,
        round=1,
        candidate_id="2024-900001-r1-1",
        candidate_name="Test Vasile Pop",
        name_key="pop vasile",
        party_raw="TEST PARTIDUL DEMOCRAT",
        party_normalised="TEST PARTIDUL DEMOCRAT",
        is_independent=False,
        is_alliance=False,
        votes=500,
        vote_share=55.55,
        rank=1,
        is_winner=True,
        source_id="aep_local",
        source_url="https://example.com/test",
        retrieved_at=datetime(2026, 10, 13, 10, 0, 0),
        raw_sha256="0" * 64,
    )
    assert rec.siruta == 900001
    assert rec.is_winner is True

    # 2020 party candidate with null name
    rec_2020 = MayorCandidateRecord(
        year=2020,
        siruta=900001,
        round=1,
        candidate_id="2020-900001-r1-1",
        candidate_name=None,
        name_key=None,
        party_raw="TEST PARTIDUL DEMOCRAT",
        party_normalised="TEST PARTIDUL DEMOCRAT",
        is_independent=False,
        is_alliance=False,
        votes=400,
        vote_share=60.0,
        rank=1,
        is_winner=True,
        source_id="aep_local",
        source_url="https://example.com/test",
        retrieved_at=datetime(2026, 10, 13, 10, 0, 0),
        raw_sha256="0" * 64,
    )
    assert rec_2020.candidate_name is None
    assert rec_2020.name_key is None


def test_mayor_race_schema_and_uncontested() -> None:
    # Uncontested race
    uncontested_race = MayorRaceRecord(
        year=2024,
        siruta=900002,
        election_date=date(2024, 6, 9),
        decided_in_round=1,
        is_uncontested=True,
        registered_voters=1000,
        votes_cast=600,
        valid_votes=580,
        n_candidates=1,
        winner_candidate_id="2024-900002-r1-1",
        winner_vote_share=100.0,
        runner_up_vote_share=None,
        round1_margin_pp=None,
        margin_pp=None,
        is_repeated_or_annulled=False,
        source_id="aep_local",
        source_url="https://example.com/test",
        retrieved_at=datetime(2026, 10, 13, 10, 0, 0),
        raw_sha256="0" * 64,
    )
    assert uncontested_race.is_uncontested is True
    assert uncontested_race.runner_up_vote_share is None
    assert uncontested_race.margin_pp is None
    assert isinstance(uncontested_race.election_date, date)

    # Contested race
    contested_race = MayorRaceRecord(
        year=2024,
        siruta=900003,
        election_date=date(2024, 6, 9),
        decided_in_round=1,
        is_uncontested=False,
        registered_voters=2000,
        votes_cast=1200,
        valid_votes=1150,
        n_candidates=3,
        winner_candidate_id="2024-900003-r1-1",
        winner_vote_share=55.0,
        runner_up_vote_share=35.0,
        round1_margin_pp=20.0,
        margin_pp=20.0,
        is_repeated_or_annulled=False,
        source_id="aep_local",
        source_url="https://example.com/test",
        retrieved_at=datetime(2026, 10, 13, 10, 0, 0),
        raw_sha256="0" * 64,
    )
    assert contested_race.is_uncontested is False
    assert contested_race.runner_up_vote_share == 35.0
    assert contested_race.margin_pp == 20.0


def test_mayor_term_schema() -> None:
    term = MayorTermRecord(
        term_id="2024-900001",
        siruta=900001,
        election_year=2024,
        term_start=date(2024, 10, 20),
        planned_term_end=None,
        candidate_id="2024-900001-r1-1",
        mayor_name="Test Vasile Pop",
        party_normalised="TEST PARTIDUL DEMOCRAT",
        margin_pp=15.5,
    )
    assert term.term_id == "2024-900001"
    assert isinstance(term.term_start, date)
    assert term.mayor_name == "Test Vasile Pop"


def test_polling_station_schema() -> None:
    station_rec = PollingStationMayorRecord(
        year=2024,
        siruta=900001,
        round=1,
        station_id="TEST-1",
        candidate_id="2024-900001-r1-1",
        candidate_name="Test Vasile Pop",
        party_raw="TEST PARTIDUL DEMOCRAT",
        votes=250,
        source_id="aep_local",
        source_url="https://example.com/test",
        retrieved_at=datetime(2026, 10, 13, 10, 0, 0),
        raw_sha256="0" * 64,
    )
    assert station_rec.station_id == "TEST-1"
    assert station_rec.votes == 250


def test_tied_race_runoff_and_deciding_totals() -> None:
    # Test that a tied race in Round 1 records round1_margin_pp = 0.0,
    # decided_in_round = 2, and uses Round 2 totals for registered/valid/cast.
    tied_race = MayorRaceRecord(
        year=2024,
        siruta=900004,
        election_date=date(2024, 6, 23),
        decided_in_round=2,
        is_uncontested=False,
        registered_voters=1500,  # Round 2 registered
        votes_cast=900,         # Round 2 cast
        valid_votes=850,        # Round 2 valid
        n_candidates=2,
        winner_candidate_id="2024-900004-r2-1",
        winner_vote_share=52.94,
        runner_up_vote_share=47.06,
        round1_margin_pp=0.0,   # Tied in round 1
        margin_pp=5.88,         # Deciding margin in round 2
        is_repeated_or_annulled=False,
        source_id="aep_local",
        source_url="https://example.com/test",
        retrieved_at=datetime(2026, 10, 13, 10, 0, 0),
        raw_sha256="0" * 64,
    )
    assert tied_race.decided_in_round == 2
    assert tied_race.round1_margin_pp == 0.0
    assert tied_race.margin_pp == 5.88
    assert tied_race.valid_votes == 850


def test_parquet_table_writer(tmp_path: Path) -> None:
    from mayortracker.normalise.elections import _write_parquet_tables

    dt = datetime(2026, 10, 13, 10, 0, 0)
    cand = {
        "year": 2024,
        "siruta": 900001,
        "round": 1,
        "candidate_id": "2024-900001-r1-1",
        "candidate_name": "TEST CANDIDAT",
        "name_key": "candidat test",
        "party_raw": "TEST PARTID",
        "party_normalised": "TEST PARTID",
        "is_independent": False,
        "is_alliance": False,
        "votes": 500,
        "vote_share": 100.0,
        "rank": 1,
        "is_winner": True,
        "source_id": "aep_local",
        "source_url": "https://example.com",
        "retrieved_at": dt,
        "raw_sha256": "a" * 64,
    }
    race = {
        "year": 2024,
        "siruta": 900001,
        "election_date": date(2024, 6, 9),
        "decided_in_round": 1,
        "is_uncontested": True,
        "registered_voters": 1000,
        "votes_cast": 550,
        "valid_votes": 500,
        "n_candidates": 1,
        "winner_candidate_id": "2024-900001-r1-1",
        "winner_vote_share": 100.0,
        "runner_up_vote_share": None,
        "round1_margin_pp": None,
        "margin_pp": None,
        "is_repeated_or_annulled": False,
        "source_id": "aep_local",
        "source_url": "https://example.com",
        "retrieved_at": dt,
        "raw_sha256": "a" * 64,
    }
    term = {
        "term_id": "2024-900001",
        "siruta": 900001,
        "election_year": 2024,
        "term_start": date(2024, 10, 20),
        "planned_term_end": None,
        "candidate_id": "2024-900001-r1-1",
        "mayor_name": "TEST CANDIDAT",
        "party_normalised": "TEST PARTID",
        "margin_pp": None,
    }
    station = {
        "year": 2024,
        "siruta": 900001,
        "round": 1,
        "station_id": "TEST-1",
        "candidate_id": "2024-900001-r1-1",
        "candidate_name": "TEST CANDIDAT",
        "party_raw": "TEST PARTID",
        "votes": 500,
        "source_id": "aep_local",
        "source_url": "https://example.com",
        "retrieved_at": dt,
        "raw_sha256": "a" * 64,
    }

    _write_parquet_tables(
        tmp_path, [cand], [race], [term], [station], [2024]
    )

    import pyarrow.parquet as pq

    assert (tmp_path / "mayor_candidates.parquet").is_file()
    assert (tmp_path / "mayor_races.parquet").is_file()
    assert (tmp_path / "mayor_terms.parquet").is_file()
    assert (tmp_path / "mayor_results_polling_station.parquet").is_file()

    races_t = pq.read_table(tmp_path / "mayor_races.parquet")
    assert races_t.schema.field("election_date").type == pa.date32()
    assert races_t.num_rows == 1
