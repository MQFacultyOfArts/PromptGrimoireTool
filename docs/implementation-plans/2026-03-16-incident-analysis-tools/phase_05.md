# Incident Analysis Tools Implementation Plan — Phase 5

**Goal:** CLI query commands that replace ad-hoc grep pipelines: `sources` (provenance inventory), `timeline` (cross-source event view), `breakdown` (deterministic error counts).

**Architecture:** Query functions in `scripts/incident/queries.py` (pure functions: connection → data), wired into typer CLI commands in `scripts/incident_db.py`. All commands accept `--db`, `--json`, `--csv` flags. Timeline accepts AEDT input, converts to UTC for queries.

**Tech Stack:** Python 3.14, typer, rich (tables), sqlite3, csv/json stdlib

**Scope:** Phase 5 of 6 from original design

**Codebase verified:** 2026-03-16

---

## Acceptance Criteria Coverage

This phase implements and tests:

### incident-analysis-tools.AC4: CLI queries produce correct cross-source output
- **incident-analysis-tools.AC4.1 Success:** `timeline --start "2026-03-16 16:05" --end "2026-03-16 16:14"` shows HAProxy 504s, JSONL INVALIDATEs, and PG FATALs interleaved by `ts_utc`
- **incident-analysis-tools.AC4.2 Success:** `breakdown` produces deterministic counts matching between runs on the same database
- **incident-analysis-tools.AC4.3 Success:** `sources` displays provenance table with format, sha256 prefix, claimed timezone, first/last timestamp, and line count per source
- **incident-analysis-tools.AC4.4 Failure:** `timeline` with `--start` after `--end` produces a clear error, not empty results

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create scripts/incident/queries.py

**Verifies:** None (functionality tested in Task 2)

**Files:**
- Create: `scripts/incident/queries.py`

**Implementation:**

Three pure query functions that take a `sqlite3.Connection` and return structured data:

**`query_sources(conn) -> list[dict]`**

Uses the `timeline` view (which includes `source_id`) for per-source stats — this avoids routing to format-specific tables:

```sql
SELECT s.id, s.filename, s.format, substr(s.sha256, 1, 12) AS sha256_prefix,
       s.timezone, s.size,
       MIN(t.ts_utc) AS first_ts,
       MAX(t.ts_utc) AS last_ts,
       COUNT(t.source_id) AS event_count
FROM sources s
LEFT JOIN timeline t ON t.source_id = s.id
GROUP BY s.id
ORDER BY s.id
```

The `LEFT JOIN` ensures sources with zero parsed events (e.g., empty journal) still appear with NULL timestamps and count 0. Returns list of dicts: `filename`, `format`, `sha256_prefix`, `timezone`, `size`, `first_ts`, `last_ts`, `event_count`.

**`query_timeline(conn, start_utc: str, end_utc: str, level_filter: str | None = None) -> list[dict]`**
```sql
SELECT * FROM timeline
WHERE ts_utc >= ? AND ts_utc <= ?
ORDER BY ts_utc
```
If `level_filter` is set, add `AND level_or_status = ?`. Returns list of dicts from the timeline view.

**`query_breakdown(conn) -> list[dict]`**
```sql
SELECT source, level_or_status, COUNT(*) AS count
FROM timeline
GROUP BY source, level_or_status
ORDER BY count DESC
```
Returns list of dicts: `source`, `level_or_status`, `count`. Deterministic because ORDER BY is explicit.

**Output formatting helpers:**

- `render_table(data: list[dict], title: str) -> None` — Rich table to stdout
- `render_json(data: list[dict]) -> None` — JSON array to stdout
- `render_csv(data: list[dict]) -> None` — CSV to stdout using `csv.DictWriter`

**Commit:**
```bash
git add scripts/incident/queries.py
git commit -m "feat: add query functions for sources, timeline, breakdown"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Wire CLI commands and add tests

**Verifies:** incident-analysis-tools.AC4.1, incident-analysis-tools.AC4.2, incident-analysis-tools.AC4.3, incident-analysis-tools.AC4.4

**Files:**
- Modify: `scripts/incident_db.py` — add `sources`, `timeline`, `breakdown` commands
- Create: `tests/unit/incident/test_queries.py`

**Implementation:**

Add three commands to `scripts/incident_db.py`:

```python
@app.command()
def sources(
    db: Path = typer.Option(Path("incident.db"), help="SQLite database path"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    csv_output: bool = typer.Option(False, "--csv", help="Output as CSV"),
) -> None:
    """Display provenance table for all ingested sources."""

@app.command()
def timeline(
    start: str = typer.Option(..., help="Start time (AEDT, e.g. '2026-03-16 16:05')"),
    end: str = typer.Option(..., help="End time (AEDT, e.g. '2026-03-16 16:14')"),
    level: str | None = typer.Option(None, help="Filter by level/status"),
    db: Path = typer.Option(Path("incident.db"), help="SQLite database path"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    csv_output: bool = typer.Option(False, "--csv", help="Output as CSV"),
) -> None:
    """Show cross-source timeline for a time window (times in AEDT)."""

@app.command()
def breakdown(
    db: Path = typer.Option(Path("incident.db"), help="SQLite database path"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    csv_output: bool = typer.Option(False, "--csv", help="Output as CSV"),
) -> None:
    """Show event counts grouped by source and level/status."""
```

The `timeline` command:
1. Validates `--start` < `--end` — if not, print error and exit 1 (AC4.4)
2. Looks up timezone from `sources` table (first row)
3. Converts AEDT start/end to UTC using `zoneinfo.ZoneInfo(tz)`
4. Calls `query_timeline(conn, start_utc, end_utc, level)`

**Testing:**

Create a pre-populated SQLite database fixture (in `tmp_path`) with known events across all 4 source tables. Tests verify:

- **AC4.1:** `timeline` with a known window returns HAProxy, JSONL, and PG events interleaved by `ts_utc`
- **AC4.2:** `breakdown` returns identical counts on two consecutive runs against the same database
- **AC4.3:** `sources` returns provenance with format, sha256 prefix, timezone, first/last ts, event count
- **AC4.4:** `timeline` with start > end exits with error message, not empty results

Use `typer.testing.CliRunner` to test CLI commands end-to-end.

Also test `--json` output is valid JSON (parseable by `json.loads`) and `--csv` output is valid CSV.

**Verification:**
```bash
uv run grimoire test run tests/unit/incident/test_queries.py
```

**Commit:**
```bash
git add scripts/incident_db.py tests/unit/incident/test_queries.py
git commit -m "feat: add sources, timeline, breakdown CLI commands

Rich table output by default, --json and --csv for scripting.
Timeline accepts AEDT input, converts to UTC.
Tests verify AC4.1-AC4.4."
```
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: End-to-end UAT with real 2026-03-16 incident data

**Verifies:** Design success criteria (all ACs end-to-end against real data)

This is a **human UAT step**. Unit tests use synthetic fixtures; this verifies the full pipeline against production logs.

**Prerequisites:**
- Collection script deployed and run on production (Phase 1 Task 2 completed)
- Tarball from `collect-telemetry.sh --start "2026-03-16 14:50" --end "2026-03-16 17:20"` available locally

**Steps:**

1. Ingest the real tarball:
```bash
uv run scripts/incident_db.py ingest telemetry-*.tar.gz --db /tmp/incident-test.db
```
Expected: All 4 sources ingested, event counts printed.

2. Verify sources provenance:
```bash
uv run scripts/incident_db.py sources --db /tmp/incident-test.db
```
Expected: 4 rows (journal, jsonl, haproxy, pglog) with correct sha256 prefixes, timezones, first/last timestamps, and non-zero event counts.

3. Verify the 16:06 upload stall is visible in timeline:
```bash
uv run scripts/incident_db.py timeline --start "2026-03-16 16:05" --end "2026-03-16 16:14" --db /tmp/incident-test.db
```
Expected: HAProxy 504s, JSONL INVALIDATE events, and PG FATAL/ERROR entries interleaved by UTC timestamp in a single table.

4. Verify deterministic breakdown:
```bash
uv run scripts/incident_db.py breakdown --db /tmp/incident-test.db > /tmp/breakdown1.txt
uv run scripts/incident_db.py breakdown --db /tmp/incident-test.db > /tmp/breakdown2.txt
diff /tmp/breakdown1.txt /tmp/breakdown2.txt
```
Expected: No diff (identical output).

5. Verify re-ingest is a no-op:
```bash
uv run scripts/incident_db.py ingest telemetry-*.tar.gz --db /tmp/incident-test.db
```
Expected: "0 files ingested, 4 skipped (dedup)".

6. Run pre-PR gate:
```bash
uv run grimoire test all
uv run complexipy scripts/incident/ --max-complexity-allowed 15
```
Expected: All tests pass, no complexity violations.

**Evidence required:**
- Screenshot or terminal output of timeline showing the 16:06 stall
- Breakdown output showing deterministic counts
<!-- END_TASK_3 -->
