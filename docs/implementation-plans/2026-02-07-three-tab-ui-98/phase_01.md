# Three-Tab Annotation Interface — Phase 1: Tab Container Shell

**Goal:** Wrap the existing annotation view in a NiceGUI tab container without changing any functionality.

**Architecture:** Add `ui.tabs()` + `ui.tab_panels()` around the existing `_render_workspace_view` content in `annotation.py`. The header row (save status, user count, export) stays above the tab panels. Tabs 2 and 3 get placeholder labels. Deferred rendering is implemented via `on_change` handler — Tab 2 and Tab 3 content is only created on first visit.

**Tech Stack:** NiceGUI `ui.tabs`, `ui.tab_panels`, `ui.tab_panel`

**Scope:** 7 phases from original design (phase 1 of 7)

**Codebase verified:** 2026-02-07

---

## Acceptance Criteria Coverage

This phase implements and tests:

### three-tab-ui.AC1: Tab container wraps existing functionality
- **three-tab-ui.AC1.1 Success:** Annotation page renders three tab headers (Annotate, Organise, Respond) with Annotate selected by default
- **three-tab-ui.AC1.2 Success:** All existing annotation functionality (highlight create/edit/delete, multi-client sync, cursor/selection awareness) works identically within Tab 1
- **three-tab-ui.AC1.3 Success:** Tabs 2 and 3 lazy-render — no content created until first visit
- **three-tab-ui.AC1.4 Failure:** Switching tabs does not destroy Tab 1 state (highlights, scroll position preserved)

---

## Codebase Verification Findings

- ✓ `_render_workspace_view` at `annotation.py:2194` — renders header row + document/highlights
- ✓ `PageState` dataclass at `annotation.py:296-326` — holds per-client UI refs
- ✓ Flat two-column layout at `annotation.py:1192` inside `_render_document_with_highlights`
- ✓ Header row at `annotation.py:2214-2247` (save status, user count, export button)
- ✓ Route at `annotation.py:2264`
- ✓ NO existing tab UI in annotation.py
- ✗ Design assumed NiceGUI lazy-renders tab panels by default — ACTUALLY: `keep_alive=True` (default) creates all content upfront. Must implement deferred rendering via `on_change` handler.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add tab container to _render_workspace_view

**Verifies:** three-tab-ui.AC1.1

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py:2194-2262` (`_render_workspace_view`)

**Implementation:**

Restructure `_render_workspace_view` to:
1. Keep workspace lookup and error handling unchanged (lines 2196-2201)
2. Keep `PageState` creation and `_setup_client_sync` unchanged (lines 2203-2210)
3. Keep workspace ID label unchanged (line 2212)
4. Keep header row (save status, user count, export) above tabs — unchanged (lines 2214-2247)
5. Add `ui.tabs()` with three tabs: "Annotate", "Organise", "Respond"
6. Add `ui.tab_panels(tabs, value="Annotate")` with `on_change` handler for deferred rendering
7. Move the CRDT doc loading + document rendering + add content form inside `ui.tab_panel("Annotate")`
8. Tab 2 and Tab 3 panels get placeholder `ui.label()` that is replaced on first visit

The key structural change:
```
# BEFORE (flat):
header row
crdt_doc loading
_render_document_with_highlights() or _render_add_content_form()

# AFTER (tabbed):
header row
ui.tabs() → Annotate | Organise | Respond
ui.tab_panels(tabs)
  └ tab_panel("Annotate")
      └ crdt_doc loading
      └ _render_document_with_highlights() or _render_add_content_form()
  └ tab_panel("Organise")
      └ placeholder label
  └ tab_panel("Respond")
      └ placeholder label
```

Store tab-related references on `PageState` so other phases can access them:
- `tab_panels: ui.element | None` — the tab_panels container (for programmatic switching in Phase 6)

Add a new field to `PageState` (at `annotation.py:296`):
```python
tab_panels: Any | None = None  # Tab panels container for programmatic switching
```

**Testing:**
Tests must verify:
- three-tab-ui.AC1.1: Page renders three tab headers with "Annotate" selected by default

This is a UI structural change best verified via E2E test. Write a test that:
1. Navigates to annotation page with a workspace
2. Asserts three tab elements exist with text "Annotate", "Organise", "Respond"
3. Asserts "Annotate" tab is the active/selected tab

Test file: `tests/e2e/test_annotation_tabs.py`

Follow existing E2E patterns from `tests/e2e/test_annotation_basics.py` — use `authenticated_page` fixture, `setup_workspace_with_content` helper.

**Verification:**
Run: `uv run pytest tests/e2e/test_annotation_tabs.py -v -k test_tab_headers`
Expected: Test passes

**Commit:** `feat: wrap annotation view in three-tab container`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement deferred rendering for Tabs 2 and 3

**Verifies:** three-tab-ui.AC1.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py` (the `_render_workspace_view` function modified in Task 1)

**Implementation:**

NiceGUI's `keep_alive=True` (default) renders all tab content upfront. To defer Tab 2 and Tab 3 content creation until first visit, use an `on_change` handler pattern:

1. Create Tab 2 and Tab 3 panels with placeholder content (a `ui.label("Loading...")`)
2. Register an `on_change` callback on `tab_panels` that checks which tab was activated
3. On first visit to "Organise" or "Respond", clear the placeholder and populate with real content
4. Use a set to track which tabs have been initialised (avoid re-initialisation)

Store the initialised-tabs set on `PageState`:
```python
initialised_tabs: set[str] = field(default_factory=lambda: {"Annotate"})  # Annotate is always init
```

The `on_change` handler structure:
```python
async def _on_tab_change(e: ValueChangeEventArguments) -> None:
    tab_name = str(e.value)
    if tab_name in state.initialised_tabs:
        return
    state.initialised_tabs.add(tab_name)
    # Future phases will populate Tab 2 and Tab 3 content here
```

For now (Phase 1), the handler just marks the tab as initialised — the placeholder label stays. Future phases (3, 5) will add real content creation in this handler.

**Testing:**
Tests must verify:
- three-tab-ui.AC1.3: Tabs 2 and 3 don't render heavy content until first visit

Write an E2E test that:
1. Loads annotation page with content
2. Checks that Tab 2 panel contains placeholder text (not column layout)
3. Clicks the "Organise" tab
4. Verifies the tab panel becomes visible

Test file: `tests/e2e/test_annotation_tabs.py`

**Verification:**
Run: `uv run pytest tests/e2e/test_annotation_tabs.py -v -k test_deferred_rendering`
Expected: Test passes

**Commit:** `feat: add deferred tab rendering via on_change handler`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify Tab 1 state preservation on tab switch

**Verifies:** three-tab-ui.AC1.2, three-tab-ui.AC1.4

**Files:**
- Test: `tests/e2e/test_annotation_tabs.py`

**Implementation:**

No code changes — this task verifies that existing annotation functionality is unbroken by the tab wrapping. The `keep_alive=True` default means Tab 1 content persists in the DOM when switching tabs.

**Testing:**
Tests must verify:
- three-tab-ui.AC1.2: All existing annotation functionality works identically within Tab 1
- three-tab-ui.AC1.4: Switching tabs does not destroy Tab 1 state

Write E2E tests that:
1. Load annotation page, create a highlight in Tab 1
2. Switch to Tab 2 ("Organise"), then back to Tab 1 ("Annotate")
3. Assert the highlight still exists (annotation card visible, highlight CSS present)
4. Assert scroll position is preserved (or at least the page doesn't jump to top)

Also verify multi-client sync still works:
1. Open two browser contexts on the same workspace
2. Create a highlight in context 1
3. Assert it appears in context 2 (existing `two_annotation_contexts` fixture)

Test file: `tests/e2e/test_annotation_tabs.py`

Follow patterns from `tests/e2e/test_annotation_highlights.py` and `tests/e2e/test_annotation_collab.py`.

**Verification:**
Run: `uv run pytest tests/e2e/test_annotation_tabs.py -v`
Expected: All tests pass

**Commit:** `test: add tab state preservation and existing functionality E2E tests`

<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

---

## UAT Steps

1. [ ] Start the app: `uv run python -m promptgrimoire`
2. [ ] Navigate to: `/annotation`
3. [ ] Create a workspace and add content
4. [ ] Verify: Three tab headers visible (Annotate, Organise, Respond)
5. [ ] Verify: Annotate tab is selected by default, showing the existing two-column layout
6. [ ] Click "Organise" tab — verify placeholder content appears
7. [ ] Click "Respond" tab — verify placeholder content appears
8. [ ] Click "Annotate" tab — verify the document and any highlights are still there
9. [ ] Create a highlight in Tab 1, switch tabs, switch back — verify highlight persists
10. [ ] Open a second browser tab to the same workspace — verify multi-client sync works

## Evidence Required
- [ ] Screenshot showing three tab headers
- [ ] Test output showing green for `test_annotation_tabs.py`
