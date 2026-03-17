# Incident Analysis Tools Implementation Plan — Phase 2

**Goal:** SQLite schema creation, tarball ingest orchestration, and provenance tracking with sha256 deduplication.

**Architecture:** Standalone typer CLI (`scripts/incident_db.py`) with `scripts/incident/` package. Source-typed tables unified by a `timeline` UNION ALL view. Pure function provenance parsing (FCIS).

**Tech Stack:** Python 3.14, typer, SQLite (stdlib sqlite3), pathlib, hashlib

**Scope:** Phase 2 of 6 from original design

**Codebase verified:** 2026-03-16

---

## Acceptance Criteria Coverage

This phase implements and tests:

### incident-analysis-tools.AC2: Ingest loads all sources with correct timezones
- **incident-analysis-tools.AC2.1 Success:** `ingest` populates `sources` table with one row per file, matching manifest metadata
- **incident-analysis-tools.AC2.5 Edge:** Re-ingesting the same tarball is a no-op (sha256 dedup) — zero new rows inserted
- **incident-analysis-tools.AC2.6 Failure:** Tarball without `manifest.json` produces a clear error message, not a traceback

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create scripts/incident/ package structure and schema

**Verifies:** None (infrastructure task)

**Files:**
- Create: `scripts/incident/__init__.py`
- Create: `scripts/incident/schema.py`

**Implementation:**

`scripts/incident/__init__.py` — empty package init.

`scripts/incident/schema.py` — SQLite schema as a module-level string constant. Tables:

- `sources` — one row per ingested file: `id INTEGER PRIMARY KEY`, `filename TEXT NOT NULL`, `format TEXT NOT NULL` (journal/jsonl/haproxy/pglog/beszel), `sha256 TEXT NOT NULL UNIQUE`, `size INTEGER NOT NULL`, `mtime INTEGER NOT NULL`, `hostname TEXT NOT NULL`, `timezone TEXT NOT NULL`, `window_start_utc TEXT NOT NULL`, `window_end_utc TEXT NOT NULL`, `ingested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))`
- `journal_events` — `id INTEGER PRIMARY KEY`, `source_id INTEGER NOT NULL REFERENCES sources(id)`, `ts_utc TEXT NOT NULL`, `priority INTEGER`, `pid INTEGER`, `unit TEXT`, `message TEXT`, `raw_json TEXT`
- `jsonl_events` — `id INTEGER PRIMARY KEY`, `source_id INTEGER NOT NULL REFERENCES sources(id)`, `ts_utc TEXT NOT NULL`, `level TEXT`, `event TEXT`, `user_id TEXT`, `workspace_id TEXT`, `request_path TEXT`, `exc_info TEXT`, `extra_json TEXT`
- `haproxy_events` — `id INTEGER PRIMARY KEY`, `source_id INTEGER NOT NULL REFERENCES sources(id)`, `ts_utc TEXT NOT NULL`, `client_ip TEXT`, `status_code INTEGER`, `tr_ms INTEGER`, `tw_ms INTEGER`, `tc_ms INTEGER`, `tr_resp_ms INTEGER`, `ta_ms INTEGER`, `backend TEXT`, `server TEXT`, `method TEXT`, `path TEXT`, `bytes_read INTEGER`
- `pg_events` — `id INTEGER PRIMARY KEY`, `source_id INTEGER NOT NULL REFERENCES sources(id)`, `ts_utc TEXT NOT NULL`, `pid INTEGER`, `level TEXT`, `error_type TEXT`, `detail TEXT`, `statement TEXT`, `message TEXT`
- `beszel_metrics` — `id INTEGER PRIMARY KEY`, `source_id INTEGER NOT NULL REFERENCES sources(id)`, `ts_utc TEXT NOT NULL`, `cpu REAL`, `mem_used REAL`, `mem_percent REAL`, `net_sent REAL`, `net_recv REAL`, `disk_read REAL`, `disk_write REAL`, `load_1 REAL`, `load_5 REAL`, `load_15 REAL`

Indexes:
- `CREATE INDEX idx_journal_ts ON journal_events(ts_utc)`
- `CREATE INDEX idx_jsonl_ts ON jsonl_events(ts_utc)`
- `CREATE INDEX idx_haproxy_ts ON haproxy_events(ts_utc)`
- `CREATE INDEX idx_pg_ts ON pg_events(ts_utc)`
- `CREATE INDEX idx_beszel_ts ON beszel_metrics(ts_utc)`

Timeline view (includes `source_id` for per-source stats in `sources` command):
```sql
CREATE VIEW IF NOT EXISTS timeline AS
SELECT source_id, ts_utc, 'journal' AS source, priority AS level_or_status, message, NULL AS extra
FROM journal_events
UNION ALL
SELECT source_id, ts_utc, 'jsonl' AS source, level AS level_or_status, event AS message, extra_json AS extra
FROM jsonl_events
UNION ALL
SELECT source_id, ts_utc, 'haproxy' AS source, CAST(status_code AS TEXT) AS level_or_status,
       method || ' ' || path AS message, NULL AS extra
FROM haproxy_events
UNION ALL
SELECT source_id, ts_utc, 'pglog' AS source, level AS level_or_status, message, detail AS extra
FROM pg_events
ORDER BY ts_utc;
```

Expose a `create_schema(conn: sqlite3.Connection) -> None` function that executes all DDL statements and enables WAL mode + `synchronous=NORMAL`.

**Verification:**

```bash
uv run python -c "
import sqlite3
from scripts.incident.schema import create_schema
conn = sqlite3.connect(':memory:')
create_schema(conn)
tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
print('Tables:', sorted(tables))
assert 'sources' in tables
assert 'journal_events' in tables
print('OK')
"
```

**Commit:**
```bash
git add scripts/incident/__init__.py scripts/incident/schema.py
git commit -m "feat: add SQLite schema for incident analysis"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create scripts/incident_db.py typer CLI entry point

**Verifies:** None (infrastructure task)

**Files:**
- Create: `scripts/incident_db.py`

**Implementation:**

Standalone typer CLI with `no_args_is_help=True`. For Phase 2, only the `ingest` command is wired up. Other commands (`sources`, `timeline`, `breakdown`) are registered as stubs that print "Not yet implemented" — they'll be filled in Phase 5.

```python
#!/usr/bin/env python3
"""Incident analysis CLI — ingest production telemetry tarballs into SQLite."""

from pathlib import Path
import typer

app = typer.Typer(no_args_is_help=True, help="Incident analysis: ingest and query production telemetry.")

@app.command()
def ingest(
    tarball: Path = typer.Argument(..., help="Path to telemetry tarball (.tar.gz)"),
    db: Path = typer.Option(Path("incident.db"), help="SQLite database path"),
) -> None:
    """Ingest a telemetry tarball into the SQLite database."""
    from scripts.incident.ingest import run_ingest
    run_ingest(tarball, db)

if __name__ == "__main__":
    app()
```

**Verification:**

```bash
uv run scripts/incident_db.py --help
```
Expected: Help text with `ingest` command listed.

```bash
uv run scripts/incident_db.py ingest --help
```
Expected: Help text for ingest showing `TARBALL` argument and `--db` option.

**Commit:**
```bash
git add scripts/incident_db.py
git commit -m "feat: add incident analysis CLI entry point"
```
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Create scripts/incident/provenance.py (manifest parsing)

**Verifies:** None (functionality tested in Task 4)

**Files:**
- Create: `scripts/incident/provenance.py`

**Implementation:**

Pure functions (FCIS pattern) for manifest parsing and sha256 computation:

- `parse_manifest(manifest_bytes: bytes) -> dict` — Parse manifest.json from bytes, validate required fields (hostname, timezone, requested_window, files array). Raise `ValueError` with clear message if required fields missing.
- `compute_sha256(file_path: Path) -> str` — Compute sha256 hex digest of a file using `hashlib.file_digest()` (Python 3.11+).
- `format_to_table(filename: str) -> str` — Map filename to source format string: `journal.json` → `journal`, `structlog.jsonl` → `jsonl`, `haproxy.log` → `haproxy`, `postgresql.log` → `pglog`. Raise `ValueError` for unknown filenames.

**Commit:**
```bash
git add scripts/incident/provenance.py
git commit -m "feat: add manifest parsing and provenance helpers"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Create scripts/incident/ingest.py and tests

**Verifies:** incident-analysis-tools.AC2.1, incident-analysis-tools.AC2.5, incident-analysis-tools.AC2.6

**Files:**
- Create: `scripts/incident/ingest.py`
- Create: `tests/unit/incident/__init__.py`
- Create: `tests/unit/incident/test_ingest.py`

**Implementation:**

`scripts/incident/ingest.py` — `run_ingest(tarball: Path, db_path: Path) -> None`:
1. Extract tarball to temp directory
2. Read and parse `manifest.json` — if missing, print error to stderr and `raise SystemExit(1)` (AC2.6)
3. Open/create SQLite database, call `create_schema(conn)`
4. For each file in manifest:
   a. Check if sha256 already in `sources` table — if so, skip (AC2.5 dedup)
   b. Insert row into `sources` with metadata from manifest
   c. Dispatch to appropriate parser (stub for now — parsers added in Phase 3-4)
5. Print summary: N files ingested, M skipped (dedup)

Parsers are called via a dispatch dict mapping format strings to parser functions. Phase 2 registers no parsers — the dispatch dict is empty, so source rows are inserted but no events are parsed yet.

**Testing:**

Tests must verify:
- **AC2.1:** After ingest, `sources` table has one row per file in manifest
- **AC2.5:** Re-ingesting same tarball produces zero new rows
- **AC2.6:** Tarball without `manifest.json` prints error and exits non-zero

Test fixtures: Create a minimal tarball in `tmp_path` containing a `manifest.json` and dummy log files. Use `tarfile` stdlib module to construct the fixture programmatically.

**Verification:**
```bash
uv run grimoire test run tests/unit/incident/test_ingest.py
```

**Commit:**
```bash
git add scripts/incident/ingest.py tests/unit/incident/__init__.py tests/unit/incident/test_ingest.py
git commit -m "feat: add tarball ingest with sha256 deduplication

Implements source registration, manifest validation, and dedup.
Tests verify AC2.1, AC2.5, AC2.6."
```
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->
