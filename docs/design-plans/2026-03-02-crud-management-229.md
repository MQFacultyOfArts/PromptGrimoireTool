# CRUD Management for Weeks, Activities, Documents, and Units

**GitHub Issue:** [#229](https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/229)

## Summary

PromptGrimoire's course management UI currently allows instructors to create weeks, activities, and workspaces but provides no way to edit or delete them. This feature adds the full CRUD lifecycle across the hierarchy: units (courses), weeks, activities, workspaces, and individual documents. The work is scoped to two audiences — instructors managing course structure, and students managing their own workspace instances.

The central design decision is that deletion guards live in the database layer rather than the UI. Each delete function gains a `force` parameter; when `force=False` (the default), the function raises a typed exception if student workspaces exist underneath the target entity. The UI catches that exception and shows a count-bearing notification to the instructor. Admins can pass `force=True` to cascade through student work with an additional confirmation step. Document deletion adds a second layer: a `source_document_id` foreign key on `WorkspaceDocument` distinguishes template-cloned documents (protected from individual deletion) from user-uploaded ones (deletable). The UI suppresses the delete button for protected documents, and the DB function raises a typed exception as a defence-in-depth backstop.

## Definition of Done

1. **Instructors can edit week and activity metadata** (title, week_number, description) via the course management UI, with a warning dialog when the template has already been cloned by students.

2. **Instructors can delete weeks and activities** from the course management UI, blocked when student workspaces exist under them, with an admin-only cascade override (confirm dialog).

3. **Workspace owners can delete their own workspaces** (both cloned instances and loose workspaces), enabling "start over" workflows.

4. **Workspace owners can delete individual documents they uploaded**, preserving workspace tags. Template-cloned documents are protected from individual deletion.

5. **Document provenance is tracked** via a `source_document_id` FK on WorkspaceDocument, set during cloning, enabling the template-clone protection rule.

6. **Admins and unit convenors can delete units.** Convenor can delete their own unit; admins can delete any unit. Same cascade rules apply (blocked if student workspaces exist, admin override available).

7. **Course detail page UI cleanup:** Move settings cog from title area to the action bar alongside Add Week, Manage Enrollments, etc. All action buttons consistently styled and cogs labelled with text (e.g. "Unit Settings", "Activity Settings"), not icon-only.

## Acceptance Criteria

### crud-management-229.AC1: Edit week and activity metadata
- **crud-management-229.AC1.1 Success:** Instructor edits week title and week_number via dialog; changes persist after page refresh
- **crud-management-229.AC1.2 Success:** Instructor edits activity title and description via dialog; changes persist after page refresh
- **crud-management-229.AC1.3 Success:** Edit dialog pre-fills current values from the model
- **crud-management-229.AC1.4 Success:** Edit triggers broadcast refresh to other connected clients
- **crud-management-229.AC1.5 Edge:** Template clone warning shown when instructor clicks "Edit Template" on an activity with student clones
- **crud-management-229.AC1.6 Edge:** Template clone warning not shown when no students have cloned

### crud-management-229.AC2: Delete weeks and activities (guarded)
- **crud-management-229.AC2.1 Success:** Instructor deletes a week with no student workspaces; week and its activities are removed
- **crud-management-229.AC2.2 Success:** Instructor deletes an activity with no student workspaces; activity and template workspace are removed
- **crud-management-229.AC2.3 Failure:** Delete blocked with notification showing student count when student workspaces exist (force=False)
- **crud-management-229.AC2.4 Success:** Admin force-deletes a week with student workspaces; cascade removes all child entities
- **crud-management-229.AC2.5 Success:** Confirmation dialog shown before all destructive deletes
- **crud-management-229.AC2.6 Success:** UI refreshes and broadcasts after deletion

### crud-management-229.AC3: Workspace owners delete their own workspaces
- **crud-management-229.AC3.1 Success:** Owner deletes workspace from course detail page; "Start Activity" reappears
- **crud-management-229.AC3.2 Success:** Owner deletes workspace from navigator; card is removed
- **crud-management-229.AC3.3 Success:** Confirmation dialog shown before workspace deletion
- **crud-management-229.AC3.4 Failure:** Non-owner cannot see or trigger workspace delete
- **crud-management-229.AC3.5 Failure:** DB-level `delete_workspace()` raises PermissionError when user_id is not workspace owner (defence in depth)

### crud-management-229.AC4: Document deletion with provenance protection
- **crud-management-229.AC4.1 Success:** Owner deletes a user-uploaded document (source_document_id IS NULL); document and annotations removed, tags preserved
- **crud-management-229.AC4.2 Success:** After deletion, owner can upload a replacement document
- **crud-management-229.AC4.3 Failure:** Template-cloned document (source_document_id IS NOT NULL) has no delete button in UI
- **crud-management-229.AC4.4 Failure:** DB-level `delete_document()` raises ProtectedDocumentError for template-cloned documents (defence in depth)

### crud-management-229.AC5: Document provenance tracking
- **crud-management-229.AC5.1 Success:** Cloned documents have source_document_id set to the template document's ID
- **crud-management-229.AC5.2 Success:** User-uploaded documents have source_document_id as NULL
- **crud-management-229.AC5.3 Edge:** Pre-migration documents have NULL source_document_id (treated as user-uploaded)
- **crud-management-229.AC5.4 Edge:** Deleting a template source document sets clones' source_document_id to NULL (ON DELETE SET NULL)
- **crud-management-229.AC5.5 Edge:** Warning shown when deleting a template document that has clones: "X students have copies. Deleting makes their copies deletable."

### crud-management-229.AC6: Unit deletion
- **crud-management-229.AC6.1 Success:** Admin deletes a unit with no student workspaces
- **crud-management-229.AC6.2 Success:** Convenor (coordinator) deletes their own unit with no student workspaces
- **crud-management-229.AC6.3 Failure:** Delete blocked when student workspaces exist (same guard as weeks/activities)
- **crud-management-229.AC6.4 Success:** Admin force-deletes unit with student workspaces
- **crud-management-229.AC6.5 Failure:** Non-admin, non-convenor cannot see Delete Unit button

### crud-management-229.AC7: UI consistency and testability
- **crud-management-229.AC7.1 Success:** Settings cog in action bar labelled "Unit Settings" (not icon-only)
- **crud-management-229.AC7.2 Success:** Activity settings labelled "Activity Settings"
- **crud-management-229.AC7.3 Success:** All action buttons follow styling convention (primary/outline/negative)
- **crud-management-229.AC7.4 Success:** Course detail page uses page_layout() and wider content column
- **crud-management-229.AC7.5 Success:** All interactive elements have data-testid attributes (including previously missing ones)

## Glossary

- **Activity**: A unit of student work within a Week. Each Activity owns a template Workspace that instructors configure; students clone it to produce their own working copy.
- **Alembic**: A database migration tool for SQLAlchemy/SQLModel. The only sanctioned way to add or change columns in this project.
- **broadcast refresh**: After a mutation (edit, delete, publish), the server pushes a UI refresh event to all other browser tabs currently viewing the same page.
- **clone / clone_workspace_from_activity()**: Copying an instructor's template Workspace (documents, tags, structure) into a new student-owned Workspace. Source document IDs are stamped during this copy operation.
- **convenor / unit convenor**: The instructor who owns a unit (Australian university term for the person responsible for a course). Can delete their own unit but not others'.
- **CRDT**: Conflict-free Replicated Data Type (via `pycrdt`), used to store document annotations collaboratively. Deleting a document removes its associated CRDT data.
- **data-testid**: An HTML attribute placed on interactive elements so Playwright E2E tests can locate them without depending on visible text or CSS classes.
- **DeletionBlockedError**: Custom exception raised by DB delete functions when `force=False` and student workspaces exist under the target entity. Carries a count of affected workspaces.
- **defence in depth**: Multiple independent layers each enforce the same constraint. Here: UI hides the delete button, and the DB function independently raises `ProtectedDocumentError`.
- **NiceGUI**: The Python web UI framework used throughout this project. Dialogs, buttons, and page layout are constructed with NiceGUI components.
- **ON DELETE SET NULL**: PostgreSQL FK referential action. When the referenced row is deleted, the FK column in referencing rows is set to `NULL` rather than cascade-deleting them.
- **page_layout()**: Shared NiceGUI wrapper in `pages/layout.py` providing consistent page chrome (header, sidebar, content column width).
- **ProtectedDocumentError**: Custom exception raised by `delete_document()` when attempting to delete a template-cloned document.
- **Quasar**: Vue component library underlying NiceGUI. Button appearance controlled via Quasar props (`color`, `outline`, `flat`).
- **source_document_id**: Nullable UUID FK added to `WorkspaceDocument`. `NULL` = user-uploaded (deletable); non-NULL = cloned from template (protected).
- **SQLModel**: ORM combining Pydantic (validation) and SQLAlchemy (database access). Model fields map directly to database columns.
- **template Workspace**: Instructor-owned Workspace attached to an Activity. Students clone it; the original is never a student workspace.
- **xdist**: pytest plugin that distributes tests across multiple worker processes. Fixtures must be designed for cross-worker isolation.

## Architecture

### Approach: Guards in DB Delete Functions

Delete guard logic lives in the DB layer, not in UI handlers. Each delete function gains a `force: bool = False` parameter. When `force` is `False` and student workspaces exist under the target entity, the function raises `DeletionBlockedError` with a count of affected student workspaces. When `force` is `True` (admin override), deletion proceeds regardless.

This centralises enforcement — the UI cannot accidentally bypass guards — and makes guard logic independently testable via integration tests without touching NiceGUI.

### Key Query: `has_student_workspaces()`

`has_student_workspaces(activity_id: UUID) -> int` in `src/promptgrimoire/db/workspaces.py` counts non-template workspaces where `workspace.activity_id == activity_id`. The template workspace is excluded by checking `workspace.id != activity.template_workspace_id`. Returns a count (0 = safe to delete, >0 = blocked). Used by delete guards in `delete_week()`, `delete_activity()`, and `delete_course()`, and by the template clone warning in the UI.

### Convenor Detection for Unit Deletion

`delete_course()` takes a `user_id` parameter. The UI handler checks the user's enrollment role before calling: if `enrollment.role == "coordinator"` for this specific course, or if `is_privileged_user()` returns `True` (admin), deletion is permitted. The DB function itself enforces the student workspace guard; the role check is a UI-layer concern matching the existing pattern for `can_manage` checks in `courses.py`.

### Data Flow

```
UI handler (courses.py / navigator)
  │
  ├─ Edit: calls update_week() / update_activity() directly
  │
  ├─ Delete (guarded): calls delete_week() / delete_activity() / delete_course()
  │   ├─ force=False → DeletionBlockedError if student workspaces exist
  │   └─ force=True  → CASCADE proceeds (admin only)
  │
  ├─ Delete workspace: calls delete_workspace(workspace_id, user_id)
  │   ├─ user_id is not workspace owner → PermissionError (defence in depth)
  │   └─ user_id is owner → deletes workspace and all children
  │
  └─ Delete document: calls delete_document()
      ├─ source_document_id IS NOT NULL → ProtectedDocumentError
      └─ source_document_id IS NULL → deletes document + annotations, preserves tags
```

### Schema Change

Add `source_document_id` to `workspace_document`:
- Nullable UUID FK → `workspace_document.id`
- `ON DELETE SET NULL` — if the template source document is deleted, cloned copies survive but lose provenance (become deletable)
- Set during `clone_workspace_from_activity()` to point at the original template document
- `NULL` for user-uploaded documents and all pre-migration documents

### UI Button Styling Convention

Replace inconsistent `flat` buttons with a clear visual hierarchy:

| Button type | Quasar props | Visual |
|-------------|-------------|--------|
| Primary action (Add Week, Create) | `color=primary` | Filled blue |
| Secondary action (Manage Enrollments, Unit Settings, Activity Settings) | `outline color=primary` | Blue border |
| Destructive (Delete Week, Delete Unit) | `outline color=negative` | Red border |
| Cancel/Back | `flat` | Text-only (intentionally link-like) |

### Page Layout

Course detail page adopts `page_layout()` wrapper (from `src/promptgrimoire/pages/layout.py`) and a `courses.css` file following the navigator pattern. Content column uses `width: min(100%, 73rem)` for wider layout.

### Template Clone Warning

When an instructor clicks "Edit Template" on an activity that has student clones, an interstitial confirmation dialog warns: "X students have cloned this template. Changes here won't propagate to existing copies." The instructor can proceed or cancel.

## Existing Patterns

### DB Layer CRUD (followed)

Existing `delete_week()` (`src/promptgrimoire/db/weeks.py:187-201`) and `delete_activity()` (`src/promptgrimoire/db/activities.py:125-150`) already handle the tricky deletion order (Activity first to release RESTRICT FK, then template Workspace). This design extends them with guard logic rather than replacing them.

`update_week()` (`db/weeks.py:156-184`) and `update_activity()` (`db/activities.py:84-122`) already accept keyword arguments for all editable fields. No changes needed to these functions.

### Settings Dialogs (followed)

`open_course_settings()` and `open_activity_settings()` in `courses.py` establish the dialog pattern: `ui.dialog()` + `ui.card()`, inputs pre-filled from model, Save/Cancel buttons, async save handler that updates model and closes dialog. Edit dialogs for weeks and activities follow this exact pattern.

### Navigator Page Layout (followed)

Navigator uses `page_layout()` wrapper, custom CSS file, and `width: min(100%, 73rem)` content column. Course detail page adopts the same approach.

### Clone Workflow (extended)

`clone_workspace_from_activity()` (`db/workspaces.py:591-730`) copies documents with new UUIDs. This design extends the document copy loop to set `source_document_id` on each cloned document.

### Test Fixtures (followed)

Integration page tests in `courses-refactor-212` worktree (`tests/integration/pages/conftest.py`) provide database-seeded fixtures with xdist-safe auth injection. New CRUD tests follow this established pattern.

### `data-testid` Convention (followed)

All interactable elements get `data-testid` attributes per project convention (`docs/testing.md`). New elements follow existing naming patterns (e.g. `delete-week-btn`, `edit-activity-btn`). Existing elements missing testids (template button, cancel buttons, resume button, start activity button, back arrow) get them added.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Schema Migration & Document Provenance

**Goal:** Add `source_document_id` FK to WorkspaceDocument and wire it into cloning.

**Components:**
- Alembic migration adding `source_document_id` column to `workspace_document` table
- `src/promptgrimoire/db/models.py` — add `source_document_id` field to WorkspaceDocument model
- `src/promptgrimoire/db/workspaces.py` — update `clone_workspace_from_activity()` to set `source_document_id` on cloned documents

**Dependencies:** None (first phase)

**Done when:** Migration applies cleanly; cloned documents have `source_document_id` set; existing documents have `NULL`; tests verify provenance is tracked through cloning
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Delete Guards & Exceptions

**Goal:** Centralised guard logic in DB delete functions with custom exceptions.

**Components:**
- `src/promptgrimoire/db/exceptions.py` (new) — `DeletionBlockedError(student_workspace_count)` and `ProtectedDocumentError`
- `src/promptgrimoire/db/workspaces.py` — new `has_student_workspaces(activity_id) -> int` query; extend `delete_workspace()` with `user_id` parameter and ownership check (raises `PermissionError` for non-owners)
- `src/promptgrimoire/db/weeks.py` — extend `delete_week()` with `force` parameter and student workspace check via `has_student_workspaces()`
- `src/promptgrimoire/db/activities.py` — extend `delete_activity()` with `force` parameter and student workspace check
- `src/promptgrimoire/db/courses.py` — new `delete_course()` with same guard pattern; takes `user_id` for convenor detection (UI checks enrollment role)
- `src/promptgrimoire/db/workspace_documents.py` — new `delete_document()` that raises `ProtectedDocumentError` for template-cloned documents

**Dependencies:** Phase 1 (source_document_id must exist for delete_document guard)

**Done when:** Guard functions raise correct exceptions when student work exists; force=True bypasses guards; delete_document rejects template copies; delete_workspace rejects non-owners; all tests pass
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Course Detail Page Layout & Button Styling

**Goal:** Adopt page_layout(), widen content area, and establish consistent button styling across the course detail page.

**Components:**
- `src/promptgrimoire/static/courses.css` (new) — content column width, following navigator.css pattern
- `src/promptgrimoire/pages/courses.py` — adopt `page_layout()` wrapper; refactor action bar with consistent button styling; move settings cog to action bar with "Unit Settings" label; label "Activity Settings" cog; add `data-testid` to all interactive elements currently missing them (template button with `template-btn-{act.id}`, cancel buttons, back arrow, resume button, start activity button)

**Dependencies:** None (can proceed in parallel with Phase 1-2, but sequenced here for cleaner review)

**Done when:** Course detail page uses page_layout(); all buttons follow styling convention; all interactive elements have data-testid; visual review confirms consistent appearance
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Week & Activity Edit Dialogs

**Goal:** Instructors can edit week and activity metadata inline.

**Components:**
- `src/promptgrimoire/pages/courses.py` — new `open_edit_week()` dialog (week_number + title inputs); new `open_edit_activity()` dialog (title + description inputs); Edit buttons on week cards and activity rows
- Template clone warning: `has_student_workspaces()` check in Edit Template button handler, interstitial dialog before navigating to annotation workspace

**Dependencies:** Phase 3 (button styling established)

**Done when:** Weeks and activities can be edited via dialog; changes persist and refresh the UI; template edit warning shown when students have cloned; tests verify edit persistence and warning display
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Week, Activity & Unit Delete UI

**Goal:** Instructors can delete weeks, activities, and units from the course management UI with appropriate guards.

**Components:**
- `src/promptgrimoire/pages/courses.py` — Delete buttons on week cards and activity rows; confirmation dialogs; `DeletionBlockedError` handling (shows student count in notification); admin force-delete with cascade warning; "Delete Unit" button in action bar (convenor/admin only); `delete_course()` integration

**Dependencies:** Phase 2 (guard logic), Phase 3 (button styling)

**Done when:** Delete buttons appear for authorised users; guarded deletes show blocking notification with student count; unguarded deletes succeed after confirmation; admin override works; UI refreshes after deletion; tests verify all paths
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Workspace Deletion

**Goal:** Workspace owners can delete their own workspaces from both the course detail page and navigator.

**Components:**
- `src/promptgrimoire/pages/courses.py` — delete icon next to Resume button; confirmation dialog ("Delete your workspace? You can start fresh by cloning again."); after deletion, workspace disappears and "Start Activity" reappears
- `src/promptgrimoire/pages/navigator/_cards.py` — delete icon on owned workspace cards; confirmation dialog; card removal after deletion

**Dependencies:** Phase 3 (button styling)

**Done when:** Workspace delete available on both course detail and navigator; confirmation dialog shown; workspace removed from UI after deletion; "Start Activity" reappears on course page; tests verify both entry points
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Document Deletion

**Goal:** Workspace owners can delete user-uploaded documents; template-cloned documents are protected.

**Components:**
- `src/promptgrimoire/pages/annotation/` — delete button on user-uploaded documents in workspace sidebar/document list; no delete button on template-cloned documents; confirmation dialog ("Delete [title]? Annotations will be removed. Tags preserved."); UI refresh after deletion
- Integration with `delete_document()` from Phase 2

**Dependencies:** Phase 1 (source_document_id), Phase 2 (delete_document function)

**Done when:** Delete button appears only on user-uploaded documents; template copies have no delete option; deletion removes document and annotations; tags survive; user can upload replacement; tests verify protection and deletion
<!-- END_PHASE_7 -->

## Additional Considerations

**Pre-migration documents:** All documents created before the `source_document_id` migration will have `NULL`, making them deletable. This is correct — they predate the provenance system and there's no way to retroactively determine their origin. If this becomes a problem, a data migration could match documents by content hash, but this is not in scope.

**Cascade semantics on source document deletion:** `ON DELETE SET NULL` means if an instructor deletes a template document, all student clones of that document lose their `source_document_id` and become deletable. This is intentional — if the instructor removed the template document, there's no reason to protect copies of it. However, since this is irreversible, the UI shows a warning when deleting a template document that has been cloned: "X students have copies of this document. Deleting it will make their copies deletable." This prevents accidental unprotection.

**Broadcast after mutations:** Edit and delete operations on weeks/activities must call `_broadcast_weeks_refresh()` to update other connected clients viewing the same course, following the existing pattern from publish/unpublish.
