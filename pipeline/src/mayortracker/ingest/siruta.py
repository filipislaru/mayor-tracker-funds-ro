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
    "https://data.gov.ro/dataset/721c9059-5f87-4c79-9854-a1d5c18f58d5/"
    "resource/dac903f0-32b5-489a-89e7-2c80d96cf68d/download/siruta_s1_2026.csv"
)
DOC_URL = (
    "https://data.gov.ro/dataset/06950cb3-41b7-48b8-91bb-4a329786d178/"
    "resource/8d5d8a77-d8bf-425d-a9f9-2514d751e84e/download/legenda-siruta.xml"
)
ALLOWED_HOSTS: frozenset[str] = frozenset({"data.gov.ro"})


def ingest_siruta(
    settings: Settings, *, client: PoliteClient | None = None
) -> list[ManifestEntry]:
    """Download the official SIRUTA CSV nomenclature and documentation XML and record manifest.

    Parameters
    ----------
    settings : Settings
        Application settings.
    client : PoliteClient | None
        Optional PoliteClient instance (e.g. for testing with mocked transports).

    Returns
    -------
    list[ManifestEntry]
        Manifest entries detailing the saved raw files.
    """
    from mayortracker.util.http import PoliteClient

    if client is None:
        client = PoliteClient(settings)

    with client:
        logger.info("Ingesting SIRUTA CSV from %s", SOURCE_URL)
        csv_entry = client.download(
            SOURCE_URL,
            source_id=SOURCE_ID,
            filename="siruta_s1_2026.csv",
            allowed_hosts=set(ALLOWED_HOSTS),
        )
        logger.info("Ingesting SIRUTA documentation XML from %s", DOC_URL)
        doc_entry = client.download(
            DOC_URL,
            source_id=SOURCE_ID,
            filename="legenda-siruta.xml",
            allowed_hosts=set(ALLOWED_HOSTS),
        )
        return [csv_entry, doc_entry]
