# Business Exception Handling Implementation Plan — Phase 2

**Goal:** Add `BusinessLogicError` catch clause to `get_session()` with WARNING-level logging and `exc_class` structured field.

**Architecture:** New `except BusinessLogicError` clause before the generic `except Exception` in `get_session()`. Both branches roll back and re-raise. Business exceptions log at WARNING (no Discord), unexpected exceptions log at ERROR (Discord fires).

**Tech Stack:** Python 3.14, structlog, pytest

**Scope:** 4 phases from original design (phases 1-4). This is Phase 2.

**Codebase verified:** 2026-03-16

---

## Acceptance Criteria Coverage

This phase implements and tests:

### business-exception-handling-363.AC2: get_session() Exception Triage
- **business-exception-handling-363.AC2.1 Success:** `BusinessLogicError` raised inside `get_session()` → transaction rolled back, `logger.warning()` called (NOT `logger.exception()`), exception re-raised to caller
- **business-exception-handling-363.AC2.2 Success:** Unexpected `Exception` raised inside `get_session()` → transaction rolled back, `logger.exception()` (ERROR) called, exception re-raised to caller
- **business-exception-handling-363.AC2.3 Success:** Business-exception branch uses a distinct event name (NOT "Database session error, rolling back transaction")
- **business-exception-handling-363.AC2.4 Success:** Both branches include `exc_class` field in structured log output
- **business-exception-handling-363.AC2.5 Failure:** `BusinessLogicError` does NOT trigger Discord webhook (WARNING level, not ERROR)
- **business-exception-handling-363.AC2.6 Integration:** `grant_share(..., sharing_allowed=False)` raises `SharePermissionError` and does NOT produce "Database session error" log event
- **business-exception-handling-363.AC2.7 Integration:** `delete_workspace()` by non-owner raises `OwnershipError` and does NOT produce "Database session error" log event

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Modify get_session() exception handling

**Verifies:** business-exception-handling-363.AC2.1, business-exception-handling-363.AC2.2, business-exception-handling-363.AC2.3, business-exception-handling-363.AC2.4

**Files:**
- Modify: `src/promptgrimoire/db/engine.py` — lines 296-302 (the try/except block inside `get_session()`)

**Implementation:**

Add import at top of `engine.py`:
```python
from promptgrimoire.db.exceptions import BusinessLogicError
```

Replace the current exception handling block (lines 296-302):

```python
# CURRENT:
        try:
            yield session
            await session.commit()
        except Exception:
            logger.exception("Database session error, rolling back transaction")
            await session.rollback()
            raise
```

With:

```python
        try:
            yield session
            await session.commit()
        except BusinessLogicError as exc:
            logger.warning(
                "Business logic error, rolling back transaction",
                exc_class=type(exc).__name__,
            )
            await session.rollback()
            raise
        except Exception as exc:
            logger.exception(
                "Database session error, rolling back transaction",
                exc_class=type(exc).__name__,
            )
            await session.rollback()
            raise
```

Key differences:
- `BusinessLogicError` branch uses `logger.warning()` (no traceback, WARNING level → no Discord)
- Generic `Exception` branch uses `logger.exception()` (includes traceback, ERROR level → Discord fires)
- Both branches include `exc_class=type(exc).__name__` for structured log filtering
- Both branches roll back and re-raise

**Verification:**

```bash
uv run python -c "
import ast, inspect
# Verify the file parses correctly
with open('src/promptgrimoire/db/engine.py') as f:
    ast.parse(f.read())
print('engine.py parses successfully')
"
```

**Commit:** `feat: add BusinessLogicError triage to get_session() exception handling`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Unit tests for get_session() exception triage

**Verifies:** business-exception-handling-363.AC2.1, business-exception-handling-363.AC2.2, business-exception-handling-363.AC2.3, business-exception-handling-363.AC2.4, business-exception-handling-363.AC2.5

**Files:**
- Modify: `tests/unit/test_db_engine.py` — add new test methods to existing TestGetSession class (verified: file exists at `tests/unit/test_db_engine.py` with `TestGetSession` class at lines 23-61)

**Testing:**

The file `tests/unit/test_db_engine.py` already exists with a `TestGetSession` class using mock session factory pattern via `_state.session_factory`. Add tests to this existing class:

Tests must verify:
- business-exception-handling-363.AC2.1: `BusinessLogicError` inside get_session() → rollback called, `logger.warning()` called (not `logger.exception()`), exception re-raised
- business-exception-handling-363.AC2.2: Generic `Exception` inside get_session() → rollback called, `logger.exception()` called, exception re-raised
- business-exception-handling-363.AC2.3: Business branch uses event "Business logic error, rolling back transaction", NOT "Database session error, rolling back transaction"
- business-exception-handling-363.AC2.4: Both branches include `exc_class` in structured log output — mock the logger and check kwargs
- business-exception-handling-363.AC2.5: Business branch logs at WARNING (confirm `logger.warning` called, not `logger.exception` or `logger.error`)

Test strategy: Patch `promptgrimoire.db.engine.logger` to capture log calls. Create a mock session factory that yields a mock session. Raise the appropriate exception type inside the `async with get_session()` block.

**Verification:**

```bash
uv run grimoire test run tests/unit/test_db_engine.py
uv run grimoire test all
```

**Commit:** `test: add get_session() BusinessLogicError triage tests`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Integration tests for exception triage (AC2.6, AC2.7)

**Verifies:** business-exception-handling-363.AC2.6, business-exception-handling-363.AC2.7

**Files:**
- Create: `tests/integration/test_business_exception_triage.py` — cross-cutting concern (get_session triage), not sharing-specific

**Testing:**

These are integration tests that verify end-to-end: a real DB operation raises the correct exception subclass and produces the correct log event (WARNING "Business logic error", NOT ERROR "Database session error").

Tests must verify:
- business-exception-handling-363.AC2.6: Call `grant_share()` with `sharing_allowed=False` for a non-staff user → raises `SharePermissionError` → log output contains "Business logic error" at WARNING level, does NOT contain "Database session error"
- business-exception-handling-363.AC2.7: Call `delete_workspace()` with a non-owner `user_id` → raises `OwnershipError` → log output contains "Business logic error" at WARNING level, does NOT contain "Database session error"

Follow existing integration test pattern from `test_sharing_controls.py` (create user, create workspace, grant permission, then test rejection). Use `caplog` or `capsys` to verify log output.

**Verification:**

```bash
uv run grimoire test run tests/integration/test_business_exception_triage.py
uv run grimoire test all
```

**Commit:** `test: add integration tests for BusinessLogicError triage in get_session()`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Run complexipy on modified files

**Files:** None (diagnostic only)

**Verification:**

```bash
uv run complexipy src/promptgrimoire/db/engine.py --max-complexity-allowed 15
```

If `get_session()` now exceeds complexity 15 due to the additional except clause, refactor by extracting the exception handling into a helper. Note: adding one more except clause to a try block typically adds ~1-2 complexity points, unlikely to breach 15.

No commit needed for this task.
<!-- END_TASK_4 -->

## UAT Steps

1. [ ] Start the app: `uv run run.py`
2. [ ] Log in as a non-staff user who owns a workspace with sharing disabled (`allow_sharing=False`)
3. [ ] Attempt to share the workspace via the API or UI
4. [ ] Verify: The operation fails with a permission error (expected business logic rejection)
5. [ ] Check structured logs: `journalctl -u promptgrimoire --since "5 min ago" -o cat | jq 'select(.event == "Business logic error, rolling back transaction")'`
6. [ ] Verify: Log entry exists at WARNING level with `exc_class=SharePermissionError`
7. [ ] Verify: No Discord webhook alert fired for this event
8. [ ] Check: `journalctl -u promptgrimoire --since "5 min ago" -o cat | jq 'select(.event == "Database session error, rolling back transaction")'`
9. [ ] Verify: No "Database session error" entry for the business logic rejection

## Evidence Required
- [ ] Test output showing green (`uv run grimoire test all`)
- [ ] Log output showing WARNING-level "Business logic error" (not ERROR)
- [ ] Discord channel showing no alert for the business logic rejection
