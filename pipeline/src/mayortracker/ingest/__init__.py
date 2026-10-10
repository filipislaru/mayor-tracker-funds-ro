"""Data ingestion pipelines."""

from mayortracker.ingest.boundaries import ingest_lau_boundaries
from mayortracker.ingest.siruta import ingest_siruta

__all__ = ["ingest_lau_boundaries", "ingest_siruta"]
