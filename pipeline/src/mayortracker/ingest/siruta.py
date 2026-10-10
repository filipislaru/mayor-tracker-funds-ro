"""Ingest official SIRUTA nomenclature files from data.gov.ro."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mayortracker.util.config import Settings
    from mayortracker.util.http import ManifestEntry, PoliteClient

logger = logging.getLogger(__name__)

SOURCE_ID = "siruta"
SOURCE_URL = (
    "https://data.gov.ro/dataset/26e9db4c-2afe-4d86-8a8f-caa879cae7ea/"
    "resource/1f023137-96d7-498c-a90f-75c13253615c/download/siruta.csv"
)
ALLOWED_HOSTS: frozenset[str] = frozenset({"data.gov.ro"})


def ingest_siruta(settings: Settings, *, client: PoliteClient | None = None) -> ManifestEntry:
    """Download the official SIRUTA CSV nomenclature and record manifest.

    Parameters
    ----------
    settings : Settings
        Application settings.
    client : PoliteClient | None
        Optional PoliteClient instance (e.g. for testing with mocked transports).

    Returns
    -------
    ManifestEntry
        Manifest entry detailing the saved raw file.
    """
    from mayortracker.util.http import PoliteClient

    if client is None:
        client = PoliteClient(settings)

    with client:
        logger.info("Ingesting SIRUTA from %s", SOURCE_URL)
        return client.download(
            SOURCE_URL,
            source_id=SOURCE_ID,
            filename="siruta.csv",
            allowed_hosts=set(ALLOWED_HOSTS),
        )
