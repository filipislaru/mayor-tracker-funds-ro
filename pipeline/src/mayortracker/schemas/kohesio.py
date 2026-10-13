"""Pydantic schemas for Kohesio projects, beneficiaries, and UAT matches."""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from pydantic import BaseModel


class MatchConfidence(StrEnum):
    """Confidence levels for beneficiary-to-UAT matches."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class MatchMethod(StrEnum):
    """Methods used to classify and match beneficiaries."""

    NAME_COUNTY_EXACT = "name_county_exact"
    NAME_COUNTY_NORMALISED = "name_county_normalised"
    LOCALITY_CANDIDATE = "locality_candidate"
    UNMATCHED_LOCAL_AUTHORITY = "unmatched_local_authority"
    COUNTY_COUNCIL = "county_council"
    OTHER_BODY = "other_body"


class KohesioProjectRecord(BaseModel):
    """A clean record representing an EU cohesion-policy project."""

    project_id: str
    local_id: str
    title: str
    title_en: str | None = None
    programme_code: str
    programme_name: str
    fund_code: str
    fund_name: str
    programming_period: str
    total_eligible_expenditure_amount: float
    total_eligible_expenditure_currency: str
    eu_budget: float
    cofinancing_rate: float | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    has_multiple_beneficiaries: bool = False
    lau_ids: str | None = None
    lau_labels: str | None = None
    nuts3_code: str | None = None
    nuts3_label: str | None = None
    coordinates: str | None = None
    source_id: str = "kohesio"
    source_url: str
    retrieved_at: dt.datetime
    raw_sha256: str


class KohesioBeneficiaryRecord(BaseModel):
    """A record representing a project-beneficiary pair."""

    project_id: str
    beneficiary_id: str
    beneficiary_name: str
    beneficiary_local_id: str | None = None
    is_local_authority: bool
    source_id: str = "kohesio"
    source_url: str
    retrieved_at: dt.datetime
    raw_sha256: str


class BeneficiaryUatMatchRecord(BaseModel):
    """A match record linking a local authority beneficiary to a UAT SIRUTA code."""

    beneficiary_id: str
    beneficiary_name: str
    beneficiary_local_id: str | None = None
    siruta: int | None = None
    uat_name: str | None = None
    county_code: str | None = None
    match_method: MatchMethod
    match_confidence: MatchConfidence
    evidence: str
    source_id: str = "kohesio"
    retrieved_at: dt.datetime


class UatFiscalCodeRecord(BaseModel):
    """A crosswalk record linking a confirmed UAT to its fiscal code (CUI/CIF)."""

    siruta: int
    fiscal_code: str
    number_of_projects: int
    is_multi_uat_fiscal_code: bool = False
    is_multi_fiscal_code_uat: bool = False
    evidence: str
