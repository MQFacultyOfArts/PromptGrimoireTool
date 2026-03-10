# Tag Lifecycle Refactor — Phase 2: DB–CRDT Dual Write

**Goal:** Every tag/group mutation writes to both DB and CRDT.

**Architecture:** Add an optional `crdt_doc: AnnotationDocument | None = None` parameter to all mutation functions in `db/tags.py`. When provided, write to the live CRDT doc after the DB write. When `None`, skip the CRDT write (CLI/scripts/import contexts). Refactor `_cleanup_crdt_highlights_for_tag()` to use the passed doc when available.

**Tech Stack:** SQLModel (existing), pycrdt via AnnotationDocument methods from Phase 1

**Scope:** 8 phases from original design (phase 2 of 8)

**Codebase verified:** 2026-03-06

---

## Acceptance Criteria Coverage

This phase implements and tests:

### tag-lifecycle-235-291.AC1: Tag metadata in DB and CRDT
- **tag-lifecycle-235-291.AC1.1 Success:** Creating a tag writes metadata to both DB `tag` table and CRDT `tags` Map with matching fields
- **tag-lifecycle-235-291.AC1.2 Success:** Updating a tag's name/colour/description in the management dialog updates both DB and CRDT
- **tag-lifecycle-235-291.AC1.3 Success:** Deleting a tag removes it from both DB and CRDT, including its highlights list
- **tag-lifecycle-235-291.AC1.4 Success:** Creating/updating/deleting a tag group writes to both DB and CRDT

---

## Pre-existing Complexity Violations

The following functions in files touched by this phase exceed the complexipy threshold (15). When modifying these functions, extract helpers to bring them below threshold:

| Function | File | Complexity | Action |
|----------|------|-----------|--------|
| `update_tag` | db/tags.py | 18 | Adding crdt_doc parameter — extract lock-check and partial-update logic into helpers |

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Add `crdt_doc` parameter to `create_tag()` and `create_tag_group()`

**Verifies:** tag-lifecycle-235-291.AC1.1, tag-lifecycle-235-291.AC1.4

**Files:**
- Modify: `src/promptgrimoire/db/tags.py:44-95` (`create_tag_group`), `src/promptgrimoire/db/tags.py:173-240` (`create_tag`)
- Test: `tests/integration/test_tag_crud.py` (extend existing test classes)

**Implementation:**

Add `crdt_doc: AnnotationDocument | None = None` as a keyword-only parameter to both functions.

For `create_tag_group()`, after the DB flush that assigns `order_index` (around line 90), add:

```python
if crdt_doc is not None:
    crdt_doc.set_tag_group(
        group_id=group.id,
        name=group.name,
        order_index=group.order_index,
        colour=group.color,
    )
```

For `create_tag()`, after the DB flush (around line 230), add:

```python
if crdt_doc is not None:
    crdt_doc.set_tag(
        tag_id=tag.id,
        name=tag.name,
        colour=tag.color,
        order_index=tag.order_index,
        group_id=tag.group_id,
        description=tag.description,
        highlights=[],
    )
```

Add the import at the top of `db/tags.py`:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from promptgrimoire.crdt.annotation_doc import AnnotationDocument
```

**Testing:**

Tests must verify:
- tag-lifecycle-235-291.AC1.1: `create_tag(ws_id, name, color, crdt_doc=doc)` — verify both DB row exists AND `doc.get_tag(tag.id)` returns matching data
- tag-lifecycle-235-291.AC1.4: `create_tag_group(ws_id, name, crdt_doc=doc)` — verify both DB row AND CRDT entry
- Edge: `create_tag(ws_id, name, color)` without `crdt_doc` — verify DB row created, no crash
- Edge: `create_tag_group(ws_id, name)` without `crdt_doc` — same

Integration test pattern: Create an `AnnotationDocument("test")` in the test, pass it to the function, then verify both DB state (query) and CRDT state (`doc.get_tag()`).

**Verification:**
Run: `uv run pytest tests/integration/test_tag_crud.py -v -k "create"`
Expected: All tests pass

**Commit:** `feat: add crdt_doc parameter to create_tag and create_tag_group`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add `crdt_doc` parameter to `update_tag()` and `update_tag_group()`

**Verifies:** tag-lifecycle-235-291.AC1.2, tag-lifecycle-235-291.AC1.4

**Files:**
- Modify: `src/promptgrimoire/db/tags.py:107-140` (`update_tag_group`), `src/promptgrimoire/db/tags.py:249-296` (`update_tag`)
- Test: `tests/integration/test_tag_crud.py` (extend existing test classes)

**Implementation:**

Add `crdt_doc: AnnotationDocument | None = None` as keyword-only parameter.

For `update_tag_group()`, after the DB flush, add CRDT write. Read the full current state from DB (the function already has the refreshed model), then call `set_tag_group()` with ALL current values (not just changed ones — full replacement pattern):

```python
if crdt_doc is not None:
    crdt_doc.set_tag_group(
        group_id=group.id,
        name=group.name,
        order_index=group.order_index,
        colour=group.color,
    )
```

For `update_tag()`, same pattern — after DB flush, write full current state:

```python
if crdt_doc is not None:
    # Preserve existing highlights from CRDT
    existing = crdt_doc.get_tag(tag.id)
    highlights = existing.get("highlights", []) if existing else []
    crdt_doc.set_tag(
        tag_id=tag.id,
        name=tag.name,
        colour=tag.color,
        order_index=tag.order_index,
        group_id=tag.group_id,
        description=tag.description,
        highlights=highlights,
    )
```

Note: `update_tag()` preserves the existing `highlights` list from CRDT — the update only changes metadata fields.

**Testing:**

Tests must verify:
- tag-lifecycle-235-291.AC1.2: Create tag with crdt_doc, then `update_tag(tag_id, name="New", crdt_doc=doc)` — verify CRDT entry has new name, existing highlights preserved
- tag-lifecycle-235-291.AC1.4: Create group with crdt_doc, then `update_tag_group(group_id, name="New", crdt_doc=doc)` — verify CRDT entry updated
- Edge: Update without crdt_doc — DB updated, no crash
- Edge: Update tag that doesn't exist in CRDT (crdt_doc provided but tag was created without it) — should create the CRDT entry

**Verification:**
Run: `uv run pytest tests/integration/test_tag_crud.py -v -k "update"`
Expected: All tests pass

**Commit:** `feat: add crdt_doc parameter to update_tag and update_tag_group`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add `crdt_doc` parameter to `delete_tag()` and `delete_tag_group()`

**Verifies:** tag-lifecycle-235-291.AC1.3, tag-lifecycle-235-291.AC1.4

**Files:**
- Modify: `src/promptgrimoire/db/tags.py:143-156` (`delete_tag_group`), `src/promptgrimoire/db/tags.py:299-336` (`delete_tag`), `src/promptgrimoire/db/tags.py:540-595` (`_cleanup_crdt_highlights_for_tag`)
- Test: `tests/integration/test_tag_crud.py` (extend existing test classes)

**Implementation:**

For `delete_tag_group()`, add `crdt_doc` parameter. After DB delete:

```python
if crdt_doc is not None:
    crdt_doc.delete_tag_group(group_id)
```

For `delete_tag()`, add `crdt_doc` parameter. The function already calls `_cleanup_crdt_highlights_for_tag()`. Refactor:

- Pass `crdt_doc` to `_cleanup_crdt_highlights_for_tag()`
- In `_cleanup_crdt_highlights_for_tag()`: if `crdt_doc` is provided, operate on it directly (remove highlights, delete tag_order entry, **and** delete from `tags` Map). If `crdt_doc` is `None`, fall back to the current load-from-DB pattern.
- Add `crdt_doc.delete_tag(tag_id)` to remove from the new `tags` Map (the existing cleanup only removes from `tag_order` and `highlights`)

Update `_cleanup_crdt_highlights_for_tag` signature:

```python
async def _cleanup_crdt_highlights_for_tag(
    workspace_id: UUID,
    tag_id: UUID,
    crdt_doc: AnnotationDocument | None = None,
) -> int:
```

When `crdt_doc` is provided:
- Operate on the passed doc directly (no DB load/save round-trip)
- Remove matching highlights from the doc
- Delete from `doc.tag_order` (existing behaviour)
- Delete from `doc.tags` (new)
- Do NOT save back to DB — the persistence layer handles that via the observer

When `crdt_doc` is `None`:
- Existing behaviour: load from DB, modify, save back

**Testing:**

Tests must verify:
- tag-lifecycle-235-291.AC1.3: Create tag with crdt_doc, add highlights, then `delete_tag(tag_id, crdt_doc=doc)` — verify tag removed from CRDT `tags` Map, highlights removed, tag_order entry removed
- tag-lifecycle-235-291.AC1.4: Create group with crdt_doc, then `delete_tag_group(group_id, crdt_doc=doc)` — verify group removed from CRDT
- Edge: Delete without crdt_doc — existing load-from-DB cleanup still works (regression test for existing `TestDeleteTagCrdtCleanup`)
- Edge: Delete tag that has no CRDT entry — no crash

**Verification:**
Run: `uv run pytest tests/integration/test_tag_crud.py -v -k "delete"`
Expected: All tests pass

**Commit:** `feat: add crdt_doc parameter to delete_tag, delete_tag_group, and _cleanup`

<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->
<!-- START_TASK_4 -->
### Task 4: Add `crdt_doc` parameter to reorder functions

**Verifies:** tag-lifecycle-235-291.AC1.1 (order_index sync), tag-lifecycle-235-291.AC1.4 (group order sync)

**Files:**
- Modify: `src/promptgrimoire/db/tags.py:353-386` (`reorder_tags`), `src/promptgrimoire/db/tags.py:389-422` (`reorder_tag_groups`)
- Test: `tests/integration/test_tag_crud.py` (extend existing test classes)

**Implementation:**

Add `crdt_doc: AnnotationDocument | None = None` parameter to both.

For `reorder_tags()`, after DB updates, sync order_index values to CRDT:

```python
if crdt_doc is not None:
    for idx, tag_id in enumerate(tag_ids):
        existing = crdt_doc.get_tag(tag_id)
        if existing:
            existing["order_index"] = idx
            crdt_doc.set_tag(
                tag_id=tag_id,
                name=existing["name"],
                colour=existing["colour"],
                order_index=idx,
                group_id=existing.get("group_id"),
                description=existing.get("description"),
                highlights=existing.get("highlights", []),
            )
```

Same pattern for `reorder_tag_groups()`.

**Testing:**

Tests must verify:
- Reorder tags with crdt_doc — verify CRDT entries have updated order_index values
- Reorder groups with crdt_doc — same
- Edge: Reorder without crdt_doc — DB updated, no crash

**Verification:**
Run: `uv run pytest tests/integration/test_tag_crud.py -v -k "reorder"`
Expected: All tests pass

**Commit:** `feat: add crdt_doc parameter to reorder_tags and reorder_tag_groups`

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Verify all existing tests pass — full regression

**Verifies:** None (regression verification)

**Files:**
- No modifications — verification only

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass. The optional `crdt_doc` parameter with `None` default means all existing call sites work unchanged.

**Commit:** No commit needed — verification only

<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->
