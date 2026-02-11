# 94-hierarchy-placement Implementation Handoff

**Date:** 2026-02-11 (updated)
**Branch:** 94-hierarchy-placement
**Base SHA:** 5ba6f76 (before Phase 1)
**Current HEAD:** 6dbfdf6

## Status Summary

| Phase | Status | Commits | Tests Added |
|-------|--------|---------|-------------|
| Phase 1: Activity Entity, Schema, CRUD | **Complete** (UAT passed) | 8db798d..d93da7c (6) | 25 |
| Phase 2: Workspace Placement | **Complete** (UAT passed) | a37b06d..2f91d13 (6) | 12 |
| Phase 3: Workspace Cloning (Documents) | **Complete** (code review passed) | fc9f24b..ea67df5 (2) | 5 |
| Phase 4: Workspace Cloning (CRDT State) | **Complete** (code review passed) | 2b496ce..b70d70c (3) | 8 |
| UAT fixes | **Complete** | 9e7c41f..6dbfdf6 (2) | — |
| seed-data CLI | Done (out-of-plan) | 01f9f84 | — |
| Implementation plans | Archived | 55c6903 | — |

**Total tests:** 2266 pass, 0 fail
**Total commits on branch:** 26

## UAT Results (2026-02-11)

All 5 human verification criteria passed:

| Criterion | Result | Notes |
|-----------|--------|-------|
| AC2.5 — Activities under Weeks | **Pass** | Correct hierarchy, icons, "No activities yet" for empty weeks |
| AC2.6 — Create Activity form | **Pass** | Title + description, redirect back to course page |
| AC2.7 — Activity link → template | **Pass** | Navigates to `/annotation?workspace_id={template_id}` |
| AC3.7 — Placement dialog cycle | **Pass** | All three states persist across hard refresh (Ctrl+Shift+F5) |
| AC4.12 — Start clones correctly | **Pass** | Edits clone down but not up; different workspace ID |

## UAT-Driven Fixes

Issues found and fixed during UAT session:

### 1. Missing `await` on `_render_workspace_header()` (annotation.py:2893)
The function was changed from sync to async (to support the placement chip) but the call site was never updated. The entire header (save status, user count, export button, placement chip) silently never rendered.

### 2. Template workspace not auto-placed in its Activity (activities.py)
`create_activity()` created the template `Workspace()` without setting `activity_id`. The Activity knew about the workspace (via `template_workspace_id` FK), but the workspace didn't know about the Activity. Fixed: set `activity_id = activity.id` on the template after Activity creation.

### 3. Ambiguous "Start" button on course page (courses.py)
Original UI showed a title link + generic "Start" button per activity. Instructors couldn't distinguish "go edit the template" from "clone for myself". Fixed: explicit "Edit Template" / "Create Template" and "Start Activity" buttons with clear labels and icons.

### 4. Template placement chip was editable (annotation.py, workspaces.py)
Instructors could use the placement dialog to unplace a template workspace from its Activity, breaking the structural relationship. Fixed: `PlacementContext.is_template` flag locks the chip (purple, lock icon, tooltip: "Template placement is managed by the Activity").

### 5. Dynamic Create/Edit Template label (courses.py, workspace_documents.py)
Added `workspaces_with_documents()` batch query. Course page shows "Create Template" (+ icon) for empty templates and "Edit Template" (pencil icon) for populated ones.

## Key Implementation Decisions

### Phase 1
- `Activity.template_workspace_id` uses `RESTRICT` (not CASCADE) — deleting workspace directly is blocked while Activity exists. `delete_activity()` handles ordering: delete Activity first (triggers SET NULL on student workspaces), then delete orphaned template.
- SQLModel `table=True` bypasses Pydantic validators on direct construction. DB CHECK constraint is the true guard for mutual exclusivity.
- `update_activity()` uses ellipsis sentinel for `description` to distinguish "not provided" from explicit None.

### Phase 2
- `PlacementContext.placement_type` is `Literal["activity", "course", "loose"]`.
- `PlacementContext.is_template` detects template workspaces via `Activity.template_workspace_id` query and locks their placement chip.
- `list_loose_workspaces_for_course` has defense-in-depth `activity_id == None` filter — redundant with CHECK constraint but makes intent explicit.
- Annotation page placement chip is read-only for unauthenticated users and locked for templates.

### Phase 3 & 4
- `clone_workspace_from_activity()` clones documents and CRDT state in a single session (atomic).
- CRDT cloning replays highlights with remapped document IDs via `doc_id_map`. Client metadata is not cloned.

### UAT additions
- Template workspaces are auto-placed in their Activity on creation (back-link).
- `workspaces_with_documents()` uses GROUP BY for efficient batch check of template content.

## User Feedback Notes

- "Language games" — the placement labels ("Unplaced", "Loose work for LAWS1100") may not make intuitive sense to end users. Worth a UX pass later but not blocking.
- seed-data traceback noise — `DuplicateEnrollmentError` logging on idempotent re-run is ugly but harmless.
- Future: workspace placement dashboard (instructor sees all student workspaces per activity; student sees "My Workspaces" with placement). Tracked as a separate concern outside this branch.

## Implementation Plan Location

`docs/implementation-plans/2026-02-08-94-hierarchy-placement/`
- `phase_01.md` through `phase_04.md`
- `test-requirements.md`

## Commit Log

```
6dbfdf6 feat: dynamic Create/Edit Template label on course page
9e7c41f wip: UAT fixes — header await, template placement, UI clarity
55c6903 docs: add implementation plans for 94-hierarchy-placement
b70d70c fix: address code review feedback for Phase 4 CRDT cloning
068bfca test: add CRDT cloning integration tests
2b496ce feat: add CRDT state cloning with document ID remapping
ae4092f feat: add Start button for Activity cloning on course page
ea67df5 test: add document cloning integration tests
fc9f24b feat: add clone_workspace_from_activity for document cloning
873b7af fix: use TEST_DATABASE_URL in pre-test cleanup to prevent dev DB truncation
2f91d13 fix: address code review feedback for Phase 2
efa73e8 feat: add placement status chip and dialog to annotation page
9fbe461 test: add placement context integration tests
ec55798 feat: add placement context query for hierarchy display
0cf05f5 test: add workspace placement integration tests
a37b06d feat: add workspace placement CRUD functions
01f9f84 feat: add seed-data CLI command for dev provisioning
d93da7c feat: add Create Activity page and button on course detail
c07ed86 feat: display Activities under Weeks on course detail page
c6d95fe test: add Activity CRUD integration tests
0bbdf65 feat: add Activity CRUD module
3d5cfb4 test: add Workspace placement mutual exclusivity unit tests
132f643 test: add Activity model and schema integration tests
0346143 feat: add Alembic migration for Activity table and Workspace placement
8db798d feat: add Activity model and extend Workspace with placement fields
536baa3 docs: add Seam B hierarchy & placement implementation plan
```

## Next Steps

1. Final code review
2. Finish development branch (PR or merge)
