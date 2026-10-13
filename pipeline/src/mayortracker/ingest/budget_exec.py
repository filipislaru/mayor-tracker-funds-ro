"""Ingest budget execution datasets into data/raw/budget_exec/."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from mayortracker.util.http import PoliteClient

if TYPE_CHECKING:
    from mayortracker.util.config import Settings
    from mayortracker.util.http import ManifestEntry

logger = logging.getLogger(__name__)

BUDGET_EXEC_2024_URL = (
    "https://data.gov.ro/dataset/c0d25ff7-27d5-4c31-9809-540f77b20180/resource/"
    "aac89795-56f0-41ee-a631-26695f73c5d6/download/situaia-veniturilor-i-cheltuielilor-2024.xlsx"
)


def ingest_budget_exec(
    settings: Settings, client: PoliteClient | None = None
) -> list[ManifestEntry]:
    """Download available official local budget execution files via PoliteClient."""
    entries: list[ManifestEntry] = []
    own_client = client is None
    c = client or PoliteClient(settings)
    try:
        logger.info("Downloading 2024 local budget execution file from data.gov.ro")
        entry = c.download(
            BUDGET_EXEC_2024_URL,
            source_id="budget_exec",
            filename="situaia-veniturilor-i-cheltuielilor-2024.xlsx",
        )
        entries.append(entry)
    finally:
        if own_client:
            c.close()
    return entries
