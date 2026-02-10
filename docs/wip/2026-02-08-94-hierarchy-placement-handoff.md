# 94-hierarchy-placement Implementation Handoff

**Date:** 2026-02-08
**Branch:** 94-hierarchy-placement
**Base SHA:** 5ba6f76 (before Phase 1)
**Current HEAD:** 23bf30f

## Status Summary

| Phase | Status | Commits | Tests Added |
|-------|--------|---------|-------------|
| Phase 1: Activity Entity, Schema, CRUD | **Complete** (UAT confirmed) | 6c80dca..f35735d (6) | 25 |
| Phase 2: Workspace Placement | **UAT in progress** | f533398..23bf30f (6) | 12 |
| Phase 3: Workspace Cloning (Documents) | Not started | — | — |
| Phase 4: Workspace Cloning (CRDT State) | Not started | — | — |
| seed-data CLI | Done (out-of-plan) | 47e886b | — |

**Total tests:** 2010 pass, 2 skip, 0 fail

## Phase 2 UAT Status

Code review passed (zero issues after one fix cycle). Proleptic challenge resolved.

**UAT partially verified:**
- User confirmed "Unplaced" chip appears on annotation page header
- Remaining AC3.7 steps not yet verified:
  - Place workspace in Activity via dialog (cascading selects)
  - Place workspace in Course via dialog
  - Cycle through all three states (unplaced → activity → course → unplaced)

**To complete Phase 2 UAT:**
1. Start app with `AUTH_MOCK=true` and `DATABASE_URL` set
2. Log in as `instructor@uni.edu`
3. Go to course page, click an Activity link to open annotation page
4. Click the placement chip → test all three placement modes
5. Reply "Confirmed" to proceed to Phase 3

## User Feedback Notes

- "Language games" — the placement labels ("Unplaced", "Loose work for LAWS1100") may not make intuitive sense to end users. Worth a UX pass later but not blocking.
- seed-data traceback noise — `DuplicateEnrollmentError` logging on idempotent re-run is ugly but harmless. Could suppress the engine-level error log for expected exceptions.

## Key Implementation Decisions

### Phase 1
- `Activity.template_workspace_id` uses `RESTRICT` (not CASCADE) — deleting workspace directly is blocked while Activity exists. `delete_activity()` handles ordering: delete Activity first (triggers SET NULL on student workspaces), then delete orphaned template.
- SQLModel `table=True` bypasses Pydantic validators on direct construction. DB CHECK constraint is the true guard for mutual exclusivity.
- `update_activity()` uses ellipsis sentinel for `description` to distinguish "not provided" from explicit None.

### Phase 2
- `PlacementContext.placement_type` is `Literal["activity", "course", "loose"]` (fixed from bare `str` during review).
- `list_loose_workspaces_for_course` has defense-in-depth `activity_id == None` filter — redundant with CHECK constraint but makes intent explicit.
- Annotation page placement chip is read-only for unauthenticated users.
- Cascade select handlers have error handling wrapping DB calls.

## Implementation Plan Location

`docs/implementation-plans/2026-02-08-94-hierarchy-placement/`
- `phase_01.md` through `phase_04.md`
- `test-requirements.md`

## Guidance Files

- Implementation guidance: `.ed3d/implementation-plan-guidance.md`
- Test requirements: `docs/implementation-plans/2026-02-08-94-hierarchy-placement/test-requirements.md`

## Commit Log

```
23bf30f fix: address code review feedback for Phase 2
40380f0 feat: add placement status chip and dialog to annotation page
5d16bf5 test: add placement context integration tests
de1fb85 feat: add placement context query for hierarchy display
5fa7fdb test: add workspace placement integration tests
f533398 feat: add workspace placement CRUD functions
47e886b feat: add seed-data CLI command for dev provisioning
f35735d feat: add Create Activity page and button on course detail
83b5d75 feat: display Activities under Weeks on course detail page
de235dd test: add Activity CRUD integration tests
34824ab feat: add Activity CRUD module
f4694fb test: add Workspace placement mutual exclusivity unit tests
a6e235f test: add Activity model and schema integration tests
0c671ca feat: add Alembic migration for Activity table and Workspace placement
6c80dca feat: add Activity model and extend Workspace with placement fields
```

## Next Steps (for resuming session)

1. Complete Phase 2 UAT (user verifies placement dialog)
2. Phase 3: Workspace Cloning — Documents (3 tasks, 2 subcomponents)
3. Phase 4: Workspace Cloning — CRDT State (2 tasks, 1 subcomponent)
4. Final review sequence (code review + test analysis)
5. Finish development branch
