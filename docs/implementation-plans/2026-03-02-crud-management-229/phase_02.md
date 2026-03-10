# CRUD Management Implementation Plan - Phase 2: Delete Guards & Exceptions

**Goal:** Centralised guard logic in DB delete functions with custom exceptions, ownership checks, and template workspace cleanup.

**Architecture:** Each delete function gains a `force: bool = False` parameter. When `force` is False and student workspaces exist, the function raises `DeletionBlockedError`. Document deletion raises `ProtectedDocumentError` for template-cloned docs. Workspace deletion verifies ownership via ACL query. Week and course deletion collect and clean up orphaned template workspaces after cascade.

**Tech Stack:** SQLModel, PostgreSQL, pytest (integration tests against real DB)

**Scope:** Phase 2 of 7 from original design

**Codebase verified:** 2026-03-02

**Testing documentation:** `docs/testing.md`, `CLAUDE.md` (async fixture rule, E2E locator convention, TDD mandate)

---

## Acceptance Criteria Coverage

This phase implements and tests:

### crud-management-229.AC2: Delete weeks and activities (guarded)
- **crud-management-229.AC2.1 Success:** Instructor deletes a week with no student workspaces; week and its activities are removed
- **crud-management-229.AC2.2 Success:** Instructor deletes an activity with no student workspaces; activity and template workspace are removed
- **crud-management-229.AC2.3 Failure:** Delete blocked with notification showing student count when student workspaces exist (force=False)
- **crud-management-229.AC2.4 Success:** Admin force-deletes a week with student workspaces; cascade removes all child entities

### crud-management-229.AC3: Workspace owners delete their own workspaces
- **crud-management-229.AC3.5 Failure:** DB-level `delete_workspace()` raises PermissionError when user_id is not workspace owner (defence in depth)

### crud-management-229.AC4: Document deletion with provenance protection
- **crud-management-229.AC4.4 Failure:** DB-level `delete_document()` raises ProtectedDocumentError for template-cloned documents (defence in depth)

### crud-management-229.AC6: Unit deletion
- **crud-management-229.AC6.1 Success:** Admin deletes a unit with no student workspaces
- **crud-management-229.AC6.3 Failure:** Delete blocked when student workspaces exist (same guard as weeks/activities)
- **crud-management-229.AC6.4 Success:** Admin force-deletes unit with student workspaces

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create exceptions module

**Files:**
- Create: `src/promptgrimoire/db/exceptions.py`

**Implementation:**

Create two custom exception classes:

```python
"""Custom exceptions for database CRUD guard logic."""

from __future__ import annotations


class DeletionBlockedError(Exception):
    """Raised when deletion is blocked by existing student workspaces.

    Attributes:
        student_workspace_count: Number of student workspaces blocking deletion.
    """

    def __init__(self, student_workspace_count: int) -> None:
        self.student_workspace_count = student_workspace_count
        super().__init__(
            f"Deletion blocked: {student_workspace_count} student workspace(s) exist"
        )


class ProtectedDocumentError(Exception):
    """Raised when attempting to delete a template-cloned document.

    Template-cloned documents (source_document_id IS NOT NULL) are protected
    from individual deletion as a defence-in-depth measure.
    """
```

**Verification:**

Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add DeletionBlockedError and ProtectedDocumentError exceptions`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add has_student_workspaces() query

**Verifies:** (supports AC2.3, AC6.3 — guard logic building block)

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py` (add new function after `delete_workspace()` around line 310)

**Implementation:**

Add a function that counts non-template workspaces for a given activity. The template workspace is identified by `activity.template_workspace_id` — any other workspace with matching `activity_id` is a student clone.

```python
async def has_student_workspaces(activity_id: UUID) -> int:
    """Count student (non-template) workspaces for an activity.

    Returns 0 if no student workspaces exist (safe to delete),
    or the count of student workspaces (deletion should be blocked).
    """
    from promptgrimoire.db.models import Activity

    async with get_session() as session:
        activity = await session.get(Activity, activity_id)
        if not activity:
            return 0

        result = await session.exec(
            select(func.count())
            .select_from(Workspace)
            .where(
                Workspace.activity_id == activity_id,
                Workspace.id != activity.template_workspace_id,
            )
        )
        return result.one()
```

Requires adding `from sqlalchemy import func` to the imports at the top of the file if not already present.

**Testing:**

- Create an activity with template workspace, call `has_student_workspaces()` — should return 0
- Clone the activity for a user, call again — should return 1
- Clone for a second user — should return 2
- Activity not found — should return 0

**Verification:**

Run: `uv run test-changed`
Expected: All tests pass

**Commit:** `feat: add has_student_workspaces() query for delete guards`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Extend delete_activity() with force parameter and guard

**Verifies:** crud-management-229.AC2.2, crud-management-229.AC2.3

**Files:**
- Modify: `src/promptgrimoire/db/activities.py:125-150` (existing `delete_activity()`)

**Implementation:**

Extend the existing `delete_activity()` signature to accept `force: bool = False`. Before the existing deletion logic, add a guard that calls `has_student_workspaces()`:

```python
async def delete_activity(activity_id: UUID, *, force: bool = False) -> bool:
```

Guard logic (insert before existing deletion code):
1. Call `has_student_workspaces(activity_id)` to get student count
2. If count > 0 and `force` is False, raise `DeletionBlockedError(count)`
3. If count > 0 and `force` is True, proceed with deletion (cascade)
4. If count == 0, proceed regardless of `force`

The existing deletion order (Activity first, then template workspace) remains unchanged.

Import `DeletionBlockedError` from `promptgrimoire.db.exceptions` and `has_student_workspaces` from `promptgrimoire.db.workspaces`.

**Testing:**

Tests must verify:
- crud-management-229.AC2.2: Delete activity with no student workspaces (force=False) — succeeds, both activity and template workspace removed
- crud-management-229.AC2.3: Delete activity with student workspaces (force=False) — raises `DeletionBlockedError` with correct count
- Force-delete activity with student workspaces (force=True) — succeeds, activity and template workspace removed, student workspaces have `activity_id = NULL`

**Verification:**

Run: `uv run test-changed`
Expected: All tests pass

**Commit:** `feat: add delete guard to delete_activity()`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Extend delete_week() with force parameter, guard, and template cleanup

**Verifies:** crud-management-229.AC2.1, crud-management-229.AC2.3, crud-management-229.AC2.4

**Files:**
- Modify: `src/promptgrimoire/db/weeks.py:187-201` (existing `delete_week()`)

**Implementation:**

Extend signature to `async def delete_week(week_id: UUID, *, force: bool = False) -> bool`.

The implementation must:
1. Fetch the week
2. Query all activities for this week (use `list_activities_for_week()` from `db/activities.py`)
3. For each activity, call `has_student_workspaces()` and sum the counts
4. If total > 0 and `force` is False, raise `DeletionBlockedError(total)`
5. Collect all `activity.template_workspace_id` values before deletion
6. Delete the week (CASCADE removes activities, SET NULL on student workspaces)
7. Clean up orphaned template workspaces by deleting each collected template workspace

This fixes the existing template workspace orphan issue — previously, `delete_week()` relied solely on CASCADE which left template workspaces orphaned.

**Testing:**

Tests must verify:
- crud-management-229.AC2.1: Delete week with no student workspaces — week, activities, AND template workspaces all removed
- crud-management-229.AC2.3: Delete week containing activities with student workspaces (force=False) — raises `DeletionBlockedError` with total count across all activities
- crud-management-229.AC2.4: Force-delete week with student workspaces — week, activities, template workspaces all removed; student workspaces survive with `activity_id = NULL`
- Template workspace cleanup: After week deletion, verify no orphaned template workspaces remain (query by collected IDs)

**Important: student workspace behaviour under force=True.** When `force=True`, student workspaces are NOT deleted — they are orphaned with `activity_id = NULL` (FK SET NULL). This is intentional per the design: student workspaces belong to students and are only deletable by their owners (Phase 6). The force-delete removes the course structure (weeks, activities, template workspaces) but preserves student work as standalone workspaces.

**Verification:**

Run: `uv run test-changed`
Expected: All tests pass

**Commit:** `feat: add delete guard and template cleanup to delete_week()`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 5-6) -->
<!-- START_TASK_5 -->
### Task 5: Add delete_course() with guard and template cleanup

**Verifies:** crud-management-229.AC6.1, crud-management-229.AC6.3, crud-management-229.AC6.4

**Files:**
- Modify: `src/promptgrimoire/db/courses.py` (add new function, e.g. after `archive_course()` at line 155)

**Implementation:**

Create `delete_course()` following the same guard pattern as `delete_week()`:

```python
async def delete_course(course_id: UUID, *, force: bool = False) -> bool:
```

The implementation must:
1. Fetch the course
2. Query all activities across all weeks in the course (join Week → Activity or use `list_activities_for_course()` from `db/activities.py` if it exists — investigation confirmed `list_activities_for_course()` exists)
3. For each activity, call `has_student_workspaces()` and sum the counts
4. If total > 0 and `force` is False, raise `DeletionBlockedError(total)`
5. Collect all `activity.template_workspace_id` values
6. Delete the course (CASCADE: course → weeks → activities; SET NULL on student workspace activity_ids)
7. Clean up orphaned template workspaces

Note: the design mentions `user_id` parameter for convenor detection, but investigation confirms the role check is a UI-layer concern (matching the existing `can_manage` pattern in `pages/courses.py`). The DB function only enforces the student workspace guard.

Import `DeletionBlockedError` from `promptgrimoire.db.exceptions`.

**Testing:**

Tests must verify:
- crud-management-229.AC6.1: Delete course with no student workspaces — course, weeks, activities, template workspaces all removed
- crud-management-229.AC6.3: Delete course with student workspaces (force=False) — raises `DeletionBlockedError` with total count
- crud-management-229.AC6.4: Force-delete course with student workspaces — everything removed, student workspaces survive with `activity_id = NULL`
- Verify `archive_course()` still works independently (regression check — should still soft-delete without affecting children)

**Verification:**

Run: `uv run test-changed`
Expected: All tests pass

**Commit:** `feat: add delete_course() with guard and template cleanup`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Extend delete_workspace() with ownership check

**Verifies:** crud-management-229.AC3.5

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py:300-309` (existing `delete_workspace()`)

**Implementation:**

Extend signature to add optional `user_id` parameter:

```python
async def delete_workspace(workspace_id: UUID, *, user_id: UUID | None = None) -> None:
```

When `user_id` is provided:
1. Query ACLEntry for `(workspace_id, user_id, permission="owner")`
2. If no matching ACLEntry found, raise `PermissionError("User does not own this workspace")`
3. If found, proceed with existing deletion logic

When `user_id` is `None`, the function behaves as before (no ownership check) — this preserves backward compatibility for internal callers like `delete_activity()` which delete template workspaces without a user context.

Import `ACLEntry` from `promptgrimoire.db.models` and use `select(ACLEntry).where(...)`.

**Testing:**

Tests must verify:
- crud-management-229.AC3.5: Call `delete_workspace(ws_id, user_id=non_owner)` — raises `PermissionError`
- Owner deletes workspace — succeeds, workspace and children removed
- `user_id=None` (backward compat) — no ownership check, succeeds
- Template workspace deletion from `delete_activity()` still works (regression — no user_id passed)

**Verification:**

Run: `uv run test-changed`
Expected: All tests pass

Run: `uv run test-all`
Expected: No regressions (existing callers of delete_workspace pass no user_id)

**Commit:** `feat: add ownership check to delete_workspace()`
<!-- END_TASK_6 -->
<!-- END_SUBCOMPONENT_C -->

<!-- START_SUBCOMPONENT_D (tasks 7-8) -->
<!-- START_TASK_7 -->
### Task 7: Add delete_document() with provenance protection

**Verifies:** crud-management-229.AC4.4

**Files:**
- Modify: `src/promptgrimoire/db/workspace_documents.py` (add new function after `reorder_documents()` at line 165)

**Implementation:**

```python
async def delete_document(document_id: UUID) -> bool:
```

The implementation must:
1. Fetch the document by ID
2. If not found, return False
3. If `source_document_id is not None`, raise `ProtectedDocumentError` (template-cloned document)
4. If `source_document_id is None`, delete the document and return True

Import `ProtectedDocumentError` from `promptgrimoire.db.exceptions`.

Note: deleting a document CASCADE-deletes associated CRDT data (via FK constraints). Tags on the workspace are preserved because tags belong to the workspace, not the document.

**Testing:**

Tests must verify:
- crud-management-229.AC4.4: Call `delete_document()` on a template-cloned document (source_document_id IS NOT NULL) — raises `ProtectedDocumentError`
- Delete a user-uploaded document (source_document_id IS NULL) — succeeds, document removed
- Delete non-existent document — returns False
- After deletion, other documents in the workspace still exist
- After deletion, workspace tags still exist

Note: these tests depend on Phase 1's `source_document_id` field existing. To test with a template-cloned document, clone a workspace and verify the cloned document has `source_document_id` set, then attempt to delete it.

**Verification:**

Run: `uv run test-changed`
Expected: All tests pass

**Commit:** `feat: add delete_document() with provenance protection`
<!-- END_TASK_7 -->

<!-- START_TASK_8 -->
### Task 8: Integration tests for all delete guards

**Verifies:** crud-management-229.AC2.1, crud-management-229.AC2.2, crud-management-229.AC2.3, crud-management-229.AC2.4, crud-management-229.AC3.5, crud-management-229.AC4.4, crud-management-229.AC6.1, crud-management-229.AC6.3, crud-management-229.AC6.4

**Files:**
- Create: `tests/integration/test_delete_guards.py`

**Testing:**

This is a comprehensive test file covering all guard logic. Follow the project's test patterns:
- Module-level `pytestmark` skip guard
- `from __future__ import annotations`
- Class-based organisation by function under test
- UUID-isolated test data via helper functions

Classes to implement:

**`TestDeleteActivityGuard`** — AC2.2, AC2.3:
- Activity with no student workspaces: delete succeeds
- Activity with student workspaces, force=False: `DeletionBlockedError` with correct count
- Activity with student workspaces, force=True: delete succeeds

**`TestDeleteWeekGuard`** — AC2.1, AC2.3, AC2.4:
- Week with no student workspaces: delete succeeds, template workspaces cleaned up
- Week with student workspaces across multiple activities, force=False: `DeletionBlockedError` with aggregate count
- Week force-delete: cascades and cleans up template workspaces

**`TestDeleteCourseGuard`** — AC6.1, AC6.3, AC6.4:
- Course with no student workspaces: delete succeeds
- Course with student workspaces, force=False: blocked
- Course force-delete: cascades

**`TestDeleteWorkspaceOwnership`** — AC3.5:
- Non-owner raises `PermissionError`
- Owner succeeds
- No user_id (backward compat) succeeds

**`TestDeleteDocumentProtection`** — AC4.4:
- Template-cloned doc raises `ProtectedDocumentError`
- User-uploaded doc deletes successfully

Helper functions needed:
- `_make_course_week_activity()` — creates full hierarchy
- `_clone_for_user(activity_id)` — creates user and clones workspace
- `_upload_document(workspace_id)` — adds a user-uploaded document

**Verification:**

Run: `uv run test-changed`
Expected: All guard tests pass

Run: `uv run test-all`
Expected: No regressions

**Commit:** `test: add comprehensive integration tests for delete guards`
<!-- END_TASK_8 -->
<!-- END_SUBCOMPONENT_D -->
