# Epoch Analysis Implementation Plan — Phase 5: Trend Analysis

**Goal:** Cross-epoch comparison computing deltas and percentage changes for key metrics, flagging anomalous spikes to surface deteriorating behaviour.

**Architecture:** Pure Python function `compute_trends()` in `scripts/incident/analysis.py` that takes the enriched epochs list (with per-epoch stats already attached) and computes consecutive deltas. No SQL — operates on in-memory epoch dicts assembled by Phases 2-4.

**Tech Stack:** Python arithmetic, no external deps

**Scope:** 6 phases from original design (phase 5 of 6)

**Codebase verified:** 2026-03-18

---

## Acceptance Criteria Coverage

This phase implements and tests:

### epoch-analysis.AC5: Trend analysis
- **epoch-analysis.AC5.1 Success:** Each epoch shows delta and percentage change vs previous for error rate, 5xx rate, memory peak, mean CPU, active users
- **epoch-analysis.AC5.2 Success:** Anomalous spikes (>100% increase) flagged in the report

---

<!-- START_TASK_1 -->
### Task 1: `compute_trends()` — cross-epoch trend computation

**Verifies:** epoch-analysis.AC5.1, epoch-analysis.AC5.2

**Files:**
- Modify: `scripts/incident/analysis.py` (add function)
- Test: `tests/unit/test_epoch_trends.py` (unit)

**Implementation:**

Add to `scripts/incident/analysis.py`:

```python
def compute_trends(epochs: list[dict]) -> list[dict]:
```

**Input:** List of epoch dicts, each already enriched with per-epoch stats from Phases 2-4. Expected keys on each epoch (set by the review orchestrator):
- `error_rate`: float | None — total errors per hour (from `query_epoch_errors`)
- `rate_5xx`: float | None — 5xx responses per hour (from `query_epoch_haproxy`)
- `memory_peak_bytes`: int | None — from journal enrichment (`_parse_memory_bytes`)
- `mean_cpu`: float | None — from `query_epoch_resources`
- `active_users`: int | None — from `query_epoch_users`
- `is_crash_bounce`: bool

**Logic:**

For each epoch (except the first), compute vs the previous non-crash-bounce epoch:
1. For each metric in `[error_rate, rate_5xx, memory_peak_bytes, mean_cpu, active_users]`:
   - `delta = current - previous` (absolute change)
   - `pct_change = (delta / previous) * 100` if previous != 0, else None
   - `is_anomaly`: flag using BOTH relative AND absolute thresholds to avoid false positives on low-baseline metrics. A metric is anomalous only if the percentage change exceeds the threshold AND the absolute values are above a minimum floor:
     - `error_rate`: >100% increase AND current > 5/hour (avoids flagging 1→3 errors/hr)
     - `rate_5xx`: >100% increase AND current > 2/hour
     - `memory_peak_bytes`: >50% increase AND current > 1GB (memory is expensive; lower threshold)
     - `mean_cpu`: >100% increase AND current > 20%
     - `active_users`: NOT flagged as anomalous (user counts are not an operational concern — changes reflect usage patterns, not degradation)
   These thresholds should be defined as module-level constants for easy tuning.
2. Skip crash-bounce epochs for trend computation (they don't have normalised rates)
3. First epoch has no trends (no predecessor)

**Return:** List of trend dicts, one per non-crash-bounce epoch (except the first). Each dict:
- `epoch_index`: int — index into the epochs list
- `commit`: str — epoch's commit hash
- `metrics`: dict mapping metric name to `{value, previous, delta, pct_change, is_anomaly}`

**Anomaly flagging:**

An epoch is "anomalous" if ANY of its metrics has `is_anomaly == True`. The report renderer (Phase 6) uses this flag to highlight the epoch.

**Helper: `_safe_delta(current, previous)`**

Handles None values gracefully:
```python
def _safe_delta(current: float | int | None, previous: float | int | None) -> dict:
    if current is None or previous is None:
        return {"value": current, "previous": previous, "delta": None, "pct_change": None}
    delta = current - previous
    pct = (delta / previous) * 100 if previous != 0 else None
    return {
        "value": current,
        "previous": previous,
        "delta": delta,
        "pct_change": pct,
        # is_anomaly is set by the caller with metric-specific thresholds
    }
```

**Testing:**

Tests must verify:
- epoch-analysis.AC5.1: Given 3 epochs with known metrics, trends correctly compute deltas and percentages
- epoch-analysis.AC5.2: Epoch with >100% increase in any metric is flagged as anomalous
- Crash-bounce epochs are excluded from trend computation
- First epoch has no trends
- None metric values handled gracefully (no division errors)

**Verification:**

```bash
uv run pytest tests/unit/test_epoch_trends.py -v
```

**Commit:** `feat: add cross-epoch trend analysis with anomaly detection`

## UAT Steps

1. Run trend analysis against enriched epochs from `incident.db`:
```bash
uv run python -c "
from scripts.incident.analysis import compute_trends
# Simulate enriched epochs with known metrics
epochs = [
    {'commit': 'aaa', 'is_crash_bounce': False, 'error_rate': 10.0, 'rate_5xx': 2.0, 'memory_peak_bytes': 1_000_000, 'mean_cpu': 25.0, 'active_users': 5},
    {'commit': 'bbb', 'is_crash_bounce': False, 'error_rate': 25.0, 'rate_5xx': 8.0, 'memory_peak_bytes': 3_000_000, 'mean_cpu': 60.0, 'active_users': 3},
]
trends = compute_trends(epochs)
for t in trends:
    print(f'Epoch {t[\"commit\"]}:')
    for name, m in t['metrics'].items():
        print(f'  {name}: delta={m[\"delta\"]}, pct={m[\"pct_change\"]:.0f}%, anomaly={m[\"is_anomaly\"]}')
"
```
2. Verify: error_rate shows +150% (anomaly), rate_5xx shows +300% (anomaly), memory shows +200% (anomaly)

## Complexity Check

```bash
uv run complexipy scripts/incident/analysis.py
```
<!-- END_TASK_1 -->
