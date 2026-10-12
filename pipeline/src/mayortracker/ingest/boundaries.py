"""Ingest Eurostat GISCO LAU boundaries files."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mayortracker.util.config import Settings
    from mayortracker.util.http import ManifestEntry, PoliteClient

logger = logging.getLogger(__name__)

SOURCE_ID = "lau_boundaries"
SOURCE_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/lau/shp/LAU_RG_01M_2024_4326.shp.zip"
)
ALLOWED_HOSTS: frozenset[str] = frozenset({"gisco-services.ec.europa.eu"})


def ingest_lau_boundaries(
    settings: Settings, *, client: PoliteClient | None = None
) -> ManifestEntry:
    """Download Eurostat GISCO LAU boundaries shapefile zip and record manifest.

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
        logger.info("Ingesting LAU boundaries from %s", SOURCE_URL)
        return client.download(
            SOURCE_URL,
            source_id=SOURCE_ID,
            filename="ref-lau-2024-01m.shp.zip",
            allowed_hosts=set(ALLOWED_HOSTS),
        )
