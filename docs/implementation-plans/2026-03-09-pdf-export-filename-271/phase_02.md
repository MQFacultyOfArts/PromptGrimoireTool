# PDF Export Filename Convention Implementation Plan

**Goal:** Implement a database-backed helper that resolves the correct owner-facing export metadata for any workspace, independent of the current viewer session.

**Architecture:** Extend `src/promptgrimoire/db/workspaces.py` because it already owns workspace placement resolution. The new helper should compose two existing concerns inside one async session: owner lookup via ACL and placement lookup via the existing activity/course resolution helpers. The return type stays narrow and export-focused so later phases can call one stable seam without importing ORM models into UI code.

**Tech Stack:** Python 3.14, SQLModel/SQLAlchemy async, pytest

**Scope:** 4 phases from original design (phase 2 of 4)

**Codebase verified:** 2026-03-09

---

## Acceptance Criteria Coverage

This phase implements and tests:

### pdf-export-filename-271.AC1: Export metadata is resolved from the workspace owner and placement
- **pdf-export-filename-271.AC1.1 Success:** Activity-placed workspace export uses the workspace owner's display name, the resolved unit code, the activity title, the workspace title, and the export date.
- **pdf-export-filename-271.AC1.2 Success:** If a privileged instructor or admin exports another user's workspace, the filename still uses the owner name rather than the current viewer name.
- **pdf-export-filename-271.AC1.3 Success:** Course-placed workspaces with no activity use the course code plus the activity fallback label `Loose_Work`.
- **pdf-export-filename-271.AC1.4 Success:** Fully loose / unplaced workspaces use `Unplaced` for the unit slot and `Loose_Work` for the activity slot instead of failing export.
- **pdf-export-filename-271.AC1.5 Edge:** Blank or null workspace titles use the fallback segment `Workspace`.
- **pdf-export-filename-271.AC1.6 Edge:** Blank or missing owner display names use the fallback name `Unknown Unknown`.

---

<!-- START_TASK_1 -->
### Task 1: Add `WorkspaceExportMetadata` and a one-session metadata resolver

**Verifies:** pdf-export-filename-271.AC1.1, pdf-export-filename-271.AC1.2

**Files:**
- Modify: `src/promptgrimoire/db/workspaces.py`

**Implementation:**

Add a new frozen dataclass near `PlacementContext`:

```python
@dataclass(frozen=True)
class WorkspaceExportMetadata:
    course_code: str | None
    activity_title: str | None
    workspace_title: str | None
    owner_display_name: str | None
```

Add:

```python
async def get_workspace_export_metadata(
    workspace_id: UUID,
) -> WorkspaceExportMetadata | None:
    """Return export metadata for a workspace, or None if the workspace is missing."""
```

Required behaviour:

1. Open a single async DB session and fetch the `Workspace` row by `workspace_id`.
2. If the workspace does not exist, return `None`.
3. Resolve owner identity with an explicit owner-ACL join:
   - join `ACLEntry` to `User`
   - filter `ACLEntry.workspace_id == workspace_id`
   - filter `ACLEntry.permission == "owner"`
   - select `User.display_name`
4. Do not read any viewer/session identity from NiceGUI or auth storage. This helper must be viewer-agnostic by construction.
5. Reuse the existing placement-resolution internals already in `db/workspaces.py` inside the same session:
   - activity-placed workspace -> `_resolve_activity_placement(session, workspace.activity_id)`
   - course-placed workspace -> `_resolve_course_placement(session, workspace.course_id)`
   - fully loose workspace -> `PlacementContext(placement_type="loose")`
6. Return a narrow `WorkspaceExportMetadata` dataclass populated from:
   - `course_code=placement.course_code`
   - `activity_title=placement.activity_title`
   - `workspace_title=workspace.title`
   - `owner_display_name=<joined owner display name or None>`
7. Keep fallback labels out of this helper. `Loose Work`, `Unplaced`, `Workspace`, and `Unknown Unknown` remain Phase 1 filename-policy concerns.

Implementation notes:
- Do not call the public `get_placement_context(...)` from inside the helper because it opens its own session. Reuse the existing private placement helpers directly so owner lookup and placement resolution happen in one transaction boundary.
- If the owner join finds no row, return `owner_display_name=None` rather than raising. That preserves the design contract that the filename builder applies the fallback.
- Keep this helper in `db/workspaces.py`, not `db/acl.py`, because the exported object is workspace-export context rather than a generic ACL query result.

**Verification:**

Run:
```bash
uvx ty check src/promptgrimoire/db/workspaces.py
```

Expected: No type errors after adding the dataclass and helper.

## UAT Steps
1. [ ] Open `src/promptgrimoire/db/workspaces.py`.
2. [ ] Confirm `WorkspaceExportMetadata` exists alongside the existing placement types.
3. [ ] Confirm `get_workspace_export_metadata(...)` does not import or call any NiceGUI/session helpers.
4. [ ] Confirm the helper reads owner name from an owner-ACL join and returns a narrow dataclass.

## Evidence Required
- [ ] `ty check` output for `src/promptgrimoire/db/workspaces.py`
- [ ] Code review evidence that no viewer-session lookup is used

**Commit:** `feat: add workspace export metadata resolver`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add focused integration tests for owner resolution and placement fallbacks

**Verifies:** pdf-export-filename-271.AC1.1, pdf-export-filename-271.AC1.2, pdf-export-filename-271.AC1.3, pdf-export-filename-271.AC1.4, pdf-export-filename-271.AC1.5, pdf-export-filename-271.AC1.6

**Files:**
- Create: `tests/integration/test_workspace_export_metadata.py`

**Implementation:**

Create a focused integration test module rather than extending the placement or peer-discovery files. This feature has its own contract and needs both placement setup and owner-ACL setup in one place.

Use the existing patterns from:
- `tests/integration/test_peer_discovery_with_owners.py` for owner joins
- `tests/integration/test_workspace_placement.py` for hierarchy and loose/course/activity placement setup

Import the Phase 1 builder so these tests assert the real contract at the export-metadata boundary:
- `get_workspace_export_metadata(...)` provides the DB-backed input
- `build_pdf_export_stem(...)` renders the deterministic filename stem

This makes Phase 1 a required dependency for Task 2, not merely a recommended ordering preference. The integration test module will not compile until the Phase 1 filename-policy module exists.

Use a fixed date in every test, for example:

```python
EXPORT_DATE = date(2026, 3, 9)
```

Recommended test classes:
- `TestGetWorkspaceExportMetadata`
- `TestWorkspaceExportMetadataFilenameContract`

Required test cases:

1. Activity-placed workspace returns owner and hierarchy metadata.
   - create owner user, separate viewer user, course, week, activity, workspace
   - grant `owner` permission to the owner user
   - set a concrete workspace title
   - call `get_workspace_export_metadata(workspace.id)`
   - assert raw metadata:
     - `course_code == course.code`
     - `activity_title == activity.title`
     - `workspace_title == <title>`
     - `owner_display_name == owner.display_name`
   - pass the metadata through `build_pdf_export_stem(...)` with the fixed date
   - assert the stem contains the owner-derived surname/first-name ordering, not the viewer name

2. Course-placed workspace uses the course code and builder fallback activity label.
   - create course and course-placed workspace with owner ACL
   - assert `activity_title is None` in raw metadata
   - build the stem and assert it contains `Loose_Work`
   - assert it still uses the correct course code and owner name

3. Fully loose workspace uses builder fallbacks for both unit and activity.
   - create loose workspace with owner ACL
   - assert raw metadata has `course_code is None` and `activity_title is None`
   - build the stem and assert it starts with `Unplaced_` and contains `Loose_Work`

4. Blank workspace title falls back to `Workspace` through the builder.
   - set `Workspace.title = ""`
   - assert raw metadata returns the blank title
   - build the stem and assert the workspace segment becomes `Workspace`

5. Blank owner display name falls back to `Unknown_Unknown` through the builder.
   - create an owner user with `display_name=""`
   - grant owner ACL
   - assert raw metadata returns the blank display name
   - build the stem and assert the owner segments become `Unknown_Unknown`

6. Missing workspace returns `None`.
   - call `get_workspace_export_metadata(uuid4())`
   - assert the result is `None`

Testing constraints:
- Keep these as integration tests only. Do not use NiceGUI page setup or browser fixtures here.
- Use real DB rows and ACL grants. Do not mock the owner join or placement helpers.
- Make falsifiable assertions on both the raw metadata and the rendered stem so the tests prove the thing itself at this seam.

**Verification:**

Run:
```bash
uv run grimoire test all -- tests/integration/test_workspace_export_metadata.py -v
```

Expected: All metadata-resolution integration tests pass.

Run:
```bash
uvx ty check \
  src/promptgrimoire/db/workspaces.py \
  tests/integration/test_workspace_export_metadata.py
```

Expected: No type errors.

Optional confidence check:

```bash
uv run grimoire test all -- \
  tests/integration/test_peer_discovery_with_owners.py \
  tests/integration/test_workspace_placement.py \
  tests/integration/test_workspace_export_metadata.py -v
```

Expected: Existing adjacent integration seams still pass.

## UAT Steps
1. [ ] Run `uv run grimoire test all -- tests/integration/test_workspace_export_metadata.py -v`.
2. [ ] Inspect one passing activity-placement test and confirm the stem uses the owner's name rather than the separate viewer test user.
3. [ ] Inspect one passing course-placement test and confirm `Loose_Work` came from the builder fallback, not from hardcoded metadata.
4. [ ] Inspect one passing loose-workspace test and confirm `Unplaced` and `Loose_Work` both appear in the rendered stem.

## Evidence Required
- [ ] Green pytest output for `tests/integration/test_workspace_export_metadata.py`
- [ ] `ty check` output with zero issues
- [ ] Test code showing both raw metadata assertions and rendered-stem assertions

**Commit:** `test: cover workspace export metadata integration`
<!-- END_TASK_2 -->

---

## Phase 2 Exit Criteria

Phase 2 is complete when:

1. `get_workspace_export_metadata(...)` exists in `src/promptgrimoire/db/workspaces.py` and returns a narrow dataclass sourced from the workspace row, the owner ACL row, and existing placement helpers.
2. The helper is viewer-agnostic and contains no NiceGUI/session lookups.
3. Integration tests prove:
   - activity-placed exports use owner metadata
   - course-placed exports defer activity fallback to the builder
   - loose exports defer both unit/activity fallbacks to the builder
   - blank title / blank owner name degrade to the expected fallback filename segments
4. `ty check` passes for the changed module and test file.

## Risks To Watch

- Reusing `get_placement_context(...)` directly would accidentally open a second session and weaken the one-helper contract. Keep the resolver inside one session.
- Returning fallback strings from the DB helper would blur Phase 1 and Phase 2 responsibilities. Keep this helper raw and let the builder own presentation fallbacks.
- Tests that assert only raw metadata would miss the actual filename boundary for course/loose workspaces. At least one test per placement mode should render the final stem with a fixed date.
