# Incident Analysis Tools

**GitHub Issue:** None

## Summary

PromptGrimoire's production server emits four log streams relevant to incident analysis: systemd journal, application structlog JSONL, HAProxy access log, and PostgreSQL log. A fifth source — Beszel system metrics on a separate monitoring server — may optionally be correlated. During the 2026-03-16 afternoon incident, these were analysed manually using ad-hoc `jq`/`grep`/`awk` pipelines — a process that introduced methodology errors including incorrect timezone filtering, inflated event counts from mis-scoped time windows, and a missed finding (PostgreSQL errors) due to a UTC offset mistake. This tooling replaces that ad-hoc workflow with a reproducible two-stage pipeline.

Stage 1 is a bash script (`collect-telemetry.sh`) that runs on the production server, bounds the journal export to a requested time window, copies all log files, hashes each one, and bundles everything with provenance metadata into a single tarball. Stage 2 is a local Python CLI (`incident_db.py`) that ingests the tarball into a SQLite database — normalising all timestamps to UTC regardless of their source format — and exposes three commands: `sources` (inventory with provenance), `timeline` (cross-source event view ordered by UTC timestamp), and `breakdown` (deterministic error counts by category). The parsers are pure functions isolated from I/O, following the project's functional core / imperative shell pattern. SQLite is used purely as a local query engine; it is not connected to the application database.

## Definition of Done

Provide reusable tooling for post-incident analysis of PromptGrimoire production logs. A bash script on the production server collects time-windowed telemetry from four data sources (systemd journal, structlog JSONL, HAProxy access log, PostgreSQL log), packages them with provenance metadata, and produces a gzipped tarball. A local Python tool ingests the tarball into a SQLite database with source-typed tables, correct UTC normalisation per source, and sha256-based file-level deduplication. CLI commands provide cross-source timeline queries, error breakdowns, and source inventory — replacing the ad-hoc jq/grep/awk pipelines that produced methodology errors during the 2026-03-16 afternoon analysis.

**Constraint:** The collection script requires root SSH access to the production server. In this deployment, the analyst and sysadmin roles collapse into the same person. If this changes, collection becomes a two-person workflow (sysadmin runs script, analyst receives tarball).

**Success criteria:** Given the 2026-03-16 afternoon logs, the tooling can: (1) inventory all sources with provenance metadata, (2) display the 16:06 upload stall as a cross-source UTC timeline showing HAProxy 504s, JSONL INVALIDATE spikes, and PG FATAL connection drops in one query, (3) produce deterministic error counts that match between re-runs.

**Out of scope:** Real-time monitoring, alerting, automated report generation, causal analysis. Beszel metric collection is optional (Phase 6) — the core pipeline works without it.

## Acceptance Criteria

### incident-analysis-tools.AC1: Collection script produces valid tarball
- **incident-analysis-tools.AC1.1 Success:** Running `collect-telemetry.sh --start "2026-03-16 14:50" --end "2026-03-16 17:20"` produces a `.tar.gz` containing journal JSON, JSONL, HAProxy log, PG log, and `manifest.json`
- **incident-analysis-tools.AC1.2 Success:** `manifest.json` contains sha256, size, mtime for each collected file, plus server hostname, timezone, and requested window in both AEDT and UTC
- **incident-analysis-tools.AC1.3 Success:** sha256 values in manifest match `sha256sum` of the corresponding extracted files
- **incident-analysis-tools.AC1.4 Failure:** Missing `--start` or `--end` argument prints usage and exits non-zero
- **incident-analysis-tools.AC1.5 Edge:** Journal export for a window with zero events produces an empty file but still appears in manifest

### incident-analysis-tools.AC2: Ingest loads all sources with correct timezones
- **incident-analysis-tools.AC2.1 Success:** `ingest` populates `sources` table with one row per file, matching manifest metadata
- **incident-analysis-tools.AC2.2 Success:** Journal `__REALTIME_TIMESTAMP` (µs epoch) converts to correct ISO 8601 UTC in `ts_utc`
- **incident-analysis-tools.AC2.3 Success:** HAProxy timestamps extracted from rsyslog prefix (not the inner HAProxy `[%tr]` field) and converted to UTC using `manifest.json` timezone
- **incident-analysis-tools.AC2.4 Success:** PG and JSONL timestamps stored as-is (already UTC)
- **incident-analysis-tools.AC2.5 Edge:** Re-ingesting the same tarball is a no-op (sha256 dedup) — zero new rows inserted
- **incident-analysis-tools.AC2.6 Failure:** Tarball without `manifest.json` produces a clear error message, not a traceback

### incident-analysis-tools.AC3: Parsers extract source-specific fields
- **incident-analysis-tools.AC3.1 Success:** HAProxy parser extracts status code, all 5 timing fields (TR/Tw/Tc/Tr/Ta), request method, request path, client IP from a real log line
- **incident-analysis-tools.AC3.2 Success:** PG parser groups multi-line entries (ERROR + DETAIL + STATEMENT) into single rows
- **incident-analysis-tools.AC3.3 Success:** JSONL parser extracts `user_id`, `workspace_id`, `exc_info` into dedicated columns, remaining fields into `extra_json`
- **incident-analysis-tools.AC3.4 Failure:** Unparseable HAProxy lines are counted and reported at end of ingest, not silently dropped
- **incident-analysis-tools.AC3.5 Edge:** JSONL lines with `exc_info: null` store NULL, not the string "null"

### incident-analysis-tools.AC4: CLI queries produce correct cross-source output
- **incident-analysis-tools.AC4.1 Success:** `timeline --start "2026-03-16 16:05" --end "2026-03-16 16:14"` shows HAProxy 504s, JSONL INVALIDATEs, and PG FATALs interleaved by `ts_utc`
- **incident-analysis-tools.AC4.2 Success:** `breakdown` produces deterministic counts matching between runs on the same database
- **incident-analysis-tools.AC4.3 Success:** `sources` displays provenance table with format, sha256 prefix, claimed timezone, first/last timestamp, and line count per source
- **incident-analysis-tools.AC4.4 Failure:** `timeline` with `--start` after `--end` produces a clear error, not empty results

## Glossary

- **structlog JSONL**: The application's structured log output — one JSON object per line, written by structlog. Each entry includes `timestamp` (ISO 8601 UTC), `level`, `event`, and optional fields like `user_id`, `workspace_id`, `exc_info`. Distinct from the systemd journal.
- **systemd journal**: Linux's centralised log store, written by systemd and services that log to stderr. Exported with `journalctl --output=json`, where each entry has a `__REALTIME_TIMESTAMP` (microseconds since Unix epoch, UTC) and a `MESSAGE` field.
- **HAProxy**: The reverse proxy sitting in front of the application. Logs one line per HTTP request in a custom format that includes client IP, timestamps (local time), status code, five timing fields (TR/Tw/Tc/Tr/Ta), and request method/path.
- **HAProxy timing fields (TR/Tw/Tc/Tr/Ta)**: Per-request timing breakdown: time to receive full request (TR), queue wait (Tw), backend connect (Tc), response from backend (Tr), and total active time (Ta). All in milliseconds.
- **504 Gateway Timeout**: HTTP status code returned by HAProxy when the backend does not respond within the configured timeout (60 seconds in this deployment).
- **503 Service Unavailable / `<NOSRV>`**: Returned by HAProxy when no healthy backend server is available — occurs during a service restart.
- **PostgreSQL log (pglog)**: PostgreSQL's own log file, distinct from the application's logs. Contains database-level events: connection errors, constraint violations, FATAL disconnects. Multi-line entries (ERROR + DETAIL + STATEMENT) must be grouped before analysis.
- **Beszel**: An infrastructure monitoring tool (built on PocketBase) deployed to a separate monitoring server. Collects CPU, memory, load, disk, and network metrics at 1-minute intervals. Data queried via PocketBase REST API.
- **PocketBase**: Open-source backend-as-a-service that Beszel uses for storage and its REST API. Metric export requires querying PocketBase endpoints with time-window filters.
- **INVALIDATE event**: Application-level structured log event emitted when SQLAlchemy invalidates (destroys) a connection in the async connection pool, typically due to a `CancelledError`. High INVALIDATE rates indicate connection pool churn.
- **CancelledError**: Python asyncio exception raised when an async task is cancelled. When this occurs inside a database transaction, SQLAlchemy destroys the connection rather than returning it to the pool, producing an INVALIDATE event.
- **Connection pool / QueuePool**: SQLAlchemy's pool of reusable database connections. Configured with `pool_size=10` and `max_overflow=20` (ceiling: 30).
- **sha256 deduplication**: The ingest command hashes each source file and records the hash. On re-ingest, files with matching hashes are skipped — preventing duplicate rows.
- **provenance metadata**: Information about where data came from: server hostname, collection timestamp, file path, hash, size, modification time, timezone. Stored in `manifest.json` for reproducibility.
- **AEDT**: Australian Eastern Daylight Time (UTC+11), the local timezone of the production server. HAProxy logs in local time; all other sources use UTC.
- **functional core / imperative shell (FCIS)**: Architecture pattern used throughout the project. Pure functions handle parsing; orchestration code handles I/O. Parsers in this tool: `bytes → list[dict]`, no direct database access.
- **typer**: Python CLI framework. Used for `incident_db.py`'s subcommands, following the project's existing `grimoire` CLI pattern.
- **pgtoolkit**: Python library for PostgreSQL log file parsing. Used for multi-line entry grouping (ERROR + DETAIL + STATEMENT).
- **`timeline` view**: SQL `UNION ALL` view combining all event tables into a single time-ordered stream with a common `ts_utc` column.

## Architecture

Two-stage pipeline: collect on server, analyse locally.

**Stage 1 — Collection (`deploy/collect-telemetry.sh`):** Runs on grimoire.drbbs.org as root. Takes an AEDT time window. Exports systemd journal in JSON format (`journalctl --output=json`), copies JSONL/HAProxy/PG log files in full, computes sha256 hashes, writes a `manifest.json` with provenance metadata, and tars everything into `/tmp/telemetry-YYYYMMDD-HHMM.tar.gz`. The user scps the tarball to their local machine.

**Stage 2 — Ingest + Analysis (`scripts/incident_db.py`):** Local Python CLI (typer). `ingest` unpacks the tarball, reads the manifest, and loads all sources into a SQLite database with source-typed tables. Each source type has a dedicated parser (pure function: bytes → list[dict]) and a table with source-specific columns. A `timeline` view unions all event tables for cross-source queries. CLI commands (`sources`, `timeline`, `breakdown`) replace ad-hoc grep pipelines.

**Timezone contract:** Every table stores `ts_utc` as ISO 8601 TEXT. Conversion rules are fixed per source format:

| Source | Raw timezone | Conversion method |
|--------|-------------|-------------------|
| Journal JSON | `__REALTIME_TIMESTAMP` (µs since epoch, UTC) | Direct from epoch |
| Structlog JSONL | `.timestamp` ISO 8601 UTC | Parse directly |
| HAProxy | rsyslog-prefixed ISO 8601 local timestamp before HAProxy payload | Convert using rsyslog timestamp + `manifest.json` timezone field |
| PostgreSQL | UTC | Parse directly |
| Beszel | UTC (PocketBase API) | Parse directly |

**Data flow:**

```
grimoire.drbbs.org                    local machine
┌─────────────────┐                  ┌──────────────────────┐
│ collect-telemetry│──tarball──scp──→│ incident_db.py ingest│
│   .sh            │                  │         ↓             │
│ journalctl       │                  │    SQLite database    │
│ cp jsonl/haproxy │                  │         ↓             │
│ cp pglog         │                  │ incident_db.py        │
│ manifest.json    │                  │  sources / timeline / │
└─────────────────┘                  │  breakdown            │
                                     └──────────────────────┘
```

## Existing Patterns

Investigation found these relevant patterns in the codebase:

- **`deploy/restart.sh`** — Server-side bash script running as root. Uses `set -euo pipefail`, `step()` helper for progress, `socat` for HAProxy admin socket. The collection script follows the same conventions.
- **`scripts/extract_workspace.py`** — Standalone operator script with direct database access, outputs JSON. Establishes the pattern of scripts that run on the server and produce data for local analysis.
- **`src/promptgrimoire/cli/`** — Typer-based CLI with sub-apps. The incident analysis tool uses the same typer pattern but as a standalone script (not a `grimoire` subcommand), since it operates on local SQLite, not the application database.
- **Functional core / imperative shell** — Parsers are pure functions (bytes → dicts). The ingest orchestrator handles I/O (tarball extraction, SQLite writes). This matches the project's FCIS pattern used in `wargame/roster.py`, `wargame/turn_cycle.py`, and `export/roleplay_export.py`.

**New pattern:** SQLite as a local analysis database. No existing precedent in the project, but the choice is driven by the problem (cross-format log correlation needs a query engine, not more grep).

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Collection Script

**Goal:** Bash script on the server that packages time-windowed telemetry into a provenance-tracked tarball.

**Components:**
- `deploy/collect-telemetry.sh` — accepts `--start` and `--end` in AEDT, exports journal as JSON, copies JSONL/HAProxy/PG log files, computes sha256 per file, writes `manifest.json`, produces gzipped tarball
- `manifest.json` schema — file paths, sha256, size, mtime, server hostname, timezone (`timedatectl`), requested window (AEDT and UTC), collection timestamp

**Dependencies:** None (first phase)

**Done when:** Running the script on grimoire.drbbs.org with a known time window produces a tarball containing all expected files and a valid manifest with correct hashes. Manual verification: untar, check manifest sha256 values match `sha256sum` of extracted files.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Schema + Ingest Scaffolding

**Goal:** SQLite schema creation and tarball ingest orchestration (without parsers — just provenance and raw file tracking).

**Components:**
- `scripts/incident_db.py` — typer CLI entry point with `ingest` command
- `scripts/incident/__init__.py` — package init
- `scripts/incident/schema.py` — `CREATE TABLE` statements for `sources`, all five event/metric tables, indexes, `timeline` view
- `scripts/incident/ingest.py` — tarball extraction, manifest reading, source registration (sha256 dedup), parser dispatch loop
- `scripts/incident/provenance.py` — manifest parsing, sha256 computation, source metadata extraction
- Dev dependency: `pgtoolkit` added to `pyproject.toml` (PG log multi-line grouping). No dataframe library needed — SQLite handles aggregation, parsers return lists of dicts, `executemany` does insertion.

**Dependencies:** Phase 1 (tarball format must be defined)

**Done when:** `uv run scripts/incident_db.py ingest <tarball>` creates a SQLite database with populated `sources` table. Re-running with the same tarball is a no-op (sha256 dedup). Tests verify schema creation, manifest parsing, and deduplication.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Parsers — Journal + JSONL

**Goal:** Parse the two structlog-adjacent formats into their respective tables.

**Components:**
- `scripts/incident/parsers/journal.py` — parses `journalctl --output=json` lines, extracts `__REALTIME_TIMESTAMP`, `PRIORITY`, `MESSAGE`, `_PID`, stores full JSON as `raw_json`
- `scripts/incident/parsers/jsonl.py` — parses structlog JSONL lines, extracts `timestamp`, `level`, `event`, `user_id`, `workspace_id`, `request_path`, `exc_info`, remaining fields as `extra_json`
- Time-window filtering: both parsers accept UTC start/end bounds (from manifest, with 5-minute buffer) and discard out-of-window events
- Integration with `ingest.py` dispatch loop

**Dependencies:** Phase 2 (schema and ingest scaffolding)

**Done when:** Ingesting a tarball containing journal and JSONL files populates `journal_events` and `jsonl_events` tables. Fixture-based tests verify timestamp conversion, field extraction, and window filtering. Re-ingest produces identical row counts.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Parsers — HAProxy + PostgreSQL

**Goal:** Parse the two non-JSON formats.

**Components:**
- `scripts/incident/parsers/haproxy.py` — regex parser for rsyslog-prefixed HAProxy log lines. The actual log lines on grimoire have an rsyslog ISO 8601 timestamp prefix before the HAProxy payload (`%ci:%cp [%tr] %ft %b/%s %TR/%Tw/%Tc/%Tr/%Ta %ST %B %CC %CS %tsc %ac/%fc/%bc/%sc/%rc %sq/%bq %hr %hs %{+Q}r`). The parser extracts the timestamp from the rsyslog prefix (more reliable than the inner `[%tr]` field), then parses the HAProxy payload for client IP, status code, 5 timing fields, backend/server, request method/path, bytes. Converts local-time timestamps to UTC using manifest timezone.
- `scripts/incident/parsers/pglog.py` — uses `pgtoolkit.log` for multi-line entry grouping (ERROR + DETAIL + STATEMENT). Extracts timestamp, PID, level, error type, detail, statement. PG timestamps are already UTC. **Note:** pgtoolkit requires the `log_line_prefix` from the production PostgreSQL config. The implementation must verify this matches grimoire's actual `postgresql.conf` setting (likely `'%t [%p]: '`). If pgtoolkit cannot handle the format, fall back to a ~20-line regex state machine.
- Integration with `ingest.py` dispatch loop

**Dependencies:** Phase 3 (parser integration pattern established)

**Done when:** Ingesting a tarball with all four log types populates all four event tables. Fixture-based tests verify HAProxy regex against real log lines, PG multi-line grouping, and timezone conversion. HAProxy local→UTC conversion matches manual calculation.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: CLI Query Commands

**Goal:** Analysis commands that replace ad-hoc grep pipelines.

**Components:**
- `scripts/incident/queries.py` — query functions for `sources`, `timeline`, `breakdown` commands
- `sources` command: tabulates source provenance (format, sha256, timezone, first/last ts, line count)
- `timeline` command: queries the `timeline` view with AEDT start/end (converted to UTC), optional level filter, ordered by `ts_utc`. Output as Rich table.
- `breakdown` command: groups events by source type + event/status, sorted by count descending. Equivalent to `jq | sort | uniq -c`.
- All commands accept `--db` (default `incident.db`), `--json` and `--csv` output format flags

**Dependencies:** Phase 4 (all parsers complete, data in database)

**Done when:** Running `sources`, `timeline`, and `breakdown` against the 2026-03-16 afternoon database produces correct, deterministic output. The 16:06 upload stall is visible in `timeline --start "2026-03-16 16:05" --end "2026-03-16 16:14"` showing HAProxy 504s, JSONL INVALIDATEs, and PG FATALs interleaved by timestamp.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Beszel Metrics (Optional)

**Goal:** Fetch Beszel system metrics via PocketBase REST API and ingest into `beszel_metrics` table.

**Components:**
- `scripts/incident/parsers/beszel.py` — HTTP client that queries PocketBase API with time-window filter, extracts compact JSON keys (`cpu`, `mu`, `mp`, `ns`, `nr`, etc.) into normalised columns
- `beszel` CLI command on `incident_db.py` — accepts `--start`, `--end` (AEDT), `--hub` URL (default `http://localhost:8090`), `--db`
- Requires SSH tunnel to brian.fedarch.org for API access

**Dependencies:** Phase 2 (schema includes `beszel_metrics` table)

**Done when:** With an SSH tunnel active, `beszel` command fetches metrics for the specified window and populates the `beszel_metrics` table. If the API is unreachable or returns errors, the command fails with a clear message (not a traceback). Metrics appear alongside events when querying by timestamp.
<!-- END_PHASE_6 -->

## Additional Considerations

**Journal size:** The 2026-03-16 afternoon journal was 502K lines (~50MB). `journalctl --output=json` is more verbose than text format. The collection script uses `journalctl`'s native `-S`/`-U` time filtering to bound the export. Even so, large incidents may produce tarballs of 100MB+. SQLite handles this fine; ingest uses `executemany` with batched inserts.

**HAProxy log format stability:** The regex parser is coupled to the log format string in `/etc/haproxy/haproxy.cfg`. If the format changes, the parser breaks. The manifest should record the HAProxy version, and the parser should fail loudly on unparseable lines (log the line, count failures, report at end) rather than silently dropping data.

**PG log rotation and event overlap:** PostgreSQL may rotate logs mid-incident. The collection script copies the current log file. If the incident spans a rotation, the analyst must collect both files and ingest separately. **sha256 deduplication is file-level, not event-level** — it prevents re-ingesting the same file, but does NOT prevent duplicate events across two rotated files with overlapping coverage. This is the analyst's responsibility: only ingest non-overlapping source files for the same format. The `sources` command's first/last timestamp display helps verify non-overlap. A future enhancement could add event-level dedup (e.g., composite key of timestamp + PID + message hash), but this is not in scope for the initial implementation.

**Implementation scoping:** This design has 6 phases. All fit within the 8-phase limit for a single implementation plan.
