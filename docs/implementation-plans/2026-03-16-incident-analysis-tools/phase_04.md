# Incident Analysis Tools Implementation Plan — Phase 4

**Goal:** Parse HAProxy access logs and PostgreSQL logs (both text and JSON formats) into their respective SQLite tables.

**Architecture:** Pure function parsers (FCIS pattern). HAProxy: regex for rsyslog-prefixed lines with local→UTC timestamp conversion. PostgreSQL: two parsers — a regex state machine for legacy text format (`%t [%p]: `) and a trivial JSON parser for jsonlog format (PostgreSQL 15+). The collection script detects format by file extension (`.json` vs `.log`).

**Tech Stack:** Python 3.14, stdlib re/json/zoneinfo, datetime

**Scope:** Phase 4 of 6 from original design

**Codebase verified:** 2026-03-16

---

## Acceptance Criteria Coverage

This phase implements and tests:

### incident-analysis-tools.AC2: Ingest loads all sources with correct timezones
- **incident-analysis-tools.AC2.3 Success:** HAProxy timestamps extracted from rsyslog prefix (not the inner HAProxy `[%tr]` field) and converted to UTC using `manifest.json` timezone

### incident-analysis-tools.AC3: Parsers extract source-specific fields
- **incident-analysis-tools.AC3.1 Success:** HAProxy parser extracts status code, all 5 timing fields (TR/Tw/Tc/Tr/Ta), request method, request path, client IP from a real log line
- **incident-analysis-tools.AC3.2 Success:** PG parser groups multi-line entries (ERROR + DETAIL + STATEMENT) into single rows
- **incident-analysis-tools.AC3.4 Failure:** Unparseable HAProxy lines are counted and reported at end of ingest, not silently dropped

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create HAProxy parser

**Verifies:** None (functionality tested in Task 2)

**Files:**
- Create: `scripts/incident/parsers/haproxy.py`

**Implementation:**

```python
def parse_haproxy(data: bytes, window_start_utc: str, window_end_utc: str, timezone: str) -> tuple[list[dict], int]:
```

Returns `(events, unparseable_count)` — AC3.4 requires reporting unparseable lines.

The `timezone` parameter comes from `manifest.json` (e.g., `"Australia/Sydney"`).

Logic:
1. Decode bytes as UTF-8, split on newlines, skip empty lines
2. For each line, apply regex to extract rsyslog ISO 8601 prefix and HAProxy payload
3. **Rsyslog prefix regex:** The first space-delimited token is the ISO 8601 timestamp with timezone offset (e.g., `2026-03-16T16:06:30+11:00`). Parse with `datetime.fromisoformat()` and convert to UTC.
4. **HAProxy payload regex** — match the format string `%ci:%cp [%tr] %ft %b/%s %TR/%Tw/%Tc/%Tr/%Ta %ST %B %CC %CS %tsc %ac/%fc/%bc/%sc/%rc %sq/%bq %hr %hs %{+Q}r`:
   - Client IP:port before `[`
   - Skip `[%tr]` inner timestamp (use rsyslog prefix instead)
   - Backend/server after `]`
   - 5 timing fields as `/`-separated integers: TR, Tw, Tc, Tr, Ta
   - Status code (integer)
   - Bytes read (integer)
   - Skip cookie/cache/termination/connection/queue fields
   - Request line in quotes at end: `"METHOD /path HTTP/version"` — extract method and path
5. Apply time-window filter on UTC timestamp (same shared helper as journal/JSONL)
6. Lines that don't match the regex: increment `unparseable_count`, continue
7. Return list of dicts with keys: `ts_utc`, `client_ip`, `status_code`, `tr_ms`, `tw_ms`, `tc_ms`, `tr_resp_ms`, `ta_ms`, `backend`, `server`, `method`, `path`, `bytes_read`

**Commit:**
```bash
git add scripts/incident/parsers/haproxy.py
git commit -m "feat: add HAProxy log parser with rsyslog timestamp extraction"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: HAProxy parser tests

**Verifies:** incident-analysis-tools.AC2.3, incident-analysis-tools.AC3.1, incident-analysis-tools.AC3.4

**Files:**
- Create: `tests/unit/incident/test_haproxy_parser.py`

**Testing:**

Tests must verify:
- **AC2.3:** rsyslog prefix `2026-03-16T16:06:30+11:00` converts to UTC `2026-03-16T05:06:30+00:00` (AEDT = UTC+11)
- **AC3.1:** From a real log line, extract: status code (e.g., 504), all 5 timing fields, request method (GET), request path (`/annotation/ws-xyz`), client IP
- **AC3.4:** Feed 5 lines where 2 are garbage — function returns 3 events and `unparseable_count=2`
- Time-window filtering excludes events outside UTC bounds
- Different timezone offsets produce correct UTC (e.g., AEST +10:00 vs AEDT +11:00)

Use realistic fixture data matching the production HAProxy format:
```
2026-03-16T16:06:45+11:00 grimoire haproxy[2345]: 192.0.2.100:45678 [16/Mar/2026:16:06:45.123 +1100] http-in backend/srv01 10/2/5/150/167 504 0 - - ---- 1/1/1/1/0 0/0 {|} {|} "GET /annotation/ws-xyz HTTP/1.1"
```

**Verification:**
```bash
uv run grimoire test run tests/unit/incident/test_haproxy_parser.py
```

**Commit:**
```bash
git add tests/unit/incident/test_haproxy_parser.py
git commit -m "test: add HAProxy parser tests (AC2.3, AC3.1, AC3.4)"
```
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-5) -->
<!-- START_TASK_3 -->
### Task 3: Create PostgreSQL parsers (text + JSON)

**Verifies:** None (functionality tested in Task 4)

**Files:**
- Create: `scripts/incident/parsers/pglog.py`

**Implementation:**

Two parser functions in one module:

**1. Text format parser (legacy, for pre-jsonlog logs):**

```python
def parse_pglog_text(data: bytes, window_start_utc: str, window_end_utc: str) -> list[dict]:
```

Regex state machine (~20 lines) for `log_line_prefix = '%t [%p]: '`:
1. Decode bytes, split on newlines
2. Regex for prefixed lines: `^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \w+ \[(\d+)\]: (\w+):\s+(.*)$`
3. Group entries by PID + timestamp proximity: when a new prefixed line has the same PID and timestamp as the current buffer, and its severity is DETAIL/STATEMENT/HINT/CONTEXT, merge it into the current entry
4. When a new prefixed line has a different PID or timestamp, flush the buffer as a complete entry
5. PG timestamps are already UTC — store directly as `ts_utc`
6. Apply time-window filter
7. Return list of dicts: `ts_utc`, `pid`, `level`, `error_type` (first line message), `detail`, `statement`, `message` (full concatenated text)

**2. JSON format parser (for PostgreSQL 15+ jsonlog):**

```python
def parse_pglog_json(data: bytes, window_start_utc: str, window_end_utc: str) -> list[dict]:
```

Trivial — same pattern as JSONL parser:
1. Decode bytes, split on newlines, parse each as JSON
2. Extract fields: `timestamp` → `ts_utc`, `pid`, `error_severity` → `level`, `message` → `error_type`, `detail`, `statement`, `message`
3. PG jsonlog timestamps are UTC — convert `"2026-03-16 04:32:52.000 GMT"` to ISO 8601
4. Apply time-window filter
5. Return list of dicts (same schema as text parser)

**Commit:**
```bash
git add scripts/incident/parsers/pglog.py
git commit -m "feat: add PostgreSQL log parsers (text + jsonlog formats)"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: PostgreSQL parser tests

**Verifies:** incident-analysis-tools.AC3.2

**Files:**
- Create: `tests/unit/incident/test_pglog_parser.py`

**Testing:**

Tests must verify for **text format parser**:
- **AC3.2:** Input with ERROR + DETAIL + STATEMENT (3 separate prefixed lines, same PID + timestamp) produces a single event dict with `level="ERROR"`, `detail` containing the DETAIL text, `statement` containing the STATEMENT text
- Single-line FATAL entry produces one event with no detail/statement
- Two unrelated entries (different PIDs) produce two separate events
- Time-window filtering works correctly
- Timestamps stored as-is (already UTC)

Tests must verify for **JSON format parser**:
- JSON entry with `error_severity`, `message`, `detail`, `statement` fields extracts correctly
- Timestamp `"2026-03-16 04:32:52.000 GMT"` converts to proper ISO 8601 UTC
- Entries without `detail`/`statement` fields store NULL for those columns
- Time-window filtering works correctly

Use realistic fixture data from the postmortem:
```
2026-03-16 04:32:52 UTC [1234]: ERROR:  duplicate key value violates unique constraint "uq_tag_workspace_name"
2026-03-16 04:32:52 UTC [1234]: DETAIL:  Key (workspace_id, name)=(dbf5feaa-..., Important Info) already exists.
2026-03-16 04:32:52 UTC [1234]: STATEMENT:  INSERT INTO tag (id, workspace_id, name, ...) VALUES ($1, $2, $3, ...)
2026-03-16 04:50:16 UTC [5678]: FATAL:  connection to client lost
```

**Verification:**
```bash
uv run grimoire test run tests/unit/incident/test_pglog_parser.py
```

**Commit:**
```bash
git add tests/unit/incident/test_pglog_parser.py
git commit -m "test: add PostgreSQL parser tests (AC3.2, text + JSON formats)"
```
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
### Task 5: Wire HAProxy + PG parsers into ingest dispatch and update collection script

**Verifies:** incident-analysis-tools.AC3.4 (end-to-end: unparseable count reported)

**Files:**
- Modify: `scripts/incident/ingest.py` — register haproxy and pglog parsers in dispatch dict
- Modify: `scripts/incident/provenance.py` — update `format_to_table()` to handle `postgresql.json` → `pglog` mapping
- Modify: `deploy/collect-telemetry.sh` — update PG log collection to detect `.json` vs `.log` format, copy both if present

**Implementation:**

Update ingest dispatch to handle HAProxy's different return signature (events + unparseable_count):
```python
PARSERS = {
    "journal": parse_journal,
    "jsonl": parse_jsonl,
    "haproxy": parse_haproxy,   # returns (events, unparseable_count)
    "pglog": parse_pglog_auto,  # auto-detects text vs JSON format
}
```

Add `parse_pglog_auto(data, ...)` that sniffs the first non-empty line: if it starts with `{`, use `parse_pglog_json`; otherwise use `parse_pglog_text`.

Update collection script PG section to:
1. Look for both `.json` and `.log` files in PG log directory
2. Copy the most recent file of either type
3. Filename in tarball preserves the extension (`postgresql.log` or `postgresql.json`)

Update `format_to_table()` to map both `postgresql.log` → `pglog` and `postgresql.json` → `pglog`.

For HAProxy, after ingest print the unparseable count: `"  → {N} events parsed ({M} unparseable lines skipped)"`.

**Verification:**

1. Verify bash script syntax:
```bash
bash -n deploy/collect-telemetry.sh
```
Expected: No output (clean parse)

2. Run Python tests:
```bash
uv run grimoire test run tests/unit/incident/
```

3. Manual verification of PG format detection (if production tarball available):
```bash
# Extract tarball, check PG file extension
tar -tzf telemetry-*.tar.gz | grep postgresql
# Expected: ./postgresql.json (if collected after jsonlog switch) or ./postgresql.log (before)
```

**Commit:**
```bash
git add scripts/incident/ingest.py scripts/incident/provenance.py deploy/collect-telemetry.sh
git commit -m "feat: wire HAProxy + PG parsers into ingest dispatch

Supports both text and JSON PostgreSQL log formats.
Reports unparseable HAProxy line count (AC3.4)."
```
<!-- END_TASK_5 -->
