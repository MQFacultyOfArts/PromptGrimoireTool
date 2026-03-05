# CLI Typer Migration Implementation Plan — Phase 4

**Goal:** Extract unit/integration test commands to `testing.py`, populate `_shared.py` with cross-module infrastructure, and reduce `_stream_with_progress` cognitive complexity from 36 to ≤15.

**Architecture:** `_shared.py` holds `_pre_test_db_cleanup()`, `_build_test_header()`, the Rich `Console()` instance, and all 5 regex constants. `testing.py` holds `_stream_with_progress` (refactored), `_stream_plain`, `_run_pytest`, `_parse_collection`, `_is_summary_boundary`, `_parse_result`, `_xdist_worker_count`, and the three test commands. The complexity reduction extracts `_handle_collecting_phase()` and `_handle_running_phase()` from `_stream_with_progress`.

**Tech Stack:** Typer, Rich (Console, Progress, Text, Panel), subprocess, regex

**Scope:** Phase 4 of 6 from original design

**Codebase verified:** 2026-03-02. Confirmed: `_stream_with_progress` cognitive complexity = 36 (via complexipy).

---

## Acceptance Criteria Coverage

### cli-typer-211.AC2: Typer Framework
- **cli-typer-211.AC2.1 Success:** All commands use `typer.Argument()` / `typer.Option()` for parameter declaration
- **cli-typer-211.AC2.4 Edge:** Pytest passthrough args (e.g., `-k test_foo -x`) are forwarded correctly via `ctx.args`

### cli-typer-211.AC4: Complexity Compliance
- **cli-typer-211.AC4.1 Success:** `complexipy src/promptgrimoire/cli/ --max-complexity-allowed 15` reports zero failures
- **cli-typer-211.AC4.2 Success:** `_stream_with_progress` cognitive complexity ≤ 15

### cli-typer-211.AC5: Tests Pass and Expand
- **cli-typer-211.AC5.1 Success:** `test_cli_header.py` passes with import from `promptgrimoire.cli._shared`

---

<!-- START_TASK_1 -->
### Task 1: Populate cli/_shared.py with Cross-Module Infrastructure

**Files:**
- Modify: `src/promptgrimoire/cli/_shared.py` (replace empty file)

**Implementation:**

Move these from `cli_legacy.py`:
- `console = Console()` (line 30)
- `_pre_test_db_cleanup()` (lines 33-99)
- `_build_test_header()` (lines 102-130)
- 5 regex constants (lines 182-186):
  - `_COLLECTED_RE = re.compile(r"collected (\d+) items?(?:\s*/\s*(\d+) deselected)?")`
  - `_XDIST_ITEMS_RE = re.compile(r"\[(\d+) items?\]")`
  - `_RESULT_KW_RE = re.compile(r"\b(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b")`
  - `_PCT_RE = re.compile(r"\[\s*(\d+)%\s*\]")`
  - `_SEPARATOR_RE = re.compile(r"^={5,}")`

**Important:** `docs.py` (from Phase 3) currently imports `_pre_test_db_cleanup` from `cli_legacy`. After this task, update `docs.py` to import from `cli._shared` instead:

```python
# In docs.py, change:
from promptgrimoire.cli_legacy import _pre_test_db_cleanup
# To:
from promptgrimoire.cli._shared import _pre_test_db_cleanup
```

Similarly update `test_make_docs.py` patches if they reference the legacy module path for `_pre_test_db_cleanup`.

**Verification:**

Run: `python -c "from promptgrimoire.cli._shared import console, _pre_test_db_cleanup, _build_test_header"`
Expected: No import errors.

**Commit:** `feat: populate _shared.py with cross-module CLI infrastructure`
<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-3) -->
<!-- START_TASK_2 -->
### Task 2: Populate cli/testing.py with Test Commands and Refactored Streaming

**Verifies:** cli-typer-211.AC2.1, cli-typer-211.AC2.4, cli-typer-211.AC4.2

**Files:**
- Modify: `src/promptgrimoire/cli/testing.py` (replace placeholder)

**Implementation:**

Move these functions from `cli_legacy.py` into `testing.py`:
- `_parse_collection` (lines 189-199)
- `_is_summary_boundary` (lines 202-204)
- `_parse_result` (lines 207-218)
- `_stream_plain` (lines 133-175) — adjust to import regex from `_shared`
- `_stream_with_progress` (lines 221-293) — **refactor for complexity reduction**
- `_run_pytest` (lines 296-380)
- `_xdist_worker_count` (lines 425-437)
- `test_changed` (lines 383-422) → becomes `@test_app.command("changed")`
- `test_all` (lines 440-474) → becomes `@test_app.command("all")`
- `test_all_fixtures` (lines 477-496) → becomes `@test_app.command("all-fixtures")`

Import shared infrastructure from `_shared.py`:
```python
from promptgrimoire.cli._shared import (
    console,
    _pre_test_db_cleanup,
    _build_test_header,
    _COLLECTED_RE,
    _XDIST_ITEMS_RE,
    _RESULT_KW_RE,
    _PCT_RE,
    _SEPARATOR_RE,
)
```

**Typer command pattern** for test commands with pytest passthrough:

```python
@test_app.command(
    "all",
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False},
)
def all_tests(ctx: typer.Context) -> None:
    """Run unit and integration tests under xdist parallel execution."""
    sys.exit(
        _run_pytest(
            title="Full Test Suite (unit + integration, excludes E2E)",
            log_path=Path("test-all.log"),
            default_args=[
                "-m", "not e2e",
                "-n", _xdist_worker_count(),
                "--dist=worksteal",
                "--reruns", "3",
                "-v",
            ],
            extra_args=ctx.args,
        )
    )
```

**Note:** `_run_pytest` currently reads `sys.argv[1:]` for extra args (line 315). Refactor it to accept an `extra_args` parameter instead, passed from `ctx.args`. This eliminates `sys.argv` usage and satisfies AC2.3.

**Complexity reduction for `_stream_with_progress`:**

The current function has cognitive complexity 36 due to a 4-level conditional nesting inside a for loop within a try/finally. Extract two phase-handler functions:

1. `_handle_collecting_phase(line, count)` → Returns `(new_count, transition_to_running: bool)`. Encapsulates the collection parsing and count detection.

2. `_handle_running_phase(line, progress, task_id, total, done_count)` → Returns `(new_done_count, transition_to_summary: bool)`. Encapsulates result parsing, progress advancement, and summary boundary detection.

The refactored `_stream_with_progress` becomes a phase-dispatch loop:

```python
def _stream_with_progress(process, log_file) -> int:
    phase = "collecting"
    count = None
    done = 0
    # ... progress bar setup ...
    try:
        for raw_line in process.stdout:
            log_file.write(raw_line)
            stripped = raw_line.rstrip()
            if phase == "summary":
                console.print(stripped)
                continue
            if phase == "collecting":
                count, start_running = _handle_collecting_phase(stripped, count)
                if start_running:
                    phase = "running"
                    # create progress bar with count
                continue
            # phase == "running"
            done, enter_summary = _handle_running_phase(
                stripped, progress, task_id, count, done
            )
            if enter_summary:
                phase = "summary"
    finally:
        process.wait()
    return process.returncode
```

Target: cognitive complexity ≤ 10. Verify with `uv run complexipy src/promptgrimoire/cli/testing.py --max-complexity-allowed 15`.

**Testing:**

Tests must verify:
- cli-typer-211.AC4.2: `_stream_with_progress` complexity ≤ 15

**Verification:**

Run: `uv run complexipy src/promptgrimoire/cli/testing.py --max-complexity-allowed 15`
Expected: Zero failures.

Run: `uv run grimoire test all --help`
Expected: Shows help with description.

**Commit:** `feat: populate testing.py with typer commands and refactored streaming`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update test_cli_header.py Import

**Verifies:** cli-typer-211.AC5.1

**Files:**
- Modify: `tests/unit/test_cli_header.py`

**Implementation:**

Change the import at line 11:
```python
# From:
from promptgrimoire.cli import _build_test_header
# To:
from promptgrimoire.cli._shared import _build_test_header
```

**Testing:**

Tests must verify:
- cli-typer-211.AC5.1: All 11 test_cli_header tests pass with import from `promptgrimoire.cli._shared`

**Verification:**

Run: `uv run pytest tests/unit/test_cli_header.py -v`
Expected: All 11 tests pass.

**Commit:** `test: update test_cli_header.py import to cli._shared`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_4 -->
### Task 4: Remove Migrated Test Functions from cli_legacy.py

**Files:**
- Modify: `src/promptgrimoire/cli_legacy.py`
- Modify: `pyproject.toml`

**Implementation:**

1. In `pyproject.toml`, remove these entry points:
   - `test-changed = "promptgrimoire.cli_legacy:test_changed"`
   - `test-all = "promptgrimoire.cli_legacy:test_all"`
   - `test-all-fixtures = "promptgrimoire.cli_legacy:test_all_fixtures"`

2. In `cli_legacy.py`, delete ALL functions that were moved to `_shared.py` and `testing.py`:
   - `console = Console()` (line 30)
   - `_pre_test_db_cleanup` (lines 33-99)
   - `_build_test_header` (lines 102-130)
   - `_stream_plain` (lines 133-175)
   - Regex constants (lines 182-186)
   - `_parse_collection` (lines 189-199)
   - `_is_summary_boundary` (lines 202-204)
   - `_parse_result` (lines 207-218)
   - `_stream_with_progress` (lines 221-293)
   - `_run_pytest` (lines 296-380)
   - `test_changed` (lines 383-422)
   - `_xdist_worker_count` (lines 425-437)
   - `test_all` (lines 440-474)
   - `test_all_fixtures` (lines 477-496)

   **Do NOT delete** E2E-related functions (`_allocate_ports`, `_start_e2e_server`, `_stop_e2e_server`, etc.) — they move in Phase 5.

3. `docs.py` still imports `_start_e2e_server` and `_stop_e2e_server` from `cli_legacy` — these remain there until Phase 5.

4. Run `uv sync`.

**Verification:**

Run: `uv run grimoire test all`
Expected: All tests pass via new entry point.

**Commit:** `refactor: remove migrated test functions from cli_legacy`
<!-- END_TASK_4 -->

## UAT Steps

1. [ ] Run `uv run grimoire test all --help` — shows test command help
2. [ ] Run `uv run grimoire test changed --help` — shows changed test help
3. [ ] Run `uv run grimoire test all-fixtures --help` — shows fixtures help
4. [ ] Run `uv run complexipy src/promptgrimoire/cli/testing.py --max-complexity-allowed 15` — zero failures
5. [ ] Run `uv run pytest tests/unit/test_cli_header.py -v` — all 11 tests pass
6. [ ] Run `uv run grimoire test all` — full test suite passes

## Evidence Required

- [ ] complexipy output showing `_stream_with_progress` ≤ 15
- [ ] Test suite passing via new `grimoire test all` command
