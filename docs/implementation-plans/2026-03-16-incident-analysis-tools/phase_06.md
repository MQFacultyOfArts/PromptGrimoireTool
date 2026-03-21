# Incident Analysis Tools Implementation Plan — Phase 6

**Goal:** Fetch Beszel system metrics via PocketBase REST API and ingest into `beszel_metrics` table. Optional phase — the core pipeline works without it.

**Architecture:** httpx sync client queries PocketBase API with time-window filter. Metrics JSON parsed from `stats` column. CLI command accepts AEDT times, converts to UTC for API filter. Requires SSH tunnel to brian.fedarch.org for API access.

**Tech Stack:** Python 3.14, httpx (already a project dep), json stdlib

**Scope:** Phase 6 of 6 from original design (optional)

**Codebase verified:** 2026-03-16

---

## Acceptance Criteria Coverage

This phase has no numbered ACs in the design plan. Verification is operational:
- Beszel command fetches metrics for a time window and populates `beszel_metrics` table
- Unreachable API produces clear error message, not traceback
- Metrics appear in timeline view alongside log events

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create scripts/incident/parsers/beszel.py and CLI command

**Verifies:** None (infrastructure + functionality, verified operationally and in Task 2)

**Files:**
- Create: `scripts/incident/parsers/beszel.py`
- Modify: `scripts/incident_db.py` — add `beszel` command

**Implementation:**

`scripts/incident/parsers/beszel.py`:

```python
def fetch_beszel_metrics(
    hub_url: str,
    start_utc: str,
    end_utc: str,
    collection: str = "system_stats",
) -> list[dict]:
```

Logic:
1. Build PocketBase filter: `created >= "{start_utc}" && created <= "{end_utc}"`
2. Paginate through results: `GET {hub_url}/api/collections/{collection}/records?filter=...&page=N&perPage=200&sort=created`
3. For each record, parse `stats` JSON column and extract:
   - `ts_utc` from `created` field (PocketBase stores UTC)
   - `cpu`, `mem_used` (from `m` or `mu`), `mem_percent` (from `mp`), `net_sent` (from `ns`), `net_recv` (from `nr`), `disk_read` (from `dr`), `disk_write` (from `dw`), `load_1`, `load_5`, `load_15`
4. Return list of dicts matching `beszel_metrics` table schema
5. On connection error: raise `SystemExit(1)` with clear message (not traceback)

Use `httpx.Client()` (sync) — this is a CLI tool, no async needed.

Add `beszel` command to `scripts/incident_db.py`:

```python
@app.command()
def beszel(
    start: str = typer.Option(..., help="Start time (AEDT)"),
    end: str = typer.Option(..., help="End time (AEDT)"),
    hub: str = typer.Option("http://localhost:8090", help="Beszel hub URL (via SSH tunnel)"),
    db: Path = typer.Option(Path("incident.db"), help="SQLite database path"),
) -> None:
    """Fetch Beszel system metrics for a time window."""
```

The command:
1. Converts AEDT start/end to UTC (same pattern as timeline command)
2. Calls `fetch_beszel_metrics(hub, start_utc, end_utc)`
3. Opens SQLite database, creates schema if needed
4. Inserts a synthetic source row with `format='beszel'`, `filename='beszel-api'`, `sha256` derived from `hashlib.sha256(f"{hub}:{start_utc}:{end_utc}".encode()).hexdigest()`, and the timezone/window from the command args. This satisfies the `beszel_metrics.source_id NOT NULL REFERENCES sources(id)` FK constraint.
5. Prints summary: "Fetched {N} metric data points"

**Commit:**
```bash
git add scripts/incident/parsers/beszel.py scripts/incident_db.py
git commit -m "feat: add Beszel metrics fetcher and CLI command

Queries PocketBase REST API via SSH tunnel.
Parses compact JSON keys into normalised columns."
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Beszel fetcher tests with mocked API

**Verifies:** Operational correctness (no design ACs for this phase)

**Files:**
- Create: `tests/unit/incident/test_beszel.py`

**Testing:**

Tests must verify:
- Successful fetch: mock httpx response with realistic PocketBase JSON → returns correct list of dicts with normalised column names
- Pagination: mock 2-page response → returns all records from both pages
- Empty result: mock empty `items` array → returns empty list
- Connection error: mock `httpx.ConnectError` → raises `SystemExit` with clear message
- HTTP error (e.g., 404): mock 404 response → raises `SystemExit` with status code in message
- Compact key mapping: `ns` → `net_sent`, `nr` → `net_recv`, `cpu` → `cpu`, etc.

Use `unittest.mock.patch` on `httpx.Client.get` to mock responses. Do NOT make real HTTP calls in tests.

**Verification:**
```bash
uv run grimoire test run tests/unit/incident/test_beszel.py
```

**Commit:**
```bash
git add tests/unit/incident/test_beszel.py
git commit -m "test: add Beszel metrics fetcher tests with mocked API"
```
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
