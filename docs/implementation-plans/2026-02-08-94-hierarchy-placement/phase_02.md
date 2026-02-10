# 94-hierarchy-placement Phase 2: Workspace Placement

**Goal:** Workspaces can be placed into/removed from Activities and Courses, with UI controls showing full hierarchy context.

**Architecture:** Placement functions in `db/workspaces.py` handle the FK updates with pre-validation. The annotation page header gains a status chip showing placement state ("Unplaced" / "Activity: [title] in Week [N] for [Course code]") and a dialog for changing placement. Listing functions support querying workspaces by Activity or Course association.

**Tech Stack:** SQLModel, NiceGUI

**Scope:** Phase 2 of 4 from original design

**Codebase verified:** 2026-02-08

**Key files for executor context:**
- Testing patterns: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/docs/testing.md`
- CLAUDE.md: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/CLAUDE.md`
- Annotation page: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/pages/annotation.py` (workspace_id query param, header at ~line 2194)
- Workspace CRUD: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/db/workspaces.py`

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

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Workspace placement CRUD functions

**Verifies:** 94-hierarchy-placement.AC3.1, 94-hierarchy-placement.AC3.2, 94-hierarchy-placement.AC3.3, 94-hierarchy-placement.AC3.4, 94-hierarchy-placement.AC3.5, 94-hierarchy-placement.AC3.6

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py` (add placement and listing functions)
- Modify: `src/promptgrimoire/db/__init__.py` (add new exports)

**Implementation:**

Add to `src/promptgrimoire/db/workspaces.py`. Add imports: `Activity`, `Course` from models, `select` from sqlmodel.

Functions to implement (all follow the existing async `get_session()` pattern):

**`place_workspace_in_activity(workspace_id, activity_id) -> Workspace`:**
- Pre-check: fetch workspace (raise `ValueError` if not found)
- Pre-check: fetch activity (raise `ValueError` if not found)
- Set `workspace.activity_id = activity_id`, `workspace.course_id = None`
- Update `updated_at`, flush, refresh, return

**`place_workspace_in_course(workspace_id, course_id) -> Workspace`:**
- Same pattern: pre-check both, set `course_id`, clear `activity_id`

**`make_workspace_loose(workspace_id) -> Workspace`:**
- Pre-check workspace exists
- Clear both `activity_id` and `course_id`

**`list_workspaces_for_activity(activity_id) -> list[Workspace]`:**
- `select(Workspace).where(Workspace.activity_id == activity_id).order_by(Workspace.created_at)`

**`list_loose_workspaces_for_course(course_id) -> list[Workspace]`:**
- `select(Workspace).where(Workspace.course_id == course_id).where(Workspace.activity_id == None).order_by(Workspace.created_at)`
- Note: The `activity_id == None` filter is defense-in-depth. The mutual exclusivity constraint guarantees that `course_id` being set implies `activity_id` is None, but the explicit filter protects against constraint violations and makes the query's intent clear.

Update `src/promptgrimoire/db/__init__.py`: add imports and add to `__all__`.

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add workspace placement CRUD functions`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Workspace placement integration tests

**Verifies:** 94-hierarchy-placement.AC3.1, 94-hierarchy-placement.AC3.2, 94-hierarchy-placement.AC3.3, 94-hierarchy-placement.AC3.4, 94-hierarchy-placement.AC3.5, 94-hierarchy-placement.AC3.6

**Files:**
- Create: `tests/integration/test_workspace_placement.py`

**Implementation:**

Integration tests following the pattern in `test_workspace_crud.py`. Module-level skip guard for `TEST_DATABASE_URL`. Class-based organisation.

**Testing:**

Test cases:

- **AC3.1:** `TestPlaceWorkspace::test_place_in_activity_sets_activity_id_clears_course_id` -- Create Activity and Workspace. First place workspace in Course, then place in Activity. Verify activity_id is set, course_id is None, updated_at changed.
- **AC3.2:** `TestPlaceWorkspace::test_place_in_course_sets_course_id_clears_activity_id` -- Create Activity, Course, and Workspace. Place in Activity first, then place in Course. Verify course_id is set, activity_id is None.
- **AC3.3:** `TestPlaceWorkspace::test_make_loose_clears_both` -- Place workspace in Activity, then make loose. Verify both are None.
- **AC3.4:** `TestPlaceWorkspace::test_place_in_nonexistent_activity_raises` -- Call `place_workspace_in_activity(ws_id, uuid4())`. Assert raises `ValueError` matching "Activity.*not found".
- **AC3.4:** `TestPlaceWorkspace::test_place_in_nonexistent_course_raises` -- Same pattern for Course.
- **AC3.4:** `TestPlaceWorkspace::test_place_nonexistent_workspace_raises` -- Call with non-existent workspace_id. Assert raises `ValueError` matching "Workspace.*not found".
- **AC3.5:** `TestListWorkspaces::test_list_for_activity` -- Create Activity, place 2 workspaces in it, leave 1 unplaced. List for activity. Verify returns exactly 2.
- **AC3.6:** `TestListWorkspaces::test_list_loose_for_course` -- Create Course, associate 2 workspaces with course_id, place 1 of those in an Activity too. List loose for course. Verify returns only the 1 without activity_id.

Helper function using unique identifiers:
```python
async def _setup_hierarchy() -> tuple[Course, Week, Activity]:
    code = f"P{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name="Placement Test", semester="2026-S1")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    activity = await create_activity(week_id=week.id, title="Test Activity")
    return course, week, activity
```

**Verification:**
Run: `uv run pytest tests/integration/test_workspace_placement.py -v`
Expected: All tests pass

**Commit:** `test: add workspace placement integration tests`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Placement context query function

**Verifies:** 94-hierarchy-placement.AC3.7 (supports UI display)

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py` (add PlacementContext dataclass and query function)
- Modify: `src/promptgrimoire/db/__init__.py` (export)

**Implementation:**

The placement UI needs to show full hierarchy context. Add a `PlacementContext` dataclass and a query function that resolves the full chain in a single session.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class PlacementContext:
    """Full hierarchy context for a workspace's placement."""

    placement_type: str  # "activity", "course", or "loose"
    activity_title: str | None = None
    week_number: int | None = None
    week_title: str | None = None
    course_code: str | None = None
    course_name: str | None = None

    @property
    def display_label(self) -> str:
        """Human-readable placement label.

        Shows full hierarchy: "Activity Title in Week N for COURSE_CODE"
        """
        if self.placement_type == "activity":
            return (
                f"{self.activity_title} "
                f"in Week {self.week_number} "
                f"for {self.course_code}"
            )
        if self.placement_type == "course":
            return f"Loose work for {self.course_code}"
        return "Unplaced"
```

**`get_placement_context(workspace_id) -> PlacementContext`:**
- Fetch workspace. If not found or no placement, return `PlacementContext(placement_type="loose")`.
- If `activity_id` set: fetch Activity, then Week (via `activity.week_id`), then Course (via `week.course_id`). Return context with all fields populated.
- If `course_id` set: fetch Course. Return context with course fields.
- All within single session for consistency.

Add `Week` and `Course` to imports if not already present.

Update `__init__.py` to export `PlacementContext` and `get_placement_context`.

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add placement context query for hierarchy display`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Placement context integration tests

**Verifies:** 94-hierarchy-placement.AC3.7 (supports UI display)

**Files:**
- Modify: `tests/integration/test_workspace_placement.py` (add context tests)

**Implementation:**

**Testing:**

- `TestPlacementContext::test_loose_workspace` -- Create workspace with no placement. `get_placement_context()` returns `placement_type="loose"`, `display_label="Unplaced"`.
- `TestPlacementContext::test_activity_placement_shows_full_hierarchy` -- Create full hierarchy (Course -> Week -> Activity), place workspace in Activity. Verify all fields populated. `display_label` should be "[Activity title] in Week [N] for [Course code]".
- `TestPlacementContext::test_course_placement` -- Place workspace in Course. Verify `placement_type="course"`, course fields populated. `display_label` should be "Loose work for [Course code]".
- `TestPlacementContext::test_nonexistent_workspace` -- Call with random UUID. Returns loose context.

**Verification:**
Run: `uv run pytest tests/integration/test_workspace_placement.py -v -k TestPlacementContext`
Expected: All tests pass

**Commit:** `test: add placement context integration tests`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 5) -->
<!-- START_TASK_5 -->
### Task 5: Annotation page placement UI

**Verifies:** 94-hierarchy-placement.AC3.7

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py` (~line 2194, header controls in `_render_workspace_view`)

**Implementation:**

In `_render_workspace_view()`, after the existing header controls (save status, user count badge, Export PDF button), add a placement status chip and dialog.

**Status chip** in the header row:
- Query `get_placement_context(workspace_id)` when rendering
- Show colour-coded chip:
  - Grey for "Unplaced"
  - Blue for Activity placement (shows full hierarchy label from `display_label`)
  - Green for Course placement (shows "Loose work for [code]")
- Chip is clickable (opens placement dialog)
- Use `@ui.refreshable` so it updates after placement changes

**Placement dialog** (opened by clicking the chip):
1. Three radio buttons: "Unplaced" / "Place in Activity" / "Associate with Course"
2. When "Place in Activity" selected: cascading selects:
   - Course dropdown (user's enrolled courses from `list_user_enrollments`)
   - Week dropdown (populated when course selected, from `list_weeks`)
   - Activity dropdown (populated when week selected, from `list_activities_for_week`)
3. When "Associate with Course" selected: single Course dropdown
4. Confirm/Cancel buttons

Add imports:

```python
from promptgrimoire.db.activities import list_activities_for_week
from promptgrimoire.db.courses import list_user_enrollments, get_course_by_id
from promptgrimoire.db.weeks import list_weeks
from promptgrimoire.db.workspaces import (
    get_placement_context,
    make_workspace_loose,
    place_workspace_in_activity,
    place_workspace_in_course,
    PlacementContext,
)
```

**Cascading select behaviour:** Use NiceGUI `on_change` handlers:
- When Course changes: fetch weeks for that course, populate Week dropdown, clear Activity dropdown
- When Week changes: fetch activities for that week, populate Activity dropdown

**After confirm:** Call placement function, refresh chip, show `ui.notify()` confirmation.

**Auth consideration:** The annotation page has `requires_auth=False`. If no user is authenticated, show the chip as read-only (display state but disable click). If authenticated, enable the dialog with the user's enrolled courses.

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add placement status chip and dialog to annotation page`
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_C -->

---

## UAT Steps

After all Phase 2 tasks are complete, verify manually:

### AC3.7: Workspace can be placed into/removed from Activity or Course via UI
1. Open an existing workspace in the annotation page at `/annotation?workspace_id={id}`
2. **Verify:** A placement status chip is visible in the header (shows "Unplaced" in grey for a loose workspace)
3. Click the chip to open the placement dialog
4. Select "Place in Activity", choose a Course, Week, then Activity from the cascading dropdowns
5. Click Confirm
6. **Verify:** Chip updates to show full hierarchy: "{Activity title} in Week {N} for {Course code}" in blue
7. Click the chip again, select "Associate with Course", choose a Course
8. Click Confirm
9. **Verify:** Chip updates to "Loose work for {Course code}" in green
10. Click the chip again, select "Unplaced"
11. Click Confirm
12. **Verify:** Chip reverts to "Unplaced" in grey
13. **Evidence:** Chip state changes correctly for each placement mode
