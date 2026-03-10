# Tag Lifecycle Refactor — Phase 3: CRDT-Primary Rendering

**Goal:** `TagInfo` is built from CRDT maps instead of DB queries during live sessions.

**Architecture:** Add `workspace_tags_from_crdt()` to build `TagInfo` from CRDT maps. Add consistency check (hydration/reconciliation) in `AnnotationDocumentRegistry.get_or_create_for_workspace()`. Extend `handle_update_from_other()` to rebuild tag state when CRDT updates arrive, using the existing broadcast infrastructure for multi-client sync.

**Tech Stack:** pycrdt (Map reading), NiceGUI (existing broadcast mechanism), existing `TagInfo` dataclass

**Scope:** 8 phases from original design (phase 3 of 8)

**Codebase verified:** 2026-03-06

---

## Acceptance Criteria Coverage

This phase implements and tests:

### tag-lifecycle-235-291.AC1: Tag metadata in DB and CRDT
- **tag-lifecycle-235-291.AC1.5 Edge:** On workspace load, if CRDT maps are empty but DB has tags, CRDT is hydrated from DB
- **tag-lifecycle-235-291.AC1.6 Edge:** On workspace load, if DB has a tag the CRDT doesn't, CRDT is reconciled (tag added)

### tag-lifecycle-235-291.AC2: Tag lifecycle sync
- **tag-lifecycle-235-291.AC2.1 Success:** Creating a tag via quick create immediately appears on all connected clients' tag bars (no refresh)
- **tag-lifecycle-235-291.AC2.2 Success:** Creating a tag via management dialog immediately appears on all connected clients
- **tag-lifecycle-235-291.AC2.3 Success:** Editing a tag's name updates on all connected clients' toolbars
- **tag-lifecycle-235-291.AC2.4 Success:** Editing a tag's colour updates highlight CSS on all connected clients
- **tag-lifecycle-235-291.AC2.5 Success:** Deleting a tag removes it from all connected clients' toolbars and organise tabs

---

## Pre-existing Complexity Violations

The following functions in files touched by this phase exceed the complexipy threshold (15). When modifying these functions, extract helpers to bring them below threshold:

| Function | File | Complexity | Action |
|----------|------|-----------|--------|
| `_setup_client_sync` | broadcast.py | **63** | Extending handle_update_from_other — extract tag-refresh logic into a named helper; consider further decomposition of the 63-complexity function if changes touch enough of it |

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create `workspace_tags_from_crdt()` function

**Verifies:** tag-lifecycle-235-291.AC2.1 (data source for rendering)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tags.py:23-84` (add function after existing `workspace_tags()`)
- Test: `tests/unit/test_annotation_doc.py` (new test class — pure unit test, no DB)

**Implementation:**

Add a new function that builds `list[TagInfo]` from CRDT maps. This is a pure function — no DB access, no async.

```python
def workspace_tags_from_crdt(crdt_doc: AnnotationDocument) -> list[TagInfo]:
    """Build TagInfo list from CRDT maps instead of DB.

    Returns TagInfo instances ordered by group order_index then tag
    order_index, matching the same ordering as workspace_tags().
    """
```

Logic:
1. Read all tag groups from `crdt_doc.list_tag_groups()` — build a lookup `{group_id: group_data}`
2. Read all tags from `crdt_doc.list_tags()` — for each, build a `TagInfo`:
   - `name` = tag data `"name"`
   - `colour` = tag data `"colour"`
   - `raw_key` = tag UUID string (the Map key)
   - `group_name` = group lookup by tag's `group_id` → `"name"` (None if no group)
   - `group_colour` = group lookup → `"colour"` (None if no group)
   - `description` = tag data `"description"`
3. Sort by (group `order_index` — ungrouped last, then tag `order_index`)
4. Return the sorted list

Keep existing `workspace_tags()` (DB query version) unchanged — it's still used by export pipeline and FTS.

**Testing:**

Tests must verify:
- Tags with groups are ordered by group order_index then tag order_index
- Tags without groups appear after grouped tags
- Group metadata (group_name, group_colour) is resolved from tag_groups Map
- Empty CRDT doc returns empty list
- Tags with all fields populated produce correct TagInfo instances

Test pattern: Create `AnnotationDocument("test")`, populate with `set_tag()` / `set_tag_group()`, call `workspace_tags_from_crdt(doc)`, assert result.

**Verification:**
Run: `uv run pytest tests/unit/test_annotation_doc.py -v -k "workspace_tags_from_crdt"`
Expected: All tests pass

**Commit:** `feat: add workspace_tags_from_crdt() to build TagInfo from CRDT`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add consistency check to workspace load path

**Verifies:** tag-lifecycle-235-291.AC1.5, tag-lifecycle-235-291.AC1.6

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py:602-640` (`get_or_create_for_workspace`)
- Test: `tests/integration/test_tag_crud.py` (new test class)

**Implementation:**

After loading CRDT state from DB in `get_or_create_for_workspace()` (around line 631), add a consistency check. Extract this into a standalone async function for testability:

```python
async def _ensure_crdt_tag_consistency(
    doc: AnnotationDocument,
    workspace_id: UUID,
) -> None:
    """Hydrate or reconcile CRDT tag maps against DB state.

    Called on every workspace load. If CRDT tags/tag_groups maps are
    empty but DB has rows, hydrate from DB. If both have data, add any
    DB entries missing from CRDT (DB is authoritative). Log discrepancies
    at WARNING level.
    """
```

Logic:
1. Query DB: `list_tags_for_workspace(workspace_id)` and `list_tag_groups_for_workspace(workspace_id)`
2. Read CRDT: `doc.list_tags()` and `doc.list_tag_groups()`
3. **Hydration** (AC1.5): If CRDT maps are empty but DB has rows, call `doc.hydrate_tags_from_db(tags, groups)` (from Phase 1)
4. **Reconciliation** (AC1.6): If both have data, compare. For each DB tag not in CRDT, add it. For each CRDT tag not in DB, log WARNING and remove it (DB is authoritative).
5. After hydration/reconciliation, persist updated CRDT state back to `workspace.crdt_state` if any changes were made. If persistence fails, log at ERROR level and continue — the consistency check will re-run on next workspace load.

Call `_ensure_crdt_tag_consistency(doc, workspace_id)` from `get_or_create_for_workspace()` after `doc.apply_update(workspace.crdt_state)`.

**Testing:**

Integration tests (requires DB):
- tag-lifecycle-235-291.AC1.5: Create workspace with tags in DB, create AnnotationDocument with NO tag data in CRDT state, call consistency check — verify CRDT maps now populated
- tag-lifecycle-235-291.AC1.6: Create workspace with tags in DB, create CRDT with most tags but missing one — verify missing tag is added to CRDT after consistency check
- Edge: Empty DB + empty CRDT → no changes, no errors
- Edge: CRDT has tag not in DB → tag removed from CRDT, WARNING logged

**Verification:**
Run: `uv run pytest tests/integration/test_tag_crud.py -v -k "consistency"`
Expected: All tests pass

**Commit:** `feat: add CRDT tag consistency check on workspace load`

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Switch initial page load to CRDT-primary rendering

**Verifies:** tag-lifecycle-235-291.AC2.1, tag-lifecycle-235-291.AC2.2

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/workspace.py:366` (initial load)
- Modify: `src/promptgrimoire/pages/annotation/tag_management_save.py:23-69` (`_refresh_tag_state`)

**Implementation:**

In `_resolve_workspace_context()` (workspace.py), replace the initial tag load:

**Before** (line 366):
```python
state.tag_info_list = await workspace_tags(workspace_id)
```

**After:**
```python
# Build tags from CRDT (populated by consistency check in get_or_create_for_workspace)
state.tag_info_list = workspace_tags_from_crdt(state.crdt_doc)
```

Import `workspace_tags_from_crdt` from `tags.py`.

In `_refresh_tag_state()` (tag_management_save.py), replace the DB query with CRDT read:

**Before:**
```python
state.tag_info_list = await workspace_tags(state.workspace_id)
```

**After:**
```python
state.tag_info_list = workspace_tags_from_crdt(state.crdt_doc)
```

Note: `_refresh_tag_state()` becomes synchronous for the tag loading part (CRDT is in-memory). The CSS rebuild and highlight menu rebuild remain as-is. Do not remove the `reload_crdt` parameter here — Phase 8, Task 5 removes it as part of legacy cleanup.

**Testing:**

Integration test: create a workspace with tags in DB, run consistency check to populate CRDT, call `workspace_tags_from_crdt(doc)` — verify output matches what `workspace_tags(workspace_id)` would return (same tags, same colours, same ordering). This is the critical correctness test for the rendering switch.

**Verification:**
Run: `uv run pytest tests/integration/test_tag_crud.py -v -k "crdt_primary"`
Expected: All tests pass

**Commit:** `refactor: switch tag rendering to CRDT-primary source`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Extend broadcast callback to rebuild tag state on receiving clients

**Verifies:** tag-lifecycle-235-291.AC2.1, tag-lifecycle-235-291.AC2.3, tag-lifecycle-235-291.AC2.4, tag-lifecycle-235-291.AC2.5

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/broadcast.py` (`handle_update_from_other` closure)
- Modify: `src/promptgrimoire/pages/annotation/tag_management_save.py` (ensure broadcast is called after tag mutations)

**Implementation:**

In `broadcast.py`, extend the `handle_update_from_other()` callback (currently rebuilds CSS and refreshes annotations) to also rebuild tag state from CRDT:

Add to the callback body:
```python
# Rebuild tag state from updated CRDT
state.tag_info_list = workspace_tags_from_crdt(state.crdt_doc)
_update_highlight_css(state)
```

The existing `_update_highlight_css(state)` call already rebuilds CSS from `state.tag_colours()`. With `tag_info_list` now updated from CRDT, the CSS will reflect any tag colour changes.

For the tag toolbar rebuild: the toolbar needs to be rebuilt when tags change. Add a call to rebuild the toolbar if `state.toolbar_container` exists. This follows the existing pattern in `_rebuild_toolbar()`.

In `_refresh_tag_state()`: after refreshing the local client's tag state, ensure `state.broadcast_update()` is called. Check existing call sites — some already call it, others may not. Every tag mutation path needs to end with a broadcast.

**Testing:**

Unit test (pure CRDT, no DB): construct two `AnnotationDocument` instances sharing state (apply one's update to the other). Set a tag on doc A, sync to doc B, call `workspace_tags_from_crdt(doc_b)` — verify the tag appears. This tests the CRDT sync pathway that broadcast relies on.

**Verification:**
Run: `uv run pytest tests/unit/test_annotation_doc.py -v -k "sync"`
Expected: All tests pass

**Commit:** `feat: extend broadcast callback to sync tag state across clients`

<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
### Task 5: E2E test — tag create propagates to second client

**Verifies:** tag-lifecycle-235-291.AC2.1, tag-lifecycle-235-291.AC2.2

**Files:**
- Test: `tests/e2e/test_tag_sync.py` (new file)

**Implementation:**

E2E test using two browser contexts on the same workspace:

1. Client A opens workspace, creates a tag via quick create
2. Client B (already open on same workspace) should see the new tag appear in the tag toolbar within a few seconds — no page refresh
3. Assert via `page_b.get_by_test_id("tag-chip-<tag_name>")` or equivalent toolbar element

This is the minimal E2E verification that the full pipeline works: DB write → CRDT write → broadcast → receiving client rebuilds tag_info_list → toolbar updates.

**Testing:**

Single test: `test_tag_create_propagates_to_second_client`

**Verification:**
Run: `uv run grimoire e2e run -k "tag_create_propagates"`
Expected: Test passes

**Commit:** `test: E2E verify tag create propagates to second client`

<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Full regression verification

**Verifies:** None (regression verification)

**Files:**
- No modifications — verification only

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass. Tag toolbar renders correctly from CRDT data.

**Commit:** No commit needed — verification only

<!-- END_TASK_6 -->
