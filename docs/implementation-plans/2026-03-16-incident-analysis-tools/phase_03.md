# Incident Analysis Tools Implementation Plan — Phase 3

**Goal:** Parse the two JSON-based log formats (systemd journal and structlog JSONL) into their respective SQLite tables.

**Architecture:** Pure function parsers (FCIS pattern): `bytes → list[dict]`. Each parser accepts UTC time-window bounds and discards out-of-window events. Parsers integrated into ingest dispatch loop from Phase 2.

**Tech Stack:** Python 3.14, stdlib json, datetime

**Scope:** Phase 3 of 6 from original design

**Codebase verified:** 2026-03-16

---

## Acceptance Criteria Coverage

This phase implements and tests:

### incident-analysis-tools.AC2: Ingest loads all sources with correct timezones
- **incident-analysis-tools.AC2.2 Success:** Journal `__REALTIME_TIMESTAMP` (µs epoch) converts to correct ISO 8601 UTC in `ts_utc`
- **incident-analysis-tools.AC2.4 Success:** PG and JSONL timestamps stored as-is (already UTC)

### incident-analysis-tools.AC3: Parsers extract source-specific fields
- **incident-analysis-tools.AC3.3 Success:** JSONL parser extracts `user_id`, `workspace_id`, `request_path`, `exc_info` into dedicated columns, remaining fields into `extra_json`
- **incident-analysis-tools.AC3.5 Edge:** JSONL lines with `exc_info: null` store NULL, not the string "null"

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create scripts/incident/parsers/ package and journal parser

**Verifies:** None (functionality tested in Task 2)

**Files:**
- Create: `scripts/incident/parsers/__init__.py`
- Create: `scripts/incident/parsers/journal.py`

**Implementation:**

`scripts/incident/parsers/__init__.py` — package init with shared time-window filter helper:

```python
def in_window(ts_utc: str, window_start: str, window_end: str, buffer_minutes: int = 5) -> bool:
    """Check if a UTC timestamp falls within the window (with buffer on each side)."""
```

Parse ISO 8601 strings, subtract `buffer_minutes` from start, add to end, return whether `ts_utc` is in range. All parsers import this: `from scripts.incident.parsers import in_window`.

`scripts/incident/parsers/journal.py` — pure function parser:

```python
def parse_journal(data: bytes, window_start_utc: str, window_end_utc: str) -> list[dict]:
```

Logic:
1. Decode bytes as UTF-8, split on newlines, skip empty lines
2. Parse each line as JSON
3. Extract `__REALTIME_TIMESTAMP` (string of integer microseconds), convert to ISO 8601 UTC:
   - `int(ts_str) / 1_000_000` → `datetime.fromtimestamp(epoch, tz=timezone.utc)` → `.isoformat()`
4. Apply time-window filter: skip events outside `[window_start_utc - 5min, window_end_utc + 5min]`
5. Return list of dicts with keys: `ts_utc`, `priority` (int from `PRIORITY` string), `pid` (int from `_PID` string), `unit` (from `_SYSTEMD_UNIT`), `message` (from `MESSAGE`), `raw_json` (the full JSON line as string)

Priority mapping not needed in parser — store as integer. Syslog priorities: 0=EMERG through 7=DEBUG.

**Commit:**
```bash
git add scripts/incident/parsers/__init__.py scripts/incident/parsers/journal.py
git commit -m "feat: add systemd journal JSON parser"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Journal parser tests

**Verifies:** incident-analysis-tools.AC2.2

**Files:**
- Create: `tests/unit/incident/test_journal_parser.py`

**Testing:**

Tests must verify:
- **AC2.2:** `__REALTIME_TIMESTAMP` `"1710536535123456"` converts to `"2024-03-16T00:42:15.123456+00:00"` (or equivalent ISO 8601 UTC)
- Correct field extraction (priority as int, pid as int, message, unit)
- `raw_json` contains the full original JSON line
- Time-window filtering excludes events outside the window
- Time-window 5-minute buffer includes events just outside the strict window
- Empty input returns empty list
- Lines with missing `__REALTIME_TIMESTAMP` are skipped (logged, not fatal)

Use inline fixture data — construct journal JSON lines programmatically in the test.

**Verification:**
```bash
uv run grimoire test run tests/unit/incident/test_journal_parser.py
```

**Commit:**
```bash
git add tests/unit/incident/test_journal_parser.py
git commit -m "test: add journal parser tests (AC2.2)"
```
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Create JSONL parser

**Verifies:** None (functionality tested in Task 4)

**Files:**
- Create: `scripts/incident/parsers/jsonl.py`

**Implementation:**

```python
def parse_jsonl(data: bytes, window_start_utc: str, window_end_utc: str) -> list[dict]:
```

Logic:
1. Decode bytes as UTF-8, split on newlines, skip empty lines
2. Parse each line as JSON
3. Extract `timestamp` field — already ISO 8601 UTC, use directly as `ts_utc`
4. Apply time-window filter (same 5-minute buffer logic as journal parser — extract into shared helper)
5. Extract known fields into dedicated keys: `level`, `event`, `user_id`, `workspace_id`, `request_path`, `exc_info`
6. For `exc_info`: if value is `None` or JSON `null`, store as Python `None` (not string `"null"`) — AC3.5
7. Collect remaining fields (everything NOT in the known set: `timestamp`, `level`, `event`, `logger`, `pid`, `branch`, `commit`, `version`, `user_id`, `workspace_id`, `request_path`, `exc_info`) into `extra_json` as a JSON string

Known fields to extract to columns: `level`, `event`, `user_id`, `workspace_id`, `request_path`, `exc_info`
Known fields to discard (not stored in columns or extra_json — they're metadata, not analysis-relevant): none — put everything not in columns into `extra_json` for completeness.

Actually, keep it simple: extract the 6 column fields, put ALL remaining key-value pairs into `extra_json`. This means `logger`, `pid`, `branch`, `commit`, `version`, `host`, `port`, and any custom bindings all go into `extra_json`.

**Commit:**
```bash
git add scripts/incident/parsers/jsonl.py
git commit -m "feat: add structlog JSONL parser"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: JSONL parser tests

**Verifies:** incident-analysis-tools.AC2.4, incident-analysis-tools.AC3.3, incident-analysis-tools.AC3.5

**Files:**
- Create: `tests/unit/incident/test_jsonl_parser.py`

**Testing:**

Tests must verify:
- **AC2.4:** Timestamp stored as-is (ISO 8601 UTC string matches input)
- **AC3.3:** `user_id`, `workspace_id`, `exc_info` appear in dedicated dict keys, remaining fields in `extra_json`
- **AC3.5:** JSONL line with `"exc_info": null` produces Python `None` for `exc_info`, NOT the string `"null"`
- `extra_json` contains the non-extracted fields as a JSON string (parseable back to dict)
- `extra_json` does NOT contain the 6 extracted fields or `timestamp`
- Time-window filtering works correctly (same behavior as journal parser)
- Empty input returns empty list
- Malformed JSON lines are skipped with count

Use realistic fixture data matching the structlog format from `docs/logging.md`:
```python
{
    "timestamp": "2026-03-15T08:42:17.123456Z",
    "level": "error",
    "event": "database_connection_failed",
    "logger": "promptgrimoire.db",
    "pid": 12345,
    "branch": "main",
    "commit": "a1b2c3d",
    "version": "0.1.0+a1b2c3d",
    "user_id": "user-123",
    "workspace_id": "ws-456",
    "request_path": "/annotation/ws-456",
    "exc_info": "ValueError: connection refused\nTraceback..."
}
```

**Verification:**
```bash
uv run grimoire test run tests/unit/incident/test_jsonl_parser.py
```

**Commit:**
```bash
git add tests/unit/incident/test_jsonl_parser.py
git commit -m "test: add JSONL parser tests (AC2.4, AC3.3, AC3.5)"
```
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
### Task 5: Wire parsers into ingest dispatch and integration test

**Verifies:** incident-analysis-tools.AC2.1 (end-to-end: ingest with parsers populates event tables)

**Files:**
- Modify: `scripts/incident/ingest.py` — register journal and jsonl parsers in dispatch dict
- Create: `tests/unit/incident/test_ingest_with_parsers.py`

**Implementation:**

Update `ingest.py` to import and register:
```python
PARSERS = {
    "journal": parse_journal,
    "jsonl": parse_jsonl,
}
```

After inserting a source row, if the format has a registered parser:
1. Read the file bytes
2. Call the parser with UTC window bounds from manifest
3. Insert returned dicts into the appropriate table using `executemany`
4. Print count: "  → {N} events parsed"

**Testing:**

Create a minimal tarball fixture with `manifest.json`, a 3-line journal file, and a 3-line JSONL file. Ingest it. Verify:
- `sources` has 2+ rows
- `journal_events` has rows with correct `ts_utc`
- `jsonl_events` has rows with correct field extraction
- Re-ingest is still a no-op (dedup)

**Verification:**
```bash
uv run grimoire test run tests/unit/incident/test_ingest_with_parsers.py
```

**Commit:**
```bash
git add scripts/incident/ingest.py tests/unit/incident/test_ingest_with_parsers.py
git commit -m "feat: wire journal + JSONL parsers into ingest dispatch

Integration test verifies end-to-end ingest populates event tables."
```
<!-- END_TASK_5 -->
