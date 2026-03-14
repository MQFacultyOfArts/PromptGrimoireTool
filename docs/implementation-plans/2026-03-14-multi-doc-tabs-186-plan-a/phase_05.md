## Phase 5: Diff-Based Card Updates (Design Phase 4)

### Acceptance Criteria Coverage

This phase implements and tests:

### multi-doc-tabs-186.AC12: Diff-Based Card Updates
- **multi-doc-tabs-186.AC12.1 Success:** Adding a highlight inserts one card without destroying or rebuilding other cards
- **multi-doc-tabs-186.AC12.2 Success:** Removing a highlight deletes one card element without full container rebuild
- **multi-doc-tabs-186.AC12.3 Success:** New card inserted at correct position sorted by `start_char`
- **multi-doc-tabs-186.AC12.4 Success:** Tag or comment change on a highlight updates only that card
- **multi-doc-tabs-186.AC12.5 Edge:** Rapid successive CRDT updates (debounced) do not produce duplicate or missing cards

**Design phase note:** `remove_highlights_for_document()` is listed in design Phase 4 components but implemented here in impl Phase 5 alongside the diff-based card updates. Plan B Phase 8 (delete document with CRDT purge) depends on this method existing — it will be available since Plan A completes before Plan B begins.

---

<!-- START_TASK_1 -->
### Task 1: Add remove_highlights_for_document() to AnnotationDoc

**Verifies:** None directly (prerequisite for AC9 in Plan B, enables testing diff removals)

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py` (add method after `remove_highlight()`)
- Test: `tests/unit/test_annotation_doc.py` (extend with new tests)

**Implementation:**
Add convenience method to `AnnotationDoc`:

```python
def remove_highlights_for_document(
    self, document_id: str, origin_client_id: str | None = None
) -> int:
    """Remove all highlights belonging to a document.

    Args:
        document_id: Document ID whose highlights should be removed.
        origin_client_id: Client making the change (for echo prevention).

    Returns:
        Number of highlights removed.
    """
    highlights = self.get_highlights_for_document(document_id)
    removed = 0
    for hl in highlights:
        hl_id = hl.get("id", "")
        if hl_id and self.remove_highlight(hl_id, origin_client_id):
            removed += 1
    return removed
```

**Testing:**
- Add highlights to document A (5) and document B (3)
- Call `remove_highlights_for_document(A)` → returns 5
- Verify document A has 0 highlights, document B still has 3
- Call on empty document → returns 0

**Verification:**
Run: `uv run grimoire test run tests/unit/test_annotation_doc.py`
Expected: All tests pass

**Commit:** `feat: add remove_highlights_for_document to AnnotationDoc`
<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-4) -->
<!-- START_TASK_2 -->
### Task 2: Implement _diff_annotation_cards() core function

**Verifies:** multi-doc-tabs-186.AC12.1, multi-doc-tabs-186.AC12.2, multi-doc-tabs-186.AC12.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/cards.py` (add diff function, modify refresh)
- Test: `tests/integration/test_annotation_cards_charac.py` (extend with diff tests)

**Implementation:**
Add `_diff_annotation_cards(state: PageState) -> None` that replaces the clear+rebuild in `_refresh_annotation_cards()`.

Algorithm:
1. Get current highlights from CRDT (same as existing: `get_highlights_for_document()` or `get_all_highlights()`)
2. Build sets: `crdt_ids = {hl["id"] for hl in highlights}`, `registry_ids = set(state.annotation_cards.keys())`
3. **Removed** (`registry_ids - crdt_ids`): For each, call `state.annotation_cards[id].delete()`, remove from dict
4. **Added** (`crdt_ids - registry_ids`): For each, call `_build_annotation_card(state, hl)`, find correct position by `start_char` ordering, call `card.move(target_container=state.annotations_container, target_index=position)`
5. **Changed** (IDs in both): Compare highlight data to detect tag/comment changes. If changed, delete old card, rebuild new card at same position using `.move(target_index=position)`. If unchanged, skip.
6. Increment `cards_epoch`, broadcast to JS

**Key implementation details:**
- Build all operations within `with state.annotations_container:` context (slot resolution)
- Position calculation: sort CRDT highlights by `start_char`, find index of new highlight in sorted list
- For "changed" detection: compare tag, comment count, and comment text against cached values. Store a hash or relevant fields in the registry alongside the card element.
- Consider changing `state.annotation_cards` from `dict[str, ui.card]` to `dict[str, tuple[ui.card, dict]]` where the dict stores the highlight snapshot for change detection. **Note:** If this type change is adopted, the design doc's architecture section (`annotation_cards: dict[str, ui.element]`) must be updated before implementation begins, per the implementation guidance's planning gate requirement.

**Modify `_refresh_annotation_cards()`** to call `_diff_annotation_cards()` instead of clearing:
```python
def _refresh_annotation_cards(state: PageState) -> None:
    if state.annotations_container is None or state.crdt_doc is None:
        return
    if state.annotation_cards is None:
        # First render — do full build
        state.annotation_cards = {}
        with state.annotations_container:
            highlights = _get_highlights(state)
            for hl in highlights:
                hl_id = hl.get("id", "")
                card = _build_annotation_card(state, hl)
                state.annotation_cards[hl_id] = card
            state.cards_epoch += 1
            ui.run_javascript(f"window.__annotationCardsEpoch = {state.cards_epoch}")
    else:
        # Subsequent renders — diff
        _diff_annotation_cards(state)
```

**Testing:**
- AC12.1: Add highlight, verify card count increased by 1, other cards not destroyed (check `expanded_cards` preservation)
- AC12.2: Remove highlight, verify card count decreased by 1, other cards intact
- AC12.3: Add highlight with `start_char` between two existing highlights, verify card appears at correct position

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass (Phase 1 characterisation tests + new diff tests)

**Commit:** `feat: implement diff-based card updates replacing clear+rebuild`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Handle tag/comment changes in diff

**Verifies:** multi-doc-tabs-186.AC12.4

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/cards.py` (extend diff with change detection)
- Test: `tests/integration/test_annotation_cards_charac.py` (extend)

**Implementation:**
Extend `_diff_annotation_cards()` to detect when a highlight's tag or comments have changed:

1. Store highlight snapshot alongside card in registry (tag value, comment IDs/text hash)
2. On diff, compare current CRDT highlight against stored snapshot
3. If changed: delete old card element, rebuild new card, `.move()` to same position, update snapshot
4. Preserve `expanded_cards` set — if the highlight was expanded before the change, it should remain expanded after

**Testing:**
- AC12.4: Change tag on a highlight → only that card rebuilds, other cards unaffected
- AC12.4: Add comment to a highlight → only that card rebuilds
- Expansion state preserved after tag change

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `feat: detect and handle tag/comment changes in card diff`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Verify rapid CRDT update handling

**Verifies:** multi-doc-tabs-186.AC12.5

**Files:**
- Test: `tests/integration/test_annotation_cards_charac.py` (extend with rapid update test)

**Implementation:**
Test that multiple CRDT changes arriving in quick succession produce correct card state:

1. Add 3 highlights to CRDT in rapid succession (no await between adds)
2. Trigger refresh
3. Verify exactly 3 cards exist, in correct `start_char` order, no duplicates

Also test:
- Rapid add + remove (add highlight then immediately remove it) → card should not appear
- Rapid tag changes on same highlight → final state reflects last change

**Testing:**
- AC12.5: Create test that exercises rapid successive operations, verify final card state is consistent

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass, no duplicate or missing cards

Run: `uv run complexipy src/promptgrimoire/pages/annotation/cards.py`
Expected: All functions within complexity limits (especially `_diff_annotation_cards` — may need to extract helpers if > 15)

**Commit:** `test: verify rapid CRDT updates produce consistent card state`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_A -->
