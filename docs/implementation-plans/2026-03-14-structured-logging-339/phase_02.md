# Structured Logging Implementation Plan — Phase 2

**Goal:** Mechanically rewrite all modules from stdlib logging to structlog, set per-module log levels, add print guard test.

**Architecture:** ast-grep (`sg`) structural rewrites for safe mechanical migration. Guard test follows existing AST-scanning pattern from `test_async_fixture_safety.py`.

**Tech Stack:** ast-grep (sg CLI), structlog, AST-based guard test

**Scope:** 7 phases from original design (phases 1-7)

**Codebase verified:** 2026-03-14

---

## Acceptance Criteria Coverage

This phase implements and tests:

### structured-logging-339.AC2: Module migration and print guard
- **structured-logging-339.AC2.1 Success:** All modules in `src/promptgrimoire/` use `structlog.get_logger()` with explicit log level set
- **structured-logging-339.AC2.2 Success:** Guard test fails if a `print()` call is added to any `.py` file under `src/promptgrimoire/`
- **structured-logging-339.AC2.3 Success:** Existing stdlib `logging.getLogger()` calls from third-party libraries (NiceGUI, SQLAlchemy) produce JSON output through ProcessorFormatter
- **structured-logging-339.AC2.4 Failure:** Guard test produces clear error message identifying file and line number of offending `print()`

---

<!-- START_TASK_1 -->
### Task 1: Convert print() calls in __init__.py to logger calls

**Files:**
- Modify: `src/promptgrimoire/__init__.py` (lines 109, 116, 137, 156, 157)

**Implementation:**

Replace the 5 `print()` calls in `main()` with structlog logger calls. These are startup messages that should use the structured logger now that Phase 1 has configured it.

Get a structlog logger at module level: `log = structlog.get_logger()`

Convert each print to an appropriate log call:
- `print("Created database — seeding development data...")` → `log.info("database_created", action="seeding development data")`
- `print(f"Branch: {branch} | Database: {db_name}")` → `log.info("branch_config", branch=branch, database=db_name)`
- `print("Database connected")` → `log.info("database_connected")`
- `print(f"PromptGrimoire v{get_version_string()}")` → `log.info("app_starting", version=get_version_string())`
- `print(f"Starting application on http://0.0.0.0:{port}")` → `log.info("app_starting", host="0.0.0.0", port=port)`

Keep `import logging` and `from logging.handlers import RotatingFileHandler` in `__init__.py` — these are needed by `_setup_logging()` itself. Add `import structlog` for the module-level logger.

**Verification:**

Run: `uv run ruff check src/promptgrimoire/__init__.py && uvx ty check`
Expected: No lint or type errors

Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `refactor: replace print() with structured log calls in __init__.py`

<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-3) -->
<!-- START_TASK_2 -->
### Task 2: Mechanical ast-grep migration of all modules

**Verifies:** structured-logging-339.AC2.1

**Files:**
- Modify: 46 `.py` files under `src/promptgrimoire/` (see investigation report for full list)

**Implementation:**

Use `sg` (ast-grep CLI) for structural rewrites. This is a mechanical migration — do NOT do manual read/write across 46 files.

**Step 1: Replace `import logging` with `import structlog`**

Use ast-grep to find files that import `logging` only for `getLogger`:

```bash
# Find all files with `import logging` under src/promptgrimoire/
sg --pattern 'import logging' --lang python src/promptgrimoire/ --json | jq -r '.[].file'
```

For each file (except `__init__.py` which keeps `import logging` for RotatingFileHandler):

```bash
# Replace import logging with import structlog
sg --pattern 'import logging' --rewrite 'import structlog' --lang python src/promptgrimoire/<file>.py
```

**IMPORTANT:** `__init__.py` must keep `import logging` because `_setup_logging()` uses stdlib logging directly. Add `import structlog` alongside it instead.

**Step 2: Replace `logger = logging.getLogger(__name__)` with `logger = structlog.get_logger()`**

```bash
# Pattern: logger = logging.getLogger(__name__)
sg --pattern 'logger = logging.getLogger(__name__)' --rewrite 'logger = structlog.get_logger()' --lang python src/promptgrimoire/
```

Keep the variable name `logger` (not `log`) to minimise diff noise — structlog works fine with any variable name. **Design deviation:** The design document specifies `log` as the target name, but renaming across 46 files creates a large cosmetic diff. This is an intentional decision. Phase 4's exception logging guard test covers both `log.exception()` and `logger.exception()` patterns. Note that `__init__.py` (Phase 2 Task 1) uses `log` for the new structlog logger while existing files keep `logger`.

**Step 3: Handle special cases manually (3 files)**

These cannot be handled by the blanket ast-grep rule:

1. **`src/promptgrimoire/db/engine.py`** — Has two loggers:
   - `logger = logging.getLogger(__name__)` → `logger = structlog.get_logger()`
   - `_pool_logger = logging.getLogger(f"{__name__}.pool")` → `_pool_logger = structlog.get_logger(f"{__name__}.pool")`

2. **`src/promptgrimoire/db/wargames.py`** — Uses `_logger`:
   - `_logger = logging.getLogger(__name__)` → `_logger = structlog.get_logger()`

3. **`src/promptgrimoire/cli/e2e/_server_script.py`** — Has 3 named loggers:
   - `_watchdog_logger = logging.getLogger("grimoire.e2e.watchdog")` → `_watchdog_logger = structlog.get_logger("grimoire.e2e.watchdog")`
   - Same pattern for `_cleanup_logger` and `_delete_logger`

4. **`src/promptgrimoire/pages/courses.py`** — Has duplicate logger declarations (lines 75, 101). Investigate whether both are needed. If the second is dead code, remove it.

**Step 4: Set per-module log levels**

After the import migration, add explicit log level settings. Use `logging.getLogger(__name__).setLevel()` (stdlib level setting works with structlog via ProcessorFormatter):

```python
import logging
import structlog

logger = structlog.get_logger()
logging.getLogger(__name__).setLevel(logging.WARNING)  # for DB/CRDT modules
```

Module level assignments per design:

| Module category | Files | Level |
|----------------|-------|-------|
| Background workers | `deadline_worker.py`, `search_worker.py` | INFO |
| Export pipeline | `export/*.py`, `word_count.py` | INFO |
| CRDT sync | `crdt/*.py` | WARNING |
| Auth | `auth/client.py`, `pages/auth.py` | INFO |
| Pages/UI | `pages/**/*.py` | INFO |
| Database | `db/engine.py`, `db/tags.py`, `db/wargames.py` | WARNING |

For modules set to WARNING, add `import logging` back alongside `import structlog` for the `setLevel()` call.

**Verification of AC2.1 (explicit log level):** After migration, use ast-grep to verify every migrated file has a `setLevel()` call. PR reviewer should spot-check 3-5 migrated files to confirm levels match the module category table above.

**Step 5: Verify no remaining stdlib logging usage**

```bash
# Should return only __init__.py AND files that re-import logging for setLevel() (Step 4)
# Files importing logging alongside structlog for setLevel() are expected — not migration gaps
sg --pattern 'logging.getLogger($$$)' --lang python src/promptgrimoire/
```

**Verification:**

Run: `uv run ruff check src/promptgrimoire/ && uvx ty check`
Expected: No lint or type errors

Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `feat: migrate all modules from stdlib logging to structlog`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Print guard test

**Verifies:** structured-logging-339.AC2.2, structured-logging-339.AC2.4

**Files:**
- Create: `tests/unit/test_print_usage_guard.py`

**Implementation:**

Create a guard test following the pattern in `tests/unit/test_async_fixture_safety.py`. The test scans all `.py` files under `src/promptgrimoire/` for bare `print()` calls.

Key requirements:
- Scan `src/promptgrimoire/` recursively for `.py` files
- **Exclude** `src/promptgrimoire/cli/` — CLI tools legitimately use `print()` for terminal output (test harness passthrough, docs build output)
- Skip `__pycache__` directories
- Use `ast.parse()` and `ast.walk()` to find `ast.Call` nodes where:
  - `func` is an `ast.Name` with `id == "print"` (bare `print()`)
  - NOT `ast.Attribute` (i.e. not `sys.stdout.write()` or similar)
- Collect violations as `f"{relative_path}:{node.lineno} — print() call; use structlog logger instead"`
- Assert no violations with a clear multiline error message

**Testing:**

- structured-logging-339.AC2.2: The test itself IS the verification — it should pass with no violations after Task 1 converts the `__init__.py` print calls
- structured-logging-339.AC2.4: Verify the error message format includes file path and line number by temporarily adding a `print()` to a source file, running the test, checking the output, then removing it

Follow project testing patterns. Task-implementor generates actual test code at execution time.

**Verification:**

Run: `uv run grimoire test run tests/unit/test_print_usage_guard.py`
Expected: Test passes (no print() violations in src/promptgrimoire/ excluding cli/)

**Commit:** `test: add print() usage guard test`

<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_4 -->
### Task 4: Verify third-party library JSON output

**Verifies:** structured-logging-339.AC2.3

**Files:**
- Test: `tests/unit/test_structured_logging.py` (add to existing test file from Phase 1)

**Implementation:**

Add a test that verifies third-party library log calls (e.g. from NiceGUI, SQLAlchemy) produce JSON output through ProcessorFormatter. The test should:

1. Configure `_setup_logging()` with a temp directory
2. Get a stdlib logger that simulates a third-party library: `logging.getLogger("nicegui.helpers")`
3. Call `stdlib_logger.warning("third party message")`
4. Read the log file and parse the output line as JSON
5. Assert it has the same structure as structlog-originated events (`level`, `timestamp`, `event`, `pid`, `branch`, `commit`)

This verifies that ProcessorFormatter's `foreign_pre_chain` correctly processes non-structlog log events.

**Testing:**

- structured-logging-339.AC2.3: Test that a stdlib logger (simulating third-party code) produces JSON output with standard fields

Follow project testing patterns. Task-implementor generates actual test code at execution time.

**Verification:**

Run: `uv run grimoire test run tests/unit/test_structured_logging.py`
Expected: All tests pass

**Commit:** `test: verify third-party library JSON output via ProcessorFormatter`

<!-- END_TASK_4 -->

## UAT Steps

1. Run: `grep -r "logging.getLogger" src/promptgrimoire/ --include="*.py" | grep -v __init__.py | grep -v __pycache__` — should return zero results (all migrated)
2. Run: `grep -r "import logging" src/promptgrimoire/ --include="*.py" | grep -v __init__.py | grep -v __pycache__` — only files with explicit `setLevel()` should import logging alongside structlog
3. Run: `uv run grimoire test run tests/unit/test_print_usage_guard.py` — should pass
4. Add a `print("test")` line to `src/promptgrimoire/pages/courses.py`, run the guard test — should fail with clear error. Remove the test line.
5. Start the app: `uv run run.py` — verify console output is human-readable (ConsoleRenderer) and log file is JSON (JSONRenderer)
6. Run: `uv run complexipy src/promptgrimoire/ --max-complexity-allowed 15` — verify no new violations
