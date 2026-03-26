# Query Optimisation and Graceful Restart — Phase 6

**Goal:** Zero-overhead periodic diagnostics to narrow memory leak investigation without tracemalloc. Emits a flattened `memory_diagnostic` structlog event every 5 minutes with RSS, NiceGUI client counts, asyncio task count, and CRDT registry/presence sizes.

**Architecture:** Port collection functions from NiceGUI #5660 draft (`nicegui/.worktrees/diagnostics-5660/nicegui/diagnostics.py`) into `src/promptgrimoire/diagnostics.py`. Add PromptGrimoire-specific CRDT fields. Run as a 4th background task alongside search, deadline, and export workers. When #5660 merges upstream and the pin bumps, swap ported functions with `from nicegui import diagnostics`.

**Tech Stack:** stdlib `resource`, `/proc/self/status`, `asyncio.all_tasks()`, structlog, NiceGUI `Client.instances`

**Scope:** Phase 6 of 6 from original design

**Codebase verified:** 2026-03-26

---

## Acceptance Criteria Coverage

This phase implements and tests:

### query-optimisation-and-graceful-restart-186.AC5: Memory leak diagnostic logging
- **query-optimisation-and-graceful-restart-186.AC5.1 Success:** `memory_diagnostic` event emitted every 5 minutes to JSONL
- **query-optimisation-and-graceful-restart-186.AC5.2 Success:** Includes NiceGUI snapshot fields (RSS, client counts, asyncio tasks) plus CRDT registry/presence sizes
- **query-optimisation-and-graceful-restart-186.AC5.3 Edge:** Collection logic ported from NiceGUI #5660 draft; when upstream merges, swap to `from nicegui import diagnostics`

---

## Implementation Tasks

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Create `src/promptgrimoire/diagnostics.py` with collection functions

**Verifies:** query-optimisation-and-graceful-restart-186.AC5.2, query-optimisation-and-graceful-restart-186.AC5.3

**Files:**
- Create: `src/promptgrimoire/diagnostics.py`

**Implementation:**

Port three functions from `/home/brian/people/Brian/nicegui/.worktrees/diagnostics-5660/nicegui/diagnostics.py`:

1. **`_collect_memory()`** (lines 43-70) — Returns `peak_rss_bytes` via `resource.getrusage()` and `current_rss_bytes` via `/proc/self/status VmRSS`. Platform-safe guards for non-POSIX and non-Linux.

2. **`_collect_task_summary()`** (lines 22-40) — Returns `total` asyncio task count and `by_coroutine` breakdown. For periodic logging, only emit `total` (flatten); the `by_coroutine` detail is available for future diagnostic endpoint.

3. **`collect_snapshot()`** — Aggregates memory, NiceGUI client counts, asyncio tasks. Import `Client` from `nicegui` lazily (AC5.3: zero import-time cost). Add PromptGrimoire-specific fields:

```python
"""Runtime diagnostics for PromptGrimoire.

Collection functions ported from NiceGUI PR #5660 (draft, not yet merged).
When #5660 merges upstream and the NiceGUI pin bumps, replace the NiceGUI-generic
portions with ``from nicegui import diagnostics``.

Source: nicegui/.worktrees/diagnostics-5660/nicegui/diagnostics.py
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from typing import Any

import structlog

# NOTE: resource module is POSIX-only; gracefully degrade on other platforms
try:
    import resource
except ImportError:
    resource = None  # type: ignore[assignment]  # resource is ModuleType | None; ty can't narrow conditional import

logger = structlog.get_logger()


def _collect_memory() -> dict[str, Any]:
    """Collect memory usage metrics."""
    result: dict[str, Any] = {}

    if resource is not None:
        peak_rss_raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # NOTE: on Linux, ru_maxrss is in KB; on macOS it is in bytes
        result["peak_rss_bytes"] = peak_rss_raw * 1024 if sys.platform == "linux" else peak_rss_raw
    else:
        result["peak_rss_bytes"] = None

    result["current_rss_bytes"] = None
    with contextlib.suppress(OSError):
        with open("/proc/self/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    result["current_rss_bytes"] = int(line.split()[1]) * 1024
                    break

    return result


def collect_snapshot() -> dict[str, Any]:
    """Collect a flattened diagnostics snapshot for structlog emission.

    Includes NiceGUI client counts, memory metrics, asyncio task count,
    and PromptGrimoire-specific CRDT registry/presence sizes.
    """
    # Lazy imports — zero cost at module import time
    from nicegui import Client

    from promptgrimoire.pages.annotation import _workspace_presence, _workspace_registry

    memory = _collect_memory()

    return {
        # Memory
        "current_rss_bytes": memory["current_rss_bytes"],
        "peak_rss_bytes": memory["peak_rss_bytes"],
        # NiceGUI clients
        "clients_total": len(Client.instances),
        "clients_connected": sum(
            1 for c in Client.instances.values() if c.has_socket_connection
        ),
        # Asyncio tasks
        "asyncio_tasks_total": len(asyncio.all_tasks()),
        # PromptGrimoire application state
        "app_ws_registry": len(_workspace_registry._documents),
        "app_ws_presence_workspaces": len(_workspace_presence),
        "app_ws_presence_clients": sum(
            len(v) for v in _workspace_presence.values()
        ),
    }
```

**Verification:**
Run: `uvx ty@0.0.24 check`
Expected: No type errors

**Commit:** `feat: add diagnostics module ported from NiceGUI #5660 (#432)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add periodic diagnostic logger background task

**Verifies:** query-optimisation-and-graceful-restart-186.AC5.1

**Files:**
- Modify: `src/promptgrimoire/__init__.py` (add 4th background task in startup/shutdown)

**Implementation:**

Add the diagnostic logger task alongside the existing three workers in `__init__.py`:

1. Define the logger function (can be in `diagnostics.py` or inline in `__init__.py`):

```python
async def start_diagnostic_logger(*, interval_seconds: float = 300.0) -> None:
    """Emit memory_diagnostic structlog event at regular intervals."""
    while True:
        try:
            snapshot = collect_snapshot()
            logger.info("memory_diagnostic", **snapshot)
        except Exception:
            logger.exception("diagnostic_snapshot_failed")
        await asyncio.sleep(interval_seconds)
```

2. In `startup()` (after existing worker creation, ~line 393):
```python
_diagnostic_logger_task = asyncio.create_task(
    start_diagnostic_logger(),
)
```

3. In `shutdown()` — add cancellation alongside the other workers:
```python
if _diagnostic_logger_task is not None:
    _diagnostic_logger_task.cancel()
    tasks_to_cancel.append(_diagnostic_logger_task)
    _diagnostic_logger_task = None
```

4. Add `_diagnostic_logger_task: asyncio.Task[None] | None = None` to the module-level variables near the existing worker task variables.

**Verification:**
Run: `uvx ty@0.0.24 check`
Expected: No type errors

Run: `uv run run.py` — wait 5 minutes, check log output for `memory_diagnostic` event
Expected: Event appears with all fields populated (or null for non-Linux fields)

**Commit:** `feat: add periodic memory diagnostic logger (#432)`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Unit tests for diagnostics collection

**Verifies:** query-optimisation-and-graceful-restart-186.AC5.2

**Files:**
- Create: `tests/unit/test_diagnostics.py`

**Testing:**

Tests must verify AC5.2 — that the snapshot contains all expected fields with correct types:

- **Test: collect_snapshot returns all expected keys** — Call `collect_snapshot()`, verify the result dict contains: `current_rss_bytes`, `peak_rss_bytes`, `clients_total`, `clients_connected`, `asyncio_tasks_total`, `app_ws_registry`, `app_ws_presence_workspaces`, `app_ws_presence_clients`. All values should be `int` or `None` (for non-Linux platforms).

- **Test: _collect_memory returns RSS on Linux** — On Linux (CI and dev), `current_rss_bytes` should be a positive integer. `peak_rss_bytes` should also be a positive integer. Skip on non-Linux with `pytest.mark.skipif(sys.platform != "linux", reason="VmRSS only on Linux")`.

- **Test: _collect_memory handles missing /proc gracefully** — Monkeypatch `open` to raise `OSError`, verify `current_rss_bytes` is `None`.

Follow unit test patterns: class-based, imports inside test body, monkeypatch for mocking.

**Verification:**
Run: `uv run grimoire test run tests/unit/test_diagnostics.py`
Expected: All tests pass

**Commit:** `test: add unit tests for diagnostics collection (#432)`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

---

## Complexipy Check

After completing this phase, run:
```bash
uv run complexipy src/promptgrimoire/diagnostics.py src/promptgrimoire/__init__.py --max-complexity-allowed 15
```

## UAT Steps

1. [ ] Start the app: `uv run run.py`
2. [ ] Wait 5 minutes (or temporarily reduce interval to 10s for testing)
3. [ ] Check logs: `tail -f test-debug.log | grep memory_diagnostic` (or `jq 'select(.event == "memory_diagnostic")'`)
4. [ ] Verify event contains: `current_rss_bytes`, `peak_rss_bytes`, `clients_total`, `clients_connected`, `asyncio_tasks_total`, `app_ws_registry`, `app_ws_presence_workspaces`, `app_ws_presence_clients`
5. [ ] Verify all values are integers (not null on Linux)

## Evidence Required
- [ ] `uv run grimoire test run tests/unit/test_diagnostics.py` output showing green
- [ ] Log output showing a `memory_diagnostic` event with all fields populated

## Pre-PR Gate

Before creating a PR, all three suites must pass:
```bash
uv run grimoire test all
uv run grimoire e2e all
uv run grimoire e2e firefox
```

Present results to Brian before proceeding with PR creation.
