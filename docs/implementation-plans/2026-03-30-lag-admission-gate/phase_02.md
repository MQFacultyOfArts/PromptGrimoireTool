# Lag-Based Admission Gate Implementation Plan

**Goal:** Wire admission cap computation and batch admission into the existing diagnostic loop; initialise admission state at app startup.

**Architecture:** diagnostics.py calls into the admission module after measuring lag each cycle. __init__.py initialises the admission singleton during startup. No new background tasks.

**Tech Stack:** Python 3.14, structlog, asyncio

**Scope:** 5 phases from original design (phase 2 of 5)

**Codebase verified:** 2026-03-30

---

## Acceptance Criteria Coverage

This phase implements and tests:

### lag-admission-gate.AC5: Admission state visible in diagnostic logs
- **lag-admission-gate.AC5.1 Success:** `memory_diagnostic` structlog event includes `admission_cap`, `admission_admitted`, `admission_queue_depth`, `admission_tickets`
- **lag-admission-gate.AC5.2 Success:** All config values (`initial_cap`, `batch_size`, `lag_increase_ms`, `lag_decrease_ms`, `queue_timeout_seconds`, `ticket_validity_seconds`) configurable via env vars

---

<!-- START_TASK_1 -->
### Task 1: Initialise admission state at app startup

**Verifies:** lag-admission-gate.AC5.2 (config values are wired through)

**Files:**
- Modify: `src/promptgrimoire/__init__.py` (startup hook, around lines 156-193)

**Implementation:**

In the `_register_db_lifecycle()` function (the `app.on_startup` handler), after diagnostic logger task creation (line 192), initialise the admission state:

```python
from promptgrimoire.admission import init_admission

# After diagnostic logger task creation:
init_admission(get_settings().admission)
```

This must happen BEFORE the diagnostic loop's first iteration can call admission functions, but since `start_diagnostic_logger` does an initial `await asyncio.sleep(interval_seconds)` before its first measurement, there's no race.

**Verification:**

Run: `uv run grimoire test all`
Expected: All tests pass. The admission module initialises with default config values.

**Commit:** `feat: initialise admission state at app startup`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Wire admission into diagnostic loop and add log fields

**Verifies:** lag-admission-gate.AC5.1

**Files:**
- Modify: `src/promptgrimoire/diagnostics.py` (start_diagnostic_logger, around lines 277-306)
- Create: `tests/unit/test_admission_diagnostics.py`

**Implementation:**

In `start_diagnostic_logger()`, after the memory threshold check (around line 301) and before the sleep, add admission processing:

```python
from promptgrimoire.admission import get_admission_state
from promptgrimoire.auth import client_registry

# After memory threshold check, before sleep:
_admission = get_admission_state()
_admitted_count = len(client_registry._registry)

# Update cap based on latest lag
_admission.update_cap(
    lag_ms=snapshot["event_loop_lag_ms"],
    admitted_count=_admitted_count,
)

# Admit queued users if capacity available
_admission.admit_batch(admitted_count=_admitted_count)

# Clean up expired queue entries and tickets
_admission.sweep_expired()

# Add admission fields to snapshot for logging
snapshot["admission_cap"] = _admission.cap
snapshot["admission_admitted"] = _admitted_count
snapshot["admission_queue_depth"] = len(_admission._queue)
snapshot["admission_tickets"] = len(_admission._tickets)
```

Note: the `logger.info("memory_diagnostic", **snapshot)` call at line 293 happens BEFORE admission processing. The admission fields need to be logged too. Two options:
1. Move the log call after admission processing (changes log timing)
2. Add a second log call for admission fields
3. Move admission processing before the log call but after lag measurement

Option 3 is cleanest — process admission right after lag measurement (line 292), then log everything in one event. Reorder to:

```
snapshot["event_loop_lag_ms"] = await measure_event_loop_lag()
# Admission processing here (update_cap, admit_batch, sweep, add fields)
logger.info("memory_diagnostic", **snapshot)
_check_memory_threshold(...)
```

This way all fields are in the single `memory_diagnostic` event.

**Testing:**

Test file: `tests/unit/test_admission_diagnostics.py`

Tests verify AC5.1: diagnostic log includes admission fields.

- lag-admission-gate.AC5.1: Mock `get_admission_state()` to return an `AdmissionState` with known values. Mock `client_registry._registry` to a dict with known length. Call the admission processing logic (extracted as a testable function or tested via the snapshot dict). Verify snapshot dict contains `admission_cap`, `admission_admitted`, `admission_queue_depth`, `admission_tickets` with correct values.

Since `start_diagnostic_logger` is an infinite async loop, testing the admission integration directly requires either:
- Extracting the per-cycle logic into a testable function (preferred)
- OR testing via structlog capture

The cleanest approach: extract a `_run_diagnostic_cycle(snapshot, threshold_mb)` function from the loop body. This makes the per-cycle logic unit-testable without running the full async loop.

**Verification:**

Run: `uv run grimoire test run tests/unit/test_admission_diagnostics.py`
Expected: All tests pass

Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `feat: wire admission gate into diagnostic loop with structlog fields`
<!-- END_TASK_2 -->
