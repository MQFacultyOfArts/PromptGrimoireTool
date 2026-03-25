# Incident Analysis Library

Freshness: 2026-03-24

## Purpose

Standalone post-incident telemetry analysis tooling. Ingests production log tarballs into a local SQLite database for cross-source timeline correlation and querying. Completely independent of the main PromptGrimoire application -- no imports from `src/promptgrimoire/`.

## Contracts

### Exposes
- `schema.create_schema(conn)` -- creates all tables, indexes, views; runs lightweight migrations
- `ingest.run_ingest(tarball, db_path)` -- extracts tarball, parses manifest, dispatches parsers, inserts events
- `queries.query_sources(conn)`, `query_timeline(conn, start, end, level)`, `query_breakdown(conn)` -- pure query functions
- `queries.render_table()`, `render_json()`, `render_csv()` -- output renderers
- `provenance.parse_manifest(bytes)` -- validates manifest.json structure
- `provenance.format_to_table(filename)` -- maps filenames to format strings
- `parsers.normalise_utc(ts)` -- canonical UTC timestamp format: `YYYY-MM-DDTHH:MM:SS.ffffffZ`
- `parsers.in_window(ts_utc, start, end)` -- window filtering
- `analysis.extract_epochs(conn)` -- detect epoch boundaries from JSONL commit hash transitions
- `analysis.enrich_epochs_journal(conn, epochs)` -- enrich epochs with journal Consumed message data (memory peak, CPU consumed)
- `analysis.enrich_epochs_github(conn, epochs)` -- enrich epochs with GitHub PR metadata via commit hash prefix matching
- `analysis.normalise_event(event_str)` -- collapse runtime-varying tokens (UUIDs, hex addresses, task names) to stable class keys
- `analysis.compute_error_landscape(conn, epochs)` -- per-epoch appeared/resolved error class sets
- `analysis.detect_pool_config(conn, start_utc, end_utc)` -- extract pool_size and max_overflow from INVALIDATE events
- `analysis.enrich_restart_gaps(epochs)` -- compute downtime duration between consecutive epochs
- `analysis.query_epoch_js_timeouts(conn, start, end, duration)` -- JS timeout events by call site, extracted from exception tracebacks
- `analysis.query_epoch_errors(conn, start, end, duration)` -- JSONL errors by level/event, normalised to per-hour
- `analysis.query_epoch_haproxy(conn, start, end, duration)` -- HAProxy status codes and percentiles
- `analysis.query_epoch_resources(conn, start, end)` -- Beszel mean/max CPU, memory, load
- `analysis.query_epoch_pg(conn, start, end)` -- PG errors by level/type
- `analysis.query_epoch_journal_anomalies(conn, start, end)` -- journal events priority <= 3
- `analysis.query_epoch_users(conn, start, end)` -- per-epoch user activity metrics
- `analysis.query_summative_users(conn)` -- full-window union user metrics
- `analysis.compute_trends(epochs)` -- cross-epoch trend deltas with anomaly detection
- `analysis.render_review_report(...)` -- markdown report assembly
- `analysis.load_static_counts(path)` -- JSON file parser for static DB counts
- `parsers.github.resolve_github_token(token_override)` -- GitHub token resolution (override -> env -> gh CLI)
- `parsers.github.fetch_github_prs(repo, start, end, token)` -- fetch merged PRs via GitHub REST API

### Guarantees
- All `ts_utc` values use canonical microsecond-precision UTC format (`normalise_utc`)
- SHA256 dedup on `sources` table -- re-ingesting the same tarball is safe
- Query bounds are padded to microsecond precision for correct SQLite string comparison
- Parsers skip unparseable lines with counts rather than failing
- `github_events` table stores merged PR metadata (pr_number, title, author, commit_oid, url) with `ts_utc` index
- Epoch boundaries are derived from JSONL commit hash transitions; crash-bounce detection uses a 300-second threshold
- Trend computation detects anomalies via cross-epoch delta analysis

### Expects
- Tarballs contain `manifest.json` with `hostname`, `timezone`, `requested_window`, `files`
- `collect-telemetry.sh` (in `deploy/`) produces compliant tarballs
- SQLite3 stdlib module available (no external DB driver)

## Dependencies

### Uses
- `pgtoolkit.log` -- PostgreSQL log multi-line grouping (pglog parser)
- `typer` -- CLI framework (via `scripts/incident_db.py`)
- `rich` -- table rendering in query output
- `httpx` -- Beszel API fetching, GitHub REST API fetching

### Used By
- `scripts/incident_db.py` -- Typer CLI entry point
- `deploy/collect-telemetry.sh` -- produces tarballs this library ingests

## Invariants

1. **Timestamp canonicalisation**: Every parser must produce `ts_utc` via `normalise_utc()` -- never raw format strings
2. **SHA256 dedup**: `sources.sha256` is UNIQUE; ingest checks before INSERT
3. **One-response principle**: Parsers return `list[dict]`; the ingest orchestrator handles DB insertion
4. **Format isolation**: Each parser handles exactly one log format; `_PARSERS` dispatch table in `ingest.py` maps format strings to `(parser_fn, table_name, columns)`
5. **Epoch analysis is read-only**: `analysis.py` functions only query the database; they never modify it. GitHub PR data is ingested separately via the `github` CLI subcommand

## Key Decisions

- **SQLite not PostgreSQL**: Incident analysis is a local developer tool, not a server feature. SQLite requires no setup and the database is disposable.
- **Functional core / imperative shell**: Parsers are pure functions `(bytes, window_start, window_end) -> list[dict]`. DB orchestration lives in `ingest.py`.
- **pgtoolkit for PG logs**: Multi-line PG log grouping (ERROR + DETAIL + STATEMENT) is error-prone to implement. pgtoolkit handles format edge cases.
- **Timeline UNION ALL view**: Cross-source correlation via a single SQL view that normalises all event types to `(source_id, ts_utc, source, level_or_status, message, extra)`. Includes `github_events` leg (`'pr'` level, `#N title` message format).
- **Epoch analysis pipeline**: `review` CLI subcommand orchestrates: extract epochs -> enrich with journal/GitHub data -> per-epoch queries (errors, HAProxy, resources, PG, journal anomalies, users) -> summative users -> trends -> markdown report.
