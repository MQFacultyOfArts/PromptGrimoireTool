# Enrollment Table Refactor

**GitHub Issue:** [#325](https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/325)

## Summary

The manage enrollments page currently renders each enrolled student as an individual UI card, rebuilt from scratch whenever the list changes. This teardown-and-rebuild approach has two practical problems: Quasar toast notifications disappear mid-display when the DOM is destroyed underneath them, and adding or removing a single enrollment re-renders the entire list, producing a visible flash and issuing one database query per student (an N+1 pattern).

This refactor replaces the card list with a `ui.table` (Quasar QTable) backed by a single joined SQL query. The query fetches all enrollment data — display name, email, student ID, role, and enrollment date — in one round trip to PostgreSQL by joining the `course_enrollment` and `user` tables server-side. On the UI side, mutations (add-single enrollment, bulk XLSX upload, delete) now update the table by reassigning its `rows` property directly. Quasar diffs the row data and updates only the changed cells, leaving the surrounding DOM — and any in-flight notifications — intact.

## Definition of Done

1. **Enrollment list uses `ui.table`** — the `@ui.refreshable` card-per-enrollment pattern on the manage enrollments page is replaced with a paginated Quasar QTable.
2. **Single joined query** — enrollment data (user display name, email, student ID, role, enrolled date) fetched in one PostgreSQL query instead of N+1.
3. **Notification visibility** — `ui.notify` calls after bulk upload are visible in the browser (no DOM teardown race).
4. **Mutation refresh** — add-single, bulk upload, and delete all update the table via `table.rows = ...` (incremental DOM diff, no page rebuild).

## Acceptance Criteria

### enrollment-table-325.AC1: Joined Query
- **enrollment-table-325.AC1.1 Success:** `list_enrollment_rows` returns dicts with `email`, `display_name`, `student_id`, `role`, `created_at`, `user_id` keys
- **enrollment-table-325.AC1.2 Success:** Single SQL query (no N+1 — one query regardless of enrollment count)
- **enrollment-table-325.AC1.3 Edge:** Course with zero enrollments returns empty list

### enrollment-table-325.AC2: Table Rendering
- **enrollment-table-325.AC2.1 Success:** Table displays columns: Name, Email, Student ID, Role, Enrolled, Actions
- **enrollment-table-325.AC2.2 Success:** Table paginates at 25 rows per page
- **enrollment-table-325.AC2.3 Success:** Columns are sortable client-side

### enrollment-table-325.AC3: Mutation Refresh
- **enrollment-table-325.AC3.1 Success:** After bulk upload, table rows update to reflect new enrollments
- **enrollment-table-325.AC3.2 Success:** After add-single enrollment, table rows update
- **enrollment-table-325.AC3.3 Success:** After delete enrollment, table rows update (row removed)

### enrollment-table-325.AC4: Notification Visibility
- **enrollment-table-325.AC4.1 Success:** Successful bulk upload shows notification with enrollment summary
- **enrollment-table-325.AC4.2 Success:** Upload with all duplicates shows "already enrolled" notification
- **enrollment-table-325.AC4.3 Failure:** Invalid XLSX shows warning notification with error details

### enrollment-table-325.AC5: Access Control
- **enrollment-table-325.AC5.1 Success:** Students cannot see upload widget or table actions
- **enrollment-table-325.AC5.2 Success:** Instructors see full table with delete buttons

## Glossary

- **`@ui.refreshable`**: A NiceGUI decorator that marks a function for on-demand re-execution. When the refreshable is triggered, NiceGUI tears down and rebuilds the entire DOM subtree the function produced. Efficient for small lists; problematic when notifications or in-progress interactions live in the same subtree.
- **Quasar QTable (`ui.table`)**: A feature-complete data table component from the Quasar framework, which NiceGUI uses as its component library. QTable handles client-side pagination, sorting, and row diffing in JavaScript without requiring a server round trip.
- **DOM diffing**: When a component's data changes, Quasar compares the new row list against the previous one and updates only the changed elements in the browser's Document Object Model, rather than recreating the table from scratch.
- **N+1 query**: A database access pattern where fetching a list of N records is followed by N individual queries to fetch related data for each record. The current enrollment page calls `get_user_by_id()` once per enrollment row.
- **`body-cell-action` slot**: A Quasar QTable extension point that lets you inject arbitrary HTML (here, a delete button) into a named column for each row, while the other columns render automatically from row data.
- **`row_key`**: A QTable property identifying which field uniquely identifies each row. Required for stable DOM diffing — without it, Quasar cannot tell which rows changed versus which are new.
- **`ui.notify` / Quasar notification**: A transient toast message rendered in a fixed overlay layer. It survives DOM mutations to other parts of the page, but is destroyed if the component that triggered it is torn down before it expires.
- **`list_enrollment_rows()`**: The new data-layer function being introduced in `src/promptgrimoire/db/courses.py`. Returns a list of plain dicts ready for `ui.table`'s `rows` parameter.
- **NiceGUI User test**: An integration test that exercises NiceGUI page logic without a real browser, using NiceGUI's built-in `User` test client. Faster than Playwright E2E tests and sufficient for verifying data binding.
- **`data-testid`**: An HTML attribute used as a stable locator for Playwright E2E tests. The project convention requires all interactable elements to carry one; the new table uses `data-testid="enrollment-table"`.

## Architecture

Replace the `@ui.refreshable enrollments_list()` pattern with a `ui.table` backed by a single joined query.

**Data layer** — new function `list_enrollment_rows()` in `src/promptgrimoire/db/courses.py`:

```python
async def list_enrollment_rows(course_id: UUID) -> list[dict[str, Any]]:
```

Executes a single `SELECT ... JOIN` against `course_enrollment` and `user` tables. Returns a list of dicts with keys: `email`, `display_name`, `student_id`, `role`, `created_at` (ISO string), `user_id` (string, for delete action). PostgreSQL handles the join; no Python-side merging.

**UI layer** — `manage_enrollments_page()` in `src/promptgrimoire/pages/courses.py`:

- `ui.table` with columns: Name, Email, Student ID, Role, Enrolled, Actions
- `pagination=25` — all rows shipped to client, Quasar handles pagination/sorting in JavaScript
- `row_key='user_id'` for stable row identity
- Action column via `body-cell-action` slot with delete button per row
- `data-testid="enrollment-table"` on the table element

**Mutation pattern** — all three mutation paths (add-single, bulk upload, delete) call the same refresh:

```python
enrollment_table.rows = await list_enrollment_rows(cid)
```

This is a single assignment that triggers Quasar's DOM diffing. No container teardown. Notifications survive.

**Upload handler** — `_handle_enrol_upload` unchanged in logic. The `on_upload` callback refreshes the table after the handler completes. `upload_widget.reset()` called directly (no setTimeout hack).

## Existing Patterns

**`ui.table` usage:** No existing `ui.table` usage in the codebase. This introduces the pattern. Quasar QTable is a first-class NiceGUI component — well-documented and simpler than AG Grid for this use case.

**Joined queries:** The navigator uses complex `UNION ALL` CTEs with joins (`db/navigator.py`). This design uses a simpler single-table join — consistent with the project's SQLAlchemy `select()` query builder pattern.

**N+1 fix:** The current `_render_enrollment_card` does `get_user_by_id(e.user_id)` per row. This is the only N+1 pattern on the enrollments page. The joined query eliminates it.

**Divergence from `@ui.refreshable`:** Multiple pages use `@ui.refreshable` for dynamic lists. This design replaces it for enrollments because the refreshable teardown/rebuild destroys Quasar notifications and causes the "chonky" animation with large datasets. Other pages' refreshable patterns are not affected.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Joined Query

**Goal:** Single PostgreSQL query returning enrollment + user data as table-ready dicts.

**Components:**
- `list_enrollment_rows()` in `src/promptgrimoire/db/courses.py` — `SELECT` joining `course_enrollment` and `user`, returning `list[dict]`
- Unit test verifying correct dict structure, join correctness, ordering

**Dependencies:** None

**Covers:** enrollment-table-325.AC1 (joined query), enrollment-table-325.AC2 (correct data)

**Done when:** Test creates a course with enrollments, calls `list_enrollment_rows`, verifies returned dicts contain user email, display_name, student_id, role, created_at, user_id. Single query confirmed (no N+1).
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Table UI

**Goal:** Replace `@ui.refreshable` enrollment list with `ui.table` on manage enrollments page.

**Components:**
- Remove `@ui.refreshable async def enrollments_list()` and `_render_enrollment_card()` from `src/promptgrimoire/pages/courses.py`
- Add `ui.table` with column definitions, pagination, `data-testid="enrollment-table"`
- Action column with delete button via `body-cell-action` slot
- Wire all mutation callbacks (add-single, bulk upload, delete) to `table.rows = await list_enrollment_rows(cid)`
- Clean up upload handler: remove `setTimeout` JS hack, call `upload_widget.reset()` directly
- Remove diagnostic `logger.setLevel(logging.DEBUG)` and `ui.run_javascript(console.log...)` from upload handler

**Dependencies:** Phase 1 (query function)

**Covers:** enrollment-table-325.AC2 (table rendering), enrollment-table-325.AC3 (mutation refresh), enrollment-table-325.AC4 (notification visibility), enrollment-table-325.AC5 (access control)

**Done when:** NiceGUI User test confirms table renders with correct data. E2E test confirms upload shows notification and table updates. Delete button removes enrollment and refreshes table.
<!-- END_PHASE_2 -->

## Additional Considerations

**Scale:** All rows shipped to the client. With 1026 students (~100KB JSON), this is fine for an admin-only page. If a unit grows past ~5000 students, server-side pagination would be needed — but that's a separate design decision for when it becomes a real problem.

**Notification root cause:** If notifications still don't appear after this refactor, the root cause is definitively in NiceGUI's upload POST → background task → WebSocket outbox path, not DOM destruction. That would warrant a separate upstream investigation or workaround.
