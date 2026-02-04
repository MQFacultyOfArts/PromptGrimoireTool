# Database Test NullPool Migration - Phase 6

**Goal:** Confirm all DB tests distribute across xdist workers.

**Architecture:** Verification phase - no code changes. Confirms the migration achieved its goal: DB tests run in parallel without `xdist_group` clustering.

**Tech Stack:** pytest-xdist

**Scope:** Phase 6 of 7

**Codebase verified:** 2026-02-04

---

<!-- START_TASK_1 -->
### Task 1: Run full test suite

**Files:** No changes - verification only

**Step 1: Run test-all**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run test-all
```

Expected: All tests pass

**Step 2: Note any failures**

If failures occur, investigate whether they're related to the NullPool migration or pre-existing issues.

<!-- END_TASK_1 -->

---

<!-- START_TASK_2 -->
### Task 2: Verify DB tests distribute across workers

**Files:** No changes - verification only

**Step 1: Run DB integration tests with xdist and capture worker distribution**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/database-test-nullpool && uv run pytest tests/integration/test_db_async.py tests/integration/test_workspace_*.py tests/integration/test_course_service.py -n 4 -v 2>&1 | tee /tmp/xdist_output.txt
```

**Step 2: Verify tests ran on multiple workers**

Run:
```bash
grep -E "^\[gw[0-3]\]" /tmp/xdist_output.txt | cut -d']' -f1 | sort | uniq -c
```

Expected: Output shows tests distributed across gw0, gw1, gw2, gw3 (not all on one worker)

Example good output:
```
     12 [gw0
     11 [gw1
     10 [gw2
      9 [gw3
```

Example bad output (all on one worker - would indicate xdist_group still present):
```
     42 [gw0
```

**Step 3: Verify no event loop errors**

Run:
```bash
grep -i "event loop" /tmp/xdist_output.txt || echo "No event loop errors found"
```

Expected: "No event loop errors found"

<!-- END_TASK_2 -->

---

<!-- START_TASK_3 -->
### Task 3: Document results

**Files:** No changes - documentation only

**Step 1: Record verification results**

After successful verification, note:
- Total tests run
- Distribution across workers
- Any unexpected findings

**Step 2: Clean up temporary files**

```bash
rm /tmp/xdist_output.txt
```

<!-- END_TASK_3 -->

---

## Phase 6 Success Criteria

1. ✅ `uv run test-all` passes
2. ✅ DB tests distributed across multiple xdist workers (not clustered on gw0)
3. ✅ No "Future attached to different loop" or "Event loop is closed" errors
4. ✅ Database NOT rebuilt between tests (canary survives if implemented)

## Definition of Done (from design)

**Primary Deliverable:**
Database integration tests run with full xdist parallelism - no `xdist_group` clustering.

**Success Criteria:**
- `uv run test-all` passes with DB tests distributed across workers (not all on gw0)
- No "Future attached to different loop" errors
- No database rebuild between tests
- Tests remain isolated by UUID/workspace
