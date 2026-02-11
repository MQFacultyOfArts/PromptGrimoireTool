# UAT Failure Investigation — Phase 3+4 Cloning

## Status: BLOCKED — waiting for annotation regression fix from other branch

## Symptom

After implementing Phase 3 (workspace document cloning) and Phase 4 (CRDT state
cloning), UAT failed:

1. Cloned workspace shows "Add content to annotate" (empty)
2. CRDT state is stale — doesn't reflect recent annotations
3. Annotations are "very flaky" — hard to add at all

## Root Cause (confirmed 2026-02-08)

**Annotations are broken on the annotation page itself.** Double-clicking to
select text immediately unhighlights the word. This means the CRDT document
stays empty, and cloning an empty template produces an empty clone.

The cloning code (Phase 3+4) is likely correct — all 14 integration tests pass.
The issue is upstream: the annotation interaction is broken, probably a
regression from the three-tab merge (commit `b5d441d`).

## Hypotheses Tested

### H2: Annotation interaction broken (CONFIRMED)
- User pasted document into workspace `09d41f58-8205-497a-8c6c-f1ba7719d20d`
- Double-click to select → immediately unhighlights
- No annotations can be added → nothing to clone

### H1: CRDT persistence silently failing (NOT YET TESTED)
- `_persist_workspace` has catch-all `except Exception` that only logs
- Could be swallowing DB errors
- Test: query `workspace.crdt_state` directly in DB after adding annotations
- Moot if H2 is the root cause — can't persist what doesn't exist

### H3: Documents saved to wrong workspace (NOT YET TESTED)
- Instructor might be on a different workspace than `template_workspace_id`
- Test: compare `workspace_document.workspace_id` with `activity.template_workspace_id`
- Unlikely given the URL construction in courses.py uses `act.template_workspace_id`

### H4: Clone redirect race condition (NOT YET TESTED)
- `start_activity()` redirects immediately after clone
- Test: reload page after "Start" — if documents appear, it's a race
- Unlikely given user said "minutes later" still stale

## What Needs to Happen

1. Fix annotation regression (likely in other branch)
2. Merge fix into this branch (`94-hierarchy-placement`)
3. Re-test: can annotations be added reliably?
4. Re-test: does cloning work with real annotations?
5. If cloning still fails, investigate H1/H3/H4

## Code Investigation Summary

Persistence flow traced through 5 files — no obvious code-level bug found:

- `annotation.py`: All 5 `mark_dirty_workspace` + `force_persist_workspace`
  call sites verified (lines 645, 736, 815, 995, 2647)
- `persistence.py`: `_persist_workspace` gets doc from registry, calls
  `save_workspace_crdt_state()`, clears dirty flag on success
- `workspaces.py`: `save_workspace_crdt_state` opens session, sets crdt_state,
  auto-commits via `get_session()` context manager
- `engine.py`: `get_session()` auto-commits at line 134
- `annotation_doc.py`: Registry caches docs by `f"ws-{workspace_id}"`

Three-tab merge diff (515 lines) checked — core persistence flow unchanged.

## Commits on This Branch (Phase 3+4)

- `ca1d53f` — Phase 3 Task 1: workspace document cloning
- `8e9e363` — Phase 3 Task 2: cloning tests
- `9b0a638` — Phase 3 review fixes
- `cb8d9eb` — Phase 4 Task 1: CRDT replay
- `3768461` — Phase 4 Task 2: CRDT replay tests
- `59acc27` — Phase 4 review fixes
