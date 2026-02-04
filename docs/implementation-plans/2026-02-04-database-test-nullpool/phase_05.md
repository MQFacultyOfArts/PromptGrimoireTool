# Database Test NullPool Migration - Phase 5

**Goal:** Document fixture responsibilities (REVISED from original design)

**Architecture:** Spike testing proved `reset_db_engine_per_test` is REQUIRED for service layer tests. This phase documents the fixture's role rather than removing it.

**Tech Stack:** pytest, SQLAlchemy asyncio

**Scope:** Phase 5 of 7

**Codebase verified:** 2026-02-04

---

## Design Revision Note

**Original design said:** "Remove `reset_db_engine_per_test` fixture"

**Spike proved:** Removing fixture causes 6/14 tests to fail with `RuntimeError: Event loop is closed`

**Root cause:** Service layer tests use shared engine with QueuePool. Pooled connections bind to event loops. Without disposal between tests, stale connections from Test A's closed loop are reused in Test B.

**Revised approach:** Keep `reset_db_engine_per_test`, add documentation explaining its purpose.

---

<!-- START_TASK_1 -->
### Task 1: Update fixture docstring to clarify its ongoing necessity

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool/tests/integration/conftest.py:17-29`

**Step 1: Update docstring**

Change the docstring from:

```python
@pytest.fixture(autouse=True)
async def reset_db_engine_per_test() -> AsyncGenerator[None]:
    """Reset database engine after each async integration test.

    With function-scoped event loops, the async engine is bound to the
    test's event loop. After the test finishes and its loop closes,
    subsequent tests would fail trying to use the stale engine.

    This fixture ensures the engine is disposed after each test,
    allowing the next test to lazily create a fresh engine in its
    own event loop.

    Only runs cleanup if the engine was actually initialized during the test.
    """
```

To:

```python
@pytest.fixture(autouse=True)
async def reset_db_engine_per_test() -> AsyncGenerator[None]:
    """Dispose shared database engine after each test.

    REQUIRED for service layer tests that use get_session() from the shared
    engine module. The shared engine uses QueuePool, and pooled connections
    bind to the event loop that created them.

    Without this fixture:
    - Test A creates engine/connections bound to its event loop
    - Test A finishes, its event loop closes
    - Test B tries to reuse pooled connections → RuntimeError: Event loop is closed

    This fixture disposes the engine (closing all pooled connections) after
    each test. The next test lazily creates a fresh engine in its own loop.

    Note: Tests using the db_session fixture (NullPool) don't need this,
    but it doesn't hurt them either. Service layer tests REQUIRE it.
    """
```

**Step 2: Verify tests still pass**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run pytest tests/integration/test_workspace_crud.py -n 4 --tb=short
```

Expected: All tests pass

**Step 3: Commit**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && git add tests/integration/conftest.py && git commit -m "$(cat <<'EOF'
docs(tests): clarify reset_db_engine_per_test necessity

Spike testing proved this fixture is REQUIRED for service layer tests.
Updated docstring explains why: pooled connections bind to event loops,
and without disposal, stale connections cause RuntimeError.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_1 -->

---

## Phase 5 Verification

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run pytest tests/integration/ -n 4 --tb=short && echo "Phase 5 complete"
```

Expected: All integration tests pass, "Phase 5 complete" printed

## Spike Evidence

Removing `reset_db_engine_per_test` caused:
```
6 failed, 8 passed
RuntimeError: Event loop is closed
```

Tests that failed were ones where a second test in the same worker tried to reuse pooled connections from a previous test's closed event loop.
