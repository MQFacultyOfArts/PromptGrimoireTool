# Query Optimisation and Graceful Restart — Phase 2

**Goal:** Prevent reintroduction of redundant queries with measurable regression guards using SQLAlchemy engine event instrumentation.

**Architecture:** A reusable query-counting context manager wraps `before_cursor_execute` event registration. Four tests exercise it: two pass (proving Phase 1 optimisation), two xfail (documenting #377 regressions as known debt).

**Tech Stack:** SQLAlchemy `event.listen()` / `event.remove()` on `sync_engine`, pytest xfail markers

**Scope:** Phase 2 of 6 from original design

**Codebase verified:** 2026-03-26

---

## Acceptance Criteria Coverage

This phase tests (regression guards for):

### query-optimisation-and-graceful-restart-186.AC1: Query optimisation
- **query-optimisation-and-graceful-restart-186.AC1.1 Success:** `list_document_headers()` returns documents with all metadata columns; no `content` column transferred
- **query-optimisation-and-graceful-restart-186.AC1.3 Failure:** Accessing `.content` on a headers-only object raises `DetachedInstanceError`

---

## Implementation Tasks

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create reusable query-counting context manager

**Verifies:** None (infrastructure for testing)

**Files:**
- Create: `tests/integration/test_query_efficiency.py`

**Implementation:**

Create a context manager that counts SQL statements executed against the engine. Follow the existing pattern from `tests/integration/test_clone_idempotency.py:273-309` but extract it for reuse.

The context manager should:
- Accept `sync_engine` from `_state.engine.sync_engine` (after engine is initialised)
- Register `before_cursor_execute` listener on enter
- Expose a `.count` property
- Remove listener on exit (even on exception)

Include the standard integration test skip guard:
```python
pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set - skipping database integration tests",
)
```

Reference the existing pattern at `tests/integration/test_clone_idempotency.py:273-309` for how `sync_engine` is obtained and events are registered.

**Verification:**
Run: `uvx ty@0.0.24 check`
Expected: No type errors

**Commit:** (combined with Task 2)
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Query efficiency regression tests

**Verifies:** query-optimisation-and-graceful-restart-186.AC1.1, query-optimisation-and-graceful-restart-186.AC1.3

**Files:**
- Modify: `tests/integration/test_query_efficiency.py` (add test classes)

**Testing:**

Four tests in the same file, organised as two classes:

**Class `TestDocumentHeadersEfficiency`:**
- **Test: headers exclude content** — Create a workspace with 3 documents with known content. Call `list_document_headers()`. Verify all metadata fields are accessible. Verify accessing `.content` raises `DetachedInstanceError`. This duplicates Phase 1's test_document_headers.py but verifies at the query level. (Verifies AC1.1, AC1.3)
- **Test: page load document query count** — Create a workspace with 3 documents. Use the query counter to measure queries during `list_document_headers()`. Assert query count is exactly 1 (single SELECT). This guards against future N+1 regressions. (Verifies AC1.1)

**Class `TestKnownQueryRegressions`:**
- **Test: workspace fetch count** — `@pytest.mark.xfail(reason="#377 Phase 1: workspace fetched multiple times per page load", strict=True)`. Count queries during a representative workspace load sequence. Assert count ≤ expected threshold. The xfail documents that the current count exceeds the threshold.
- **Test: placement context query count** — `@pytest.mark.xfail(reason="#377 Phase 1: placement context re-queried per component", strict=True)`. Count queries during `get_placement_context()`. Assert count ≤ expected threshold.

For the xfail tests: the implementor should first run WITHOUT xfail to determine the actual query counts, then set thresholds at the desired (lower) values and add the xfail marker. The xfail documents the gap between actual and desired.

Follow integration test patterns: class-based, `@pytest.mark.asyncio`, UUID isolation, imports inside test body.

Reference: `tests/integration/test_clone_idempotency.py` for the query counting approach. `src/promptgrimoire/db/workspaces.py:266` for `get_placement_context()`.

**Verification:**
Run: `uv run grimoire test run tests/integration/test_query_efficiency.py`
Expected: 2 passed, 2 xfailed

**Commit:** `test: add query efficiency regression tests (#186, #432, #377)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

---

## Complexipy Check

After completing this phase, run:
```bash
uv run complexipy tests/integration/test_query_efficiency.py --max-complexity-allowed 15
```

## UAT Steps

1. [ ] Run: `uv run grimoire test run tests/integration/test_query_efficiency.py`
2. [ ] Verify: 2 tests pass (document headers efficiency)
3. [ ] Verify: 2 tests xfail (known #377 regressions)
4. [ ] Verify: no test errors (only pass/xfail)

## Evidence Required
- [ ] Test output showing 2 passed, 2 xfailed
- [ ] Query counter fixture is reusable (used in 4 tests without duplication)
