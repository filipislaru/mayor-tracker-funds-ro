# Romania Mayor Tracker (working title)

A reproducible database and public website tracking, for each Romanian mayor
and term: planned projects, claimed achievements, independently verified
delivery, funds secured, and procurement integrity risk indicators.

- What we are building: `docs/SPEC.md`
- How it fits together: `docs/ARCHITECTURE.md`
- Where the data comes from: `docs/DATA_SOURCES.md`
- Decisions made so far: `docs/DECISIONS.md`
- What is next: `docs/TASKS.md`
- How work is done (Claude ↔ Antigravity): `docs/WORKFLOW.md`

Coding agents: read `AGENTS.md` first.

## Setup

### 1. Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/) (fast Python package and project manager)

To install `uv` (macOS / Linux):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Configure environment

Copy `.env.example` to `.env` and fill in your contact email:
```bash
cp .env.example .env
```
Edit `.env` to set `CONTACT_EMAIL` (required before running any downloads).

### 4. Initialize data directories

```bash
uv run mt init-data
```

### 5. Verify installation

Check project and environment health:
```bash
uv run mt doctor
```

Run test suite and linter:
```bash
uv run pytest
uv run ruff check .
```

