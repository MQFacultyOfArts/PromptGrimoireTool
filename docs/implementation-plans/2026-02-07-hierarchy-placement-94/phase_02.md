# Hierarchy & Placement Implementation Plan — Phase 2

**Goal:** Workspaces can be placed into/removed from Activities and Courses, with listing functions and UI controls on the annotation page.

**Architecture:** Placement functions in `db/workspaces.py` enforce mutual exclusivity (activity_id xor course_id xor both null). Annotation page header shows placement status with controls to change it.

**Tech Stack:** SQLModel, NiceGUI, PostgreSQL

**Scope:** Phase 2 of 4 from original design

**Codebase verified:** 2026-02-07

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 94-hierarchy-placement.AC3: Workspace placement
- **94-hierarchy-placement.AC3.1 Success:** Place workspace in Activity (sets activity_id, clears course_id)
- **94-hierarchy-placement.AC3.2 Success:** Place workspace in Course (sets course_id, clears activity_id)
- **94-hierarchy-placement.AC3.3 Success:** Make workspace loose (clears both)
- **94-hierarchy-placement.AC3.4 Failure:** Place workspace in non-existent Activity/Course is rejected
- **94-hierarchy-placement.AC3.5 Success:** List workspaces for Activity returns placed workspaces
- **94-hierarchy-placement.AC3.6 Success:** List loose workspaces for Course returns course-associated workspaces
- **94-hierarchy-placement.AC3.7 UAT:** Workspace can be placed into/removed from Activity or Course via UI

---

## Codebase Investigation Findings

- ✓ Annotation page at `pages/annotation.py` (2272 lines) loads workspace via `workspace_id` query param (line 2281)
- ✓ Header row (lines 2215-2244) is the natural location for placement controls
- ✓ `PageState` dataclass (lines 297-325) can track placement state during session
- ✓ `workspaces.py` is minimal (60 lines), ample space for placement functions
- ✓ `select() + where()` pattern confirmed across all CRUD modules (courses.py, weeks.py, workspace_documents.py)
- ✓ Phase 1 adds `activity_id` and `course_id` FK fields to Workspace model

**Key files for implementor to read:**
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/CLAUDE.md`
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/docs/testing.md`
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/db/workspaces.py` (add functions here)
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/db/weeks.py` (listing pattern reference)
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/pages/annotation.py` (UI modification target)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Placement and listing functions in workspaces.py

**Verifies:** 94-hierarchy-placement.AC3.1, AC3.2, AC3.3, AC3.4, AC3.5, AC3.6

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py` (add 5 new functions after existing ones)
- Test: `tests/integration/test_workspace_placement.py` (integration)

**Implementation:**

Add to `workspaces.py` after the existing `save_workspace_crdt_state()` function. Import `Activity`, `Course` from models (alongside existing `Workspace` import). Import `select` from `sqlmodel`.

Functions to add:

- `place_workspace_in_activity(workspace_id: UUID, activity_id: UUID) -> bool` — Within `get_session()`: get workspace by ID, get Activity by ID. If either is None, return False. Set `workspace.activity_id = activity_id`, set `workspace.course_id = None` (enforce mutual exclusivity), set `workspace.updated_at = datetime.now(UTC)`. `session.add(workspace)`. Return True.

- `place_workspace_in_course(workspace_id: UUID, course_id: UUID) -> bool` — Within `get_session()`: get workspace by ID, get Course by ID. If either is None, return False. Set `workspace.course_id = course_id`, set `workspace.activity_id = None`, set `workspace.updated_at = datetime.now(UTC)`. `session.add(workspace)`. Return True.

- `make_workspace_loose(workspace_id: UUID) -> bool` — Within `get_session()`: get workspace by ID. If None, return False. Set `workspace.activity_id = None`, `workspace.course_id = None`, set `workspace.updated_at = datetime.now(UTC)`. `session.add(workspace)`. Return True.

Import `datetime` and `UTC` from `datetime` module for `updated_at` updates (follows pattern from `save_workspace_crdt_state()`).

- `list_workspaces_for_activity(activity_id: UUID) -> list[Workspace]` — Within `get_session()`: `select(Workspace).where(Workspace.activity_id == activity_id).order_by("created_at")`. Return `list(result.all())`.

- `list_loose_workspaces_for_course(course_id: UUID) -> list[Workspace]` — Within `get_session()`: `select(Workspace).where(Workspace.course_id == course_id).order_by("created_at")`. Return `list(result.all())`.

**Testing:**

Integration tests in `tests/integration/test_workspace_placement.py`. Requires `TEST_DATABASE_URL`. Each test uses UUID isolation.

Setup: Create Course + Week + Activity using existing CRUD functions from Phase 1.

Tests must verify:
- AC3.1: Create workspace → `place_workspace_in_activity()` → re-fetch → `activity_id` is set, `course_id` is None
- AC3.2: Create workspace → `place_workspace_in_course()` → re-fetch → `course_id` is set, `activity_id` is None
- AC3.3: Place workspace in Activity → `make_workspace_loose()` → re-fetch → both are None
- AC3.4: `place_workspace_in_activity(workspace_id, uuid4())` → returns False (non-existent Activity). Same for non-existent Course.
- AC3.5: Create 2 workspaces, place both in same Activity → `list_workspaces_for_activity()` returns 2
- AC3.6: Create 2 workspaces, place both in same Course → `list_loose_workspaces_for_course()` returns 2
- Transition test: Place in Activity → place in Course → verify activity_id cleared, course_id set

**Verification:**

Run: `uv run pytest tests/integration/test_workspace_placement.py -v`
Expected: All tests pass

**Commit:** `feat: add workspace placement and listing functions`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Placement UI on annotation page

**Verifies:** 94-hierarchy-placement.AC3.7

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py` (header row area, ~lines 2210-2244)

**Implementation:**

In the annotation page, add placement controls in the header row area (after the workspace UUID label and near the existing export button). The UI should show:

1. **Placement status badge**: Show "Loose" (grey), "Activity: [title]" (blue), or "Course: [code]" (green) based on `workspace.activity_id` and `workspace.course_id`. Fetch Activity/Course titles for display.

2. **"Change Placement" button** (only when workspace is loaded): Opens a dialog with three options:
   - "Place in Activity" — Select from a list of Activities (needs user to be enrolled in a course to see its Activities). Use `list_activities_for_course()` from Phase 1 to populate options.
   - "Place in Course" — Select from a list of Courses the user is enrolled in. Use `list_user_enrollments()` + `get_course_by_id()` to populate.
   - "Make Loose" — Calls `make_workspace_loose()`.

3. **On change**: Call the appropriate placement function, refresh the status badge.

Import from db modules: `place_workspace_in_activity`, `place_workspace_in_course`, `make_workspace_loose`, `get_activity`, `list_activities_for_course` (from activities), `get_course_by_id`, `list_user_enrollments` (from courses).

The dialog follows the pattern from `src/promptgrimoire/pages/dialogs.py` if reusable patterns exist there, otherwise use inline NiceGUI dialog.

**Testing:** UAT (manual verification via browser).

**Verification:**

Start app, navigate to annotation page with a workspace, verify placement controls appear and function.

**Commit:** `feat: add workspace placement controls to annotation page`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

---

## UAT Steps

1. [ ] Start app with seeded test data (from Phase 1 seed)
2. [ ] Login as `admin@example.com`
3. [ ] Navigate to course detail → create an Activity under Week 1 (if not done in Phase 1 UAT)
4. [ ] Click the Activity to open its template workspace in annotation page
5. [ ] Verify: Placement status shows "Activity: [Activity title]"
6. [ ] Navigate to `/annotation` (no workspace_id) → create a new workspace
7. [ ] Verify: Placement status shows "Loose"
8. [ ] Click "Change Placement" → select "Place in Activity" → choose the Activity
9. [ ] Verify: Status updates to "Activity: [title]"
10. [ ] Click "Change Placement" → select "Make Loose"
11. [ ] Verify: Status updates to "Loose"
12. [ ] Click "Change Placement" → select "Place in Course" → choose LAWS1100
13. [ ] Verify: Status updates to "Course: LAWS1100"
14. [ ] Run all tests: `uv run test-all`
15. [ ] Verify: All tests pass

## Evidence Required
- [ ] Screenshot of annotation page showing "Activity: [title]" placement badge
- [ ] Screenshot of placement dialog with Activity/Course/Loose options
- [ ] Test output showing green for all tests
