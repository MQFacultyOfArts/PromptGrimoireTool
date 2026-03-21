# Epoch Analysis Implementation Plan — Phase 4: User Activity Metrics

**Goal:** Per-epoch and summative user/workspace activity metrics from JSONL events, plus static production DB counts from a JSON file.

**Architecture:** Two query functions in `scripts/incident/analysis.py` (`query_epoch_users`, `query_summative_users`) plus a JSON file parser for static counts. Summative metrics use UNION (not sum of per-epoch) to avoid double-counting users active across multiple epochs.

**Tech Stack:** SQLite aggregate functions (COUNT DISTINCT), Python json module

**Scope:** 6 phases from original design (phase 4 of 6)

**Codebase verified:** 2026-03-18

---

## Acceptance Criteria Coverage

This phase implements and tests:

### epoch-analysis.AC4: User activity metrics
- **epoch-analysis.AC4.1 Success:** Per-epoch unique logins, active users, active workspaces, workspace-interacting users
- **epoch-analysis.AC4.2 Success:** Summative totals across full window (union, not sum of per-epoch)
- **epoch-analysis.AC4.3 Success:** Static DB counts from `--counts-json` displayed as "N of M total" context

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: `query_epoch_users()` — per-epoch user activity

**Verifies:** epoch-analysis.AC4.1

**Files:**
- Modify: `scripts/incident/analysis.py` (add function)
- Test: `tests/unit/test_epoch_users.py` (unit)

**Implementation:**

Add to `scripts/incident/analysis.py`:

```python
def query_epoch_users(
    conn: sqlite3.Connection, start_utc: str, end_utc: str
) -> dict:
```

**SQL queries:**

Unique logins (events matching `Login successful%`):
```sql
SELECT COUNT(DISTINCT user_id) AS unique_logins
FROM jsonl_events
WHERE ts_utc >= ? AND ts_utc <= ?
  AND event LIKE 'Login successful%'
  AND user_id IS NOT NULL
```

Active users (any event with user_id):
```sql
SELECT COUNT(DISTINCT user_id) AS active_users
FROM jsonl_events
WHERE ts_utc >= ? AND ts_utc <= ?
  AND user_id IS NOT NULL
```

Active workspaces:
```sql
SELECT COUNT(DISTINCT workspace_id) AS active_workspaces
FROM jsonl_events
WHERE ts_utc >= ? AND ts_utc <= ?
  AND workspace_id IS NOT NULL
```

Users who interacted with workspaces:
```sql
SELECT COUNT(DISTINCT user_id) AS workspace_users
FROM jsonl_events
WHERE ts_utc >= ? AND ts_utc <= ?
  AND user_id IS NOT NULL
  AND workspace_id IS NOT NULL
```

**Known limitation — login event string dependency:** The `Login successful%` pattern is a hard-coded dependency on the structlog event string produced by the auth layer. If this string changes in future app versions, `unique_logins` will silently drop to zero. The login pattern string should be defined as a module-level constant (e.g., `LOGIN_EVENT_PATTERN = "Login successful%"`) with a docstring explaining the dependency, so it is easy to find and update.

**Return:** Dict with keys: `unique_logins`, `active_users`, `active_workspaces`, `workspace_users`

**Testing:**

Tests must verify:
- epoch-analysis.AC4.1: Given test JSONL events with known user_ids and workspace_ids, returns correct distinct counts
- Login events are filtered by `event LIKE 'Login successful%'`

**Verification:**

```bash
uv run pytest tests/unit/test_epoch_users.py -k "test_epoch_users" -v
```

**Commit:** `feat: add per-epoch user activity metrics`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: `query_summative_users()` — full-window union totals

**Verifies:** epoch-analysis.AC4.2

**Files:**
- Modify: `scripts/incident/analysis.py` (add function)
- Modify: `tests/unit/test_epoch_users.py` (add tests)

**Implementation:**

Add to `scripts/incident/analysis.py`:

```python
def query_summative_users(conn: sqlite3.Connection) -> dict:
```

This queries across the **entire** JSONL event set (no time bounds), providing union totals. The same four metrics as `query_epoch_users` but across all data.

**SQL:** Same four queries as Task 1, but without the `ts_utc` WHERE clause.

**Why not sum per-epoch:** A user active in epoch 1 and epoch 3 should be counted once in summative, not twice. COUNT(DISTINCT) across the full window handles this correctly.

**Return:** Same dict shape as `query_epoch_users`.

**Testing:**

Tests must verify:
- epoch-analysis.AC4.2: User active in two epochs counted once in summative total

**Verification:**

```bash
uv run pytest tests/unit/test_epoch_users.py -k "test_summative_users" -v
```

**Commit:** `feat: add summative user activity metrics (union totals)`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Static counts JSON parser

**Verifies:** epoch-analysis.AC4.3

**Files:**
- Modify: `scripts/incident/analysis.py` (add function)
- Modify: `tests/unit/test_epoch_users.py` (add tests)

**Implementation:**

Add to `scripts/incident/analysis.py`:

```python
def load_static_counts(counts_path: Path | None) -> dict | None:
```

**Logic:**
- If `counts_path` is None, return None
- Read JSON file, return as dict
- Expected format: `{"users": 1936, "workspaces": 1151, "courses": 11, ...}` (string keys, integer values)
- Raise `FileNotFoundError` if file doesn't exist (CLI catches this)
- Raise `json.JSONDecodeError` if invalid JSON (CLI catches this)

**Testing:**

Tests must verify:
- epoch-analysis.AC4.3: Valid JSON file parsed correctly
- None path returns None
- Invalid JSON raises appropriate error

**Verification:**

```bash
uv run pytest tests/unit/test_epoch_users.py -k "test_static_counts" -v
```

**Commit:** `feat: add static counts JSON parser for review context`

## UAT Steps

1. Run user activity queries against `incident.db`:
```bash
uv run python -c "
import sqlite3
from scripts.incident.schema import create_schema
from scripts.incident.analysis import extract_epochs, query_epoch_users, query_summative_users
conn = sqlite3.connect('incident.db')
create_schema(conn)
epochs = extract_epochs(conn)
e = [ep for ep in epochs if not ep['is_crash_bounce']][0]
users = query_epoch_users(conn, e['start_utc'], e['end_utc'])
print(f'Epoch {e[\"commit\"]}: logins={users[\"unique_logins\"]}, active={users[\"active_users\"]}, workspaces={users[\"active_workspaces\"]}')
summary = query_summative_users(conn)
print(f'Summative: logins={summary[\"unique_logins\"]}, active={summary[\"active_users\"]}')
"
```
2. Verify: Non-zero user counts, summative >= per-epoch counts

## Complexity Check

```bash
uv run complexipy scripts/incident/analysis.py
```
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
