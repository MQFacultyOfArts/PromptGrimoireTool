# Workspace Sharing & Visibility — Phase 1: Data Model & Migration

**Goal:** Schema changes, reference data, and PlacementContext resolution for all subsequent phases.

**Architecture:** Single Alembic migration adds columns to Workspace, Activity, and Course tables, inserts `peer` permission row. Model updates mirror the migration. `_resolve_course_placement` fixed to propagate all tri-state course defaults (not just for anonymous_sharing — generalised fix).

**Tech Stack:** SQLModel, Alembic, PostgreSQL

**Scope:** 7 phases from original design (phase 1 of 7)

**Codebase verified:** 2026-02-19

**Dependencies:** None (first phase)

---

## Acceptance Criteria Coverage

This phase implements and tests:

### workspace-sharing-97.AC1: Peer permission level
- **workspace-sharing-97.AC1.1 Success:** Permission table contains 'peer' with level 15

### workspace-sharing-97.AC4: Anonymity control
- **workspace-sharing-97.AC4.1 Success:** Activity.anonymous_sharing=True hides author names from peer viewers
- **workspace-sharing-97.AC4.2 Success:** Activity.anonymous_sharing=None inherits Course.default_anonymous_sharing

### workspace-sharing-97.AC5: Workspace titles
- **workspace-sharing-97.AC5.1 Success:** Workspace has optional title field (VARCHAR 200, nullable)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Update SQLModel classes with new fields

**Verifies:** workspace-sharing-97.AC5.1 (workspace title field), workspace-sharing-97.AC1.1 (peer permission data model support)

**Files:**
- Modify: `src/promptgrimoire/db/models.py:292-335` (Workspace class)
- Modify: `src/promptgrimoire/db/models.py:241-289` (Activity class)
- Modify: `src/promptgrimoire/db/models.py:121-169` (Course class)

**Implementation:**

Add to the **Workspace** class (after `enable_save_as_draft`, before `created_at`):
- `title: str | None = Field(default=None, max_length=200)` — optional display name
- `shared_with_class: bool = Field(default=False)` — student opt-in for peer discovery

Add to the **Activity** class (after `allow_sharing`, before `created_at`):
- `anonymous_sharing: bool | None = Field(default=None)` — tri-state: None=inherit from course, True/False=override. Follow the exact docstring pattern from `copy_protection` and `allow_sharing`.

Add to the **Course** class (after `default_allow_sharing`, before `default_instructor_permission`):
- `default_anonymous_sharing: bool = Field(default=False)` — course-level anonymity default

**Testing:**

No dedicated tests — type checker verifies field types, Alembic migration (Task 2) verifies schema. The `test_db_schema.py` unit test checks table registration but not column-level details.

**Verification:**
Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat(models): add workspace sharing and anonymity fields`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create Alembic migration

**Verifies:** workspace-sharing-97.AC1.1, workspace-sharing-97.AC5.1

**Files:**
- Create: `alembic/versions/<revision>_add_sharing_anonymity_columns.py`

**Implementation:**

Generate migration with `alembic revision --autogenerate -m "add sharing anonymity columns"`, then manually add the `peer` permission INSERT.

The migration must:
1. Add `title` (VARCHAR 200, nullable) to `workspace`
2. Add `shared_with_class` (BOOLEAN, NOT NULL, server_default `false`) to `workspace`
3. Add `anonymous_sharing` (BOOLEAN, nullable) to `activity`
4. Add `default_anonymous_sharing` (BOOLEAN, NOT NULL, server_default `false`) to `course`
5. INSERT `('peer', 15)` into `permission` table

Follow existing patterns from prior migrations:
- `nullable=True` for tri-state fields (no server default)
- `nullable=False, server_default=sa.text("false")` for boolean defaults
- `op.execute("INSERT INTO permission ...")` for reference data

Downgrade must reverse all operations: drop columns, DELETE the peer row.

**Testing:**

Integration test verifying the peer permission row exists in the reference table. Follow the pattern in `tests/integration/test_acl_reference_tables.py`:
- Test class: `TestPeerPermission`
- Verify `peer` row exists with level 15
- Verify level 15 uniqueness constraint holds (existing constraint `uq_permission_level`)

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass including new peer permission test

**Commit:** `feat(db): add sharing/anonymity columns and peer permission`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Add anonymous_sharing to PlacementContext and resolution

**Verifies:** workspace-sharing-97.AC4.1, workspace-sharing-97.AC4.2

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py:105-141` (PlacementContext dataclass)
- Modify: `src/promptgrimoire/db/workspaces.py:182-222` (`_resolve_activity_placement`)
- Modify: `src/promptgrimoire/db/workspaces.py:225-237` (`_resolve_course_placement`)

**Implementation:**

1. Add `anonymous_sharing: bool = False` field to `PlacementContext` (after `allow_sharing`, with matching docstring style).

2. In `_resolve_activity_placement`: add tri-state resolution for `anonymous_sharing` following the exact pattern of `copy_protection` and `allow_sharing`:
   ```python
   if activity.anonymous_sharing is not None:
       resolved_anon = activity.anonymous_sharing
   else:
       resolved_anon = course.default_anonymous_sharing
   ```
   Pass `anonymous_sharing=resolved_anon` to the PlacementContext constructor.

3. In `_resolve_course_placement`: generalise to propagate ALL course defaults. Currently this function only returns `course_code` and `course_name`. Update it to also pass:
   - `copy_protection=course.default_copy_protection`
   - `allow_sharing=course.default_allow_sharing`
   - `anonymous_sharing=course.default_anonymous_sharing`

**Testing:**

Integration tests in a new file `tests/integration/test_anonymous_sharing_resolution.py`. Follow the pattern from `tests/integration/test_sharing_controls.py` (which tests tri-state allow_sharing inheritance).

Tests must verify:
- workspace-sharing-97.AC4.1: Activity with `anonymous_sharing=True` → PlacementContext has `anonymous_sharing=True`
- workspace-sharing-97.AC4.2: Activity with `anonymous_sharing=None` → inherits `course.default_anonymous_sharing`
- Activity with `anonymous_sharing=False` → PlacementContext has `anonymous_sharing=False` (explicit override)
- Course-placed workspace (no activity_id) → PlacementContext inherits `course.default_anonymous_sharing`
- Course-placed workspace → also inherits `default_copy_protection` and `default_allow_sharing` (generalised fix)
- Loose workspace (no activity_id, no course_id) → PlacementContext has `anonymous_sharing=False` (default)

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `feat(workspaces): resolve anonymous_sharing and fix course placement defaults`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update test_sharing_controls for generalised course placement

**Verifies:** workspace-sharing-97.AC4.2 (regression from generalised course placement fix)

**Files:**
- Modify: `tests/integration/test_sharing_controls.py`

**Implementation:**

The existing `test_sharing_controls.py` tests `allow_sharing` tri-state resolution. Since `_resolve_course_placement` now propagates `default_allow_sharing`, any existing tests for course-placed workspaces may need updating if they previously expected `allow_sharing=False` (the old default).

Review existing tests and update expectations if the generalised fix changes their expected output.

**Testing:**

Run the existing test file — if tests pass without changes, no modification needed. If any fail due to the `_resolve_course_placement` fix, update expectations to match the new (correct) behaviour.

**Verification:**
Run: `uv run pytest tests/integration/test_sharing_controls.py -v`
Expected: All tests pass

**Commit:** `test: update sharing controls for generalised course placement defaults`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->
