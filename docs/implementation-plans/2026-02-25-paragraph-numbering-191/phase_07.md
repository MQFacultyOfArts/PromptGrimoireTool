# Paragraph Numbering Implementation Plan — Phase 7: Toggle UI

**Goal:** Users can view and change the auto-number setting after document creation, see source numbering detection in the upload dialog, and edit para_ref on annotation cards.

**Architecture:** A `ui.switch` in the workspace header controls `auto_number_paragraphs`. Toggle rebuilds the paragraph map, re-renders margin numbers, and does NOT modify existing highlight `para_ref` values. Upload dialog gets a pre-set switch showing auto-detect results. Annotation cards get click-to-edit on para_ref via a new CRDT update method.

**Tech Stack:** NiceGUI (`ui.switch`, `ui.dialog`), pycrdt CRDT

**Scope:** Phase 7 of 7 from original design

**Codebase verified:** 2026-02-27

---

## Acceptance Criteria Coverage

This phase implements and tests:

### paragraph-numbering-191.AC3: Auto-detection on paste-in (remaining)
- **paragraph-numbering-191.AC3.3 Success:** Upload dialog shows detected state with override checkbox

### paragraph-numbering-191.AC5: Annotation cards display para_ref (remaining)
- **paragraph-numbering-191.AC5.3 Success:** User can edit `para_ref` on an existing annotation card

### paragraph-numbering-191.AC7: Toggle is changeable post-creation
- **paragraph-numbering-191.AC7.1 Success:** Toggle visible in workspace header area
- **paragraph-numbering-191.AC7.2 Success:** Toggling rebuilds `paragraph_map` and updates margin numbers
- **paragraph-numbering-191.AC7.3 Success:** Toggling does NOT modify existing `para_ref` values on highlights

---

## Reference Files

The executor MUST read these before implementing:
- `src/promptgrimoire/pages/annotation/header.py` — workspace header controls (~line 79), existing chip/switch patterns
- `src/promptgrimoire/pages/annotation/sharing.py` — `ui.switch()` toggle pattern (~line 57)
- `src/promptgrimoire/pages/dialogs.py` — content type dialog (~line 10)
- `src/promptgrimoire/crdt/annotation_doc.py` — `update_highlight_tag()` (~line 287) as template for `update_highlight_para_ref()`
- `src/promptgrimoire/pages/annotation/cards.py` — para_ref display (~line 353)
- `src/promptgrimoire/pages/annotation/document.py` — rendering flow (~line 176)
- `src/promptgrimoire/input_pipeline/paragraph_map.py` — `build_paragraph_map()`, `inject_paragraph_attributes()`
- `src/promptgrimoire/db/workspace_documents.py` — document update path
- `CLAUDE.md` — testing conventions

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add `update_highlight_para_ref()` to CRDT

**Verifies:** paragraph-numbering-191.AC5.3

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py` (~line 287, after `update_highlight_tag()`)

**Implementation:**

Add a new method following the `update_highlight_tag()` pattern:

```python
def update_highlight_para_ref(
    self,
    highlight_id: str,
    new_para_ref: str,
    origin_client_id: str | None = None,
) -> bool:
    """Update a highlight's para_ref field."""
```

Logic (same as `update_highlight_tag` but updating `"para_ref"` instead of `"tag"`):
1. Set origin context variable
2. Check if `highlight_id` exists in `self.highlights`
3. Copy highlight data, update `"para_ref"` field
4. Write back to CRDT map
5. Return success/failure

**Verification:**
```bash
uvx ty check
```

**Commit:** `feat: add update_highlight_para_ref() to CRDT annotation document`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Unit test for CRDT para_ref update

**Verifies:** paragraph-numbering-191.AC5.3

**Files:**
- Modify: `tests/unit/test_annotation_doc.py` (add alongside existing para_ref test)

**Testing:**

Add test `test_update_highlight_para_ref`:
- Create highlight with `para_ref="[3]"`
- Call `update_highlight_para_ref(highlight_id, "[3a]")`
- Verify `get_highlight()` returns `para_ref="[3a]"`
- Verify other fields unchanged
- Test update on non-existent highlight returns `False`

Follow the existing test patterns in the file.

**Verification:**
```bash
uv run pytest tests/unit/test_annotation_doc.py -v -k "para_ref"
```

**Commit:** `test: add CRDT para_ref update test`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Add paragraph toggle to workspace header

**Verifies:** paragraph-numbering-191.AC7.1, AC7.2, AC7.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/header.py` (~line 170-193, between copy protection and sharing)
- Modify: `src/promptgrimoire/db/workspace_documents.py` (add `update_document_paragraph_settings()` function)

**Implementation:**

1. **Add DB update function** to `workspace_documents.py`:

   ```python
   async def update_document_paragraph_settings(
       document_id: UUID,
       auto_number_paragraphs: bool,
       paragraph_map: dict[str, int],
   ) -> None:
   ```

   Updates both columns on the `WorkspaceDocument` record.

2. **Add toggle to header** in `header.py`:

   Add a `ui.switch` after the copy protection chip, before sharing controls. Follow the sharing toggle pattern:

   ```python
   ui.switch(
       "Auto-number ¶",
       value=doc.auto_number_paragraphs,
       on_change=lambda e: _handle_paragraph_toggle(e.value),
   ).props('data-testid="paragraph-toggle"')
   ```

3. **Toggle handler** `_handle_paragraph_toggle(new_value: bool)`:
   - Call `build_paragraph_map(doc.content, auto_number=new_value)` to rebuild map
   - Call `update_document_paragraph_settings(doc.id, new_value, new_map)`
   - Update `state.paragraph_map` cache
   - Re-render document HTML with `inject_paragraph_attributes()` using new map
   - Show toast notification
   - **Do NOT touch existing highlight `para_ref` values** (AC7.3)

**Re-render mechanism:** The executor must use `@ui.refreshable` on the document render function (or the portion that outputs `ui.html`). The toggle handler calls `.refresh()` on that refreshable after updating `state.paragraph_map`. This follows NiceGUI's standard pattern for re-rendering a section of the page without a full page reload. The executor should:
1. Check if `_render_document_with_highlights()` is already decorated with `@ui.refreshable` — if so, call `.refresh()`
2. If not, wrap the `ui.html()` portion in a `@ui.refreshable` helper and store a reference in `PageState` for the toggle handler to call

**Verification:**
```bash
uvx ty check
```

**Commit:** `feat: add paragraph numbering toggle to workspace header`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add numbering switch to upload/paste dialog

**Verifies:** paragraph-numbering-191.AC3.3

**Files:**
- Modify: `src/promptgrimoire/pages/dialogs.py` (~line 10-71, `show_content_type_dialog()`)
- Modify: `src/promptgrimoire/pages/annotation/content_form.py` (~lines 565-591, paste handler; ~lines 618-639, upload handler)

**Implementation:**

1. **Extend `show_content_type_dialog()`** signature:

   ```python
   async def show_content_type_dialog(
       detected_type: ContentType,
       preview: str = "",
       source_numbering_detected: bool = False,
   ) -> tuple[ContentType, bool] | None:
   ```

   Returns a tuple of `(content_type, auto_number_paragraphs)` or `None` if cancelled.

2. **Add switch to dialog UI** after the type selector:

   ```python
   auto_number = ui.switch(
       "Auto-number paragraphs",
       value=not source_numbering_detected,
   ).props('data-testid="auto-number-switch"')

   if source_numbering_detected:
       ui.label("Source paragraph numbers detected").classes("text-xs text-amber-600")
   ```

3. **Update dialog submit** to return the tuple:
   ```python
   ui.button("Confirm", on_click=lambda: dialog.submit((selected_type, auto_number.value)))
   ```

4. **Update ALL callers** of `show_content_type_dialog()` — the return type changes from `ContentType | None` to `tuple[ContentType, bool] | None`, which is a breaking change. There are 3 call sites:
   - `content_form.py` paste handler (~line 571): pass `source_numbering_detected=detect_source_numbering(processed_html)`, destructure result tuple
   - `content_form.py` upload handler (~line 618): pass detection result, destructure result tuple, use `auto_number_paragraphs` from dialog
   - `dialogs.py` (~line 25, if there's a direct call): update to handle new return type

   For direct paste (no dialog shown): use auto-detect result directly (existing Phase 3 behavior, no change needed)

**Verification:**
```bash
uvx ty check
```

**Commit:** `feat: add paragraph numbering switch to upload dialog with auto-detection hint`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Add click-to-edit para_ref on annotation cards

**Verifies:** paragraph-numbering-191.AC5.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/cards.py` (~line 353-356, para_ref display)

**Implementation:**

Replace the static `ui.label(para_ref)` with a click-to-edit pattern:

1. Default state: `ui.label(para_ref)` styled as before (monospace, small, muted)
2. On click: replace with `ui.input(value=para_ref)` inline
3. On blur or Enter: save via `state.crdt_doc.update_highlight_para_ref(highlight_id, new_value)`, persist CRDT, swap back to label

Use NiceGUI's event handling. The exact implementation depends on how the card builds — the executor should check whether `@ui.refreshable` or direct DOM manipulation is more appropriate.

Add `data-testid="para-ref-label"` to the label and `data-testid="para-ref-input"` to the input.

**Verification:**
```bash
uvx ty check
```

**Commit:** `feat: add click-to-edit para_ref on annotation cards`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Integration and E2E verification

**Verifies:** paragraph-numbering-191.AC7.1, AC7.2, AC7.3, AC3.3, AC5.3

**Files:**
- Modify: `tests/integration/test_paragraph_numbering.py` (add toggle tests)

**Testing:**

**`TestToggleParagraphNumbering`:**
- AC7.2: Create document with auto-number, toggle to source-number, verify `paragraph_map` changes in DB
- AC7.3: Create document with highlights that have `para_ref` values, toggle numbering mode, verify highlights' `para_ref` values are UNCHANGED

**`TestUploadDialogAutoDetect`:**
- AC3.3: Functional test that `show_content_type_dialog()` returns the auto-number boolean alongside the content type (test the function's return value contract)

Note: AC7.1 (toggle visible in workspace header) is a visual/layout concern that cannot be verified by integration tests alone — it requires UAT or E2E verification (see UAT steps below). Full E2E tests for the toggle UI are best added if time permits but are lower priority than the integration tests that verify data integrity (AC7.3 is critical).

**Verification:**
```bash
uv run pytest tests/integration/test_paragraph_numbering.py -v
```
Expected: All tests pass (Phase 1 + Phase 3 + Phase 5 + Phase 7 tests).

**Commit:** `test: add integration tests for paragraph toggle and upload dialog`
<!-- END_TASK_6 -->

---

## UAT Steps

1. [ ] Run all integration tests: `uv run pytest tests/integration/test_paragraph_numbering.py -v` — all pass (Phase 1 + Phase 3 + Phase 5 + Phase 7)
2. [ ] Run CRDT unit tests: `uv run pytest tests/unit/test_annotation_doc.py -v -k "para_ref"` — all pass
3. [ ] Type check clean: `uvx ty check`
4. [ ] Start the app: `uv run python -m promptgrimoire`
5. [ ] Open a workspace — verify the "Auto-number ¶" toggle is visible in the header area (AC7.1)
6. [ ] Toggle from auto-number to source-number — verify margin numbers change (AC7.2)
7. [ ] Create a highlight with a `para_ref`, toggle numbering mode — verify the highlight's `para_ref` is unchanged on the card (AC7.3)
8. [ ] Upload a file — verify the content type dialog shows the auto-number switch, pre-set based on source numbering detection (AC3.3)
9. [ ] On an annotation card with a para_ref, click the para_ref label — verify it becomes editable, save a new value, verify it persists (AC5.3)

## Evidence Required
- [ ] Integration test output all green (Phase 1 + 3 + 5 + 7)
- [ ] CRDT unit test output for para_ref tests green
- [ ] Screenshot showing toggle in workspace header
- [ ] Screenshot showing upload dialog with auto-number switch
