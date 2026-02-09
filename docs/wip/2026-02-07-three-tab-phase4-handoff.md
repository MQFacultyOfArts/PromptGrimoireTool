# Three-Tab UI — Phase 4 Handoff Notes

**Date:** 2026-02-07
**Branch:** `milkdown-crdt-spike`
**Base commit (pre-three-tab):** `37b1d92`

## Overall Plan Status

7-phase implementation plan: `docs/implementation-plans/2026-02-07-three-tab-ui/`

| Phase | Description | Status |
|-------|------------|--------|
| 1 | Tab container + deferred rendering | Done (commits `fc5fa0e`, `cbbc0ca`) |
| 2 | CRDT extensions (tag_order, response_draft, response_draft_markdown) | Done (commits `e877329`, `cd6f016`, `2cace72`) |
| 3 | Tab 2 tag columns + highlight cards | Done (commits `7829609`, `72f5b1c`, `b30a74a`, `92a4fce`, `10f899f`, `41ecf13`, `1c3e1ea`) |
| 4 | Drag-and-drop | **In progress — UX issues unresolved** |
| 5 | Milkdown editor in Tab 3 | Not started |
| 6 | Warp navigation + cross-tab reactivity | Not started |
| 7 | PDF export integration | Not started |

## Phase 4 State (Drag-and-Drop)

### What's committed

- `a0ab9dd` — drag-and-drop infrastructure module (`annotation_drag.py`)
- `956e113` — wired drag-drop to CRDT operations
- `4a455c4` — E2E tests for drag-and-drop
- `9045e7f` — typed DragState, documented reorder MVP trade-off
- `3c7e371` — rewrote to use canonical NiceGUI trello cards pattern
- `85d5926` — removed dragover/dragleave visual feedback (flickering)
- `40b09c8` — used `element.move()` instead of `panel.clear()` for visual updates

### What's uncommitted

Two changes in `annotation_organise.py` (see `git diff HEAD`):

1. **Drop zone spacer** at bottom of each tag column — a `div` with `flex-grow min-h-16` dashed border, intended to make the full column height a valid drop target (not just the card area).
2. **`items-stretch`** on the parent row + `self-stretch` on columns — intended to make all columns stretch to the same height.

### Known UX Issues (not resolved)

The drag-and-drop works mechanically (CRDT updates, tag reassignment) but the UX is poor:

1. **Floating/mispositioned cards** — the drop-zone spacer and stretch classes cause odd visual artefacts ("odd floating cards" per user).
2. **In-column reorder is not visually implemented** — any in-column drag moves to the bottom. There's no visual indication of where within the column you're dropping.
3. **Visual updates require refresh** — after a drag, the card doesn't always visually update in place. Sometimes you need to navigate away and back.
4. **Drop targets feel wrong** — dragging into empty column space (not onto a card) doesn't always register.
5. **No "go to Tab 1" button on cards** — cards in Organise tab lack a navigate/locate button (this is Phase 6, but was noticed during testing).

### Key Reference: NiceGUI PR #4656

The user pointed at https://github.com/zauberzeug/nicegui/pull/4656 as a potential better approach for drop handling. This was the last thing discussed before the conversation died (context window exhausted).

Also relevant:
- https://github.com/zauberzeug/nicegui/discussions/932 — community patterns for drag-and-drop
- https://github.com/zauberzeug/nicegui/tree/main/examples/trello_cards — canonical trello cards example

### Key Lesson: `panel.clear()` is wrong

From discussion #932: NiceGUI recommends **SortableJS** for drag-and-drop. The correct API for moving elements is `.move()` — never `panel.clear()` + rebuild. The `panel.clear()` destroys the element tree during its own event handler. Commit `40b09c8` addressed this but the visual issues persist.

## Decision Point for Next Session

Phase 4 drag-and-drop has been through multiple rewrites across three conversation sessions. The core question is:

**Option A: Accept MVP drag-and-drop as-is.** In-column reorder goes to bottom, cross-column reassign works. Discard the uncommitted drop-zone spacer changes (they cause floating card issues). Commit a "known limitations" note and move on to Phase 5.

**Option B: Fix the UX properly.** Read NiceGUI PR #4656, potentially adopt SortableJS or a different drag library. This could be another session of iteration.

**Option C: Defer Phase 4 entirely.** Mark drag-and-drop as deferred, move to Phases 5-7 which are independent (Milkdown editor, warp navigation, PDF export). Come back to drag-and-drop polish later.

The user's target is Session 1 2026 (Feb 23). Phases 5-7 are arguably higher value than polished drag UX.

## Files to Know About

- `src/promptgrimoire/pages/annotation_organise.py` — Tab 2 rendering (tag columns, cards)
- `src/promptgrimoire/pages/annotation_drag.py` — drag-and-drop infrastructure (DragState, make_draggable_card, make_drop_column)
- `src/promptgrimoire/pages/annotation.py` — main annotation page, tab container, broadcast
- `src/promptgrimoire/crdt/annotation_doc.py` — AnnotationDocument CRDT (tag_order, highlights)
- `tests/e2e/test_annotation_tabs.py` — E2E tests for tabs including drag
- `tests/unit/pages/test_annotation_organise.py` — unit tests for Organise tab

## How to Resume

1. Read this file
2. Read `docs/implementation-plans/2026-02-07-three-tab-ui/phase_04.md`
3. Decide on Option A/B/C above
4. If continuing: `git diff HEAD` shows the uncommitted drop-zone changes
5. Run `uv run test-debug` to check current test state
