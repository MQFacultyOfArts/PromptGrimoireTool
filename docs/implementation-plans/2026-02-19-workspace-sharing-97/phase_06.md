# Workspace Sharing & Visibility — Phase 6: Peer Discovery & Instructor View

**Goal:** Student peer browsing on activity pages, workspace title display, and instructor workspace roster.

**Architecture:** Extract `resolve_tri_state` utility to DRY up tri-state resolution across all call sites (Phases 1-2 inline code + new Phase 6 usage). Extend `list_peer_workspaces` (Phase 2) and `list_activity_workspaces` with User JOINs to return owner display_name in a single query — no N+1 `get_user_by_id` calls. New instructor page at `/courses/{course_id}/workspaces` following `manage_enrollments_page` auth pattern. Peer discovery gated by resolved `allow_sharing` using the utility.

**Tech Stack:** NiceGUI, SQLModel, PostgreSQL, async SQLAlchemy

**Scope:** 7 phases from original design (phase 6 of 7)

**Codebase verified:** 2026-02-19

**Dependencies:** Phase 1 (model fields, PlacementContext), Phase 2 (`list_peer_workspaces`, peer permission path), Phase 3 (anonymisation utility), Phase 4 (PageState capabilities), Phase 5 (`update_workspace_title`, sharing toggle)

---

## Acceptance Criteria Coverage

This phase implements and tests:

### workspace-sharing-97.AC5: Workspace titles
- **workspace-sharing-97.AC5.2 Success:** Title displayed in workspace header, peer discovery list, instructor roster
- **workspace-sharing-97.AC5.3 Edge:** Workspace without title displays fallback (e.g. 'Untitled Workspace')

### workspace-sharing-97.AC6: Instructor view page
- **workspace-sharing-97.AC6.1 Success:** Staff-enrolled user can access workspace roster page
- **workspace-sharing-97.AC6.2 Success (PARTIAL):** Roster lists workspaces per activity with student name, title, dates, document count. Highlight count omitted — requires CRDT blob parsing per workspace, impractical for roster query. Follow-up: add denormalised `highlight_count` column if needed.
- **workspace-sharing-97.AC6.3 Success:** Activity-level stats: N started / M enrolled
- **workspace-sharing-97.AC6.4 Success:** Click-through opens workspace at /annotation?workspace={id}
- **workspace-sharing-97.AC6.5 Failure:** Non-staff user cannot access instructor view page
- **workspace-sharing-97.AC6.6 Edge:** Activity with no student workspaces shows empty state with enrolled count

### workspace-sharing-97.AC2: Enrollment-based discovery (UI aspect)
- **workspace-sharing-97.AC2.1 Success:** Student enrolled in course can discover peer workspaces on activity page when sharing enabled

### workspace-sharing-97.AC4: Anonymity control (peer discovery aspect)
- **workspace-sharing-97.AC4.1 Success:** Peer discovery list shows anonymised author names when anonymous_sharing is active

---

## Technical Debt Note

This phase establishes User JOINs as the standard pattern for queries returning user-associated data. The following existing N+1 patterns from Seam-D remain and should be addressed in a follow-up:
- `manage_enrollments_page` (courses.py:788) — `get_user_by_id()` per enrollment row
- `get_placement_context` chain — sequential `session.get()` calls (noted at workspaces.py:188 TODO)

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Extract `resolve_tri_state` utility function

**Verifies:** No direct AC — refactoring for DRY. Enables correct `allow_sharing` and `anonymous_sharing` gating in Tasks 4 and 6.

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py` (add utility function, refactor `_resolve_activity_placement` and `_resolve_course_placement`)
- Modify: `src/promptgrimoire/db/acl.py` (refactor `_derive_enrollment_permission` inline resolution)
- Modify: `src/promptgrimoire/db/__init__.py` (export `resolve_tri_state`)

**Implementation:**

Add a module-level function in `db/workspaces.py`, above the `PlacementContext` class:

```python
def resolve_tri_state(override: bool | None, default: bool) -> bool:
    """Resolve a tri-state flag: explicit override wins, else course default."""
    return override if override is not None else default
```

Refactor `_resolve_activity_placement` (lines 201-211 after Phase 1 changes) to replace the inline `if/else` blocks:

```python
# Before (repeated 3 times for copy_protection, allow_sharing, anonymous_sharing):
if activity.copy_protection is not None:
    resolved_cp = activity.copy_protection
else:
    resolved_cp = course.default_copy_protection

# After:
resolved_cp = resolve_tri_state(activity.copy_protection, course.default_copy_protection)
resolved_sharing = resolve_tri_state(activity.allow_sharing, course.default_allow_sharing)
resolved_anon = resolve_tri_state(activity.anonymous_sharing, course.default_anonymous_sharing)
```

Apply the same refactor to `_resolve_course_placement` (Phase 1 Task 3 adds tri-state resolution there — replace with utility calls).

Refactor `_derive_enrollment_permission` in `acl.py` (Phase 2 Task 1 adds inline tri-state resolution for `allow_sharing`):

```python
# Before:
allow_sharing = (
    activity.allow_sharing
    if activity.allow_sharing is not None
    else course.default_allow_sharing
)

# After:
from promptgrimoire.db.workspaces import resolve_tri_state

allow_sharing = resolve_tri_state(activity.allow_sharing, course.default_allow_sharing)
```

Export from `db/__init__.py`:
```python
from promptgrimoire.db.workspaces import resolve_tri_state
```

**Testing:**

Pure refactor — all existing Phase 1 and Phase 2 tests must continue to pass unchanged. No new tests needed.

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass with no changes to test files

**Commit:** `refactor(db): extract resolve_tri_state utility for DRY tri-state resolution`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Extend `list_peer_workspaces` with User JOIN

**Verifies:** workspace-sharing-97.AC2.1 (discovery with author attribution), workspace-sharing-97.AC4.1 (anonymisation requires user_id and display_name)

**Files:**
- Modify: `src/promptgrimoire/db/acl.py` (extend Phase 2's `list_peer_workspaces` query)
- Modify: `tests/integration/test_peer_discovery.py` (update return type expectations)

**Implementation:**

Modify `list_peer_workspaces` (added in Phase 2 Task 3) to JOIN User via ACLEntry:

```python
async def list_peer_workspaces(
    activity_id: UUID, exclude_user_id: UUID
) -> list[tuple[Workspace, str, UUID]]:
    """List shared workspaces for an activity with owner info.

    Returns (Workspace, owner_display_name, owner_user_id) tuples.
    Excludes the requesting user's own workspaces and template workspaces.
    """
    async with get_session() as session:
        activity = await session.get(Activity, activity_id)
        if activity is None:
            return []
        template_id = activity.template_workspace_id

        result = await session.exec(
            select(Workspace, User.display_name, ACLEntry.user_id)
            .join(ACLEntry, ACLEntry.workspace_id == Workspace.id)
            .join(User, User.id == ACLEntry.user_id)
            .where(
                Workspace.activity_id == activity_id,
                Workspace.shared_with_class == True,  # noqa: E712
                ACLEntry.permission == "owner",
                ACLEntry.user_id != exclude_user_id,
            )
            .order_by(Workspace.created_at)
        )
        rows = list(result.all())
        return [
            (ws, name, uid)
            for ws, name, uid in rows
            if ws.id != template_id
        ]
```

Note the `# noqa: E712` — SQLAlchemy column comparison requires `==` not `is`.

Update Phase 2's tests in `test_peer_discovery.py` to unpack `(workspace, display_name, user_id)` tuples instead of bare `Workspace` objects.

**Testing:**

Update existing Phase 2 peer discovery tests to verify:
- Return type is `list[tuple[Workspace, str, UUID]]`
- `display_name` matches the owner's `User.display_name`
- `user_id` matches the owner's `User.id`

**Verification:**
Run: `uv run pytest tests/integration/test_peer_discovery.py -v`
Expected: All tests pass with updated assertions

**Commit:** `feat(acl): extend list_peer_workspaces with User JOIN for display_name`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create `list_activity_workspaces_with_stats` query for instructor roster

**Verifies:** workspace-sharing-97.AC6.2

**Files:**
- Modify: `src/promptgrimoire/db/acl.py` (add new function)
- Modify: `src/promptgrimoire/db/__init__.py` (export new function)
- Create: `tests/integration/test_instructor_roster.py`

**Implementation:**

Add a new function (do NOT modify the existing `list_activity_workspaces` — it has its own callers):

```python
from sqlalchemy import func

async def list_activity_workspaces_with_stats(
    activity_id: UUID,
) -> list[tuple[Workspace, str, UUID, int]]:
    """List non-template workspaces for an activity with owner info and document count.

    Returns (Workspace, owner_display_name, owner_user_id, document_count) tuples.
    Used by the instructor roster page.
    """
    async with get_session() as session:
        activity = await session.get(Activity, activity_id)
        if activity is None:
            return []
        template_id = activity.template_workspace_id

        # Subquery for document count per workspace
        doc_count = (
            select(
                WorkspaceDocument.workspace_id,
                func.count(WorkspaceDocument.id).label("doc_count"),
            )
            .group_by(WorkspaceDocument.workspace_id)
            .subquery()
        )

        result = await session.exec(
            select(
                Workspace,
                User.display_name,
                ACLEntry.user_id,
                func.coalesce(doc_count.c.doc_count, 0),
            )
            .join(ACLEntry, ACLEntry.workspace_id == Workspace.id)
            .join(User, User.id == ACLEntry.user_id)
            .outerjoin(doc_count, doc_count.c.workspace_id == Workspace.id)
            .where(
                Workspace.activity_id == activity_id,
                ACLEntry.permission == "owner",
            )
            .order_by(User.display_name)
        )
        rows = list(result.all())
        return [
            (ws, name, uid, count)
            for ws, name, uid, count in rows
            if ws.id != template_id
        ]
```

Note: highlight count is omitted — it requires parsing CRDT blobs per workspace which is impractical for a roster query. The instructor can click through to see highlights for any specific workspace. A `highlight_count` denormalisation column can be added in a follow-up if this becomes a user need.

Export from `db/__init__.py`:
```python
from promptgrimoire.db.acl import list_activity_workspaces_with_stats
```

**Testing:**

Integration tests in `tests/integration/test_instructor_roster.py`:

- `TestInstructorRosterBasic` — activity with 2 student workspaces: returns both with correct display_name, user_id, document_count
- `TestInstructorRosterDocCount` — workspace with 3 documents returns count=3, workspace with 0 returns count=0
- `TestInstructorRosterExcludesTemplate` — template workspace not included in results
- `TestInstructorRosterEmpty` — activity with no student workspaces returns empty list
- `TestInstructorRosterOrdering` — results ordered by display_name alphabetically

Each test creates its own user/course/activity/workspace hierarchy with UUID tags for isolation.

**Verification:**
Run: `uv run pytest tests/integration/test_instructor_roster.py -v`
Expected: All tests pass

**Commit:** `feat(acl): add list_activity_workspaces_with_stats with User JOIN and document count`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->
<!-- START_TASK_4 -->
### Task 4: Peer workspaces section in activity row

**Verifies:** workspace-sharing-97.AC2.1 (UI discovery), workspace-sharing-97.AC4.1 (anonymised peer list), workspace-sharing-97.AC5.2 (title in peer list)

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py:438-499` (`_render_activity_row` — add peer workspaces section)
- Modify: `src/promptgrimoire/pages/courses.py:501-580` (`weeks_list` — pre-fetch peer workspaces, thread course)

**Implementation:**

1. In `weeks_list()` (line 501), the `course` object is already available in scope (fetched earlier in `course_detail_page`). Thread it into `_render_activity_row` by adding a `course: Course` parameter.

2. After the existing user_workspace_map computation in `weeks_list()`, add a batch fetch of peer workspaces for all activities where sharing is enabled:

```python
# Pre-fetch peer workspaces for activities with sharing enabled
peer_workspace_map: dict[UUID, list[tuple[Workspace, str, UUID]]] = {}
if user_id:
    for week_data in weeks:
        for act in week_data.activities:
            if resolve_tri_state(act.allow_sharing, course.default_allow_sharing):
                peer_workspace_map[act.id] = await list_peer_workspaces(
                    act.id, user_id
                )
```

3. Add `peer_workspaces` and `course` parameters to `_render_activity_row`:

```python
def _render_activity_row(
    act: Activity,
    *,
    can_manage: bool,
    populated_templates: set[UUID],
    user_workspace_map: dict[UUID, Workspace],
    peer_workspaces: list[tuple[Workspace, str, UUID]],
    course: Course,
    anonymous_sharing: bool,
) -> None:
```

4. After the Resume/Start Activity button block (after line 499), add the peer workspaces section:

```python
# Peer workspaces section — shown when sharing is enabled and peers have shared
if peer_workspaces:
    with ui.column().classes("ml-8 mt-1 gap-1"):
        ui.label("Peer Workspaces").classes(
            "text-xs font-semibold text-gray-500 uppercase"
        )
        for ws, owner_name, owner_uid in peer_workspaces:
            display_name = (
                anonymise_display_name(owner_uid)
                if anonymous_sharing
                else owner_name
            )
            title = ws.title or "Untitled Workspace"
            qs = urlencode({"workspace_id": str(ws.id)})
            with ui.row().classes("items-center gap-2"):
                ui.icon("person", size="xs").classes("text-gray-400")
                ui.link(
                    f"{display_name} — {title}",
                    target=f"/annotation?{qs}",
                ).classes("text-sm text-blue-600")
```

5. Resolve `anonymous_sharing` in `weeks_list()` per activity using `resolve_tri_state(act.anonymous_sharing, course.default_anonymous_sharing)` and pass into the render function.

6. Import `resolve_tri_state` from `promptgrimoire.db` and `anonymise_display_name` from `promptgrimoire.auth.anonymise` (Phase 3) at the top of courses.py.

**Testing:**

This is UI rendering — primary verification is UAT (see Phase 6 UAT below). Unit testing NiceGUI rendering is impractical. Integration tests for the underlying query are in Tasks 2 and 3.

**Verification:**
Run: `uvx ty check` — verify no type errors in courses.py
Run: `uv run test-debug` — verify no regressions

**Commit:** `feat(courses): add peer workspaces section to activity row`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Workspace title in annotation page header

**Verifies:** workspace-sharing-97.AC5.2 (title in workspace header), workspace-sharing-97.AC5.3 (fallback for untitled workspace)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/workspace.py:680` (replace UUID label with title)
- Modify: `src/promptgrimoire/pages/annotation/workspace.py:640-674` (load workspace object for title)

**Implementation:**

1. The workspace object is needed at line 680. Check whether it's already loaded in `_render_workspace_view`. The function receives `workspace_id: UUID` — it calls `check_workspace_access(workspace_id, auth_user)` at line 651 but doesn't retain the workspace object. Load it:

```python
from promptgrimoire.db import get_workspace_by_id

workspace = await get_workspace_by_id(workspace_id)
```

Place this after the access check succeeds (after line 658). If `workspace is None`, show an error and return.

2. Replace line 680:

```python
# Before:
ui.label(f"Workspace: {workspace_id}").classes("text-gray-600 text-sm")

# After:
title_text = workspace.title or "Untitled Workspace"
ui.label(title_text).classes("text-gray-600 text-sm")
```

3. For owner/editor, make the title editable inline. Add an edit icon button next to the title that opens an input dialog:

```python
if state.effective_permission in ("owner", "editor"):
    async def _edit_title() -> None:
        with ui.dialog() as dlg, ui.card():
            title_input = ui.input(
                label="Workspace title",
                value=workspace.title or "",
            ).props("autofocus")

            async def _save() -> None:
                new_title = title_input.value.strip() or None
                await update_workspace_title(workspace_id, new_title)
                workspace.title = new_title  # update local ref
                dlg.close()
                ui.notify("Title updated", type="positive")

            with ui.row().classes("gap-2 mt-2"):
                ui.button("Save", on_click=_save)
                ui.button("Cancel", on_click=dlg.close).props("flat")

        dlg.open()

    ui.button(icon="edit", on_click=_edit_title).props(
        "flat round dense size=xs"
    ).tooltip("Edit title")
```

Import `update_workspace_title` from `promptgrimoire.db`.

Note: `state.effective_permission` is added in Phase 4. The inline edit is gated by permission.

**Testing:**

UI rendering — primary verification is UAT. Verify type-checking passes.

**Verification:**
Run: `uvx ty check`
Run: `uv run test-debug`

**Commit:** `feat(annotation): display workspace title in header with inline edit`
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 6-7) -->
<!-- START_TASK_6 -->
### Task 6: Instructor roster page

**Verifies:** workspace-sharing-97.AC6.1, workspace-sharing-97.AC6.2, workspace-sharing-97.AC6.4, workspace-sharing-97.AC6.5

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (add new page route at end of file)

**Implementation:**

Add a new page following the `manage_enrollments_page` pattern (courses.py:737):

```python
@ui.page("/courses/{course_id}/workspaces")
async def instructor_roster_page(course_id: str) -> None:
    """Instructor workspace roster — overview of student workspaces per activity."""
    if not await _check_auth():
        return

    if not _is_db_available():
        ui.label("Database not configured").classes("text-red-500")
        return

    await init_db()

    try:
        cid = UUID(course_id)
    except ValueError:
        ui.label("Invalid course ID").classes("text-red-500")
        return

    course = await get_course_by_id(cid)
    if not course:
        ui.label("Course not found").classes("text-red-500")
        return

    user_id = _get_user_id()
    if not user_id:
        ui.label(
            "User not found in local database. Please log out and log in again."
        ).classes("text-red-500")
        return

    # AC6.5: Staff-only access
    enrollment = await get_enrollment(course_id=cid, user_id=user_id)
    if not enrollment or enrollment.role not in _MANAGER_ROLES:
        ui.label("Only instructors can view the workspace roster").classes(
            "text-red-500"
        )
        return

    ui.label(f"Workspace Roster — {course.code}").classes(
        "text-2xl font-bold mb-4"
    )
```

Then render weeks and activities:

```python
    weeks = await get_visible_weeks(course_id=cid, user_id=user_id)
    enrollments = await list_course_enrollments(cid)
    enrolled_count = len(enrollments)

    if not weeks:
        ui.label("No weeks configured for this course.").classes("text-gray-500")
        return

    for week_data in weeks:
        with ui.card().classes("w-full mb-4"):
            ui.label(
                f"Week {week_data.week.week_number}: {week_data.week.title}"
            ).classes("text-lg font-semibold mb-2")

            for act in week_data.activities:
                roster = await list_activity_workspaces_with_stats(act.id)
                started_count = len(roster)

                with ui.column().classes("ml-4 mb-3"):
                    # Activity header with stats (AC6.3)
                    ui.label(act.title).classes("font-medium")
                    ui.label(
                        f"{started_count} started / {enrolled_count} enrolled"
                    ).classes("text-sm text-gray-500")

                    if not roster:
                        # AC6.6: Empty state
                        ui.label(
                            f"No student workspaces yet "
                            f"({enrolled_count} enrolled)"
                        ).classes("text-sm text-gray-400 italic ml-4")
                    else:
                        # Workspace table (AC6.2)
                        columns = [
                            {
                                "name": "student",
                                "label": "Student",
                                "field": "student",
                                "align": "left",
                            },
                            {
                                "name": "title",
                                "label": "Title",
                                "field": "title",
                                "align": "left",
                            },
                            {
                                "name": "created",
                                "label": "Created",
                                "field": "created",
                                "align": "left",
                            },
                            {
                                "name": "updated",
                                "label": "Updated",
                                "field": "updated",
                                "align": "left",
                            },
                            {
                                "name": "docs",
                                "label": "Documents",
                                "field": "docs",
                                "align": "center",
                            },
                        ]
                        rows = []
                        for ws, display_name, _uid, doc_count in roster:
                            ws_title = ws.title or "Untitled Workspace"
                            rows.append(
                                {
                                    "student": display_name,
                                    "title": ws_title,
                                    "created": ws.created_at.strftime(
                                        "%Y-%m-%d %H:%M"
                                    ),
                                    "updated": (
                                        ws.updated_at.strftime("%Y-%m-%d %H:%M")
                                        if ws.updated_at
                                        else "—"
                                    ),
                                    "docs": doc_count,
                                    "workspace_id": str(ws.id),
                                }
                            )

                        table = ui.table(
                            columns=columns,
                            rows=rows,
                            row_key="workspace_id",
                        ).classes("w-full")

                        # AC6.4: Click-through to workspace
                        table.on(
                            "row-click",
                            lambda e: ui.navigate.to(
                                f"/annotation?"
                                f"workspace_id={e.args[1]['workspace_id']}"
                            ),
                        )
                        table.classes("cursor-pointer")
```

Note: `enrolled_count` is a course-level number. The "N started" count is per-activity. The design says "N started / M enrolled" which is what we show.

Note: highlight count column is omitted from the table. The AC says "highlight count" but this requires CRDT parsing per workspace — add a TODO comment in the code noting this gap. If the user needs it, a denormalisation column can be added in a follow-up.

**Testing:**

UI rendering page — primary verification is UAT. The underlying query is tested in Task 3. Access control guard follows the exact same pattern as `manage_enrollments_page` (already tested by existing course tests).

**Verification:**
Run: `uvx ty check`
Run: `uv run test-debug`

**Commit:** `feat(courses): add instructor workspace roster page`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Navigation link and integration

**Verifies:** workspace-sharing-97.AC6.1 (discoverability), workspace-sharing-97.AC6.3, workspace-sharing-97.AC6.6

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (add "Workspace Roster" link on course detail page and activity row)

**Implementation:**

1. On the course detail page (`course_detail_page`, line 344), add a "Workspace Roster" button for instructors next to the existing "Manage Enrollments" link. Find the instructor toolbar area where the enrollment link is rendered and add:

```python
if enrollment.role in _MANAGER_ROLES:
    ui.button(
        "Workspace Roster",
        icon="assignment_ind",
        on_click=lambda: ui.navigate.to(
            f"/courses/{course_id}/workspaces"
        ),
    ).props("flat dense")
```

This should be placed near the existing management buttons (enrollment link is rendered somewhere in the course detail header area — find the exact location during implementation).

2. Also add a direct link from each activity row in the instructor view. In `_render_activity_row`, when `can_manage` is True, add a small icon button:

```python
if can_manage:
    # ... existing Edit Template and Settings buttons ...
    ui.button(
        icon="groups",
        on_click=lambda a=act: ui.navigate.to(
            f"/courses/{course_id}/workspaces#activity-{a.id}"
        ),
    ).props("flat round dense size=sm").tooltip("View student workspaces")
```

Note: the `#activity-{id}` anchor requires adding `id` attributes to the activity sections in the roster page (Task 6). If NiceGUI's table doesn't support anchor scrolling, omit the fragment and just navigate to the page.

**Testing:**

UI navigation — UAT verification. No integration tests needed for button rendering.

**Verification:**
Run: `uvx ty check`
Run: `uv run test-debug`

**Commit:** `feat(courses): add instructor navigation to workspace roster`
<!-- END_TASK_7 -->
<!-- END_SUBCOMPONENT_C -->

---

## UAT Protocol

### Student Peer Discovery (Tasks 4-5)

1. Log in as a student enrolled in a course with an activity where `allow_sharing=True`
2. Navigate to the course page
3. Verify: Your own workspace shows "Resume" button as before
4. Have another student share their workspace (`shared_with_class=True`)
5. Reload the course page
6. Verify: "Peer Workspaces" section appears below your Resume button with the other student's workspace listed
7. Verify: Workspace shows title (or "Untitled Workspace") and author name
8. If `anonymous_sharing=True` on the activity: verify author shows as anonymised label (e.g. "Cheerful Penguin"), not real name
9. Click a peer workspace link — verify it opens at `/annotation?workspace_id={id}`
10. Verify: The annotation page shows the workspace title in the header, not the UUID

### Student Peer Discovery — Negative Cases

11. Set `allow_sharing=False` on the activity, reload course page
12. Verify: "Peer Workspaces" section does NOT appear
13. Have the peer set `shared_with_class=False`, re-enable activity sharing, reload
14. Verify: That peer's workspace does NOT appear in the list

### Instructor Roster (Tasks 6-7)

15. Log in as an instructor enrolled in the course
16. Navigate to `/courses/{course_id}/workspaces` (or click "Workspace Roster" button)
17. Verify: Page shows weeks as sections, activities listed under each
18. Verify: Each activity shows "N started / M enrolled" stats
19. Verify: Workspace table shows student name, title, created date, updated date, document count
20. Click a workspace row — verify it opens at `/annotation?workspace_id={id}`
21. Verify: Activity with no student workspaces shows "No student workspaces yet (M enrolled)"

### Instructor Roster — Access Control

22. Log in as a student (non-staff)
23. Navigate to `/courses/{course_id}/workspaces` directly
24. Verify: Access denied message shown
