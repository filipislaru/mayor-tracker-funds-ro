"""Pydantic schemas for administrative units and localities."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class UatType(StrEnum):
    """Authoritative administrative unit type classification."""

    COMUNA = "comuna"
    ORAS = "oras"
    MUNICIPIU = "municipiu"
    MUNICIPIUL_BUCURESTI = "municipiul_bucuresti"
    SECTOR = "sector"


class UatRecord(BaseModel):
    """Schema for a single administrative unit (UAT)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    siruta: int = Field(..., description="SIRUTA identifier of the UAT")
    name: str = Field(..., description="Normalised display name (comma-below diacritics)")
    name_key: str = Field(..., description="Normalised search and join key")
    uat_type: UatType = Field(..., description="Classification enum")
    county_code: str = Field(..., description="ISO 3166-2:RO subdivision code (without RO-)")
    county_name: str = Field(..., description="County name from config/counties.yaml")
    county_siruta: int = Field(..., description="SIRUTA code of the parent county")

    # Provenance
    source_id: str = Field(..., description="Source registry identifier, e.g. 'siruta'")
    source_url: str = Field(..., description="Exact download URL of the raw file")
    retrieved_at: datetime = Field(..., description="UTC timestamp when raw file was fetched")
    raw_sha256: str = Field(..., description="SHA256 digest of the raw source file")


class LocalityRecord(BaseModel):
    """Schema for a single component locality."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    siruta: int = Field(..., description="SIRUTA identifier of the locality")
    name: str = Field(..., description="Normalised display name (comma-below diacritics)")
    name_key: str = Field(..., description="Normalised search and join key")
    parent_uat_siruta: int = Field(..., description="SIRUTA code of parent UAT")
    locality_type: str = Field(..., description="Official locality type string from INS")
    is_uat_seat: bool = Field(..., description="True if locality is the administrative seat")

    # Provenance
    source_id: str = Field(..., description="Source registry identifier, e.g. 'siruta'")
    source_url: str = Field(..., description="Exact download URL of the raw file")
    retrieved_at: datetime = Field(..., description="UTC timestamp when raw file was fetched")
    raw_sha256: str = Field(..., description="SHA256 digest of the raw source file")
