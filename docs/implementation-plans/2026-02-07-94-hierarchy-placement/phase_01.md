# Hierarchy & Placement Implementation Plan — Phase 1

**Goal:** Activity entity exists as a child of Week, with CRUD operations, template workspace auto-creation, and course page UI for managing Activities.

**Architecture:** Activity model in `db/models.py` with CASCADE FK to Week and RESTRICT FK to Workspace (application-level deletion of template workspace in `delete_activity()`). Workspace extended with optional SET NULL FKs for placement. CRUD module follows existing async patterns. Course page adds Activity display and creation under each Week.

**Tech Stack:** SQLModel, Alembic, NiceGUI, PostgreSQL

**Scope:** Phase 1 of 4 from original design

**Codebase verified:** 2026-02-07

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

## Codebase Investigation Findings

- ✓ `src/promptgrimoire/db/models.py` exists with 6 models: User, Course, CourseEnrollment, Week, Workspace, WorkspaceDocument
- ✓ `_cascade_fk_column()` helper at line 40 — `Column(Uuid(), ForeignKey(target, ondelete="CASCADE"), nullable=False)`
- ✗ No `_set_null_fk_column()` or `_restrict_fk_column()` helpers — need creation
- ✓ `get_session()` in `engine.py:73` — `@asynccontextmanager`, auto-commits on success, rollback on error
- ✓ CRUD pattern: `async with get_session()` → `session.add()` → `flush()` → `refresh()` → return
- ✓ Alembic migrations in `alembic/versions/` — 14 existing, latest `9a0b954d51bf`
- ✓ Schema guard in `db/schema_guard.py` — auto-discovers from `SQLModel.metadata.tables.keys()`
- ✓ Course page at `pages/courses.py:213` — `@ui.refreshable` pattern for weeks_list
- ✗ No Pydantic model validators in codebase yet — mutual exclusivity will be the first
- ✗ No integration test files exist yet (only conftest fixtures)
- ✓ Unit conftest has `make_user()`, `make_workspace()`, `make_workspace_document()` factories
- ✗ No `make_activity()` or `make_week()` factories — need creation

**Key files for implementor to read:**
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/CLAUDE.md`
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/docs/testing.md`
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/db/models.py`
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/db/weeks.py` (CRUD pattern reference)
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/db/courses.py` (CRUD + IntegrityError pattern)
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/src/promptgrimoire/pages/courses.py` (UI pattern reference)
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/tests/unit/conftest.py` (test factories)
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/94-hierarchy-placement/tests/integration/conftest.py` (DB engine reset)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add _set_null_fk_column helper and Activity model to models.py

**Files:**
- Modify: `src/promptgrimoire/db/models.py:40-42` (add helper after `_cascade_fk_column`)
- Modify: `src/promptgrimoire/db/models.py:155-180` (add fields to Workspace after `updated_at`)
- Modify: `src/promptgrimoire/db/models.py` (add Activity class after WorkspaceDocument, end of file)

**Implementation:**

Add `_set_null_fk_column` helper immediately after `_cascade_fk_column` (after line 42):

```python
def _set_null_fk_column(target: str) -> Any:
    """Create a nullable UUID foreign key column with SET NULL on delete."""
    return Column(Uuid(), ForeignKey(target, ondelete="SET NULL"), nullable=True)
```

Add import at top of file (alongside existing imports):

```python
from pydantic import model_validator
```

Add three new fields to `Workspace` class after the `updated_at` field (after line 180):

```python
    activity_id: UUID | None = Field(
        default=None, sa_column=_set_null_fk_column("activity.id")
    )
    course_id: UUID | None = Field(
        default=None, sa_column=_set_null_fk_column("course.id")
    )
    enable_save_as_draft: bool = Field(default=False)

    @model_validator(mode="after")
    def _check_placement_exclusivity(self) -> Workspace:
        """Workspace cannot be placed in both an Activity and a Course."""
        if self.activity_id is not None and self.course_id is not None:
            msg = "Workspace cannot have both activity_id and course_id set"
            raise ValueError(msg)
        return self
```

Add a `_restrict_fk_column` helper immediately after `_set_null_fk_column`:

```python
def _restrict_fk_column(target: str) -> Any:
    """Create a UUID foreign key column with RESTRICT on delete.

    Use when the application must explicitly handle deletion
    of the referenced row (e.g. delete_activity deletes template workspace).
    """
    return Column(Uuid(), ForeignKey(target, ondelete="RESTRICT"), nullable=False)
```

Add Activity model at end of file (after WorkspaceDocument class):

```python
class Activity(SQLModel, table=True):
    """A discrete assignment/exercise within a Week.

    Each Activity owns a template workspace that students clone
    when they start work on the assignment.

    Attributes:
        id: Primary key UUID, auto-generated.
        week_id: Foreign key to Week (CASCADE DELETE — deleting Week deletes Activity).
        template_workspace_id: Foreign key to Workspace (RESTRICT — application-level
            deletion in delete_activity() handles this; RESTRICT prevents accidental
            orphaning).
        title: Activity title.
        description: Activity description (markdown).
        created_at: Timestamp when activity was created.
        updated_at: Timestamp when activity was last modified.
    """

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    week_id: UUID = Field(sa_column=_cascade_fk_column("week.id"))
    template_workspace_id: UUID = Field(
        sa_column=_restrict_fk_column("workspace.id")
    )
    title: str = Field(max_length=200)
    description: str = Field(
        default="", sa_column=Column(sa.Text(), nullable=False, server_default="")
    )
    created_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )
    updated_at: datetime = Field(
        default_factory=_utcnow, sa_column=_timestamptz_column()
    )
```

**Note on FK behaviour:** `template_workspace_id` uses RESTRICT (not CASCADE) because the FK points FROM Activity TO Workspace. Database-level CASCADE on this FK would mean "when the Workspace is deleted, delete the Activity" — the opposite of what we want. Instead, `delete_activity()` explicitly deletes the template Workspace first, then the Activity. RESTRICT prevents accidental deletion of the Workspace from another code path (it would fail with an IntegrityError if the Workspace is still referenced by an Activity).

**Verification:**

Run: `uvx ty check`
Expected: No type errors

Run: `uv run ruff check src/promptgrimoire/db/models.py`
Expected: No lint errors

**Commit:** `feat: add Activity model and Workspace placement fields`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Alembic migration for Activity table and Workspace columns

**Files:**
- Create: `alembic/versions/<auto>_add_activity_table_and_workspace_placement.py` (generated)

**Implementation:**

Generate migration:

```bash
uv run alembic revision --autogenerate -m "add_activity_table_and_workspace_placement"
```

Review the generated migration to ensure it contains:
1. `op.create_table("activity", ...)` with all columns: `id` (UUID PK), `week_id` (UUID FK to week.id CASCADE), `template_workspace_id` (UUID FK to workspace.id RESTRICT), `title` (String 200), `description` (Text), `created_at` (DateTime TZ), `updated_at` (DateTime TZ)
2. `op.add_column("workspace", Column("activity_id", Uuid(), ForeignKey("activity.id", ondelete="SET NULL"), nullable=True))`
3. `op.add_column("workspace", Column("course_id", Uuid(), ForeignKey("course.id", ondelete="SET NULL"), nullable=True))`
4. `op.add_column("workspace", Column("enable_save_as_draft", Boolean(), server_default=text("false"), nullable=False))`
5. Correct `downgrade()` reversing all changes

**Note:** The `activity` table must be created BEFORE the `workspace.activity_id` FK column is added (Alembic should order this correctly with autogenerate).

**Verification:**

Run: `uv run alembic upgrade head`
Expected: Migration applies cleanly

Run: `uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: Downgrade and re-upgrade work cleanly

Verify schema guard detects new table:
Run: `uv run python -c "from promptgrimoire.db.schema_guard import get_expected_tables; print('activity' in get_expected_tables())"`
Expected: `True` (auto-discovered from SQLModel.metadata because Activity class is imported in models.py)

**Commit:** `feat: add Alembic migration for activity table and workspace placement`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Activity CRUD module

**Verifies:** 94-hierarchy-placement.AC1.1, AC1.2, AC1.3, AC1.4, AC2.1, AC2.2, AC2.3, AC2.4

**Files:**
- Create: `src/promptgrimoire/db/activities.py`
- Test: `tests/integration/test_activity_crud.py` (integration)

**Implementation:**

Create `src/promptgrimoire/db/activities.py` following the async CRUD patterns in `weeks.py` and `courses.py`. Functions:

- `create_activity(week_id: UUID, title: str, description: str = "") -> Activity` — Creates both a Workspace and an Activity atomically within a single `get_session()` call. The Workspace is created first (`session.add`, `flush`, `refresh` to get its ID), then the Activity references it via `template_workspace_id`. If anything fails, the entire transaction rolls back.

- `get_activity(activity_id: UUID) -> Activity | None` — Simple `session.get(Activity, activity_id)`.

- `update_activity(activity_id: UUID, title: str | None = None, description: str | None = None) -> Activity | None` — Updates mutable fields if provided, sets `updated_at` to `datetime.now(UTC)`. Returns None if not found. Uses `flush()` + `refresh()` pattern.

- `delete_activity(activity_id: UUID) -> bool` — Gets Activity. If found, fetches the template Workspace via `activity.template_workspace_id` and deletes it first, then deletes the Activity. Both within the same `get_session()` for atomicity. Returns False if Activity not found. The template Workspace FK uses RESTRICT, so the Workspace must be deleted before the Activity to avoid IntegrityError.

- `list_activities_for_week(week_id: UUID) -> list[Activity]` — `select(Activity).where(Activity.week_id == week_id).order_by("created_at")`.

- `list_activities_for_course(course_id: UUID) -> list[Activity]` — Join Activity to Week on `Activity.week_id == Week.id`, filter by `Week.course_id == course_id`, order by `Week.week_number`, `Activity.created_at`.

Imports needed: `get_session` from engine, `Activity`, `Week`, `Workspace` from models. Use `TYPE_CHECKING` guard for `UUID` import. Import `datetime`, `UTC` from datetime for `updated_at`. Import `select` from sqlmodel.

**Testing:**

Tests in `tests/integration/test_activity_crud.py` (real database). Tests require `TEST_DATABASE_URL` — skip module if not set. Each test uses UUID isolation (no cleanup needed). Follow the integration test pattern from `tests/integration/conftest.py` (engine reset per test).

Tests must verify each AC listed:
- AC1.1: `create_activity()` with valid week_id → verify returned Activity has UUID `id`, `title`, `description`, `created_at`, `updated_at` timestamps, and `week_id` matches
- AC1.2: After `create_activity()`, call `get_workspace(activity.template_workspace_id)` → verify workspace exists and is non-None
- AC1.3: `create_activity()` with `uuid4()` (non-existent week_id) → expect IntegrityError from SQLAlchemy
- AC1.4: This is enforced at the model level (NOT NULL on `week_id`). Test by verifying the column is non-nullable in the migration or model definition.
- AC2.1: Full CRUD cycle — create → get → update (change title) → verify title changed → delete → get returns None
- AC2.2: Create Activity → note its `template_workspace_id` → delete it via `delete_activity()` → verify `get_workspace(template_workspace_id)` returns None (explicitly deleted by `delete_activity()`)
- AC2.3: Create 3 Activities for same Week with known created_at ordering → `list_activities_for_week()` → verify correct count and order
- AC2.4: Create Course → 2 Weeks → Activities in each → `list_activities_for_course(course_id)` → verify returns Activities from both Weeks

Setup helper for tests: need to create Course and Week records to satisfy FK constraints. Use `create_course()` and `create_week()` from existing CRUD modules.

**Verification:**

Run: `uv run pytest tests/integration/test_activity_crud.py -v`
Expected: All tests pass

**Commit:** `feat: add Activity CRUD with atomic template workspace creation`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Workspace placement field tests (SET NULL, mutual exclusivity)

**Verifies:** 94-hierarchy-placement.AC1.5, AC1.6, AC1.7, AC1.8

**Files:**
- Test: `tests/integration/test_workspace_placement_fields.py` (integration — SET NULL behaviour)
- Test: `tests/unit/test_workspace_model.py` (unit — Pydantic validator, no DB needed)

**Testing:**

**Unit test** (`tests/unit/test_workspace_model.py`):
- AC1.6: Construct `Workspace(activity_id=uuid4(), course_id=uuid4())` → expect `ValidationError` from Pydantic. Also verify: `Workspace(activity_id=uuid4())` succeeds, `Workspace(course_id=uuid4())` succeeds, `Workspace()` succeeds (both None).

**Integration test** (`tests/integration/test_workspace_placement_fields.py`):
- AC1.5: Create Workspace → set `activity_id` to a real Activity's ID → verify field persists after re-fetch. Repeat for `course_id` with a real Course. Verify `enable_save_as_draft=True` persists.
- AC1.7: Create Activity (creates template workspace). Create a separate student workspace, set its `activity_id` to the Activity. Delete the Activity. Re-fetch the student workspace → verify `activity_id` is None, workspace still exists.
- AC1.8: Create Course. Create workspace, set its `course_id` to the Course. Delete the Course using `session.delete(course)` directly within the test session (no `delete_course()` CRUD function exists — only `archive_course()` for soft-delete, which is out of scope). Re-fetch workspace → verify `course_id` is None, workspace still exists.

Setup: Tests need to create Course, Week, Activity records to get valid FK targets. Use existing CRUD functions.

**Verification:**

Run: `uv run pytest tests/unit/test_workspace_model.py tests/integration/test_workspace_placement_fields.py -v`
Expected: All tests pass

**Commit:** `test: verify SET NULL behaviour and mutual exclusivity for workspace placement`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
### Task 5: Test factories for Activity and Week

**Files:**
- Modify: `tests/unit/conftest.py` (add `make_week` and `make_activity` factories)

**Implementation:**

Add `make_week` factory after `make_workspace_document`:

```python
@pytest.fixture
def make_week():
    """Factory for Week instances (not persisted)."""
    from uuid import uuid4

    from promptgrimoire.db.models import Week

    def _make(
        course_id: UUID | None = None,
        week_number: int = 1,
        title: str = "Test Week",
        **kwargs,
    ):
        return Week(
            course_id=course_id or uuid4(),
            week_number=week_number,
            title=title,
            **kwargs,
        )

    return _make
```

Add `make_activity` factory after `make_week`:

```python
@pytest.fixture
def make_activity():
    """Factory for Activity instances (not persisted)."""
    from uuid import uuid4

    from promptgrimoire.db.models import Activity

    def _make(
        week_id: UUID | None = None,
        template_workspace_id: UUID | None = None,
        title: str = "Test Activity",
        description: str = "",
        **kwargs,
    ):
        return Activity(
            week_id=week_id or uuid4(),
            template_workspace_id=template_workspace_id or uuid4(),
            title=title,
            description=description,
            **kwargs,
        )

    return _make
```

**Verification:**

Run: `uv run pytest tests/unit/conftest.py --collect-only`
Expected: New fixtures appear in the collection output

**Commit:** `test: add make_week and make_activity test factories`
<!-- END_TASK_5 -->

<!-- START_SUBCOMPONENT_C (tasks 6-7) -->
<!-- START_TASK_6 -->
### Task 6: Seed test data CLI command

**Files:**
- Modify: `src/promptgrimoire/cli.py` (add `seed_test_data` function)
- Modify: `pyproject.toml` (add `seed-test-data` script entry)

**Implementation:**

Add a `seed_test_data()` function to `cli.py` that creates:
1. Admin user: `admin@example.com` / "Admin User" / `is_admin=True`
2. Course: code="LAWS1100", name="Contracts", semester="2026-S1"
3. Enrol admin as coordinator
4. Week 1: "Introduction to Contract Law"
5. Week 2: "Offer and Acceptance"

The function should be idempotent — if records already exist (e.g., user with that email), skip creation rather than fail. Use `find_or_create_user()` from `db/users.py` for the user. For Course, check if code+semester exists before creating.

Follow the pattern of `set_admin()` in `cli.py`: use `asyncio.run()` to wrap the async operations, load dotenv, check for DATABASE_URL.

Add to `pyproject.toml` under `[project.scripts]`:
```toml
seed-test-data = "promptgrimoire.cli:seed_test_data"
```

**Verification:**

Run: `uv run seed-test-data`
Expected: Prints confirmation of created/skipped records

Run: `uv run seed-test-data` (again)
Expected: Prints that records already exist, no errors

**Commit:** `feat: add seed-test-data CLI command for UAT setup`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Add "Seed Test Data" button to mock login page

**Files:**
- Modify: `src/promptgrimoire/pages/auth.py` (in `_build_mock_login_section`)

**Implementation:**

In `_build_mock_login_section()` (line 298 of `auth.py`), add a button below the mock login buttons that calls the seed function. The button should:

1. Import the seed logic from `cli.py` (extract the async core into a reusable function in cli.py, e.g., `_seed_test_data_async()`)
2. Call it via an async click handler
3. Show a notification on success ("Test data seeded: admin user, LAWS1100 course, 2 weeks")
4. Disable itself after successful seed to prevent double-seeding

Place this inside the existing mock login card, after the test user buttons.

**Verification:**

Run: `uv run python -m promptgrimoire` with `AUTH_MOCK=true`
Navigate to: `/login`
Expected: "Seed Test Data" button visible below mock login buttons

Click button → Expected: notification confirms data created

**Commit:** `feat: add seed test data button to mock login page`
<!-- END_TASK_7 -->
<!-- END_SUBCOMPONENT_C -->

<!-- START_SUBCOMPONENT_D (tasks 8-9) -->
<!-- START_TASK_8 -->
### Task 8: Add Activity list and create form to course detail page

**Verifies:** 94-hierarchy-placement.AC2.5, AC2.6, AC2.7

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (course_detail_page, weeks_list refreshable)
- Create: `src/promptgrimoire/pages/activities.py` (create activity page)

**Implementation:**

**In `courses.py`:**

Add import at top: `from promptgrimoire.db.activities import list_activities_for_week, create_activity`

Inside the `weeks_list` refreshable function, within the `for week in weeks:` loop (after the week card content at ~line 300-334), add an inner section for Activities:

After the week title/status labels and publish/unpublish buttons, add:
1. Query: `activities = await list_activities_for_week(week.id)` (inside the async refreshable, this is fine)
2. For each activity, render a clickable row/item that navigates to `/annotation?workspace_id={activity.template_workspace_id}`
3. If `can_manage`, show an "Add Activity" button that navigates to `/courses/{course_id}/weeks/{week.id}/activities/new`

**Create `activities.py`:**

New page at route `/courses/{course_id}/weeks/{week_id}/activities/new`:
- Auth check, DB check, UUID parse for both course_id and week_id
- Verify week exists and belongs to course
- Verify user has `can_manage` permission (coordinator or instructor)
- Form with: title (required, text input), description (optional, textarea)
- On submit: call `create_activity(week_id=wid, title=title.value, description=description.value)`
- Navigate back to course detail page
- Follow patterns from `create_week_page()` in `courses.py`

**Testing:** UAT (manual verification via browser). See UAT Steps section below.

**Verification:**

Start app, navigate to course detail, verify Activities appear under Weeks.

**Commit:** `feat: add Activity list and create form to course detail page`
<!-- END_TASK_8 -->

<!-- START_TASK_9 -->
### Task 9: Verify annotation page accepts workspace_id query param

**Verifies:** 94-hierarchy-placement.AC2.7

**Files:**
- Read: `src/promptgrimoire/pages/annotation.py` (verify existing behaviour)

**Implementation:**

Check that the annotation page at `/annotation` already accepts a `workspace_id` query parameter. If it does, no changes needed — the Activity link from Task 8 will work. If it doesn't, add support for loading a workspace by ID from the query string.

Based on codebase investigation, the annotation page already manages workspaces by UUID. Verify this handles the `workspace_id` param correctly and loads the workspace's documents.

**Verification:**

Navigate to: `/annotation?workspace_id={some-valid-uuid}`
Expected: Annotation page loads with that workspace's documents (or empty if workspace has no documents)

**Commit:** No commit if no changes needed. If changes needed: `feat: support workspace_id query param on annotation page`
<!-- END_TASK_9 -->
<!-- END_SUBCOMPONENT_D -->

---

## UAT Steps

1. [ ] Ensure `.env` has `AUTH_MOCK=true` and `DATABASE_URL` configured
2. [ ] Run migrations: `uv run alembic upgrade head`
3. [ ] Start the app: `uv run python -m promptgrimoire`
4. [ ] Navigate to `/login` → click "Seed Test Data" button → verify notification confirms seeding
5. [ ] Click mock login for `admin@example.com`
6. [ ] Navigate to `/courses` → click "LAWS1100 - Contracts"
7. [ ] Verify: Week 1 and Week 2 visible with "Add Activity" buttons
8. [ ] Click "Add Activity" on Week 1 → enter title "Tutorial 1: Reading Contracts" and description "Read and annotate the sample contract" → submit
9. [ ] Verify: Activity appears under Week 1 on the course detail page
10. [ ] Click the Activity → Verify: navigates to annotation page with the template workspace
11. [ ] Run all tests: `uv run test-all`
12. [ ] Verify: All tests pass including Activity CRUD and placement field tests

## Evidence Required
- [ ] Screenshot of Activity visible under Week on course detail page
- [ ] Screenshot of annotation page loaded via Activity template workspace link
- [ ] Test output showing green for all tests
