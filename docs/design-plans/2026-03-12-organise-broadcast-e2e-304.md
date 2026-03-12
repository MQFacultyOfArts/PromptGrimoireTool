# Organise Tab Broadcast E2E Test Design

**GitHub Issue:** #304

## Summary

Add an E2E test verifying that the Organise tab auto-refreshes when a remote client drags a highlight between tag columns. Refactor the existing concurrent drag test to use broadcast auto-refresh instead of tab-switching workarounds. A spike confirmed the broadcast path (`broadcast.py:310-314`) already works correctly — this is test-only work.

## Definition of Done

1. New E2E test proving the Organise tab auto-refreshes on remote drag: two clients on the same workspace both viewing the Organise tab, Client A drags a highlight between tag columns, Client B's organise tab reflects the move automatically without tab switching or manual refresh.
2. Existing `test_concurrent_drag_produces_consistent_result` refactored to use broadcast auto-refresh instead of the tab-switching workaround loops.
3. No production code changes needed — the broadcast path (`broadcast.py:310-314`) already works correctly (verified by spike).

## Acceptance Criteria

### AC1: New broadcast drag test (DoD item 1)

**AC1.1** (success): Two browser contexts open to the same workspace, both on the Organise tab. Client A drags a highlight from Tag X's column to Tag Y's column. Client B sees the card appear in Tag Y's column within 10 seconds without any tab switch or page reload.

**AC1.2** (success): After the broadcast refresh, Client B's Tag X column no longer contains the dragged card.

**AC1.3** (failure): If the broadcast does not deliver within 10 seconds, the test fails with a clear timeout message identifying which client and which column.

### AC2: Refactor existing concurrent drag test (DoD item 2)

**AC2.1** (success): The two tab-switching polling loops in `test_concurrent_drag_produces_consistent_result` (lines 411-420 and 439-450) are replaced with direct `expect` assertions on column card visibility.

**AC2.2** (success): The refactored test still verifies the same invariant: both clients show consistent final state after concurrent cross-column drags.

**AC2.3** (failure): If the refactored test becomes flaky (fails >1 in 10 runs), revert and investigate whether the auto-refresh has a timing gap for concurrent operations.

## Architecture

### Broadcast path (existing, no changes)

```
Client A: drag card → _on_organise_sort_end()
  → crdt_doc.move_highlight_to_tag()
  → pm.force_persist_workspace()
  → state.broadcast_update()
    → invoke_callback() on Client B
      → with client_b.nicegui_client:  # sets NiceGUI slot context
          → _handle_remote_update(state_b)
            → if active_tab == "Organise":
                → refresh_organise_with_scroll()
                  → capture scroll → container.clear() → re-render → restore scroll
```

The `with self.nicegui_client:` context manager (NiceGUI's `Client.__enter__`) pushes the receiving client's content slot onto the asyncio task's slot stack, so all element creation and `run_javascript` calls inside the callback resolve to the correct browser tab.

### Test structure

New `TestBroadcastDrag` class in `test_annotation_drag.py`:
- Uses existing `two_annotation_contexts` fixture (provides two authenticated pages on the same workspace)
- One test: `test_organise_auto_refreshes_on_remote_drag`
- Wait strategy: `expect(column.locator('[data-highlight-id="..."]')).to_be_visible(timeout=10000)` — proven by spike

### Existing patterns followed

- `two_annotation_contexts` fixture for multi-client setup (same as `TestConcurrentDrag`)
- `create_highlight_with_tag` + `find_text_range` for highlight creation (same as all drag tests)
- `_switch_to_organise` / `_get_card_ids_in_column` / `_get_sortable_for_tag` helpers (same file)
- `data-testid` locators throughout (project convention)

## Implementation Phases

### Phase 1: Add broadcast drag test and refactor existing test

**Task 1:** Add `TestBroadcastDrag.test_organise_auto_refreshes_on_remote_drag` to `test_annotation_drag.py`. Create one highlight on page1, wait for broadcast to page2, both switch to Organise, page1 drags card between columns, assert page2 sees the move via `expect` (no tab switch).

**Task 2:** Refactor `TestConcurrentDrag.test_concurrent_drag_produces_consistent_result` — replace the two `while True` tab-switching polling loops with direct `expect` assertions on column card visibility. Remove the `import time` that was only used by the loops.

**Task 3:** Run the full E2E suite (serial) to verify no regressions. Run the new and refactored tests 5x to check for flakiness.

## Additional Considerations

### Spike evidence

A throwaway spike test confirmed the broadcast auto-refresh works (1/1 pass in 4.9s). The spike was placed in `tests/e2e/`, run via `grimoire e2e run --serial`, and deleted after confirming the result. The spike used `find_text_range(page1, "Alpha")` with a single highlight — the real test should use similar minimal setup.

### Risk: SortableJS drag simulation

Playwright's `drag_to()` synthesises drag events. The existing drag tests all use this successfully, so it's a proven pattern. The risk is low.

### Risk: Organise tab scroll restoration race

`refresh_organise_with_scroll` captures and restores scroll position via `requestAnimationFrame`. The test does not verify scroll preservation — that's a separate concern (mentioned in #304 but not in the acceptance criteria).

## Glossary

| Term | Definition |
|------|-----------|
| **Organise tab** | The second tab in the annotation workspace, showing highlights grouped into tag columns with drag-and-drop reordering |
| **Broadcast** | Server-side fan-out of CRDT updates from one client to all other clients viewing the same workspace |
| **Auto-refresh** | The organise tab re-rendering automatically when a broadcast is received, without requiring a tab switch or page reload |
| **Tag column** | A vertical container in the Organise tab holding all highlights assigned to a specific tag |
| **Slot stack** | NiceGUI's per-asyncio-task stack that determines which client's DOM receives new element creation |
