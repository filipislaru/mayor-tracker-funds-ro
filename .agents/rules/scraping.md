---
trigger: model_decision
description: "Apply when writing or changing code that downloads files, calls web APIs, crawls websites or scrapes HTML/PDF documents from the web."
---

# Scraping and downloading rules

## Order of preference
1. Official bulk download or documented API.
2. Official machine-readable file linked from an official page.
3. Polite scraping of public pages, only when 1 and 2 do not exist.

Record which option was used, and why, in the handoff.

## Politeness
- Read and obey robots.txt before crawling a host. If disallowed, stop and report.
- Maximum one request per second per host; add jitter. Lower if the host is slow.
- User-Agent: `mayor-tracker-ro/<version> (+research; contact: <CONTACT_EMAIL from .env>)`.
- Retry only transient failures (timeouts, 429, 5xx) with exponential backoff, maximum 5 attempts. Honour `Retry-After`.
- Cache every response on disk under `data/cache/http/`, keyed by URL, so reruns do not re-download.

## Hard limits
- Never bypass logins, paywalls, CAPTCHAs, rate limits or other technical restrictions.
- Never submit forms that change state, create accounts or use credentials.
- Never collect social-media content, user profiles or reader comments.
- Never follow links to sites outside the source's own domain unless the brief lists them.

## Saving
- Raw files go to `data/raw/<source_id>/<YYYY-MM-DD>/`, original filename preserved where possible.
- Write `manifest.json` in that folder: one entry per file with `url`, `retrieved_at` (UTC ISO 8601), `sha256`, `bytes`, `http_status`, `content_type`.
- Never modify a raw file after saving it.

## Discovery tasks (finding documents on many websites)
- Log every URL attempted and its outcome to `data/interim/<source_id>/crawl_log.parquet` (url, status, reason, timestamp).
- Report coverage: how many sites were attempted, reached and yielded documents, and the main reasons for failures.
- Do not guess URLs by pattern unless the brief allows it, and mark guessed URLs as such in the log.
