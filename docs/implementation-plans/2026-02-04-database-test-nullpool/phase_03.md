# Database Test NullPool Migration - Phase 3

**Goal:** Remove xdist_group clustering from workspace tests.

**Architecture:** Workspace tests use service layer functions (e.g., `create_workspace()`) which manage their own sessions via `get_session()`. With `reset_db_engine_per_test` disposing the engine after each test, and xdist workers being separate processes, the xdist_group marker is no longer needed.

**Tech Stack:** pytest-xdist, SQLAlchemy asyncio

**Scope:** Phase 3 of 7

**Codebase verified:** 2026-02-04

---

## Context: Why This Works

xdist workers are separate processes with isolated memory. Each worker has its own:
- Python interpreter
- Module-level `_state` variable in `engine.py`
- Event loops for tests

Within a single worker, tests run sequentially. The `reset_db_engine_per_test` fixture disposes the engine after each test, ensuring each test gets a fresh engine in its own event loop.

The `xdist_group("db_integration")` marker was defensive clustering that is no longer needed.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Remove xdist_group from test_workspace_crud.py

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool/tests/integration/test_workspace_crud.py:16-22`

**Step 1: Remove xdist_group marker**

Change the `pytestmark` from:

```python
pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("TEST_DATABASE_URL"),
        reason="TEST_DATABASE_URL not set - skipping database integration tests",
    ),
    pytest.mark.xdist_group("db_integration"),
]
```

To:

```python
pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set - skipping database integration tests",
)
```

Note: With single marker, we don't need a list.

**Step 2: Verify tests still pass locally**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run pytest tests/integration/test_workspace_crud.py -v
```

Expected: All tests pass

**Step 3: Commit**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && git add tests/integration/test_workspace_crud.py && git commit -m "$(cat <<'EOF'
refactor(tests): remove xdist_group from test_workspace_crud

With reset_db_engine_per_test disposing engine after each test, and
xdist workers being separate processes, clustering is no longer needed.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Remove xdist_group from test_workspace_persistence.py

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool/tests/integration/test_workspace_persistence.py:16-22`

**Step 1: Remove xdist_group marker**

Change the `pytestmark` from:

```python
pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("TEST_DATABASE_URL"),
        reason="TEST_DATABASE_URL not set - skipping database integration tests",
    ),
    pytest.mark.xdist_group("db_integration"),
]
```

To:

```python
pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set - skipping database integration tests",
)
```

**Step 2: Verify tests still pass locally**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run pytest tests/integration/test_workspace_persistence.py -v
```

Expected: All tests pass

**Step 3: Commit**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && git add tests/integration/test_workspace_persistence.py && git commit -m "$(cat <<'EOF'
refactor(tests): remove xdist_group from test_workspace_persistence

With reset_db_engine_per_test disposing engine after each test, and
xdist workers being separate processes, clustering is no longer needed.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

---

<!-- START_TASK_3 -->
### Task 3: Verify xdist parallelism works for workspace tests

**Files:** No changes - verification only

**Step 1: Run workspace tests with xdist**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run pytest tests/integration/test_workspace_crud.py tests/integration/test_workspace_persistence.py -n 4 -v 2>&1 | head -50
```

Expected: Tests pass, no "Future attached to different loop" errors

**Step 2: Verify tests distributed**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run pytest tests/integration/test_workspace_crud.py tests/integration/test_workspace_persistence.py -n 4 -v 2>&1 | grep -E "^\[gw" | head -20
```

Expected: Tests running on multiple workers (gw0, gw1, gw2, gw3)

Note: Some variance in distribution is normal (e.g., 5/4/3/2 across workers). The key check is that tests are NOT all on a single worker (gw0), which would indicate xdist_group is still active.

<!-- END_TASK_3 -->

---

## Phase 3 Verification

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run pytest tests/integration/test_workspace_*.py -n 4 -v && echo "Phase 3 complete"
```

Expected: Tests pass distributed across workers, "Phase 3 complete" printed
