# 94-hierarchy-placement Phase 1: Activity Entity, Schema, and CRUD

**Goal:** Activity table exists with correct constraints. Full CRUD operations work. Activities visible on course detail page.

**Architecture:** Activity is a new SQLModel entity under Week. Each Activity owns a template Workspace (CASCADE DELETE). Workspaces gain optional `activity_id` (SET NULL) and `course_id` (SET NULL) FKs with mutual exclusivity enforced at both Pydantic and CHECK constraint levels. CRUD follows existing async `get_session()` pattern. Course page gains inline Activity list under each Week.

**Tech Stack:** SQLModel, Alembic, PostgreSQL, NiceGUI

**Scope:** Phase 1 of 4 from original design

**Codebase verified:** 2026-02-08

**Key files for executor context:**
- Testing patterns: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/docs/testing.md`
- CLAUDE.md: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/CLAUDE.md`
- Example CRUD tests: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/tests/integration/test_workspace_crud.py`

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 94-hierarchy-placement.AC1: Activity entity and schema
- **94-hierarchy-placement.AC1.1 Success:** Activity created with week_id, title, description; has auto-generated UUID and timestamps
- **94-hierarchy-placement.AC1.2 Success:** Activity's template workspace auto-created atomically
- **94-hierarchy-placement.AC1.3 Failure:** Creating Activity with non-existent week_id is rejected
- **94-hierarchy-placement.AC1.4 Failure:** Creating Activity without week_id is rejected (NOT NULL)
- **94-hierarchy-placement.AC1.5 Success:** Workspace supports optional activity_id, course_id, enable_save_as_draft fields
- **94-hierarchy-placement.AC1.6 Failure:** Workspace with both activity_id and course_id set is rejected (app-level)
- **94-hierarchy-placement.AC1.7 Success:** Deleting Activity sets workspace activity_id to NULL (SET NULL)
- **94-hierarchy-placement.AC1.8 Success:** Deleting Course sets workspace course_id to NULL (SET NULL)

### 94-hierarchy-placement.AC2: Activity CRUD and course page UI
- **94-hierarchy-placement.AC2.1 Success:** Create, get, update, delete Activity via CRUD functions
- **94-hierarchy-placement.AC2.2 Success:** Delete Activity cascade-deletes template workspace
- **94-hierarchy-placement.AC2.3 Success:** List Activities for Week returns correct set, ordered by created_at
- **94-hierarchy-placement.AC2.4 Success:** List Activities for Course (via Week join) returns Activities across all Weeks
- **94-hierarchy-placement.AC2.5 UAT:** Activities visible under Weeks on course detail page
- **94-hierarchy-placement.AC2.6 UAT:** Create Activity form (title, description) creates Activity and template workspace
- **94-hierarchy-placement.AC2.7 UAT:** Clicking Activity navigates to template workspace in annotation page

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Activity model and Workspace model extensions

**Verifies:** 94-hierarchy-placement.AC1.1, 94-hierarchy-placement.AC1.5, 94-hierarchy-placement.AC1.6

**Files:**
- Modify: `src/promptgrimoire/db/models.py` (add Activity class, extend Workspace, add `_set_null_fk_column` helper)

**Implementation:**

Add a `_set_null_fk_column()` helper near the existing `_cascade_fk_column()` at line 40:

```python
def _set_null_fk_column(target: str) -> Any:
    """Create a UUID foreign key column with SET NULL on delete."""
    return Column(Uuid(), ForeignKey(target, ondelete="SET NULL"), nullable=True)
```

Add `Activity` class after `Week` (after line 155). Follow the Week class pattern:

```python
class Activity(SQLModel, table=True):
    """A discrete assignment or exercise within a Week.

    Each Activity has an instructor-managed template workspace that students
    clone when they start work. The template workspace is CASCADE-deleted
    when the Activity is deleted.

    Attributes:
        id: Primary key UUID, auto-generated.
        week_id: Foreign key to Week (CASCADE DELETE).
        template_workspace_id: Foreign key to Workspace (CASCADE DELETE).
        title: Activity title (e.g., "Annotate Becky Bennett Interview").
        description: Optional markdown description of the activity.
        created_at: Timestamp when activity was created.
        updated_at: Timestamp when activity was last modified.
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    week_id: UUID = Field(sa_column=_cascade_fk_column("week.id"))
    template_workspace_id: UUID = Field(
        sa_column=Column(
            Uuid(),
            ForeignKey("workspace.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        )
    )
    title: str = Field(max_length=200)
    description: str | None = Field(
        default=None, sa_column=Column(sa.Text(), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )
    updated_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )
```

**Note on `template_workspace_id` FK:** Uses `ondelete="RESTRICT"` (not CASCADE) because:
- Deleting Activity should delete its template workspace (handled in `delete_activity()` CRUD function)
- Deleting a Workspace directly should NOT cascade-delete the Activity
- RESTRICT prevents accidental deletion of a template workspace still referenced by an Activity

Extend existing `Workspace` class (after line 180) with three new fields:

```python
    activity_id: UUID | None = Field(
        default=None, sa_column=_set_null_fk_column("activity.id")
    )
    course_id: UUID | None = Field(
        default=None, sa_column=_set_null_fk_column("course.id")
    )
    enable_save_as_draft: bool = Field(default=False)
```

Add a Pydantic `model_validator` to `Workspace` for mutual exclusivity of `activity_id` and `course_id`. Add `from pydantic import model_validator` to imports:

```python
@model_validator(mode="after")
def _check_placement_exclusivity(self) -> Workspace:
    """Ensure activity_id and course_id are mutually exclusive."""
    if self.activity_id is not None and self.course_id is not None:
        msg = "Workspace cannot be placed in both an Activity and a Course"
        raise ValueError(msg)
    return self
```

**Testing:**

Tests are in Task 3 and Task 4 (after the migration in Task 2 creates the schema).

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add Activity model and extend Workspace with placement fields`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Alembic migration for Activity table and Workspace extensions

**Verifies:** 94-hierarchy-placement.AC1.1, 94-hierarchy-placement.AC1.5

**Files:**
- Create: `alembic/versions/<generated>_add_activity_and_workspace_placement.py`

**Implementation:**

Generate the migration:

```bash
cd /home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement
uv run alembic revision --autogenerate -m "add activity and workspace placement"
```

Review the generated migration. It should contain:

1. `op.create_table("activity", ...)` with columns: `id` (UUID PK), `week_id` (UUID FK to week.id CASCADE), `template_workspace_id` (UUID FK to workspace.id RESTRICT, unique), `title` (varchar 200), `description` (text nullable), `created_at` (timestamptz), `updated_at` (timestamptz)
2. `op.add_column("workspace", sa.Column("activity_id", ...))` with UUID FK to activity.id SET NULL, nullable
3. `op.add_column("workspace", sa.Column("course_id", ...))` with UUID FK to course.id SET NULL, nullable
4. `op.add_column("workspace", sa.Column("enable_save_as_draft", ...))` with Boolean, default False
5. CHECK constraint on workspace: `NOT (activity_id IS NOT NULL AND course_id IS NOT NULL)`

If the autogenerated migration does not include the CHECK constraint, add it manually:

```python
op.create_check_constraint(
    "ck_workspace_placement_exclusivity",
    "workspace",
    "NOT (activity_id IS NOT NULL AND course_id IS NOT NULL)",
)
```

Also add FK indexes for the new columns (the autogenerate may not create these):

```python
op.create_index("ix_workspace_activity_id", "workspace", ["activity_id"])
op.create_index("ix_workspace_course_id", "workspace", ["course_id"])
op.create_index("ix_activity_week_id", "activity", ["week_id"])
```

The `downgrade()` should reverse all operations.

**Verification:**
Run: `uv run alembic upgrade head`
Expected: Migration applies cleanly

Run: `uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: Downgrade and re-upgrade both succeed

**Commit:** `feat: add Alembic migration for Activity table and Workspace placement`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Activity model and schema integration tests

**Verifies:** 94-hierarchy-placement.AC1.1, 94-hierarchy-placement.AC1.2, 94-hierarchy-placement.AC1.3, 94-hierarchy-placement.AC1.4, 94-hierarchy-placement.AC1.5, 94-hierarchy-placement.AC1.6, 94-hierarchy-placement.AC1.7, 94-hierarchy-placement.AC1.8

**Files:**
- Create: `tests/integration/test_activity_crud.py`

**Implementation:**

Write integration tests following the pattern in `tests/integration/test_workspace_crud.py`. Use class-based organisation.

Module-level skip guard:

```python
import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set - skipping database integration tests",
)
```

**Testing:**

Tests must verify each AC listed above. Specific test cases:

- **AC1.1:** `TestCreateActivity::test_creates_with_uuid_and_timestamps` -- Create Activity with valid week_id, title, description. Assert id is UUID, created_at/updated_at are set.
- **AC1.2:** `TestCreateActivity::test_template_workspace_created_atomically` -- Create Activity, verify `template_workspace_id` is not None and that the Workspace exists in DB.
- **AC1.3:** `TestCreateActivity::test_rejects_nonexistent_week_id` -- Create Activity with random UUID as week_id. Assert raises `IntegrityError`.
- **AC1.4:** Covered by model definition (NOT NULL on week_id). Can test that SQLModel rejects `None` for `week_id`.
- **AC1.5:** `TestWorkspacePlacementFields::test_workspace_has_activity_id_course_id_fields` -- Create Workspace, verify `activity_id`, `course_id` default to None, `enable_save_as_draft` defaults to False.
- **AC1.6:** `TestWorkspacePlacementFields::test_rejects_both_activity_and_course` -- Construct Workspace with both `activity_id` and `course_id` set. Assert raises `ValueError`.
- **AC1.7:** `TestCascadeBehavior::test_delete_activity_nulls_workspace_activity_id` -- Create Activity, place a workspace in that Activity (set activity_id directly via session), delete the Activity via CRUD, verify workspace still exists with `activity_id=None`.
- **AC1.8:** `TestCascadeBehavior::test_delete_course_nulls_workspace_course_id` -- Create Course, set workspace `course_id` directly via session, delete Course, verify workspace still exists with `course_id=None`.

These tests need prerequisite data (Course, Week). Create a helper function:

```python
async def _make_course_and_week() -> tuple[Course, Week]:
    """Helper to create a course and week for activity tests."""
    course = await create_course(code="TEST001", name="Test", semester="2026-S1")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    return course, week
```

Use unique course codes per test class to avoid collisions under xdist (e.g., use `uuid4().hex[:8]` in the code).

**Verification:**
Run: `uv run pytest tests/integration/test_activity_crud.py -v`
Expected: All tests pass

**Commit:** `test: add Activity model and schema integration tests`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Workspace mutual exclusivity unit test

**Verifies:** 94-hierarchy-placement.AC1.6

**Files:**
- Create: `tests/unit/test_workspace_placement_validation.py`

**Implementation:**

Unit test for the Pydantic `model_validator` -- no database needed:

```python
import pytest
from uuid import uuid4
from promptgrimoire.db.models import Workspace


class TestWorkspacePlacementExclusivity:
    def test_both_none_is_valid(self) -> None:
        ws = Workspace()
        assert ws.activity_id is None
        assert ws.course_id is None

    def test_activity_only_is_valid(self) -> None:
        ws = Workspace(activity_id=uuid4())
        assert ws.activity_id is not None
        assert ws.course_id is None

    def test_course_only_is_valid(self) -> None:
        ws = Workspace(course_id=uuid4())
        assert ws.course_id is not None
        assert ws.activity_id is None

    def test_both_set_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="cannot be placed in both"):
            Workspace(activity_id=uuid4(), course_id=uuid4())
```

**Verification:**
Run: `uv run pytest tests/unit/test_workspace_placement_validation.py -v`
Expected: All tests pass

**Commit:** `test: add Workspace placement mutual exclusivity unit tests`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 5-7) -->
<!-- START_TASK_5 -->
### Task 5: Activity CRUD module

**Verifies:** 94-hierarchy-placement.AC2.1, 94-hierarchy-placement.AC2.2, 94-hierarchy-placement.AC2.3, 94-hierarchy-placement.AC2.4

**Files:**
- Create: `src/promptgrimoire/db/activities.py`
- Modify: `src/promptgrimoire/db/__init__.py` (add imports and exports)

**Implementation:**

Create `src/promptgrimoire/db/activities.py` following the pattern in `weeks.py`:

```python
"""CRUD operations for Activity.

Provides async database functions for activity management.
Activities are assignments within Weeks that own template workspaces.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import Activity, Week, Workspace

if TYPE_CHECKING:
    from uuid import UUID


async def create_activity(
    week_id: UUID,
    title: str,
    description: str | None = None,
) -> Activity:
    """Create a new activity with its template workspace atomically.

    Creates a Workspace first, then the Activity referencing it.
    Both operations are within a single session (atomic).

    Parameters
    ----------
    week_id : UUID
        The parent week's UUID.
    title : str
        Activity title.
    description : str | None
        Optional markdown description.

    Returns
    -------
    Activity
        The created Activity with template_workspace_id set.
    """
    async with get_session() as session:
        template = Workspace()
        session.add(template)
        await session.flush()

        activity = Activity(
            week_id=week_id,
            title=title,
            description=description,
            template_workspace_id=template.id,
        )
        session.add(activity)
        await session.flush()
        await session.refresh(activity)
        return activity


async def get_activity(activity_id: UUID) -> Activity | None:
    """Get an activity by ID."""
    async with get_session() as session:
        return await session.get(Activity, activity_id)


async def update_activity(
    activity_id: UUID,
    title: str | None = None,
    description: str | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel distinguishes "not provided" from explicit None (clear description)
) -> Activity | None:
    """Update activity details.

    Use description=None to clear it. Omit (or pass ...) to leave unchanged.
    """
    async with get_session() as session:
        activity = await session.get(Activity, activity_id)
        if not activity:
            return None

        if title is not None:
            activity.title = title
        if description is not ...:
            activity.description = description

        activity.updated_at = datetime.now(UTC)
        session.add(activity)
        await session.flush()
        await session.refresh(activity)
        return activity


async def delete_activity(activity_id: UUID) -> bool:
    """Delete an activity and its template workspace.

    Deletion order matters due to circular FKs:
    1. Delete Activity first — this triggers SET NULL on any
       student workspace.activity_id references.
    2. Then delete the orphaned template Workspace, which is now
       safe because no RESTRICT FK points to it.

    (Activity.template_workspace_id uses RESTRICT, so deleting
    the Workspace first would be blocked while the Activity exists.)
    """
    async with get_session() as session:
        activity = await session.get(Activity, activity_id)
        if not activity:
            return False

        template_workspace_id = activity.template_workspace_id
        await session.delete(activity)
        await session.flush()

        template = await session.get(Workspace, template_workspace_id)
        if template:
            await session.delete(template)

        return True


async def list_activities_for_week(week_id: UUID) -> list[Activity]:
    """List all activities for a week, ordered by created_at."""
    async with get_session() as session:
        result = await session.exec(
            select(Activity)
            .where(Activity.week_id == week_id)
            .order_by(Activity.created_at)  # type: ignore[arg-type]  -- SQLModel order_by() stubs don't accept Column expressions
        )
        return list(result.all())


async def list_activities_for_course(course_id: UUID) -> list[Activity]:
    """List all activities for a course (via Week join).

    Returns activities across all weeks, ordered by week number then created_at.
    """
    async with get_session() as session:
        result = await session.exec(
            select(Activity)
            .join(Week, Activity.week_id == Week.id)
            .where(Week.course_id == course_id)
            .order_by(Week.week_number, Activity.created_at)  # type: ignore[arg-type]  -- SQLModel order_by() stubs don't accept Column expressions
        )
        return list(result.all())
```

Update `src/promptgrimoire/db/__init__.py`:

- Add import block:
  ```python
  from promptgrimoire.db.activities import (
      create_activity,
      delete_activity,
      get_activity,
      list_activities_for_course,
      list_activities_for_week,
      update_activity,
  )
  ```
- Add `Activity` to models import
- Add all new names to `__all__` in alphabetical order

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add Activity CRUD module`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Activity CRUD integration tests

**Verifies:** 94-hierarchy-placement.AC2.1, 94-hierarchy-placement.AC2.2, 94-hierarchy-placement.AC2.3, 94-hierarchy-placement.AC2.4

**Files:**
- Modify: `tests/integration/test_activity_crud.py` (extend from Task 3)

**Implementation:**

Add test classes to the existing `test_activity_crud.py`:

**Testing:**

- **AC2.1:** `TestActivityCRUD::test_create_get_update_delete` -- Full lifecycle: create, get by ID (verify fields), update title and description, get again (verify changes), delete, get again (verify None).
- **AC2.2:** `TestActivityCRUD::test_delete_cascades_template_workspace` -- Create Activity (which creates template workspace), delete Activity, verify template workspace no longer exists in DB.
- **AC2.3:** `TestListActivities::test_list_for_week_ordered_by_created_at` -- Create 3 Activities in a Week with known order, list, verify order matches created_at.
- **AC2.4:** `TestListActivities::test_list_for_course_across_weeks` -- Create Course with 2 Weeks, add Activities to each, call `list_activities_for_course()`, verify all returned and ordered by week_number then created_at.

These tests need prerequisite data (Course, Week). Create a helper function using unique identifiers:

```python
async def _make_course_and_week(suffix: str = "") -> tuple[Course, Week]:
    """Helper to create a course and week for activity tests."""
    code = f"T{uuid4().hex[:6].upper()}"
    course = await create_course(code=code, name=f"Test{suffix}", semester="2026-S1")
    week = await create_week(course_id=course.id, week_number=1, title="Week 1")
    return course, week
```

**Verification:**
Run: `uv run pytest tests/integration/test_activity_crud.py -v`
Expected: All tests pass

**Commit:** `test: add Activity CRUD integration tests`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Schema guard verification

**Verifies:** None (infrastructure verification)

**Files:**
- No files to modify (Activity model import in `db/__init__.py` from Task 5 automatically registers the table)

**Implementation:**

Verify that `verify_schema()` now checks for the `activity` table. The schema guard in `bootstrap.py` uses `get_expected_tables()` which calls `SQLModel.metadata`. Since the Activity model is imported via `db/__init__.py` (done in Task 5), it will be automatically included.

**Verification:**
Run: `uv run python -c "from promptgrimoire.db.bootstrap import get_expected_tables; print(sorted(get_expected_tables()))"`
Expected: Output includes `activity` in the sorted list of table names

**Commit:** No separate commit needed -- this is verification only.
<!-- END_TASK_7 -->
<!-- END_SUBCOMPONENT_C -->

<!-- START_SUBCOMPONENT_D (tasks 8-9) -->
<!-- START_TASK_8 -->
### Task 8: Course detail page -- Activity list under Weeks

**Verifies:** 94-hierarchy-placement.AC2.5, 94-hierarchy-placement.AC2.7

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py:213-350` (course_detail_page function)

**Implementation:**

In `course_detail_page()`, the existing `weeks_list()` refreshable function renders each week as a `ui.card()`. Extend this to show Activities under each Week.

Add import at top of file:

```python
from promptgrimoire.db.activities import (
    create_activity,
    list_activities_for_week,
)
```

Inside the `weeks_list()` function (around line 290), after the week title/status display and before the publish/unpublish controls, add an Activity list for each week:

```python
# Inside the for week in weeks loop, after the week header row:
activities = await list_activities_for_week(week.id)
if activities:
    with ui.column().classes("ml-4 gap-1 mt-2"):
        for act in activities:
            with ui.row().classes("items-center gap-2"):
                ui.icon("assignment").classes("text-gray-400")
                ui.link(
                    act.title,
                    f"/annotation?workspace_id={act.template_workspace_id}",
                ).classes("text-sm")
elif can_manage:
    ui.label("No activities yet").classes(
        "text-xs text-gray-400 ml-4 mt-1"
    )
```

The Activity links navigate to the annotation page with the template workspace ID as the `workspace_id` query parameter (matching the annotation page's parameter name).

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: display Activities under Weeks on course detail page`
<!-- END_TASK_8 -->

<!-- START_TASK_9 -->
### Task 9: Course detail page -- Create Activity form

**Verifies:** 94-hierarchy-placement.AC2.6

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (add new route and button)

**Implementation:**

Add a "Add Activity" button for each Week (visible to instructors only). Following the existing pattern (the "Add Week" button navigates to a separate page), create a new route:

```python
@ui.page("/courses/{course_id}/weeks/{week_id}/activities/new")
async def create_activity_page(course_id: str, week_id: str) -> None:
    """Create a new activity page."""
```

This page follows the exact same pattern as `create_week_page()` (lines 353-423):
- Auth check, DB check, init_db, UUID parse, course lookup, enrollment check
- Form inputs: title (input), description (textarea)
- Submit handler: calls `create_activity(week_id=wid, title=..., description=...)`
- Redirect back to course detail page

Add "Add Activity" button in the `weeks_list()` for each week (visible when `can_manage`):

```python
if can_manage:
    ui.button(
        "Add Activity",
        on_click=lambda wid=week.id: ui.navigate.to(
            f"/courses/{course_id}/weeks/{wid}/activities/new"
        ),
    ).props("flat dense size=sm")
```

Also extend the `_broadcast_weeks_refresh()` mechanism to refresh when activities change, so other clients see new activities.

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add Create Activity page and button on course detail`
<!-- END_TASK_9 -->
<!-- END_SUBCOMPONENT_D -->

---

## UAT Steps

After all Phase 1 tasks are complete, verify manually:

### AC2.5: Activities visible under Weeks on course detail page
1. Navigate to a course detail page at `/courses/{course_id}`
2. **Verify:** Each Week section shows its Activities listed underneath with assignment icons
3. **Verify:** Weeks with no Activities show "No activities yet" (for instructors)
4. **Evidence:** Activities appear under correct Weeks

### AC2.6: Create Activity form creates Activity and template workspace
1. On course detail page, click "Add Activity" button under a Week
2. Fill in title (e.g., "Annotate Becky Bennett Interview") and optional description
3. Click submit
4. **Verify:** Redirected back to course detail page
5. **Verify:** New Activity appears under the correct Week
6. **Evidence:** Activity exists with title matching input

### AC2.7: Clicking Activity navigates to template workspace
1. On course detail page, click an Activity title link
2. **Verify:** Navigated to `/annotation?workspace_id={template_workspace_id}`
3. **Verify:** Annotation page loads with the template workspace (empty workspace is acceptable for a new Activity)
4. **Evidence:** URL contains correct workspace_id, annotation page renders
