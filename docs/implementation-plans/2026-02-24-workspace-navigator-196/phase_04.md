# Workspace Navigator Implementation Plan — Phase 4: Navigator Page (Core)

**Goal:** Build the navigator NiceGUI page at `/` that renders workspace data as a searchable, sectioned list — replacing the current welcome page.

**Architecture:** The page uses `page_layout` for standard header/drawer, calls `load_navigator_page()` for data, groups `NavigatorRow` objects by section, and renders workspace entries with navigation and clone actions. Anonymisation is applied at render time using pre-loaded course/activity context.

**Tech Stack:** NiceGUI (page_route, ui.refreshable, Quasar components), SQLModel, existing data loader from Phase 3.

**Scope:** Phase 4 of 8 (phases 1-3 cover FTS, load-test data, SQL query; phases 4-8 cover page, search, rename, pagination, chrome/i18n)

**Codebase verified:** 2026-02-25

---

## Acceptance Criteria Coverage

This phase implements and tests:

### workspace-navigator-196.AC1: Navigator page renders all sections
- **workspace-navigator-196.AC1.1 Success:** Student sees "My Work" with all owned workspaces grouped by unit > week > activity
- **workspace-navigator-196.AC1.2 Success:** Student sees "Unstarted Work" with all published activities they haven't started
- **workspace-navigator-196.AC1.3 Success:** Student sees "Shared With Me" with workspaces shared via explicit ACL (editor/viewer)
- **workspace-navigator-196.AC1.4 Success:** Student sees "Shared in [Unit]" per enrolled unit, with peer workspaces grouped by anonymised student
- **workspace-navigator-196.AC1.5 Success:** Instructor sees "Shared in [Unit]" with all student workspaces grouped by real student name
- **workspace-navigator-196.AC1.6 Success:** Loose workspaces (no activity) appear under "Unsorted" within each student grouping
- **workspace-navigator-196.AC1.7 Edge:** Empty sections (no shared workspaces, no unstarted work) are hidden, not rendered empty
- **workspace-navigator-196.AC1.8 Edge:** Student enrolled in multiple units sees separate "Shared in [Unit]" section per unit

### workspace-navigator-196.AC2: Workspace navigation
- **workspace-navigator-196.AC2.1 Success:** Clicking workspace title navigates to `/annotation?workspace_id=<uuid>`
- **workspace-navigator-196.AC2.2 Success:** Clicking action button (Resume/Open/View) navigates to workspace
- **workspace-navigator-196.AC2.3 Success:** Clicking [Start] on unstarted activity clones template and navigates to new workspace
- **workspace-navigator-196.AC2.4 Success:** Each workspace entry shows last edit date (`updated_at`)
- **workspace-navigator-196.AC2.5 Failure:** Unauthenticated user redirected to login, not shown navigator

### workspace-navigator-196.AC5: Cursor pagination (initial load)
- **workspace-navigator-196.AC5.1 Success:** Initial load shows first 50 rows across all sections
- **workspace-navigator-196.AC5.4 Edge:** Total rows fewer than 50 — loads all in one page, no "Load more"

---

## Codebase Context for Executor

**Key files to read before implementing:**
- `src/promptgrimoire/pages/index.py` — Current page at `/` being replaced (38 lines). Shows auth pattern and `page_layout` usage.
- `src/promptgrimoire/pages/registry.py:36-82` — `@page_route` decorator. Parameters: route, title, icon, category, requires_auth, order.
- `src/promptgrimoire/pages/layout.py:62-131` — `page_layout` context manager. Provides header + drawer + content area.
- `src/promptgrimoire/db/navigator.py:28-57` — `NavigatorRow` dataclass and `NavigatorCursor` NamedTuple.
- `src/promptgrimoire/db/navigator.py:263-349` — `load_navigator_page()` function signature and return type.
- `src/promptgrimoire/db/courses.py:234-249` — `list_user_enrollments(user_id)` returns `list[CourseEnrollment]`.
- `src/promptgrimoire/db/workspaces.py:591-727` — `clone_workspace_from_activity(activity_id, user_id)` returns `(Workspace, dict[UUID, UUID])`.
- `src/promptgrimoire/auth/__init__.py:39-52` — `is_privileged_user(auth_user)` checks admin + instructor/stytch_admin roles.
- `src/promptgrimoire/auth/anonymise.py:36-88` — `anonymise_author()` with 7 parameters. Resolution chain: no-anon → privileged viewer → privileged author → self → legacy → coolname.
- `src/promptgrimoire/pages/courses.py:75-112` — `_build_peer_map()` shows anonymisation pattern with `resolve_tristate()`.
- `src/promptgrimoire/pages/courses.py:540-550` — Clone and navigate pattern for starting activities.
- `docs/testing.md` — Full testing guidelines. Integration tests use real PostgreSQL, skip guard pattern.
- `tests/conftest.py` — `db_session` fixture, `db_schema_guard`, canary mechanism.
- `tests/integration/conftest.py` — `reset_db_engine_per_test` autouse fixture.

**Auth pattern:**
```python
user = app.storage.user.get("auth_user")
# Returns dict: {"user_id": str, "name": str, "email": str, "is_admin": bool, "roles": list[str]}
```

**Permission levels:** owner=30, editor=20, peer=15, viewer=10.

**Section display names:**
- `my_work` → "My Work"
- `unstarted` → "Unstarted Work"
- `shared_with_me` → "Shared With Me"
- `shared_in_unit` → "Shared in {course_name}" (per course)

---

## Tasks

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Create navigator page with auth and data loading

**Verifies:** workspace-navigator-196.AC2.5, workspace-navigator-196.AC1.7

**Files:**
- Create: `src/promptgrimoire/pages/navigator.py`
- Delete: `src/promptgrimoire/pages/index.py`

**Implementation:**

Create `navigator.py` registered at `/` via `@page_route`. The page function:

1. Checks auth via `app.storage.user.get("auth_user")`. If `None`, redirects to `/login` (AC2.5).
2. Checks `get_settings().database.url`. If not configured, shows error label.
3. Calls `init_db()`.
4. Extracts `user_id` (UUID from `auth_user["user_id"]`).
5. Determines `is_privileged` via `is_privileged_user(auth_user)`.
6. Loads enrollments via `list_user_enrollments(user_id)` → extracts `enrolled_course_ids`.
7. Calls `load_navigator_page(user_id, is_privileged, enrolled_course_ids)` to get first page of rows.
8. Uses `page_layout("Home")` for standard header/drawer.
9. Renders sections using a helper function (Task 2).

Delete `index.py` since navigator replaces it entirely.

**Verification:**
Run: `uv run test-changed`
Expected: No import errors. Existing tests that reference `index_page` may need updating if any exist.

**Commit:** `feat: create navigator page skeleton with auth and data loading`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Render workspace sections with grouping and navigation

**Verifies:** workspace-navigator-196.AC1.1, workspace-navigator-196.AC1.2, workspace-navigator-196.AC1.3, workspace-navigator-196.AC1.4, workspace-navigator-196.AC1.5, workspace-navigator-196.AC1.6, workspace-navigator-196.AC1.7, workspace-navigator-196.AC1.8, workspace-navigator-196.AC2.1, workspace-navigator-196.AC2.2, workspace-navigator-196.AC2.4, workspace-navigator-196.AC5.1, workspace-navigator-196.AC5.4

**Files:**
- Modify: `src/promptgrimoire/pages/navigator.py`

**Implementation:**

Add rendering logic that groups `NavigatorRow` objects by section and renders them:

1. **Section grouping:** Build a dict-based grouping (NOT `itertools.groupby` — rows are sorted by recency, not grouped by section/course, so `groupby` would produce fragmented groups). Iterate all rows and collect them into a `dict[str, list[NavigatorRow]]` keyed by section. For `shared_in_unit` rows, further group by `course_id` into a `dict[UUID, list[NavigatorRow]]` to render separate "Shared in {course_name}" headers per enrolled unit (AC1.8). Render sections in a fixed order: `my_work`, `unstarted`, `shared_with_me`, then each `shared_in_unit` course.

2. **Section headers:** Render each non-empty section with a prominent header label. Map section names to display names. Empty sections produce zero rows from the query, so they naturally don't render (AC1.7).

3. **Workspace entries:** For each row, render a card or row showing:
   - Title (clickable → navigates to `/annotation?workspace_id={row.workspace_id}`) (AC2.1)
   - Breadcrumb: course code > week title > activity title (when available)
   - Last edit date from `row.updated_at` formatted as relative time or date (AC2.4)
   - Action button: "Resume" for owned, "Open" for editor, "View" for viewer/peer (AC2.2)
   - For `shared_in_unit` and `shared_with_me`: owner display name (anonymised for students)

4. **Unstarted entries:** Rows where `row.workspace_id is None`. Show activity title with a "Start" button instead of navigation (AC1.2). See Task 3 for the clone handler.

5. **Loose workspaces:** Rows in `shared_in_unit` where `row.activity_id is None`. Group under an "Unsorted" sub-heading within the student grouping (AC1.6).

6. **Anonymisation for shared_in_unit:** Pre-load courses and activities for enrolled course IDs. For each `shared_in_unit` row, call `anonymise_author()` with:
   - `author=row.owner_display_name`
   - `user_id=str(row.owner_user_id)`
   - `viewing_user_id=str(user_id)`
   - `anonymous_sharing=resolve_tristate(activity.anonymous_sharing, course.default_anonymous_sharing)`
   - `viewer_is_privileged=is_privileged`
   - `author_is_privileged=False`
   Instructors (`is_privileged=True`) see real names (AC1.5). Students see anonymised names (AC1.4).

7. **Refreshable sections:** Wrap the section rendering in a `@ui.refreshable` async function that accepts `rows: list[NavigatorRow]` and an optional `snippets: dict[UUID, str]` (for Phase 5 search). This allows Phase 5 (search) and Phase 7 (pagination) to re-render sections by calling `.refresh()` with updated data. The rendering function should also accept `next_cursor: NavigatorCursor | None` to know if more pages exist.

8. **Pagination state:** Store `rows`, `next_cursor`, and page-level context (user_id, is_privileged, enrolled_course_ids) in module-level or page-level state so Phase 7's infinite scroll handler can load more pages and call `.refresh()` with accumulated rows.

**Verification:**
Run: `uv run python -m promptgrimoire` and manually verify sections render with seed data.
Run: `uv run test-changed`

**Commit:** `feat: render navigator sections with grouping, navigation, and anonymisation`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: "Start" button clones activity template and navigates

**Verifies:** workspace-navigator-196.AC2.3

**Files:**
- Modify: `src/promptgrimoire/pages/navigator.py`

**Implementation:**

For unstarted activity rows (`row.workspace_id is None`), add a "Start" button. The click handler:

1. Calls `clone_workspace_from_activity(row.activity_id, user_id)` — async.
2. Extracts the new workspace ID from the returned tuple.
3. Navigates to `/annotation?workspace_id={new_workspace.id}` via `ui.navigate.to()`.

Follow the existing pattern in `courses.py:548`:
```python
clone, _doc_map = await clone_workspace_from_activity(aid, uid)
qs = urlencode({"workspace_id": str(clone.id)})
ui.navigate.to(f"/annotation?{qs}")
```

Handle errors (activity not found, template missing) with `ui.notify` error message.

**Verification:**
Manual: Click "Start" on an unstarted activity. Verify navigation to new workspace. Refresh navigator — activity moves from "Unstarted" to "My Work".
Run: `uv run test-changed`

**Commit:** `feat: add Start button to clone activity template and navigate`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->
<!-- START_TASK_4 -->
### Task 4: E2E test — navigator renders sections and navigation works

**Verifies:** workspace-navigator-196.AC1.1, workspace-navigator-196.AC1.2, workspace-navigator-196.AC1.7, workspace-navigator-196.AC2.1, workspace-navigator-196.AC2.5

**Files:**
- Create: `tests/e2e/test_navigator.py`

**Implementation:**

E2E tests for the navigator page using Playwright. Follow existing E2E patterns from `tests/e2e/conftest.py`.

Tests must verify:
- AC2.5: Unauthenticated access to `/` redirects to `/login`.
- AC1.1: Authenticated student with owned workspaces sees "My Work" section with workspace entries.
- AC1.2: Student enrolled in course with unpublished activities sees "Unstarted Work" section.
- AC1.7: Sections with no data are not rendered (no empty section headers).
- AC2.1: Clicking a workspace title navigates to `/annotation?workspace_id=...`.

Use `authenticated_page` fixture for auth. Set up test data via direct DB operations (follow `_create_workspace_via_db` pattern from `tests/e2e/annotation_helpers.py`). Use course_helpers for course/week/activity setup.

**Verification:**
Run: `uv run test-e2e -k test_navigator`
Expected: All navigator E2E tests pass.

**Commit:** `test: add E2E tests for navigator page sections and navigation`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: E2E test — start activity clones and navigates

**Verifies:** workspace-navigator-196.AC2.3

**Files:**
- Modify: `tests/e2e/test_navigator.py`

**Implementation:**

E2E test for the "Start" button on unstarted activities:
- Set up a course with a published activity that has a template workspace.
- Authenticate as an enrolled student.
- Navigate to `/`.
- Verify "Unstarted Work" section shows the activity.
- Click "Start" button.
- Verify navigation to `/annotation?workspace_id=...` (new workspace).
- Navigate back to `/`.
- Verify the activity now appears under "My Work" (no longer under "Unstarted").

**Verification:**
Run: `uv run test-e2e -k test_navigator`
Expected: All navigator E2E tests pass.

**Commit:** `test: add E2E test for Start button clone and navigate`
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->

---

## Next Phase

Phase 5 adds server-side search (FTS at 3+ chars with debounce) that re-renders sections with filtered results and snippets.
