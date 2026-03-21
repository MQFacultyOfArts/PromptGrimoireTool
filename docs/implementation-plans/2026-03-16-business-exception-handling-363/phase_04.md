# Business Exception Handling Implementation Plan — Phase 4

**Goal:** Loose workspaces default `allow_sharing=True` since no course policy restricts them.

**Architecture:** Single default-value change in `PlacementContext` dataclass. All 7 existing `PlacementContext(placement_type="loose")` constructions inherit the new default. Activity-placed and course-placed paths unaffected (they set `allow_sharing` explicitly).

**Tech Stack:** Python 3.14, pytest

**Scope:** 4 phases from original design (phases 1-4). This is Phase 4.

**Codebase verified:** 2026-03-16

---

## Acceptance Criteria Coverage

This phase implements and tests:

### business-exception-handling-363.AC4: Loose Workspace Sharing Default
- **business-exception-handling-363.AC4.1 Success:** `PlacementContext(placement_type="loose").allow_sharing` is `True`
- **business-exception-handling-363.AC4.2 Success:** `get_placement_context()` for workspace with no activity and no course returns `allow_sharing=True`
- **business-exception-handling-363.AC4.3 Success:** Activity-placed workspace `allow_sharing` still resolved from `resolve_tristate(activity.allow_sharing, course.default_allow_sharing)` — unaffected
- **business-exception-handling-363.AC4.4 Success:** Course-placed workspace `allow_sharing` still resolved from `course.default_allow_sharing` — unaffected

---

<!-- START_TASK_1 -->
### Task 1: Change PlacementContext default

**Verifies:** business-exception-handling-363.AC4.1

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py` — line 158

**Implementation:**

Change line 158 from:
```python
allow_sharing: bool = False
```

To:
```python
allow_sharing: bool = True
```

No other code changes needed. All 7 `PlacementContext(placement_type="loose")` constructions at lines 255, 279, 282, 324, 327, 330, 371 inherit the new default.

**Verification:**

```bash
uv run python -c "
from promptgrimoire.db.workspaces import PlacementContext
ctx = PlacementContext(placement_type='loose')
assert ctx.allow_sharing is True, f'Expected True, got {ctx.allow_sharing}'
print('PlacementContext loose default is True')
"
```

**Commit:** `fix: default loose workspaces to allow_sharing=True`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Tests for loose workspace sharing default

**Verifies:** business-exception-handling-363.AC4.1, business-exception-handling-363.AC4.2, business-exception-handling-363.AC4.3, business-exception-handling-363.AC4.4

**Files:**
- Modify: `tests/integration/test_workspace_placement.py` — add tests to existing TestPlacementContext class

**Testing:**

Tests must verify:
- business-exception-handling-363.AC4.1: `PlacementContext(placement_type="loose").allow_sharing is True` — unit-level dataclass assertion
- business-exception-handling-363.AC4.2: `get_placement_context()` for a workspace with no activity returns `allow_sharing=True` — integration test with real DB
- business-exception-handling-363.AC4.3: Activity-placed workspace still resolves `allow_sharing` from `resolve_tristate()` — regression guard, verify an activity-placed workspace with `allow_sharing=False` in course returns `False`
- business-exception-handling-363.AC4.4: Course-placed workspace still resolves `allow_sharing` from `course.default_allow_sharing` — regression guard, verify a course-placed workspace with `default_allow_sharing=False` returns `False`

AC4.3 and AC4.4 may already be covered by existing tests in `test_workspace_placement.py`. If so, reference them rather than duplicating. If not, add new test methods.

**Verification:**

```bash
uv run grimoire test run tests/integration/test_workspace_placement.py
uv run grimoire test all
```

**Commit:** `test: add loose workspace sharing default tests covering AC4.1-AC4.4`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Run complexipy on modified file

**Files:** None (diagnostic only)

**Verification:**

```bash
uv run complexipy src/promptgrimoire/db/workspaces.py --max-complexity-allowed 15
```

The change is a single default value. Zero complexity impact. Note any pre-existing functions near the threshold.

No commit needed for this task.
<!-- END_TASK_3 -->

## UAT Steps

1. [ ] Start the app: `uv run run.py`
2. [ ] Log in as any user
3. [ ] Create a new workspace directly (not via an activity or course) — this is a "loose" workspace
4. [ ] Navigate to the annotation page for this workspace
5. [ ] Verify: The "Share with user" button is visible (sharing is enabled by default for loose workspaces)
6. [ ] Share the workspace with another user
7. [ ] Verify: Share succeeds without permission errors

## Evidence Required
- [ ] Test output showing green (`uv run grimoire test all`)
- [ ] Screenshot: loose workspace shows share button
