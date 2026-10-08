"""Shared polite HTTP helper implementing ``.agents/rules/scraping.md``.

- User-Agent ``mayor-tracker-ro/<version> (+research; contact: <CONTACT_EMAIL>)``;
  refuses to run without ``CONTACT_EMAIL``.
- robots.txt checked per host (RFC 9309): 2xx parsed, 4xx allows everything, 5xx or
  unreachable disallows the whole host. Cached in memory for the client's lifetime.
- At most one request per ``min_seconds_between_requests`` per host, plus jitter.
- Retries timeouts, network errors, 429 and 5xx with exponential backoff, honouring
  ``Retry-After``; ``max_retries`` is the total number of attempts.
- On-disk response cache in ``data/cache/http/`` keyed by the URL's sha256.
- ``download()`` saves raw files under ``data/raw/<source_id>/<YYYY-MM-DD>/`` and maintains
  ``manifest.json`` there. Existing raw files are never overwritten.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from pydantic import BaseModel

from mayortracker import __version__
from mayortracker.util.config import Settings
from mayortracker.util.robots import RobotsRules

logger = logging.getLogger(__name__)

USER_AGENT_TOKEN = "mayor-tracker-ro"
MAX_REDIRECTS = 5
MAX_BACKOFF_SECONDS = 60.0
RATE_JITTER = 0.2  # up to +20% on the per-host interval
BACKOFF_JITTER = 0.1  # up to +10% on each backoff delay
_SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
_REDIRECT_CODES = {301, 302, 303, 307, 308}


class HttpHelperError(RuntimeError):
    """Base class for errors raised by the HTTP helper."""


class MissingContactEmail(HttpHelperError):
    """``CONTACT_EMAIL`` is not set; downloads must identify the project."""


class RobotsDisallowed(HttpHelperError):
    """robots.txt disallows the URL for our user-agent token."""


class RobotsUnavailable(RobotsDisallowed):
    """robots.txt returned 5xx or was unreachable: the whole host is treated as disallowed."""


class HttpGiveUp(HttpHelperError):
    """All attempts failed with transient errors."""


class HttpStatusError(HttpHelperError):
    """The final response had a non-success status."""

    def __init__(self, url: str, status_code: int) -> None:
        super().__init__(f"{url}: HTTP {status_code}")
        self.url = url
        self.status_code = status_code


class RawFileConflict(HttpHelperError):
    """A raw file with the same path but different content already exists."""


class RedirectNotAllowed(HttpHelperError):
    """A redirect targets a host outside the allowed hosts."""

    def __init__(self, url: str, target_url: str, target_host: str) -> None:
        super().__init__(f"{url}: redirect to host {target_host!r} ({target_url}) is not allowed")
        self.url = url
        self.target_url = target_url
        self.target_host = target_host


@dataclass(frozen=True)
class FetchedResponse:
    url: str
    final_url: str
    status_code: int
    content: bytes
    content_type: str | None
    retrieved_at: datetime
    from_cache: bool


class ManifestEntry(BaseModel):
    url: str
    final_url: str
    filename: str
    retrieved_at: str
    sha256: str
    bytes: int
    http_status: int
    content_type: str | None


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def filename_from_url(url: str) -> str:
    """Original file name from the URL path, made safe for the filesystem."""
    name = unquote(urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1])
    name = re.sub(r"[^\w.\-]", "_", name).strip(".")
    return name or "download"


def _extract_host(url: str) -> str:
    """Return lower-cased hostname from a URL, or empty string if absent."""
    return (urlsplit(url).hostname or "").lower()


class PoliteClient:
    """Rate-limited, retrying, caching HTTP client. Use as a context manager."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = _utcnow,
        rng: random.Random | None = None,
        timeout: float = 60.0,
    ) -> None:
        email = (settings.contact_email or "").strip()
        if not email:
            raise MissingContactEmail(
                "CONTACT_EMAIL is not set. Add it to .env before downloading anything."
            )
        self.user_agent = f"{USER_AGENT_TOKEN}/{__version__} (+research; contact: {email})"
        self.min_interval = settings.http.min_seconds_between_requests
        self.max_attempts = settings.http.max_retries
        self.max_retry_after = settings.http.max_retry_after_seconds
        dirs = settings.data_dirs()
        self.cache_dir = dirs["cache_http"]
        self.raw_dir = dirs["raw"]
        self._sleep = sleep
        self._clock = clock
        self._now = now
        self._rng = rng or random.Random()
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, RobotsRules | str] = {}  # origin -> rules or failure reason
        self._client = httpx.Client(
            transport=transport,
            headers={"User-Agent": self.user_agent},
            timeout=timeout,
            follow_redirects=False,  # redirects are followed manually, each hop throttled
        )

    def __enter__(self) -> PoliteClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # ---- low level -------------------------------------------------------------------

    def _throttle(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            interval = self.min_interval * (1 + self._rng.uniform(0, RATE_JITTER))
            wait = interval - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_request[host] = self._clock()

    def _retry_after(self, response: httpx.Response) -> float | None:
        value = response.headers.get("Retry-After")
        if value is None:
            return None
        value = value.strip()
        if value.isdigit():
            return float(value)
        try:
            when = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return max(0.0, (when - self._now()).total_seconds())

    def _send_with_retries(self, url: str) -> httpx.Response:
        host = urlsplit(url).netloc.lower()
        last_problem = ""
        for attempt in range(1, self.max_attempts + 1):
            self._throttle(host)
            response: httpx.Response | None = None
            try:
                response = self._client.get(url)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                last_problem = f"{type(exc).__name__}: {exc}"
            else:
                if response.status_code != 429 and response.status_code < 500:
                    return response
                last_problem = f"HTTP {response.status_code}"
            delay = self._retry_after(response) if response is not None else None
            if delay is not None and delay > self.max_retry_after:
                raise HttpGiveUp(
                    f"{url}: Retry-After requested {delay:.1f}s, "
                    f"exceeding cap of {self.max_retry_after:.1f}s"
                )
            if attempt == self.max_attempts:
                break
            if delay is None:
                base = min(MAX_BACKOFF_SECONDS, 2.0**attempt)
                delay = base * (1 + self._rng.uniform(0, BACKOFF_JITTER))
            logger.warning(
                "%s: %s (attempt %d/%d), retrying in %.1fs",
                url, last_problem, attempt, self.max_attempts, delay,
            )
            self._sleep(delay)
        raise HttpGiveUp(f"{url}: giving up after {self.max_attempts} attempts ({last_problem})")

    def _fetch(
        self,
        url: str,
        *,
        check_robots: bool = True,
        allowed_hosts: set[str] | None = None,
        enforce_allowed_hosts: bool = True,
    ) -> tuple[str, httpx.Response]:
        current = url
        initial_host = _extract_host(url)
        allowed = {initial_host} | ({h.lower() for h in allowed_hosts} if allowed_hosts else set())
        for _ in range(MAX_REDIRECTS + 1):
            if check_robots:
                self._ensure_allowed(current)
            response = self._send_with_retries(current)
            location = response.headers.get("Location")
            if response.status_code in _REDIRECT_CODES and location:
                next_url = urljoin(current, location)
                if enforce_allowed_hosts:
                    next_host = _extract_host(next_url)
                    if next_host not in allowed:
                        raise RedirectNotAllowed(
                            url=current,
                            target_url=next_url,
                            target_host=next_host,
                        )
                current = next_url
                continue
            return current, response
        raise HttpHelperError(f"{url}: more than {MAX_REDIRECTS} redirects")

    # ---- robots.txt ------------------------------------------------------------------

    def _robots_for(self, url: str) -> RobotsRules | str:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc.lower()}"
        if origin not in self._robots:
            robots_url = f"{origin}/robots.txt"
            try:
                _, response = self._fetch(
                    robots_url,
                    check_robots=False,
                    enforce_allowed_hosts=False,
                )
            except HttpHelperError as exc:
                self._robots[origin] = f"robots.txt unreachable ({exc})"
            else:
                if response.is_success:
                    self._robots[origin] = RobotsRules.parse(response.text)
                elif 400 <= response.status_code < 500:
                    self._robots[origin] = RobotsRules.allow_all()
                else:
                    self._robots[origin] = f"robots.txt returned HTTP {response.status_code}"
            logger.info("robots.txt for %s: %s", origin, self._robots[origin])
        return self._robots[origin]

    def _ensure_allowed(self, url: str) -> None:
        rules = self._robots_for(url)
        if isinstance(rules, str):
            raise RobotsUnavailable(f"{url}: host treated as disallowed: {rules}")
        if not rules.is_allowed(url, USER_AGENT_TOKEN):
            raise RobotsDisallowed(f"{url}: disallowed by robots.txt for {USER_AGENT_TOKEN}")

    # ---- cache -----------------------------------------------------------------------

    def _cache_paths(self, url: str) -> tuple[Path, Path]:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{key}.body", self.cache_dir / f"{key}.json"

    def _cache_read(self, url: str) -> FetchedResponse | None:
        body_path, meta_path = self._cache_paths(url)
        if not (body_path.is_file() and meta_path.is_file()):
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("url") != url:
            return None
        return FetchedResponse(
            url=url,
            final_url=meta["final_url"],
            status_code=meta["status_code"],
            content=body_path.read_bytes(),
            content_type=meta.get("content_type"),
            retrieved_at=datetime.fromisoformat(meta["retrieved_at"]),
            from_cache=True,
        )

    def _cache_write(self, fetched: FetchedResponse) -> None:
        body_path, meta_path = self._cache_paths(fetched.url)
        meta = {
            "url": fetched.url,
            "final_url": fetched.final_url,
            "status_code": fetched.status_code,
            "content_type": fetched.content_type,
            "retrieved_at": _iso(fetched.retrieved_at),
            "sha256": hashlib.sha256(fetched.content).hexdigest(),
        }
        _atomic_write(body_path, fetched.content)
        _atomic_write(meta_path, json.dumps(meta, indent=2).encode("utf-8"))

    # ---- public API ------------------------------------------------------------------

    def get(
        self,
        url: str,
        *,
        use_cache: bool = True,
        allowed_hosts: set[str] | None = None,
    ) -> FetchedResponse:
        """GET ``url``. Serves from the on-disk cache unless ``use_cache`` is False.

        Raises :class:`HttpStatusError` on a non-2xx final status. Successful responses
        are always written to the cache.
        """
        initial_host = _extract_host(url)
        allowed = {initial_host} | ({h.lower() for h in allowed_hosts} if allowed_hosts else set())
        if use_cache:
            cached = self._cache_read(url)
            if cached is not None:
                final_host = _extract_host(cached.final_url)
                if final_host not in allowed:
                    raise RedirectNotAllowed(
                        url=url,
                        target_url=cached.final_url,
                        target_host=final_host,
                    )
                logger.debug("cache hit: %s", url)
                return cached
        final_url, response = self._fetch(
            url,
            allowed_hosts=allowed_hosts,
            enforce_allowed_hosts=True,
        )
        if not response.is_success:
            raise HttpStatusError(url, response.status_code)
        fetched = FetchedResponse(
            url=url,
            final_url=final_url,
            status_code=response.status_code,
            content=response.content,
            content_type=response.headers.get("Content-Type"),
            retrieved_at=self._now().astimezone(UTC),
            from_cache=False,
        )
        self._cache_write(fetched)
        return fetched

    def download(
        self,
        url: str,
        source_id: str,
        *,
        filename: str | None = None,
        use_cache: bool = True,
        allowed_hosts: set[str] | None = None,
    ) -> ManifestEntry:
        """Save ``url`` under ``data/raw/<source_id>/<YYYY-MM-DD>/`` and update the manifest.

        The folder date and ``retrieved_at`` are the response's original retrieval time
        (also when served from cache). Re-saving identical content is a no-op; different
        content at an existing path raises :class:`RawFileConflict`.
        """
        if not _SOURCE_ID_RE.match(source_id):
            raise ValueError(f"invalid source_id: {source_id!r}")
        name = filename or filename_from_url(url)
        if name in {"", ".", "..", "manifest.json"} or "/" in name or "\\" in name:
            raise ValueError(f"invalid filename: {name!r}")

        fetched = self.get(url, use_cache=use_cache, allowed_hosts=allowed_hosts)
        retrieved_at = fetched.retrieved_at.astimezone(UTC)
        folder = self.raw_dir / source_id / retrieved_at.date().isoformat()
        target = folder / name
        sha256 = hashlib.sha256(fetched.content).hexdigest()
        manifest_path = folder / "manifest.json"
        entries: list[dict[str, object]] = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path.is_file()
            else []
        )

        if target.exists():
            existing_sha = hashlib.sha256(target.read_bytes()).hexdigest()
            if existing_sha != sha256:
                raise RawFileConflict(
                    f"{target} exists with sha256 {existing_sha}, new content has {sha256}"
                )
            for entry in entries:
                if entry.get("filename") == name:
                    logger.info("already saved: %s", target)
                    return ManifestEntry.model_validate(entry)
        else:
            _atomic_write(target, fetched.content)
            logger.info("saved %s (%d bytes)", target, len(fetched.content))

        entry_model = ManifestEntry(
            url=url,
            final_url=fetched.final_url,
            filename=name,
            retrieved_at=_iso(retrieved_at),
            sha256=sha256,
            bytes=len(fetched.content),
            http_status=fetched.status_code,
            content_type=fetched.content_type,
        )
        entries = [e for e in entries if e.get("filename") != name]
        entries.append(entry_model.model_dump())
        entries.sort(key=lambda e: str(e["filename"]))
        _atomic_write(manifest_path, (json.dumps(entries, indent=2) + "\n").encode("utf-8"))
        return entry_model
