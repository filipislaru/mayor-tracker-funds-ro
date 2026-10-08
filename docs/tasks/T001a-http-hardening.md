# T001a — HTTP helper hardening

Status: ready
Depends on: T001
Branch: task/T001a-http-hardening

## Goal
Close two gaps in PoliteClient found in the T001 review, before the first real downloads in T002.

## Requirements
1. Retry-After cap: add `http.max_retry_after_seconds` to config/settings.yaml (default 300) and the Settings model. If a Retry-After value exceeds it, do not sleep: raise HttpGiveUp with a message stating the requested delay.
2. Host allow-list for redirects: `get()` and `download()` accept `allowed_hosts: set[str] | None`. The host of the requested URL is always allowed. A redirect to any other host raises a new `RedirectNotAllowed` error, unless that host is in `allowed_hosts`. Host comparison is case-insensitive and exact (no subdomain wildcards).
3. Tests: Retry-After above the cap gives up without sleeping; Retry-After at the cap is honoured; a cross-host redirect raises; a cross-host redirect to an allowed host succeeds; a same-host redirect works.

## Acceptance criteria
- [ ] `uv run ruff check .` and `uv run pytest` pass.
- [ ] New tests cover each requirement.
- [ ] handoff/T001a.md written.

## Out of scope
Any other change to the HTTP helper.
