# Incident Analysis Tools — Test Requirements

Traceability matrix mapping each acceptance criterion to automated tests or documented human verification.

## Conventions

- **Test lane:** All automated tests are unit tests in `tests/unit/incident/`, running in the unit lane (xdist).
- **Fixture strategy:** Synthetic tarballs and log snippets constructed programmatically in tests. Real production data used only in human UAT.
- **Phase 6 (Beszel):** Has no numbered ACs in the design. Operational verification items are listed separately at the end.

---

## AC1: Collection script produces valid tarball

The collection script (`deploy/collect-telemetry.sh`) is tested at two levels:
- **BATS unit tests** (`deploy/tests/test_collect_telemetry.bats`): Stub host commands, verify contract (UTC window, buffer semantics, provenance, canonical filenames)
- **Human UAT on production**: Verify against real log files, journalctl, and production paths

| AC | Text | Verification | Test file | What is verified |
|----|------|-------------|-----------|-----------------|
| AC1.1 | Running `collect-telemetry.sh` produces a `.tar.gz` containing journal JSON, JSONL, HAProxy log, PG log, and `manifest.json` | BATS + Human UAT | `deploy/tests/test_collect_telemetry.bats` | **BATS:** Stubbed collection produces tarball with expected files. **UAT:** Real production files at correct paths |
| AC1.2 | `manifest.json` contains sha256, size, mtime, source_path, method per file, plus hostname, timezone, requested window (local + UTC), and warnings | BATS + Human UAT | `deploy/tests/test_collect_telemetry.bats` | **BATS:** `manifest_query` verifies `requested_window.start_utc`/`end_utc` are exact requested (not buffered). **UAT:** Visual inspection of all fields |
| AC1.3 | sha256 values in manifest match `sha256sum` of the corresponding extracted files | Human UAT | N/A (Phase 1 Task 2) | Loop over files, compare `sha256sum` output to manifest values |
| AC1.4 | Missing `--start` or `--end` argument prints usage and exits non-zero | BATS | `deploy/tests/test_collect_telemetry.bats` | 4 tests: no args, --start only, --end only, unknown flag — all verify non-zero exit + "Usage:" |
| AC1.5 | Journal export for a window with zero events produces an empty file but still appears in manifest | Human UAT | N/A (Phase 1 Task 2) | Run with distant past window, confirm journal.json is 0 bytes and listed in manifest |

**Collection semantics (verified by BATS):**
- Manifest `requested_window` = exact requested interval (no buffer)
- JSONL/HAProxy filtering = requested interval ± 5 minutes (buffer for context)
- Journal = exact requested window (journalctl --since/--until)
- PostgreSQL = full copy of latest `.log` and/or `.json` file (canonical filenames)

**Remaining human-only justification:** AC1.3 (hash verification) and AC1.5 (empty journal) require the real production environment. BATS tests use stubbed `journalctl`/`timedatectl` — they verify the script's contract, not host command behaviour.

---

## AC2: Ingest loads all sources with correct timezones

| AC | Text | Verification | Test file | What is verified |
|----|------|-------------|-----------|-----------------|
| AC2.1 | `ingest` populates `sources` table with one row per file, matching manifest metadata | Automated | `tests/unit/incident/test_ingest.py` | Minimal tarball fixture with manifest + 4 dummy files → `sources` has 4 rows with correct metadata |
| AC2.2 | Journal `__REALTIME_TIMESTAMP` (µs epoch) converts to correct ISO 8601 UTC in `ts_utc` | Automated | `tests/unit/incident/test_journal_parser.py` | Known µs timestamp → correct ISO 8601 output |
| AC2.3 | HAProxy timestamps extracted from rsyslog prefix and converted to UTC using manifest timezone | Automated | `tests/unit/incident/test_haproxy_parser.py` | Rsyslog prefix `+11:00` → UTC conversion verified; DST offset test |
| AC2.4 | PG and JSONL timestamps stored as-is (already UTC) | Automated | `tests/unit/incident/test_jsonl_parser.py`, `test_pglog_parser.py` | Input timestamp string equals output `ts_utc` |
| AC2.5 | Re-ingesting the same tarball is a no-op (sha256 dedup) | Automated | `tests/unit/incident/test_ingest.py` | Ingest twice, assert row count unchanged |
| AC2.6 | Tarball without `manifest.json` produces a clear error message, not a traceback | Automated | `tests/unit/incident/test_ingest.py` | Missing manifest → `SystemExit(1)` with human-readable message |

---

## AC3: Parsers extract source-specific fields

| AC | Text | Verification | Test file | What is verified |
|----|------|-------------|-----------|-----------------|
| AC3.1 | HAProxy parser extracts status code, all 5 timing fields, request method, request path, client IP | Automated | `tests/unit/incident/test_haproxy_parser.py` | Realistic log line → all fields extracted with correct types and values |
| AC3.2 | PG parser groups multi-line entries (ERROR + DETAIL + STATEMENT) into single rows | Automated | `tests/unit/incident/test_pglog_parser.py` | 3 prefixed lines (same PID/ts) + 1 unrelated FATAL → 2 events; first has `detail`/`statement`, second has None |
| AC3.3 | JSONL parser extracts `user_id`, `workspace_id`, `request_path`, `exc_info` into dedicated columns, remaining into `extra_json` | Automated | `tests/unit/incident/test_jsonl_parser.py` | Extracted fields in top-level dict; `extra_json` has remainder without duplication |
| AC3.4 | Unparseable HAProxy lines counted and reported, not silently dropped | Automated | `tests/unit/incident/test_haproxy_parser.py` | 5 lines, 2 garbage → `(3 events, unparseable_count=2)` |
| AC3.5 | JSONL lines with `exc_info: null` store NULL, not the string "null" | Automated | `tests/unit/incident/test_jsonl_parser.py` | `"exc_info": null` → Python `None` |

---

## AC4: CLI queries produce correct cross-source output

| AC | Text | Verification | Test file | What is verified |
|----|------|-------------|-----------|-----------------|
| AC4.1 | `timeline` shows HAProxy 504s, JSONL INVALIDATEs, and PG FATALs interleaved by `ts_utc` | Automated + Human UAT | `tests/unit/incident/test_queries.py` + Phase 5 Task 3 | **Automated:** Pre-populated SQLite, verify 3 source types interleaved. **UAT:** Real 2026-03-16 data, visually confirm 16:06 stall |
| AC4.2 | `breakdown` produces deterministic counts matching between runs | Automated | `tests/unit/incident/test_queries.py` | Call twice, assert identical output |
| AC4.3 | `sources` displays provenance with format, sha256 prefix, timezone, first/last ts, line count | Automated | `tests/unit/incident/test_queries.py` | Pre-populated SQLite, verify all fields present with expected values |
| AC4.4 | `timeline` with `--start` after `--end` produces a clear error | Automated | `tests/unit/incident/test_queries.py` | CliRunner, assert non-zero exit + error message |

---

## Human UAT Summary

| UAT step | Phase | ACs covered | Justification |
|----------|-------|-------------|---------------|
| Production server collection (Phase 1 Task 2) | 1 | AC1.1, AC1.2, AC1.3, AC1.5 | Requires root access, journalctl, production log files. AC1.4 automated via BATS. |
| End-to-end with real incident data (Phase 5 Task 3) | 5 | AC4.1 (real-data) | Synthetic fixtures verify logic; real data verifies actionable analysis |
| Beszel live fetch (Phase 6 operational) | 6 | (no numbered ACs) | Requires SSH tunnel to monitoring server |

---

## Test File Summary

| Test file | Phase | ACs covered | Lane |
|-----------|-------|-------------|------|
| `deploy/tests/test_collect_telemetry.bats` | 1 | AC1.1 (partial), AC1.2 (partial), AC1.4 | bats |
| `tests/unit/incident/test_ingest.py` | 2 | AC2.1, AC2.5, AC2.6 | unit |
| `tests/unit/incident/test_journal_parser.py` | 3 | AC2.2 | unit |
| `tests/unit/incident/test_jsonl_parser.py` | 3 | AC2.4, AC3.3, AC3.5 | unit |
| `tests/unit/incident/test_ingest_with_parsers.py` | 3 | AC2.1 (end-to-end) | unit |
| `tests/unit/incident/test_haproxy_parser.py` | 4 | AC2.3, AC3.1, AC3.4 | unit |
| `tests/unit/incident/test_pglog_parser.py` | 4 | AC3.2, AC2.4 | unit |
| `tests/unit/incident/test_queries.py` | 5 | AC4.1-AC4.4 | unit |
| `tests/unit/incident/test_beszel.py` | 6 | (operational) | unit |
| `tests/unit/incident/test_bugs.py` | fix | timestamp format, buffer, PG filenames, JSONL crash, IPv6 | unit |
