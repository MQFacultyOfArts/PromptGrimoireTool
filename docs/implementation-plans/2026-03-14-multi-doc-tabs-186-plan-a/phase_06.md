## Phase 6: Extract Tab Management from workspace.py (Design Phase 5)

### Acceptance Criteria Coverage

This phase is a refactoring phase — no new ACs are implemented. It extracts tab management logic from workspace.py (866 lines) into `tab_bar.py` to reduce file size and prepare for multi-document tab creation in Phase 7. All existing tests serve as the regression safety net.

---

<!-- START_TASK_1 -->
### Task 1: Create DocumentTabState dataclass in tab_state.py

**Verifies:** None (infrastructure for Phase 7 multi-document support)

**Files:**
- Create: `src/promptgrimoire/pages/annotation/tab_state.py`
- Modify: `src/promptgrimoire/pages/annotation/__init__.py` (add `document_tabs` to PageState)

**Implementation:**
Create `tab_state.py` with the `DocumentTabState` dataclass per the design's Phase 5 specification:

```python
@dataclass
class DocumentTabState:
    """Per-document state for a source tab in the annotation workspace."""
    document_id: UUID
    tab: ui.tab
    panel: ui.tab_panel
    document_container: ui.column | None = None
    cards_container: ui.column | None = None
    annotation_cards: dict[str, ui.element] = field(default_factory=dict)
    rendered: bool = False
    cards_epoch: int = 0
```

Add to PageState in `__init__.py`:
```python
document_tabs: dict[UUID, DocumentTabState] = field(default_factory=dict)
```

Keep the old single-document fields (`state.annotation_cards`, `state.cards_epoch`) for backward compatibility — they will be migrated in Phase 7.

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass (additive change only)

**Commit:** `feat: add DocumentTabState dataclass for per-document tab state`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create tab_bar.py with extracted tab logic

**Verifies:** None (refactoring — all existing tests verify no regression)

**Files:**
- Create: `src/promptgrimoire/pages/annotation/tab_bar.py`
- Modify: `src/promptgrimoire/pages/annotation/workspace.py` (remove extracted code)

**Implementation:**
Extract the following functions from workspace.py to tab_bar.py:

**Tab creation and panel building:**
- `_build_tab_panels()` (lines 650-791) — builds all three panels with content
- Tab creation code (lines 840-843) — currently inline in `_render_workspace_view`, extract to a `build_tabs()` function

**Tab change handling:**
- `_make_tab_change_handler()` (lines 516-554) — returns async tab change closure
- `_handle_annotate_tab()` (lines 490-495)
- `_handle_organise_tab()` (lines 498-503)
- `_handle_respond_tab()` (lines 506-513)
- `_initialise_respond_tab()` (lines 326-362) — first-visit Respond tab setup
- `_sync_respond_on_leave()` (lines 474-487) — markdown sync on tab exit

**Organise drag setup:**
- `_setup_organise_drag()` (lines 260-299) — SortableJS handler wiring
- `_rebuild_organise_with_scroll()` (lines 239-257) — scroll-preserving rebuild
- `_parse_sort_end_args()` (lines 123-165) — drag-end event parsing
- `_apply_sort_reorder_or_move()` (lines 168-228) — CRDT reorder/move logic

**Import resolution:**
- tab_bar.py will need imports from: `__init__` (PageState), `highlights` (_push_highlights_to_client, _update_highlight_css), `organise` (render_organise_tab), `respond` (render_respond_tab), `cards` (_refresh_annotation_cards), `document` (relevant document rendering functions)
- Use `TYPE_CHECKING` guards where appropriate to avoid circular imports

**workspace.py** retains:
- `annotation_page()` route function
- `_render_workspace_view()` (reduced — delegates to tab_bar functions)
- Auth, workspace context loading
- Tag management callbacks
- Document rendering setup
- Copy protection JS injection

**Critical: Preserve deferred rendering gate.** The `initialised_tabs` set + first-visit check in `_handle_respond_tab` must work exactly as before. Do not change the lazy init pattern.

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass

Run: `wc -l src/promptgrimoire/pages/annotation/workspace.py src/promptgrimoire/pages/annotation/tab_bar.py`
Expected: workspace.py < 500 lines, tab_bar.py ~410 lines

**Commit:** `refactor: extract tab management from workspace.py to tab_bar.py`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify tab functionality end-to-end

**Verifies:** None (regression verification)

**Files:**
- Test: existing E2E and integration tests

**Implementation:**
Run all test suites to verify the extraction didn't break any tab-related functionality:

1. All characterisation tests from Phase 1 (card rendering across tabs)
2. Existing E2E card tests (`test_card_layout.py`, `test_edit_mode.py`)
3. Organise drag-and-drop tests (if any exist in E2E)
4. Respond tab tests (Milkdown editor, reference cards)

If any test file references workspace.py internals by name (unlikely given testid-based locators), update imports.

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass

Run: `uv run grimoire e2e cards`
Expected: All card E2E tests pass

Run: `uv run complexipy src/promptgrimoire/pages/annotation/workspace.py src/promptgrimoire/pages/annotation/tab_bar.py`
Expected: All functions within complexity limits

**Commit:** `test: verify tab extraction passes all existing tests`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update annotation-architecture.md

**Verifies:** None (documentation)

**Files:**
- Modify: `docs/annotation-architecture.md` (update module descriptions)

**Implementation:**
Update the annotation page architecture documentation to reflect the new module structure:

- Add `tab_bar.py` — tab creation, change handling, deferred rendering, organise drag setup
- Note that workspace.py is now top-level page assembly only
- Add `tab_state.py` — `DocumentTabState` dataclass for per-document state (created in Task 1)

**Verification:**
Run: `uv run grimoire docs build`
Expected: Documentation builds successfully

**Commit:** `docs: update annotation architecture for tab_bar.py extraction`
<!-- END_TASK_4 -->
