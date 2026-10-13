"""Pydantic schemas for mayoral elections, candidates, races, and terms."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class MayorCandidateRecord(BaseModel):
    """Schema for a mayoral candidate in a given race and round."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    year: int = Field(..., description="Election year (e.g. 2020 or 2024)")
    siruta: int = Field(..., description="SIRUTA code of the UAT")
    round: int = Field(..., description="Election round (1 or 2)")
    candidate_id: str = Field(
        ..., description="Unique stable ID: {year}-{siruta}-r{round}-{rank}"
    )
    candidate_name: str | None = Field(
        None, description="Normalised display form of candidate name, or null if source omitted"
    )
    name_key: str | None = Field(
        None, description="ASCII-folded search key of candidate name, or null if omitted"
    )
    party_raw: str = Field(..., description="Party or alliance name exactly as in source")
    party_normalised: str | None = Field(
        None, description="Spelling-standardised party name (comma-below diacritics, case, spaces)"
    )
    is_independent: bool = Field(..., description="True if candidate ran as independent")
    is_alliance: bool = Field(..., description="True if candidate represented an alliance")
    votes: int = Field(..., ge=0, description="Votes received in this round")
    vote_share: float = Field(..., ge=0.0, description="Vote share percentage in this round")
    rank: int = Field(..., ge=1, description="Rank within the race round by votes received")
    is_winner: bool = Field(
        ..., description="True if this candidate won the mayoralty in the deciding round"
    )

    # Provenance
    source_id: str = Field(..., description="Source registry identifier, e.g. 'aep_local'")
    source_url: str = Field(..., description="Source URL recorded in raw manifest")
    retrieved_at: datetime = Field(..., description="UTC timestamp when raw source was registered")
    raw_sha256: str = Field(..., description="SHA256 hex digest of the raw source file")


class MayorRaceRecord(BaseModel):
    """Schema for a mayoral race in a UAT."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    year: int = Field(..., description="Election year (2020 or 2024)")
    siruta: int = Field(..., description="SIRUTA code of the UAT")
    election_date: date = Field(..., description="Date of the deciding election (YYYY-MM-DD)")
    decided_in_round: int = Field(..., ge=1, le=2, description="Round deciding the race (1 or 2)")
    is_uncontested: bool = Field(
        ..., description="True if only one candidate stood in the deciding round"
    )
    registered_voters: int = Field(
        ..., ge=0, description="Registered voters in the deciding round (a)"
    )
    votes_cast: int = Field(
        ..., ge=0, description="Total voters present at urns in deciding round (b)"
    )
    valid_votes: int = Field(
        ..., ge=0, description="Total valid votes in the deciding round (c)"
    )
    n_candidates: int = Field(
        ..., ge=1, description="Number of candidates standing in the deciding round"
    )
    winner_candidate_id: str | None = Field(
        None, description="Candidate ID of the winner, or null if tie unbroken"
    )
    winner_vote_share: float | None = Field(
        None, ge=0.0, description="Winning candidate vote share in percentage"
    )
    runner_up_vote_share: float | None = Field(
        None,
        ge=0.0,
        description="Runner-up candidate vote share in percentage (null if uncontested)",
    )
    round1_margin_pp: float | None = Field(
        None,
        description="Margin in Round 1 in percentage points (0.0 if tied, null if uncontested)",
    )
    margin_pp: float | None = Field(
        None,
        description="Margin in deciding round (winner minus runner-up in pp, null if uncontested)",
    )
    is_repeated_or_annulled: bool = Field(
        ..., description="True if the main-election race was annulled and rerun on a later date"
    )

    # Provenance
    source_id: str = Field(..., description="Source registry identifier, e.g. 'aep_local'")
    source_url: str = Field(..., description="Source URL recorded in raw manifest")
    retrieved_at: datetime = Field(..., description="UTC timestamp when raw source was registered")
    raw_sha256: str = Field(..., description="SHA256 hex digest of the raw source file")


class MayorTermRecord(BaseModel):
    """Schema for a resulting mayoral term of office."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    term_id: str = Field(..., description="Unique term ID: {year}-{siruta}")
    siruta: int = Field(..., description="SIRUTA code of the UAT")
    election_year: int = Field(..., description="Year elected")
    term_start: date | None = Field(
        None, description="Official validation date if available, else null"
    )
    planned_term_end: date | None = Field(
        None, description="Official planned end date if available, else null"
    )
    candidate_id: str = Field(..., description="Candidate ID of the elected mayor")
    mayor_name: str | None = Field(
        None,
        description="Normalised display name of the elected mayor, or null if omitted in source",
    )
    party_normalised: str | None = Field(
        None, description="Standardised party name at election time"
    )
    margin_pp: float | None = Field(
        None, description="Victory margin in percentage points in the deciding round"
    )


class PollingStationMayorRecord(BaseModel):
    """Schema for polling-station level mayoral candidate results."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    year: int = Field(..., description="Election year")
    siruta: int = Field(..., description="SIRUTA code of the UAT")
    round: int = Field(..., description="Election round (1 or 2)")
    station_id: str = Field(..., description="Polling station identifier, e.g. 'CT-416'")
    candidate_id: str = Field(..., description="Candidate ID")
    candidate_name: str | None = Field(None, description="Normalised candidate name or null")
    party_raw: str = Field(..., description="Raw party string from source")
    votes: int = Field(..., ge=0, description="Votes received in this polling station")

    # Provenance
    source_id: str = Field(..., description="Source registry identifier, e.g. 'aep_local'")
    source_url: str = Field(..., description="Source URL recorded in raw manifest")
    retrieved_at: datetime = Field(..., description="UTC timestamp when raw source was registered")
    raw_sha256: str = Field(..., description="SHA256 hex digest of the raw source file")
