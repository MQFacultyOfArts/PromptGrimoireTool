# Epoch Analysis Implementation Plan — Phase 3: Per-Epoch Analysis Queries

**Goal:** Five SQL aggregate query functions, each windowed by epoch start/end UTC boundaries, providing error rates, HAProxy traffic profiles, Beszel resource stats, PG error summaries, and journal anomalies.

**Architecture:** Five pure functions in `scripts/incident/analysis.py`, each taking `(conn, start_utc, end_utc)` and returning `list[dict]` or `dict`. Follows the existing `queries.py` pattern. Rate normalisation computed in Python from epoch duration.

**Tech Stack:** SQLite aggregate functions, Python datetime arithmetic

**Row factory convention:** All query functions in `analysis.py` should set `conn.row_factory = sqlite3.Row` at their start (or the `review` CLI sets it once before calling any analysis function). This ensures consistent dict-like access. When building return values, convert Row objects to plain dicts via `dict(row)` so return types match annotations.

**Scope:** 6 phases from original design (phase 3 of 6)

**Codebase verified:** 2026-03-18

---

## Acceptance Criteria Coverage

This phase implements and tests:

### epoch-analysis.AC3: Per-epoch analysis queries
- **epoch-analysis.AC3.1 Success:** Error counts grouped by level and event type, normalised to errors/hour
- **epoch-analysis.AC3.2 Success:** HAProxy status code distribution with p50/p95/p99 response times
- **epoch-analysis.AC3.3 Success:** Beszel resource stats (mean/max CPU, memory, load) per epoch
- **epoch-analysis.AC3.4 Edge:** Epochs shorter than 5 minutes flagged as crash-bounces, not analysed for rates

---

<!-- START_TASK_1 -->
### Task 1: `query_epoch_errors()` — JSONL error profiling

**Verifies:** epoch-analysis.AC3.1, epoch-analysis.AC3.4

**Files:**
- Modify: `scripts/incident/analysis.py` (add function)
- Test: `tests/unit/test_epoch_queries.py` (unit)

**Implementation:**

Add to `scripts/incident/analysis.py`:

```python
def query_epoch_errors(
    conn: sqlite3.Connection, start_utc: str, end_utc: str, duration_seconds: float
) -> list[dict]:
```

**SQL query:**
```sql
SELECT level, event, COUNT(*) AS count
FROM jsonl_events
WHERE ts_utc >= ? AND ts_utc <= ?
  AND level IN ('error', 'critical', 'warning')
GROUP BY level, event
ORDER BY count DESC
```

**Post-processing:**
- For each row, compute `per_hour = count / (duration_seconds / 3600)` if `duration_seconds >= 300`
- If `duration_seconds < 300` (crash-bounce): set `per_hour` to `None` and add `is_crash_bounce: True`

**Return:** List of dicts with keys: `level`, `event`, `count`, `per_hour`, `is_crash_bounce`

**Testing:**

Tests must verify:
- epoch-analysis.AC3.1: Given test JSONL events with known error levels, returns correct counts and rates
- epoch-analysis.AC3.4: Short epoch returns `per_hour: None` and `is_crash_bounce: True`

**Verification:**

```bash
uv run pytest tests/unit/test_epoch_queries.py -k "test_epoch_errors" -v
```

**Commit:** `feat: add per-epoch error profiling query`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: `query_epoch_haproxy()` — HTTP traffic profiling

**Verifies:** epoch-analysis.AC3.2

**Files:**
- Modify: `scripts/incident/analysis.py` (add function)
- Modify: `tests/unit/test_epoch_queries.py` (add tests)

**Implementation:**

Add to `scripts/incident/analysis.py`:

```python
def query_epoch_haproxy(
    conn: sqlite3.Connection, start_utc: str, end_utc: str, duration_seconds: float
) -> dict:
```

**SQL queries:**

Status code distribution:
```sql
SELECT status_code, COUNT(*) AS count
FROM haproxy_events
WHERE ts_utc >= ? AND ts_utc <= ?
GROUP BY status_code
ORDER BY status_code
```

Total requests and 5xx count:
```sql
SELECT COUNT(*) AS total_requests,
       SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS count_5xx
FROM haproxy_events
WHERE ts_utc >= ? AND ts_utc <= ?
```

Response time percentiles (p50/p95/p99 via offset subquery pattern — SQLite lacks PERCENTILE):
```sql
SELECT ta_ms FROM haproxy_events
WHERE ts_utc >= ? AND ts_utc <= ? AND ta_ms IS NOT NULL
ORDER BY ta_ms
LIMIT 1 OFFSET (SELECT CAST(COUNT(*) * ? AS INTEGER) FROM haproxy_events
                 WHERE ts_utc >= ? AND ts_utc <= ? AND ta_ms IS NOT NULL)
```

Call this three times with percentile values 0.50, 0.95, 0.99.

**Return:** Dict with keys:
- `status_codes`: list of `{status_code, count}` dicts
- `total_requests`: int
- `count_5xx`: int
- `rate_5xx`: float (5xx per hour, or None if crash-bounce)
- `requests_per_minute`: float (or None if crash-bounce)
- `p50_ms`: int | None
- `p95_ms`: int | None
- `p99_ms`: int | None
- `sample_count`: int — number of requests with non-null `ta_ms` used for percentile calculation. The report renderer (Phase 6) should display this alongside percentiles so the operator can judge statistical significance (e.g., "p99=10000ms (n=1)" vs "p99=10000ms (n=50000)")

**Testing:**

Tests must verify:
- epoch-analysis.AC3.2: Given test HAProxy events, returns correct status distribution and percentiles

**Verification:**

```bash
uv run pytest tests/unit/test_epoch_queries.py -k "test_epoch_haproxy" -v
```

**Commit:** `feat: add per-epoch HAProxy traffic profiling`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: `query_epoch_resources()` — Beszel system metrics

**Verifies:** epoch-analysis.AC3.3

**Files:**
- Modify: `scripts/incident/analysis.py` (add function)
- Modify: `tests/unit/test_epoch_queries.py` (add tests)

**Implementation:**

Add to `scripts/incident/analysis.py`:

```python
def query_epoch_resources(
    conn: sqlite3.Connection, start_utc: str, end_utc: str
) -> dict:
```

**SQL query:**
```sql
SELECT
    AVG(cpu) AS mean_cpu,
    MAX(cpu) AS max_cpu,
    AVG(mem_percent) AS mean_mem,
    MAX(mem_percent) AS max_mem,
    AVG(load_1) AS mean_load,
    MAX(load_1) AS max_load
FROM beszel_metrics
WHERE ts_utc >= ? AND ts_utc <= ?
```

**Return:** Dict with keys: `mean_cpu`, `max_cpu`, `mean_mem`, `max_mem`, `mean_load`, `max_load`. All float or None if no data.

**Testing:**

Tests must verify:
- epoch-analysis.AC3.3: Given test Beszel metrics, returns correct mean/max values
- Edge case: no Beszel data in epoch returns all None

**Verification:**

```bash
uv run pytest tests/unit/test_epoch_queries.py -k "test_epoch_resources" -v
```

**Commit:** `feat: add per-epoch Beszel resource stats`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: `query_epoch_pg()` and `query_epoch_journal_anomalies()`

**Verifies:** epoch-analysis.AC3.1 (PG errors supplement JSONL errors)

**Files:**
- Modify: `scripts/incident/analysis.py` (add two functions)
- Modify: `tests/unit/test_epoch_queries.py` (add tests)

**Implementation:**

**PG error summary:**

```python
def query_epoch_pg(
    conn: sqlite3.Connection, start_utc: str, end_utc: str
) -> list[dict]:
```

```sql
SELECT level, error_type, COUNT(*) AS count
FROM pg_events
WHERE ts_utc >= ? AND ts_utc <= ?
GROUP BY level, error_type
ORDER BY count DESC
```

Returns list of dicts: `{level, error_type, count}`.

**Journal anomalies (priority <= 3 = ERROR and above):**

```python
def query_epoch_journal_anomalies(
    conn: sqlite3.Connection, start_utc: str, end_utc: str
) -> list[dict]:
```

```sql
SELECT ts_utc, priority, unit, message
FROM journal_events
WHERE ts_utc >= ? AND ts_utc <= ?
  AND priority <= 3
ORDER BY ts_utc
```

Returns list of dicts: `{ts_utc, priority, unit, message}`. Priority 0=EMERG, 1=ALERT, 2=CRIT, 3=ERR.

**Testing:**

Tests must verify:
- PG query returns grouped error counts
- Journal anomaly query returns only priority <= 3 events

**Verification:**

```bash
uv run pytest tests/unit/test_epoch_queries.py -k "test_epoch_pg or test_epoch_journal" -v
```

**Commit:** `feat: add PG error and journal anomaly queries`

## UAT Steps

1. Run all five query functions against a known epoch from `incident.db`:
```bash
uv run python -c "
import sqlite3
from scripts.incident.schema import create_schema
from scripts.incident.analysis import extract_epochs, query_epoch_errors, query_epoch_haproxy, query_epoch_resources, query_epoch_pg, query_epoch_journal_anomalies
conn = sqlite3.connect('incident.db')
create_schema(conn)
epochs = extract_epochs(conn)
e = [ep for ep in epochs if not ep['is_crash_bounce']][0]
print(f'Epoch: {e[\"commit\"]} ({e[\"duration_seconds\"]:.0f}s)')
errors = query_epoch_errors(conn, e['start_utc'], e['end_utc'], e['duration_seconds'])
print(f'Errors: {len(errors)} types')
hap = query_epoch_haproxy(conn, e['start_utc'], e['end_utc'], e['duration_seconds'])
print(f'HAProxy: {hap[\"total_requests\"]} reqs, p50={hap[\"p50_ms\"]}ms')
res = query_epoch_resources(conn, e['start_utc'], e['end_utc'])
print(f'Resources: CPU mean={res[\"mean_cpu\"]:.1f}% max={res[\"max_cpu\"]:.1f}%')
"
```
2. Verify: Non-zero request counts, reasonable percentile values, resource metrics present

## Complexity Check

```bash
uv run complexipy scripts/incident/analysis.py
```
<!-- END_TASK_4 -->
