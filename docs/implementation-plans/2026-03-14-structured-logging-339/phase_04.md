# Structured Logging Implementation Plan — Phase 4

**Goal:** Eliminate silent exception swallowing across all of `src/promptgrimoire/`. Every `except` block that catches a user-facing or operational error calls `log.exception()` or `log.warning()` as appropriate.

**Architecture:** Mechanical audit and fix. Two patterns: `log.exception()` for unexpected/catch-all exceptions, `log.warning()` for expected business logic exceptions (PermissionError, ValueError, etc.).

**Tech Stack:** structlog (already configured from Phase 1-2)

**Scope:** 7 phases from original design (phases 1-7)

**Codebase verified:** 2026-03-14

---

## Acceptance Criteria Coverage

This phase implements and tests:

### structured-logging-339.AC4: Exception handling consistency
- **structured-logging-339.AC4.1 Success:** Every `except` block in `src/promptgrimoire/pages/` that catches a user-facing error calls `log.exception()` before or alongside `ui.notify()`
- **structured-logging-339.AC4.2 Failure:** No `except` block silently swallows exceptions (catches without logging)

---

<!-- START_TASK_1 -->
### Task 1: Fix all silent exception swallowing in src/promptgrimoire/

**Verifies:** structured-logging-339.AC4.1, structured-logging-339.AC4.2

**Files:**
All files under `src/promptgrimoire/` with silent except blocks. The codebase investigation identified 30 violations in `pages/` plus additional violations in other modules. The full list (with file paths and line numbers) was captured during Phase 4B investigation.

Key files to modify (pages/):
- `src/promptgrimoire/pages/annotation/__init__.py` (line 358)
- `src/promptgrimoire/pages/annotation/document_management.py` (lines 313, 316)
- `src/promptgrimoire/pages/annotation/placement.py` (lines 110, 126, 252)
- `src/promptgrimoire/pages/annotation/sharing.py` (line 196)
- `src/promptgrimoire/pages/annotation/tag_import.py` (line 110)
- `src/promptgrimoire/pages/annotation/tag_management.py` (lines 400, 519)
- `src/promptgrimoire/pages/annotation/tag_management_rows.py` (line 421)
- `src/promptgrimoire/pages/annotation/tag_management_save.py` (lines 133, 136, 215, 218, 256)
- `src/promptgrimoire/pages/annotation/upload_handler.py` (line 152)
- `src/promptgrimoire/pages/courses.py` (lines 130, 314, 684, 692, 894, 1645)
- `src/promptgrimoire/pages/navigator/_cards.py` (lines 221, 358)
- `src/promptgrimoire/pages/navigator/_page.py` (line 137)
- `src/promptgrimoire/pages/roleplay.py` (lines 145, 327, 329)

**Implementation:**

Use ast-grep to find all except blocks across `src/promptgrimoire/` that lack a `logger.exception()`, `logger.error()`, `logger.warning()`, `log.exception()`, `log.error()`, or `log.warning()` call.

Apply two patterns based on exception type:

**Pattern A — Expected exceptions** (business logic signals):
For `except PermissionError`, `except ValueError`, `except DeletionBlockedError`, `except ProtectedDocumentError`, `except NotImplementedError`, `except EnrolmentParseError`, `except StudentIdConflictError`:

```python
# BEFORE:
except PermissionError:
    ui.notify("Permission denied", type="negative")

# AFTER:
except PermissionError:
    logger.warning("permission_denied", operation="delete_course")
    ui.notify("Permission denied", type="negative")
```

Use `log.warning()` (not `log.exception()`) — these are expected control flow, not bugs. No traceback needed.

**Pattern B — Unexpected exceptions** (catch-all, bugs):
For `except Exception`, `except Exception as e`, bare `except:`:

```python
# BEFORE:
except Exception as e:
    ui.notify(f"Error: {e}", type="negative")

# AFTER:
except Exception as e:
    logger.exception("unexpected_error", operation="stream_response")
    ui.notify(f"Error: {e}", type="negative")
```

Use `log.exception()` — includes full traceback. These indicate bugs or infrastructure failures.

**Also scan non-pages/ code:** Verify that except blocks in `db/`, `export/`, `crdt/`, `auth/`, `llm/`, `input_pipeline/` have appropriate logging. The investigation found workers already use `logger.exception()` correctly. Fix any gaps.

**Exclude:** `cli/` (CLI tools handle errors differently — they print to terminal).

**Verification:**

Run: `uv run ruff check src/promptgrimoire/ && uvx ty check`
Expected: No lint or type errors

Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `fix: add logging to all silent exception handlers`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Guard test for silent exception swallowing

**Verifies:** structured-logging-339.AC4.2

**Files:**
- Create: `tests/unit/test_exception_logging_guard.py`

**Implementation:**

Create an AST-scanning guard test (same pattern as `test_async_fixture_safety.py` and the print guard from Phase 2) that scans all `.py` files under `src/promptgrimoire/` (excluding `cli/`) for except blocks that lack a logging call.

The test should:
1. Parse each `.py` file with `ast.parse()`
2. Walk the AST to find `ast.ExceptHandler` nodes
3. For each except handler, check if the handler body contains a call to any of:
   - `logger.exception()`, `logger.error()`, `logger.warning()`
   - `log.exception()`, `log.error()`, `log.warning()`
   - `logging.exception()`, `logging.error()`, `logging.warning()`
4. If no logging call is found, record a violation with file path and line number

**Exceptions to the guard:**
- `except` blocks that only `raise` (re-raising is not swallowing)
- `except` blocks in `cli/` (CLI tools use print for terminal output)
- `except` blocks that call `continue` in a retry loop (if the retry itself is logged)

**Testing:**

- structured-logging-339.AC4.2: The guard test itself IS the verification. If it passes, no except block silently swallows exceptions.

Follow project testing patterns. Task-implementor generates actual test code at execution time.

**Verification:**

Run: `uv run grimoire test run tests/unit/test_exception_logging_guard.py`
Expected: Test passes (no violations)

**Commit:** `test: add exception logging guard test`

<!-- END_TASK_2 -->

## UAT Steps

1. Start the app: `uv run run.py`
2. Try an operation that triggers an expected error (e.g. delete a course with workspaces) — check logs for `log.warning()` entry (no traceback)
3. Try an operation that triggers an unexpected error — check logs for `log.exception()` entry with full traceback
4. Run: `uv run grimoire test run tests/unit/test_exception_logging_guard.py` — should pass
5. Run: `uv run complexipy src/promptgrimoire/pages/ --max-complexity-allowed 15` — verify no new violations from added logging calls
