## Phase 7: Multi-Document Tab Infrastructure (Design Phase 6)

### Acceptance Criteria Coverage

This phase implements and tests:

### multi-doc-tabs-186.AC1: Tab Bar Renders Document Tabs
- **multi-doc-tabs-186.AC1.1 Success:** Workspace with 3 documents shows "Source 1: Title | Source 2: Title | Source 3: Title | Organise | Respond" (partial — "+" tab added in Plan B Phase 8)
- **multi-doc-tabs-186.AC1.2 Success:** Single-document workspace shows "Source 1: Title | Organise | Respond" (partial — "+" tab added in Plan B Phase 8)
- **multi-doc-tabs-186.AC1.3 Success:** Tabs render in `order_index` sequence from DB
- **multi-doc-tabs-186.AC1.4 Success:** Quasar scroll arrows appear when tabs exceed container width
- **multi-doc-tabs-186.AC1.5 Edge:** Workspace with zero documents shows only "Organise | Respond" (partial — "+" tab added in Plan B Phase 8)
- **multi-doc-tabs-186.AC1.6 Edge:** Document with no title shows "Source N" (no trailing colon or empty string)

### multi-doc-tabs-186.AC2: Per-Document Content and Annotations
- **multi-doc-tabs-186.AC2.1 Success:** Each source tab renders its own document HTML content
- **multi-doc-tabs-186.AC2.2 Success:** Each source tab shows only that document's annotation cards (filtered by `document_id`)
- **multi-doc-tabs-186.AC2.3 Success:** Highlights created on Source 2 do not appear in Source 1's annotation cards
- **multi-doc-tabs-186.AC2.4 Success:** Tab content renders on first visit (deferred) and persists in DOM on subsequent visits (no re-render)
- **multi-doc-tabs-186.AC2.5 Edge:** Switching tabs rapidly does not cause duplicate content or orphaned elements

### multi-doc-tabs-186.AC10: Feature Flag Removal
- **multi-doc-tabs-186.AC10.1 Success:** Multi-document works without `enable_multi_document` config setting
- **multi-doc-tabs-186.AC10.2 Success:** Existing single-document workspaces continue to work unchanged

---

**Prerequisite:** `DocumentTabState` dataclass and `PageState.document_tabs` field already exist from Phase 6 Task 1.

<!-- START_TASK_1 -->
### Task 1: Remove enable_multi_document feature flag

**Verifies:** multi-doc-tabs-186.AC10.1, multi-doc-tabs-186.AC10.2

**Files:**
- Modify: `src/promptgrimoire/config.py:87` (remove flag from FeaturesConfig)
- Modify: `src/promptgrimoire/pages/annotation/workspace.py` (remove 3 usage points)

**Implementation:**
1. Remove `enable_multi_document: bool = False` from `FeaturesConfig` in config.py
2. Remove the 3 conditional checks in workspace.py:
   - Line 577: Remove the `if get_settings().features.enable_multi_document:` gate — content form always available
   - Line 773: Remove the visibility-hiding logic when flag is disabled
   - Content form becomes unconditionally rendered (the "Add Document" expansion panel is always visible)

**Testing:**
- AC10.1: App starts and runs without `enable_multi_document` in config
- AC10.2: Existing single-document workspace renders correctly without the flag

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass

Grep: `grep -r "enable_multi_document" src/`
Expected: Zero results

**Commit:** `feat: remove enable_multi_document feature flag — multi-doc is default`
<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-5) -->
<!-- START_TASK_2 -->
### Task 2: Dynamic tab creation from document list

**Verifies:** multi-doc-tabs-186.AC1.1, multi-doc-tabs-186.AC1.2, multi-doc-tabs-186.AC1.3, multi-doc-tabs-186.AC1.5, multi-doc-tabs-186.AC1.6

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tab_bar.py` (replace hardcoded 3-tab creation)
- Modify: `src/promptgrimoire/pages/annotation/workspace.py` (wire document list to tab creation)
- Test: `tests/integration/test_multi_doc_tabs.py` (integration, `@pytest.mark.nicegui_ui`)

**Implementation:**
Replace the hardcoded 3-tab creation with a dynamic loop:

1. Fetch documents: `documents = await list_documents(workspace_id)` (from `db/workspace_documents.py`)
2. Create source tabs in loop:
   ```python
   with ui.tabs().classes("w-full") as tabs:
       for i, doc in enumerate(documents):
           label = f"Source {i + 1}: {doc.title}" if doc.title else f"Source {i + 1}"
           tab = ui.tab(str(doc.id), label=label).props(f'data-testid="tab-source-{i + 1}"')
           # Store in DocumentTabState
       # Add shared tabs at end
       ui.tab("Organise").props('data-testid="tab-organise"')
       ui.tab("Respond").props('data-testid="tab-respond"')
   ```

3. Tab identifiers use `str(doc.id)` (UUID string) for stability. Display labels use "Source N: Title".

4. Handle edge cases:
   - Zero documents: only "Organise | Respond" tabs (Plan B adds "+" tab)
   - No title: "Source N" (no colon)
   - Default selected tab: first source tab (or Organise if no documents)

**Testing:**
- AC1.1 (partial): Workspace with 3 documents shows "Source 1: Title | Source 2: Title | Source 3: Title | Organise | Respond" — "+" tab deferred to Plan B
- AC1.2 (partial): Single-document workspace shows "Source 1: Title | Organise | Respond"
- AC1.3: Tabs ordered by `order_index`
- AC1.5 (partial): Zero documents shows "Organise | Respond" — "+" tab deferred to Plan B
- AC1.6: Untitled document shows "Source N" without colon

**Verification:**
Run: `uv run grimoire test run tests/integration/test_multi_doc_tabs.py`
Expected: All tab rendering tests pass

**Commit:** `feat: dynamic tab bar from document list`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Per-document tab panels with deferred rendering

**Verifies:** multi-doc-tabs-186.AC2.1, multi-doc-tabs-186.AC2.2, multi-doc-tabs-186.AC2.4

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/tab_bar.py` (per-document panels)
- Modify: `src/promptgrimoire/pages/annotation/tab_state.py` (populate DocumentTabState)
- Test: `tests/integration/test_multi_doc_tabs.py` (extend)

**Implementation:**
Create tab panels in a matching loop:

```python
with ui.tab_panels(tabs, value=default_tab, on_change=on_tab_change).classes("w-full") as panels:
    for doc_id, doc_tab_state in state.document_tabs.items():
        with ui.tab_panel(str(doc_id)) as panel:
            doc_tab_state.panel = panel
            # Deferred: content renders on first visit
            # Panel starts empty, populated by tab change handler

    with ui.tab_panel("Organise"):
        # Existing organise stub
    with ui.tab_panel("Respond"):
        # Existing respond stub
```

Update tab change handler to handle document tabs:
- When switching to a source tab (UUID identifier), check `document_tabs[doc_id].rendered`
- First visit: render document content + annotation cards, set `rendered = True`
- Subsequent visits: refresh cards (diff-based from Phase 5)

Extend deferred rendering pattern (existing Respond tab pattern) to all source tabs.

**Testing:**
- AC2.1: Each source tab shows its own document HTML
- AC2.2: Cards filtered by `document_id` per tab
- AC2.4: First visit triggers render, subsequent visits keep DOM (no re-render)

**Verification:**
Run: `uv run grimoire test all`
Expected: All tests pass

**Commit:** `feat: per-document tab panels with deferred rendering`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Migrate E2E epoch from single global to per-document map

**Verifies:** None (infrastructure — enables E2E testing of multi-document cards)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/cards.py` (epoch broadcast uses per-document key)
- Modify: `tests/e2e/card_helpers.py` (epoch polling uses per-document key)
- Modify: any E2E tests that poll `window.__annotationCardsEpoch`

**Implementation:**
The current single `window.__annotationCardsEpoch` becomes a per-document map: `window.__cardEpochs["{doc_id}"]`. Organise and Respond get separate epoch counters (`__organiseEpoch`, `__respondEpoch`).

1. In the diff-based card update (Phase 5's `_diff_annotation_cards`), change the JS broadcast:
   ```python
   # REPLACE: ui.run_javascript(f"window.__annotationCardsEpoch = {epoch}")
   # WITH:
   ui.run_javascript(f"window.__cardEpochs = window.__cardEpochs || {{}}; window.__cardEpochs['{doc_id}'] = {epoch}")
   ```

2. Update E2E helpers in `card_helpers.py` to accept a `doc_id` parameter:
   ```python
   # Wait for specific document's epoch to advance
   old_epoch = page.evaluate(f"() => (window.__cardEpochs || {{}})[\"{doc_id}\"] || 0")
   # ... action ...
   page.wait_for_function(f"(old) => ((window.__cardEpochs || {{}})['{doc_id}'] || 0) > old", arg=old_epoch)
   ```

3. For backward compatibility during migration, keep a single-document fallback:
   ```python
   # Also update legacy global for tests not yet migrated
   ui.run_javascript(f"window.__annotationCardsEpoch = {epoch}")
   ```

**Verification:**
Run: `uv run grimoire e2e cards`
Expected: All existing E2E card tests pass with epoch migration

**Commit:** `feat: migrate E2E epoch to per-document map`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Cross-document annotation isolation and rapid switching

**Verifies:** multi-doc-tabs-186.AC2.3, multi-doc-tabs-186.AC2.5, multi-doc-tabs-186.AC1.4

**Files:**
- Test: `tests/integration/test_multi_doc_tabs.py` (extend)
- Test: `tests/e2e/test_multi_doc_tabs.py` (e2e, new)

**Implementation:**
Write tests verifying multi-document isolation and tab switching:

1. **Annotation isolation (AC2.3):**
   - Create workspace with 2 documents
   - Add highlight to document 2
   - Verify Source 1 tab shows 0 annotation cards
   - Verify Source 2 tab shows 1 annotation card

2. **Rapid tab switching (AC2.5):**
   - Switch between tabs rapidly (5 switches in 1 second)
   - Verify no duplicate content, no orphaned elements
   - Verify final tab shows correct content

3. **Tab overflow (AC1.4):**
   - Create workspace with many documents (test with 8+ tabs)
   - Verify Quasar scroll arrows appear when tabs exceed container width
   - This may be purely visual — verify via E2E test with viewport width check

**Testing:**
Follow existing E2E patterns: `page.get_by_test_id()`, epoch synchronisation, testid locators.

**Verification:**
Run: `uv run grimoire test all`
Run: `uv run grimoire e2e run -k test_multi_doc`
Expected: All tests pass

Run: `uv run complexipy src/promptgrimoire/pages/annotation/tab_bar.py src/promptgrimoire/pages/annotation/tab_state.py src/promptgrimoire/pages/annotation/workspace.py`
Expected: All files within complexity limits

**Commit:** `test: verify cross-document annotation isolation and tab switching`
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_A -->
