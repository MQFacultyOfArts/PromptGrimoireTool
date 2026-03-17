# Incident Analysis Library

Freshness: 2026-03-17

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

### Guarantees
- All `ts_utc` values use canonical microsecond-precision UTC format (`normalise_utc`)
- SHA256 dedup on `sources` table -- re-ingesting the same tarball is safe
- Query bounds are padded to microsecond precision for correct SQLite string comparison
- Parsers skip unparseable lines with counts rather than failing

### Expects
- Tarballs contain `manifest.json` with `hostname`, `timezone`, `requested_window`, `files`
- `collect-telemetry.sh` (in `deploy/`) produces compliant tarballs
- SQLite3 stdlib module available (no external DB driver)

## Dependencies

### Uses
- `pgtoolkit.log` -- PostgreSQL log multi-line grouping (pglog parser)
- `typer` -- CLI framework (via `scripts/incident_db.py`)
- `rich` -- table rendering in query output
- `httpx` -- Beszel API fetching

### Used By
- `scripts/incident_db.py` -- Typer CLI entry point
- `deploy/collect-telemetry.sh` -- produces tarballs this library ingests

## Invariants

1. **Timestamp canonicalisation**: Every parser must produce `ts_utc` via `normalise_utc()` -- never raw format strings
2. **SHA256 dedup**: `sources.sha256` is UNIQUE; ingest checks before INSERT
3. **One-response principle**: Parsers return `list[dict]`; the ingest orchestrator handles DB insertion
4. **Format isolation**: Each parser handles exactly one log format; `_PARSERS` dispatch table in `ingest.py` maps format strings to `(parser_fn, table_name, columns)`

## Key Decisions

- **SQLite not PostgreSQL**: Incident analysis is a local developer tool, not a server feature. SQLite requires no setup and the database is disposable.
- **Functional core / imperative shell**: Parsers are pure functions `(bytes, window_start, window_end) -> list[dict]`. DB orchestration lives in `ingest.py`.
- **pgtoolkit for PG logs**: Multi-line PG log grouping (ERROR + DETAIL + STATEMENT) is error-prone to implement. pgtoolkit handles format edge cases.
- **Timeline UNION ALL view**: Cross-source correlation via a single SQL view that normalises all event types to `(source_id, ts_utc, source, level_or_status, message, extra)`.
