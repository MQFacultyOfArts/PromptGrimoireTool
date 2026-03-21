# Epoch Analysis Implementation Plan — Phase 2: Epoch Extraction

**Goal:** Extract epoch boundaries from JSONL commit hash transitions using SQL window functions, then enrich each epoch with journal shutdown metadata and GitHub PR correlation.

**Architecture:** Three pure functions in `scripts/incident/analysis.py`: `extract_epochs()` uses `LAG()` window function on `json_extract(extra_json, '$.commit')` to detect commit transitions; `enrich_epochs_journal()` matches epoch boundaries against journal `Consumed` messages via regex; `enrich_epochs_github()` joins commit hashes against `github_events` table.

**Tech Stack:** SQLite (LAG window function, json_extract), Python re module, sqlite3 stdlib

**Scope:** 6 phases from original design (phase 2 of 6)

**Codebase verified:** 2026-03-18

---

## Acceptance Criteria Coverage

This phase implements and tests:

### epoch-analysis.AC2: Epoch extraction and enrichment
- **epoch-analysis.AC2.1 Success:** Commit hash transitions in JSONL correctly identify epoch boundaries with start/end timestamps
- **epoch-analysis.AC2.2 Success:** Journal `Consumed` messages are matched to epoch boundaries, providing memory peak and CPU consumed
- **epoch-analysis.AC2.3 Success:** GitHub PR metadata is attached to epochs by matching commit hash prefixes
- **epoch-analysis.AC2.4 Edge:** Epochs with no matching PR (direct pushes, pre-GitHub-fetch) show "no PR" rather than failing

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Create `analysis.py` with `extract_epochs()`

**Verifies:** epoch-analysis.AC2.1

**Files:**
- Create: `scripts/incident/analysis.py`
- Test: `tests/unit/test_epoch_extraction.py` (unit)

**Implementation:**

Create `scripts/incident/analysis.py` with a single function:

```python
def extract_epochs(conn: sqlite3.Connection) -> list[dict]:
```

**SQL approach:** Use `LAG()` window function to detect where `json_extract(extra_json, '$.commit')` changes between consecutive JSONL events ordered by `ts_utc`. Each transition marks an epoch boundary.

The query should:
1. Select all JSONL events that have a non-null commit in `extra_json`
2. Use `LAG(json_extract(extra_json, '$.commit')) OVER (ORDER BY ts_utc)` to get the previous commit
3. Where `commit != prev_commit` (or `prev_commit IS NULL` for the first epoch), mark as a boundary
4. For each epoch, collect: `commit` hash, `start_utc` (first event), `end_utc` (last event before next boundary), `event_count`

**Return value:** List of dicts, each with keys:
- `commit`: str — the short commit hash (e.g., "ba70f4fa")
- `start_utc`: str — first event timestamp in this epoch
- `end_utc`: str — last event timestamp in this epoch
- `event_count`: int — number of JSONL events in this epoch
- `duration_seconds`: float — epoch duration in seconds
- `is_crash_bounce`: bool — True if duration < 300 seconds (5 minutes)

**Implementation strategy:** Use a CTE to identify boundary rows, then use those boundaries to window the full event set. Alternatively, fetch all distinct (commit, ts_utc) pairs ordered by ts_utc and group in Python.

The simpler Python approach: query all distinct commit+timestamp pairs, iterate to find transitions, then count events per epoch with a follow-up query:

```python
def extract_epochs(conn: sqlite3.Connection) -> list[dict]:
    """Detect epoch boundaries from commit hash transitions in JSONL events."""
    conn.row_factory = sqlite3.Row
    # Get all events with commit hashes, ordered by time
    rows = conn.execute("""
        SELECT ts_utc, json_extract(extra_json, '$.commit') AS commit
        FROM jsonl_events
        WHERE json_extract(extra_json, '$.commit') IS NOT NULL
        ORDER BY ts_utc
    """).fetchall()

    if not rows:
        return []

    # Detect transitions
    epochs: list[dict] = []
    current_commit = rows[0]["commit"]
    start_utc = rows[0]["ts_utc"]

    for row in rows[1:]:
        if row["commit"] != current_commit:
            # Epoch boundary: close current epoch, start new one
            # ... (close epoch logic)
            current_commit = row["commit"]
            start_utc = row["ts_utc"]
    # Close final epoch

    # For each epoch, count events
    for epoch in epochs:
        count = conn.execute("""
            SELECT COUNT(*) FROM jsonl_events
            WHERE ts_utc >= ? AND ts_utc <= ?
        """, (epoch["start_utc"], epoch["end_utc"])).fetchone()[0]
        epoch["event_count"] = count
        # Calculate duration
        # ... parse timestamps, compute seconds
        epoch["is_crash_bounce"] = epoch["duration_seconds"] < 300

    return epochs
```

**Testing:**

Tests must verify:
- epoch-analysis.AC2.1: Given a test SQLite DB with JSONL events from two different commits, `extract_epochs()` returns two epochs with correct boundaries
- Edge case: single commit (one epoch)
- Edge case: empty DB (returns empty list)
- Crash-bounce detection: epoch < 5 minutes flagged

Test approach: Create an in-memory SQLite DB, insert test JSONL events with known commit hashes and timestamps, verify epoch boundaries.

**Verification:**

```bash
uv run pytest tests/unit/test_epoch_extraction.py -v
```

**Commit:** `feat: add epoch extraction from JSONL commit transitions`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: `enrich_epochs_journal()` — journal shutdown metadata

**Verifies:** epoch-analysis.AC2.2

**Files:**
- Modify: `scripts/incident/analysis.py` (add function)
- Test: `tests/unit/test_epoch_enrichment.py` (unit)

**Implementation:**

Add to `scripts/incident/analysis.py`:

```python
def enrich_epochs_journal(conn: sqlite3.Connection, epochs: list[dict]) -> None:
```

This function enriches each epoch dict **in place** with journal `Consumed` message data.

**Journal `Consumed` message format** (verified from real data):
```
promptgrimoire.service: Consumed 1d 13h 41min 40.066s CPU time, 2.7G memory peak, 0B memory swap peak.
promptgrimoire.service: Consumed 8.509s CPU time, 366.5M memory peak, 0B memory swap peak.
```

**Regex pattern:**
```python
_CONSUMED_RE = re.compile(
    r"Consumed (.+?) CPU time, (.+?) memory peak, (.+?) memory swap peak"
)
```

**Logic:**
1. For each epoch, query journal events near the epoch's `end_utc` (within a small window, e.g., ±60 seconds) where `message LIKE '%Consumed%'`
2. Parse the first matching message with the regex
3. Add to epoch dict: `cpu_consumed` (raw string like "1d 13h 41min 40.066s"), `memory_peak` (raw string like "2.7G"), `swap_peak` (raw string like "0B")
4. Also call `_parse_memory_bytes(memory_peak)` and store the integer result as `epoch["memory_peak_bytes"]` — this is needed by trend analysis (Phase 5)
5. **Epoch end correction:** If a journal `Consumed` message is found and its `ts_utc` is LATER than the epoch's `end_utc` (from JSONL), update `epoch["end_utc"]` to the journal timestamp and recalculate `duration_seconds` and `is_crash_bounce`. Rationale: the server may idle after the last JSONL event before shutdown — using JSONL-only end times systematically underestimates epoch duration, inflating rate normalisation and potentially misclassifying crash-bounces.
6. If no match found, set all fields (`cpu_consumed`, `memory_peak`, `swap_peak`, `memory_peak_bytes`) to `None` — epoch end_utc remains as derived from JSONL

**Memory size parsing helper** (for later use in trend analysis):

```python
def _parse_memory_bytes(size_str: str) -> int | None:
    """Parse systemd memory strings like '2.7G', '366.5M', '0B' to bytes."""
```

This converts human-readable sizes to bytes for comparison. Map: B=1, K=1024, M=1024², G=1024³.

**Testing:**

Tests must verify:
- epoch-analysis.AC2.2: Given epochs and matching journal Consumed messages, enrichment adds correct memory_peak and cpu_consumed
- Edge case: no matching journal message — fields set to None

Test approach: In-memory SQLite with test journal events containing Consumed messages at epoch boundaries.

**Verification:**

```bash
uv run pytest tests/unit/test_epoch_enrichment.py -v
```

**Commit:** `feat: add journal Consumed message enrichment for epochs`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: `enrich_epochs_github()` — PR correlation

**Verifies:** epoch-analysis.AC2.3, epoch-analysis.AC2.4

**Files:**
- Modify: `scripts/incident/analysis.py` (add function)
- Modify: `tests/unit/test_epoch_enrichment.py` (add tests)

**Implementation:**

Add to `scripts/incident/analysis.py`:

```python
def enrich_epochs_github(conn: sqlite3.Connection, epochs: list[dict]) -> None:
```

This enriches each epoch dict **in place** with GitHub PR metadata from the `github_events` table.

**Matching logic:**
- The epoch has a short commit hash (8 chars, e.g., "ba70f4fa")
- The `github_events.commit_oid` has the full 40-char merge commit SHA
- Match using prefix: `commit_oid LIKE ? || '%'` with the epoch's commit hash
- This is safe because false positives are negligible at this repo size (design doc confirms)

**SQL query per epoch:**
```sql
SELECT pr_number, title, author, url
FROM github_events
WHERE commit_oid LIKE ? || '%'
LIMIT 1
```

**Enrichment:**
- If match found: add `pr_number`, `pr_title`, `pr_author`, `pr_url` to epoch dict
- If no match (AC2.4): add `pr_number: None`, `pr_title: "no PR"`, `pr_author: None`, `pr_url: None`

**Testing:**

Tests must verify:
- epoch-analysis.AC2.3: Epoch with commit hash matching a github_events row gets PR metadata
- epoch-analysis.AC2.4: Epoch with no matching PR gets "no PR" rather than failing

Test approach: In-memory SQLite with github_events rows, epochs with matching and non-matching commit hashes.

**Verification:**

```bash
uv run pytest tests/unit/test_epoch_enrichment.py -v
```

**Commit:** `feat: add GitHub PR correlation for epochs`

## UAT Steps

1. Run: `uv run python -c "
import sqlite3
from scripts.incident.schema import create_schema
from scripts.incident.analysis import extract_epochs, enrich_epochs_journal, enrich_epochs_github
conn = sqlite3.connect('incident.db')
create_schema(conn)
epochs = extract_epochs(conn)
print(f'Found {len(epochs)} epochs')
for e in epochs:
    print(f'  {e[\"commit\"]} {e[\"start_utc\"][:19]} -> {e[\"end_utc\"][:19]} ({e[\"duration_seconds\"]:.0f}s, bounce={e[\"is_crash_bounce\"]})')
enrich_epochs_journal(conn, epochs)
for e in epochs:
    print(f'  {e[\"commit\"]}: mem={e.get(\"memory_peak\")}, cpu={e.get(\"cpu_consumed\")}')
"`
2. Verify: Multiple epochs found, crash-bounces flagged, journal metadata attached
3. If github_events populated (Phase 1 UAT done first): verify PR titles appear

## Complexity Check

```bash
uv run complexipy scripts/incident/analysis.py
```
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
