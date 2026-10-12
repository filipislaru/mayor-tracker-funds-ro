"""Manual file registration for offline or manually fetched sources."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from mayortracker.util.config import Settings
from mayortracker.util.http import _atomic_write, _iso

logger = logging.getLogger(__name__)

_SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")


class RegisteredFile(BaseModel):
    """Manifest record for a manually registered raw file."""

    url: str
    filename: str
    retrieved_at: str
    sha256: str
    size: int
    bytes: int
    retrieval_method: str = "manual"
    retrieved_by: str = "user"


def register_file(
    file_path: Path,
    *,
    source_id: str,
    source_url: str,
    settings: Settings,
    now: Callable[[], datetime] | None = None,
) -> RegisteredFile:
    """Register a local file into data/raw/<source_id>/<YYYY-MM-DD>/ with a manifest entry.

    Never overwrites an existing raw file.
    """
    if not file_path.is_file():
        raise FileNotFoundError(f"File to register does not exist: {file_path}")

    if not _SOURCE_ID_RE.match(source_id):
        raise ValueError(f"Invalid source_id: {source_id!r}")

    if not source_url.strip():
        raise ValueError("source_url must not be empty")

    clock_now = (now() if now else datetime.now(UTC)).astimezone(UTC)
    date_str = clock_now.date().isoformat()

    folder = settings.data_dir / "raw" / source_id / date_str
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / file_path.name

    if target.exists():
        raise FileExistsError(
            f"Target raw file already exists: {target}. Raw files are immutable."
        )

    content = file_path.read_bytes()
    sha256 = hashlib.sha256(content).hexdigest()
    size = len(content)

    manifest_path = folder / "manifest.json"
    entries: list[dict[str, object]] = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.is_file()
        else []
    )

    for entry in entries:
        if entry.get("filename") == file_path.name:
            raise FileExistsError(
                f"File {file_path.name} already declared in manifest: {manifest_path}."
            )

    _atomic_write(target, content)
    logger.info("Copied manual file %s to %s (%d bytes)", file_path, target, size)

    entry_model = RegisteredFile(
        url=source_url,
        filename=file_path.name,
        retrieved_at=_iso(clock_now),
        sha256=sha256,
        size=size,
        bytes=size,
        retrieval_method="manual",
        retrieved_by="user",
    )
    entries.append(entry_model.model_dump())
    entries.sort(key=lambda e: str(e["filename"]))
    _atomic_write(manifest_path, (json.dumps(entries, indent=2) + "\n").encode("utf-8"))
    return entry_model
