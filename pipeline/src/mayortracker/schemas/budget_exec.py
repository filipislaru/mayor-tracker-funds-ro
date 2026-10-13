"""Pydantic schemas for local budget execution records."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel


class BudgetEuLineRecord(BaseModel):
    """An individual budget classification line recording EU funds received or spent."""

    siruta: int
    year: int
    classification_code: str
    label: str
    line_type: str  # 'revenue' or 'expenditure'
    amount: Decimal
    unit: str = "RON"
    source_id: str = "budget_exec"
    source_url: str
    retrieved_at: dt.datetime
    raw_sha256: str


class UatEuReceivedYearRecord(BaseModel):
    """Summary of EU funds received and executed per UAT and year."""

    siruta: int
    year: int
    uat_name: str
    county_name: str
    county_code: str | None = None
    eu_received_total: Decimal
    eu_received_2014_2020: Decimal
    eu_received_unspecified: Decimal
    eu_received_other: Decimal
    eu_spent_total: Decimal
    eu_spent_2014_2020: Decimal
    eu_spent_unspecified: Decimal
    eu_spent_pnrr_grant: Decimal
    eu_spent_pnrr_loan: Decimal
    spending_to_revenue_ratio: float | None = None
    ratio_2014_2020: float | None = None
    unit: str = "RON"
    source_id: str = "budget_exec"
    source_url: str
    retrieved_at: dt.datetime
    raw_sha256: str
