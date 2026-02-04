# Database Test NullPool Migration - Phase 4

**Goal:** Remove xdist_group clustering from course service tests.

**Architecture:** Same as Phase 3 - service layer tests work without xdist_group because `reset_db_engine_per_test` disposes engine after each test and xdist workers are separate processes.

**Tech Stack:** pytest-xdist, SQLAlchemy asyncio

**Scope:** Phase 4 of 7

**Codebase verified:** 2026-02-04

**Spike validated:** 2026-02-04 - test_course_service with marker removed passed 22 tests with `-n 4`

---

<!-- START_TASK_1 -->
### Task 1: Remove xdist_group from test_course_service.py

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool/tests/integration/test_course_service.py:19-25`

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
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run pytest tests/integration/test_course_service.py -v
```

Expected: All 22 tests pass

**Step 3: Commit**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && git add tests/integration/test_course_service.py && git commit -m "$(cat <<'EOF'
refactor(tests): remove xdist_group from test_course_service

With reset_db_engine_per_test disposing engine after each test, and
xdist workers being separate processes, clustering is no longer needed.

Spike validated: 22 tests pass with -n 4 without marker.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_1 -->

---

<!-- START_TASK_2 -->
### Task 2: Verify xdist parallelism works

**Files:** No changes - verification only

**Step 1: Run course service tests with xdist**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run pytest tests/integration/test_course_service.py -n 4 -v 2>&1 | head -30
```

Expected: Tests pass, no "Future attached to different loop" errors

Note: Some variance in worker distribution is normal. The key check is that tests are NOT all on a single worker.

<!-- END_TASK_2 -->

---

## Phase 4 Verification

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run pytest tests/integration/test_course_service.py -n 4 -v && echo "Phase 4 complete"
```

Expected: 22 tests pass distributed across workers, "Phase 4 complete" printed
