# Three-Tab Annotation Interface — Phase 4: Drag-and-Drop

**Goal:** Implement drag-to-reorder within columns and drag-to-reassign between columns in Tab 2.

**Architecture:** Create a new `pages/annotation_drag.py` module providing `make_draggable_card()` and `make_drop_column()` factory functions that wrap NiceGUI elements with HTML5 drag event handlers (`dragstart`, `dragover.prevent`, `drop`). Per-client drag state is held in closure scope (no global state). Drop events write to the CRDT via `AnnotationDocument.set_tag_order()` (reorder) or `move_highlight_to_tag()` (cross-column). Broadcast on mutation propagates column re-renders to all connected clients. The `render_organise_tab()` function from Phase 3 is updated to use draggable cards and drop columns.

**Tech Stack:** NiceGUI `ui.card`, `ui.column`, `ui.row`; HTML5 Drag and Drop API via `.on()` event handlers; pycrdt Map/Array for persistence

**Scope:** 7 phases from original design (phase 4 of 7)

**Codebase verified:** 2026-02-07

---

## Acceptance Criteria Coverage

This phase implements and tests:

### three-tab-ui.AC2: Tab 2 organises highlights by tag
- **three-tab-ui.AC2.3 Success:** Dragging a card within a column reorders it; order persists in CRDT
- **three-tab-ui.AC2.4 Success:** Dragging a card to a different column changes its tag; change persists in CRDT and updates Tab 1's sidebar
- **three-tab-ui.AC2.5 Success:** Two users dragging simultaneously produces a consistent merged result (no lost moves)
- **three-tab-ui.AC2.6 Edge:** A highlight with no tag appears in an "Untagged" section or column

Note: The "Untagged" column is created in Phase 3 Task 2. Phase 4 ensures it functions as a valid drag source and drop target — dragging a card from "Untagged" to a tag column assigns the tag, and dragging from a tag column to "Untagged" removes the tag.

---

## Codebase Verification Findings

- ✓ No existing `pages/annotation_drag.py` — confirmed via glob search
- ✓ NiceGUI element `.on()` method supports HTML5 drag event names: `"dragstart"`, `"dragover.prevent"`, `"drop"`
- ✓ `_build_annotation_card` at `annotation.py:718-855` returns `ui.card` (line 855) — cards can be wrapped with drag attributes
- ✓ `update_highlight_tag()` method exists on `AnnotationDocument` — used by `move_highlight_to_tag()` from Phase 2
- ✓ Broadcast pattern at `annotation.py:1478-1553` — `broadcast_update()` calls `cstate.callback()` on all other clients; `refresh_annotations()` clears and rebuilds cards from CRDT
- ✓ `PageState` dataclass at `annotation.py:296-326` — holds per-client UI refs, suitable for drag state
- ✓ NiceGUI GitHub #4040 demonstrates full drag-and-drop card system using `.on("dragstart")` / `.on("dragover.prevent")` / `.on("drop")` pattern
- ✓ `render_organise_tab()` from Phase 3 (`pages/annotation_organise.py`) creates tag columns with highlight cards — target for drag enhancement
- ✗ Tab container does not exist yet — Phase 1 creates it; Phase 4 enhances Tab 2 content within that container

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Create drag-and-drop infrastructure module

**Verifies:** three-tab-ui.AC2.3 (partially — provides the drag mechanics)

**Files:**
- Create: `src/promptgrimoire/pages/annotation_drag.py`

**Implementation:**

Create a new module `pages/annotation_drag.py` with two factory functions:

1. `make_draggable_card(card: ui.card, highlight_id: str) -> ui.card` — Adds HTML5 drag attributes and events to an existing card:
   - Sets `draggable` attribute to `true` via `card._props["draggable"] = "true"` or equivalent NiceGUI API
   - Adds `card.on("dragstart", handler)` that stores `highlight_id` in a JavaScript `DataTransfer` object (via `js_handler` argument passing the ID back to Python)
   - Adds cursor styling for drag affordance (`cursor: grab`)
   - Returns the card (for chaining)

2. `make_drop_column(column: ui.column, tag_name: str, on_drop: Callable) -> ui.column` — Makes a column a valid drop target:
   - Adds `column.on("dragover.prevent", handler)` to allow drops (prevents default browser behaviour)
   - Adds `column.on("drop", handler)` that:
     - Reads the `highlight_id` from the drop event
     - Calls `on_drop(highlight_id, tag_name, drop_index)` callback
   - Adds visual feedback class on dragover (e.g., border highlight), removed on dragleave
   - Returns the column (for chaining)

3. A closure-based `create_drag_state()` factory that returns a dict-like object for tracking the currently dragged highlight ID per client. This avoids global state — each client's `_on_tab_change` handler creates its own drag state instance.

Key design decisions:
- **No subclassing** — factory functions wrap existing NiceGUI elements rather than creating subclasses, maintaining compatibility with existing Phase 3 rendering code
- **Per-client drag state via closure** — each client gets its own drag state instance, avoiding cross-client interference
- **Callback-based drop handling** — the `on_drop` callback decouples the drag module from CRDT details; the caller wires it to CRDT operations

**Testing:**
Write unit tests in `tests/unit/pages/test_annotation_drag.py`:
- `test_create_drag_state_returns_independent_instances` — call `create_drag_state()` twice, verify they don't share state (set value in one, check the other is unaffected)
- `test_create_drag_state_tracks_dragged_id` — set a highlight ID on the drag state, verify it can be retrieved
- `test_create_drag_state_clears_on_drop` — set a highlight ID, clear it, verify it returns None

The factory functions `make_draggable_card()` and `make_drop_column()` require NiceGUI runtime context and are verified via E2E tests in Task 3.

**Verification:**
Run: `uv run pytest tests/unit/pages/test_annotation_drag.py -v && uv run ruff check src/promptgrimoire/pages/annotation_drag.py && uvx ty check`
Expected: All tests pass, no lint or type errors

**Commit:** `feat: add drag-and-drop infrastructure for Tab 2 highlight cards`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Wire drag-drop to CRDT and integrate with Tab 2

**Verifies:** three-tab-ui.AC2.3, three-tab-ui.AC2.4

**Files:**
- Modify: `src/promptgrimoire/pages/annotation_organise.py` (`render_organise_tab` from Phase 3)
- Modify: `src/promptgrimoire/pages/annotation.py` (broadcast handler to refresh Tab 2 on CRDT mutation)

**Implementation:**

Update `render_organise_tab()` in `annotation_organise.py` to:

1. Import and use `make_draggable_card()` and `make_drop_column()` from `annotation_drag.py`
2. Create a drag state instance via `create_drag_state()` per client
3. For each tag column, call `make_drop_column(column, tag_name, on_drop_handler)` where `on_drop_handler`:
   - **Same-column drop (reorder):** Calls `crdt_doc.set_tag_order(tag, new_order)` with the highlight moved to the new position within the same tag's array
   - **Cross-column drop (reassign):** Calls `crdt_doc.move_highlight_to_tag(highlight_id, from_tag, to_tag, position)` which updates both the highlight's tag field and the tag_order arrays
   - After CRDT mutation, calls `broadcast_update()` to propagate changes to all clients
4. For each highlight card, call `make_draggable_card(card, highlight_id)` to enable dragging
5. After broadcast, re-render the Organise tab columns for the current client (clear and rebuild from CRDT state)

In `annotation.py`, update the broadcast callback so that when Tab 2 is active for a client, it refreshes the Organise tab columns:
1. In the broadcast callback (registered per-client), check if the client's current tab is "Organise"
2. If so, re-render the tag columns from current CRDT state (call a `refresh_organise_tab()` helper)
3. This ensures changes from drag-drop by one client propagate to other clients viewing Tab 2

**Tab 1 sidebar update (AC2.4):** When a highlight's tag changes via cross-column drag, the existing broadcast mechanism already triggers `refresh_annotations()` for clients on Tab 1, which rebuilds sidebar cards from CRDT. The tag dropdown on each card reads from the highlight's `tag` field in the CRDT, so no additional work is needed for Tab 1 reactivity — the existing broadcast pattern handles it.

**Testing:**
Tests in Task 3 verify AC2.3 and AC2.4.

**Verification:**
Run: `uv run ruff check src/promptgrimoire/pages/annotation_organise.py src/promptgrimoire/pages/annotation_drag.py && uvx ty check`
Expected: No lint or type errors

**Commit:** `feat: wire drag-drop events to CRDT operations in Tab 2`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: E2E tests for drag-and-drop operations

**Verifies:** three-tab-ui.AC2.3, three-tab-ui.AC2.4, three-tab-ui.AC2.5

**Files:**
- Create or modify: `tests/e2e/test_annotation_tabs.py` (add drag-drop tests)

**Implementation:**

No code changes — this task adds E2E tests verifying the drag-and-drop behaviour.

**Testing:**
Tests must verify each AC listed above:
- three-tab-ui.AC2.3: Dragging a card within a column reorders it and order persists in CRDT
- three-tab-ui.AC2.4: Dragging a card to a different column changes its tag and updates Tab 1's sidebar
- three-tab-ui.AC2.5: Two users dragging simultaneously produces a consistent merged result

Write E2E tests in `tests/e2e/test_annotation_tabs.py`:

- `test_drag_reorder_within_column` — Create two highlights with the same tag, switch to Organise tab, use Playwright's `drag_to()` to move the second card above the first within the same column, verify the new order persists (switch tabs and back, verify order maintained)

- `test_drag_between_columns_changes_tag` — Create a highlight with tag A, switch to Organise tab, drag the card from tag A's column to tag B's column, verify:
  - Card now appears in tag B's column (not tag A's)
  - Switch back to Annotate tab, verify the highlight's tag dropdown shows tag B

- `test_drag_between_columns_updates_tab1_sidebar` — Create a highlight with tag A, open a second browser context on the same workspace (use `two_annotation_contexts` fixture pattern), have context 1 on Tab 2 drag a card to a new tag, verify context 2 (on Tab 1) sees the tag change reflected in the sidebar card

- `test_concurrent_drag_produces_consistent_result` — Open two browser contexts on the same workspace, both on Tab 2. Context 1 drags highlight X from column A to column B. Context 2 drags highlight Y from column B to column C (simultaneously or near-simultaneously). Verify both operations complete and both contexts show the same final state (X in B, Y in C).

Follow existing E2E patterns from `tests/e2e/test_annotation_basics.py` — use `authenticated_page` fixture, `setup_workspace_with_content` helper. For drag operations, use Playwright's `locator.drag_to(target_locator)`.

**Verification:**
Run: `uv run pytest tests/e2e/test_annotation_tabs.py -v -k test_drag`
Expected: All tests pass

**Commit:** `test: add E2E tests for drag-and-drop reorder and reassign`

<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

---

## UAT Steps

1. [ ] Run E2E tests: `uv run pytest tests/e2e/test_annotation_tabs.py -v -k test_drag`
2. [ ] Start the app: `uv run python -m promptgrimoire`
3. [ ] Navigate to `/annotation`, create a workspace, add content
4. [ ] Create several highlights with different tags (at least 2 per tag for reorder testing)
5. [ ] Click "Organise" tab
6. [ ] Drag a card within a column — verify it reorders (card stays in new position)
7. [ ] Switch to Annotate tab and back to Organise — verify reorder persisted
8. [ ] Drag a card from one tag column to a different tag column — verify it moves
9. [ ] Switch to Annotate tab — verify the moved highlight shows the new tag in its sidebar card
10. [ ] Open a second browser tab to the same workspace, navigate to Organise tab
11. [ ] Drag a card in browser tab 1 — verify the change appears in browser tab 2
12. [ ] Simultaneously drag cards in both browser tabs — verify both changes persist and both tabs show consistent state

## Evidence Required
- [ ] Test output showing green for drag-drop E2E tests
- [ ] Screenshot showing Tab 2 with drag cursor on a highlight card
- [ ] Screenshot showing a card after being dragged to a different column
