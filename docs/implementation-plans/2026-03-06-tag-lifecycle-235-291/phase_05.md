# Tag Lifecycle Refactor — Phase 5: Organise Tab Sync

**Goal:** Tag metadata changes and highlight reassignment in the organise tab propagate via CRDT.

**Architecture:** Update `move_highlight_to_tag()` to write the `highlights` field in the `tags` Map alongside the existing `tag_order` Map (dual write for backward compatibility). The organise tab already rebuilds on broadcast from Phase 3 — minimal additional changes needed. Update `set_tag_order()` to also sync the `highlights` field.

**Tech Stack:** pycrdt (existing Map operations), NiceGUI SortableJS (existing)

**Scope:** 8 phases from original design (phase 5 of 8)

**Codebase verified:** 2026-03-06

---

## Acceptance Criteria Coverage

This phase implements and tests:

### tag-lifecycle-235-291.AC5: Organise tab sync
- **tag-lifecycle-235-291.AC5.1 Success:** Reordering tags in the organise tab propagates to all connected clients
- **tag-lifecycle-235-291.AC5.2 Success:** Reassigning a tag to a different group propagates to all connected clients
- **tag-lifecycle-235-291.AC5.3 Success:** Dragging a highlight between tag columns updates the tag's highlight list in the CRDT

---

**Note on transitional dual-write:** Phase 5 writes to both `tag_order` Map and `tags` Map `highlights` field simultaneously. This is intentional — `tag_order` is still read by `organise.py` and `workspace.py` drag handlers during Phases 5-7. Phase 8 redirects those reads to `tags` Map `highlights` and removes `tag_order` entirely. The dual-write ensures no data loss during the transition.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Update `move_highlight_to_tag()` to write to `tags` Map `highlights` field

**Verifies:** tag-lifecycle-235-291.AC5.3

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py:407-458` (`move_highlight_to_tag`)
- Test: `tests/unit/test_annotation_doc.py` (extend `TestTagOrder`)

**Implementation:**

In `move_highlight_to_tag()`, after the existing `tag_order` writes, also update the `highlights` field in the `tags` Map entries:

After `self.tag_order[from_tag] = Array(source_ids)` (line 441), add:
```python
# Also update tags Map highlights field (dual write for transition)
from_tag_entry = self.get_tag(from_tag)
if from_tag_entry is not None:
    from_highlights = list(from_tag_entry.get("highlights", []))
    if highlight_id in from_highlights:
        from_highlights.remove(highlight_id)
    self.set_tag(
        tag_id=from_tag,
        name=from_tag_entry["name"],
        colour=from_tag_entry["colour"],
        order_index=from_tag_entry["order_index"],
        group_id=from_tag_entry.get("group_id"),
        description=from_tag_entry.get("description"),
        highlights=from_highlights,
    )
```

After `self.tag_order[to_tag] = Array(target_ids)` (line 449), add:
```python
to_tag_entry = self.get_tag(to_tag)
if to_tag_entry is not None:
    to_highlights = list(to_tag_entry.get("highlights", []))
    if highlight_id not in to_highlights:
        if position == -1:
            to_highlights.append(highlight_id)
        else:
            to_highlights.insert(position, highlight_id)
    self.set_tag(
        tag_id=to_tag,
        name=to_tag_entry["name"],
        colour=to_tag_entry["colour"],
        order_index=to_tag_entry["order_index"],
        group_id=to_tag_entry.get("group_id"),
        description=to_tag_entry.get("description"),
        highlights=to_highlights,
    )
```

**Testing:**

Tests must verify:
- tag-lifecycle-235-291.AC5.3: Move highlight between tags — verify both `tag_order` and `tags` Map `highlights` fields updated correctly
- Edge: Move when tags Map doesn't have the tag entry (graceful no-op for the tags Map part)
- Edge: Move to same tag (reorder) — verify highlights list reordered in tags Map

**Verification:**
Run: `uv run pytest tests/unit/test_annotation_doc.py -v -k "move_highlight"`
Expected: All tests pass

**Commit:** `feat: update move_highlight_to_tag to write tags Map highlights field`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update `set_tag_order()` to sync `tags` Map `highlights` field

**Verifies:** tag-lifecycle-235-291.AC5.1

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py:388-406` (`set_tag_order`)
- Test: `tests/unit/test_annotation_doc.py`

**Implementation:**

In `set_tag_order()`, after writing to `tag_order` Map, also sync the `highlights` field in the `tags` Map:

```python
def set_tag_order(
    self, tag: str, highlight_ids: list[str],
    origin_client_id: str | None = None,
) -> None:
    token = _origin_var.set(origin_client_id)
    try:
        self.tag_order[tag] = Array(highlight_ids)
        # Sync tags Map highlights field
        tag_entry = self.get_tag(tag)
        if tag_entry is not None:
            self.set_tag(
                tag_id=tag,
                name=tag_entry["name"],
                colour=tag_entry["colour"],
                order_index=tag_entry["order_index"],
                group_id=tag_entry.get("group_id"),
                description=tag_entry.get("description"),
                highlights=highlight_ids,
            )
    finally:
        _origin_var.reset(token)
```

**Testing:**

Tests must verify:
- Set tag order — verify `tags` Map `highlights` field matches
- Set tag order when tag doesn't exist in tags Map — no crash, tag_order still updated

**Verification:**
Run: `uv run pytest tests/unit/test_annotation_doc.py -v -k "tag_order"`
Expected: All tests pass

**Commit:** `feat: sync set_tag_order with tags Map highlights field`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Ensure organise tab drag handler calls broadcast after CRDT update

**Verifies:** tag-lifecycle-235-291.AC5.1, tag-lifecycle-235-291.AC5.2

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/workspace.py:198-268` (drag handler `_on_organise_sort_end`)

**Implementation:**

In the sort-end handler, after any CRDT write (move_highlight_to_tag or set_tag_order), ensure `state.broadcast_update()` is called to propagate to other clients. Check if this is already happening — the investigator found that broadcast is called after organise operations.

If not already present, add after CRDT writes:
```python
if state.broadcast_update:
    await state.broadcast_update()
```

Also ensure that when tag group reassignment happens via the management dialog (AC5.2), the dual-write from Phase 4 handles the crdt_doc update. The organise tab on other clients rebuilds via `state.refresh_organise()` on broadcast (already wired in Phase 3).

**Testing:**

- Existing drag tests should continue to pass

**Verification:**
Run: `uv run grimoire test changed`
Expected: All tests pass

**Commit:** `feat: ensure organise drag operations broadcast to all clients`

<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_4 -->
### Task 4: E2E test — highlight drag and group reassignment propagate

**Verifies:** tag-lifecycle-235-291.AC5.2, tag-lifecycle-235-291.AC5.3

**Files:**
- Test: `tests/e2e/test_tag_sync.py` (extend from Phase 3/4)

**Implementation:**

E2E test for organise tab highlight drag:

1. Open workspace with at least two tags and one highlight assigned to the first tag
2. Switch to organise tab
3. Drag the highlight from the first tag's column to the second tag's column (SortableJS drag simulation)
4. Verify the highlight appears in the second tag's column
5. Refresh the page — verify the highlight is still in the second tag's column (CRDT persistence)

If SortableJS drag simulation is too complex for E2E, an integration test that calls `move_highlight_to_tag()` directly and verifies both `tag_order` and `tags` Map `highlights` field are updated is an acceptable alternative.

For AC5.2 (group reassignment propagation): open two browser contexts. On client A, open the tag management dialog and change a tag's group via the group selector. Verify client B's organise tab updates to show the tag in the new group column without refresh.

**Testing:**

Two tests:
- `test_highlight_drag_between_tags_persists` (AC5.3)
- `test_tag_group_reassignment_propagates` (AC5.2)

**Verification:**
Run: `uv run grimoire e2e run -k "highlight_drag or group_reassignment"`
Expected: Both tests pass

**Commit:** `test: E2E verify highlight drag and group reassignment propagate`

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Full regression verification

**Verifies:** None (regression verification)

**Files:**
- No modifications — verification only

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** No commit needed — verification only

<!-- END_TASK_5 -->
