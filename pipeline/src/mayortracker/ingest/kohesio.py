"""Ingest official Kohesio datasets for Romania from kohesio.ec.europa.eu."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mayortracker.util.config import Settings
    from mayortracker.util.http import ManifestEntry, PoliteClient

logger = logging.getLogger(__name__)

SOURCE_ID = "kohesio"

# Official download URLs from Kohesio Data API (kohesio.ec.europa.eu/en/data)
PROJECTS_2014_2020_URL = (
    "https://kohesio.ec.europa.eu/api/data/object?id=data/projects-2014-2020/latest/RO-pp14-20-latest.csv"
)
PROJECTS_2021_2027_URL = (
    "https://kohesio.ec.europa.eu/api/data/object?id=data/projects-2021-2027/latest/RO-pp21-27-latest.csv"
)
BENEFICIARIES_URL = (
    "https://kohesio.ec.europa.eu/api/data/object?id=data/beneficiaries/latest/RO-latest.csv"
)
NUTS_URL = (
    "https://kohesio.ec.europa.eu/api/data/object?id=data/nuts/latest/RO-latest.csv"
)

ALLOWED_HOSTS: frozenset[str] = frozenset({"kohesio.ec.europa.eu"})

FILES_TO_DOWNLOAD: list[tuple[str, str]] = [
    ("RO-pp14-20-latest.csv", PROJECTS_2014_2020_URL),
    ("RO-pp21-27-latest.csv", PROJECTS_2021_2027_URL),
    ("RO-beneficiaries-latest.csv", BENEFICIARIES_URL),
    ("RO-nuts-latest.csv", NUTS_URL),
]


def ingest_kohesio(
    settings: Settings, *, client: PoliteClient | None = None
) -> list[ManifestEntry]:
    """Download official Kohesio datasets for Romania and record manifest entries.

    Downloads:
    - 2014–2020 projects CSV for Romania
    - 2021–2027 projects CSV for Romania
    - Beneficiaries CSV for Romania
    - NUTS classification hierarchy CSV for Romania

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

    entries: list[ManifestEntry] = []
    with client:
        for filename, url in FILES_TO_DOWNLOAD:
            logger.info("Ingesting Kohesio dataset '%s' from %s", filename, url)
            entry = client.download(
                url,
                source_id=SOURCE_ID,
                filename=filename,
                allowed_hosts=set(ALLOWED_HOSTS),
            )
            entries.append(entry)

    return entries
