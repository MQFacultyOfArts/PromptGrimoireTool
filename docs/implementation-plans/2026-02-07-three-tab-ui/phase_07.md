# Three-Tab Annotation Interface — Phase 7: PDF Export Integration

**Goal:** Extend PDF export to include the response draft from Tab 3.

**Architecture:** The Milkdown editor's content must be available server-side for PDF export. Since pycrdt `XmlFragment` cannot be directly serialised to markdown on the Python side (it stores ProseMirror XML tree structure, not plain text), Phase 7 uses a JS-first extraction strategy: call `window._getMilkdownMarkdown()` via `ui.run_javascript()` when the exporting client has Tab 3 initialised, falling back to reading a CRDT `Text` field (`response_draft_markdown`) that is kept in sync from the browser. The `_handle_pdf_export` function in `annotation.py` replaces the hardcoded `general_notes=""` (line 1601) with the response draft content. The existing `export_annotation_pdf()` function and `_build_general_notes_section()` in `pdf_export.py` already handle non-empty `general_notes` content — no changes needed to the export pipeline itself.

**Tech Stack:** NiceGUI `ui.run_javascript`, pycrdt `Text`, existing `export_annotation_pdf()` pipeline

**Scope:** 7 phases from original design (phase 7 of 7)

**Codebase verified:** 2026-02-07

---

## Acceptance Criteria Coverage

This phase implements and tests:

### three-tab-ui.AC6: PDF export includes response draft
- **three-tab-ui.AC6.1 Success:** "Export PDF" includes response draft content below annotated document
- **three-tab-ui.AC6.2 Edge:** Empty response draft produces no extra section in the PDF
- **three-tab-ui.AC6.3 Success:** Export works regardless of whether the exporting user has visited Tab 3

---

## Codebase Verification Findings

- ✓ `_handle_pdf_export` at `annotation.py:1556-1614` — exports highlights, tag colours, calls `export_annotation_pdf()`
- ✓ Hardcoded `general_notes=""` at `annotation.py:1601` — this is the line to replace
- ✓ `export_annotation_pdf()` at `pdf_export.py:196-289` — accepts `general_notes: str = ""` parameter (line 200)
- ✓ `_build_general_notes_section()` at `pdf_export.py:154-170` — converts HTML general notes to LaTeX; returns empty string if no content (handles AC6.2 automatically)
- ✓ General notes section template at `pdf_export.py:44-46` — `\section*{General Notes}\n{content}`
- ✓ Integration test `test_export_with_general_notes` at `test_pdf_export.py:177-196` — proves the pipeline works with non-empty general_notes
- ✓ `window._getMilkdownMarkdown()` at `static/milkdown/src/index.js:91-94` — returns markdown string or empty string if editor not initialised
- ✓ Spike usage of markdown getter at `milkdown_spike.py:107-110` — `await ui.run_javascript("window._getMilkdownMarkdown()")`
- ✗ pycrdt `XmlFragment` has no `toJSON()` or `__str__()` for markdown extraction — binary CRDT type storing ProseMirror XML tree; cannot be serialised to markdown server-side
- ✗ No `response_draft_markdown` Text field exists yet — Phase 7 must add it to `AnnotationDocument` (or Phase 2 can be amended to include it)

**External dependency findings:**
- ✓ `window._getMilkdownMarkdown()` returns markdown via `crepe.getMarkdown()` — available when editor is running in browser
- ✗ y-prosemirror's `yDocToProsemirrorJSON()` is JavaScript-only — no Python equivalent for server-side XmlFragment → JSON → markdown conversion
- ✓ Dual-field pattern (XmlFragment + Text) is the recommended approach for server-side markdown access — keep a `Text` field in sync from the browser
- ✓ pycrdt `Text` supports `str()` conversion — `str(doc["field_name"])` returns the text content

---

<!-- START_SUBCOMPONENT_A (tasks 1-4) -->

<!-- START_TASK_1 -->
### Task 1: Verify response_draft_markdown field availability (from Phase 2)

**Verifies:** three-tab-ui.AC6.3 (partially — confirms the server-side data structure is available)

**Files:**
- None (no changes — the `response_draft_markdown` Text field, its property, and `get_response_draft_markdown()` helper were added to `AnnotationDocument` in Phase 2 Task 1 and tested in Phase 2 Task 3)

**Implementation:**

No changes needed. Phase 2 Task 1 added the `response_draft_markdown` Text field to `AnnotationDocument.__init__`, the `response_draft_markdown` property, and the `get_response_draft_markdown()` helper method. Phase 2 Task 3 tests verify it works (round-trip, empty default, coexistence). This task is a verification checkpoint before wiring the sync and export logic.

**Testing:**
Run existing tests to confirm field is available:

**Verification:**
Run: `uv run pytest tests/unit/test_annotation_doc.py -v -k response_draft_markdown`
Expected: All tests pass (from Phase 2)

**Commit:** No commit — verification only.

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Sync Milkdown markdown to CRDT Text field from browser

**Verifies:** three-tab-ui.AC6.3 (ensures markdown is available server-side)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation_respond.py` (add markdown sync callback)
- Modify: `src/promptgrimoire/static/milkdown/src/index.js` (add markdown sync export)

**Implementation:**

1. In the JS bundle (`index.js`), add a new export `window._syncMilkdownMarkdown` that:
   - Gets the current markdown via `crepe.getMarkdown()`
   - Sends it to a Python callback via the NiceGUI bridge
   - Called periodically or on content change (debounced) to keep the Text field in sync

2. In `annotation_respond.py`, after the Milkdown editor is created and the Yjs relay is set up:
   - Register a periodic sync callback (e.g., every 5 seconds or on blur/tab switch) that:
     - Calls `await ui.run_javascript("window._getMilkdownMarkdown()")` to get current markdown
     - Writes it to `crdt_doc.response_draft_markdown` via a transaction
   - Also trigger a sync when the user leaves Tab 3 (tab change event) to ensure the latest content is captured before export

3. Alternative simpler approach: Instead of periodic sync, sync the markdown in the `onYjsUpdate` callback — whenever the editor content changes, also update the Text field:
   - In the Python `onYjsUpdate` handler (which receives Yjs updates from the browser), after applying the update to the Doc, call `ui.run_javascript("window._getMilkdownMarkdown()")` and write the result to `crdt_doc.response_draft_markdown`
   - This ensures the markdown field is always up-to-date after any edit

4. Rebuild the JS bundle: `cd src/promptgrimoire/static/milkdown && npm run build`

**Key design decision:** The markdown Text field is a **best-effort mirror** — it may lag slightly behind the XmlFragment during rapid editing, but will be current enough for export. The JS-first approach (Task 3) provides the most accurate content when the editor is running.

**Testing:**
No separate tests — verified via E2E tests in Task 4.

**Verification:**
Run: `cd src/promptgrimoire/static/milkdown && npm run build`
Expected: Build succeeds

**Commit:** `feat: sync Milkdown markdown to CRDT Text field`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update _handle_pdf_export to include response draft

**Verifies:** three-tab-ui.AC6.1, three-tab-ui.AC6.2, three-tab-ui.AC6.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py` (`_handle_pdf_export` function)

**Implementation:**

Update `_handle_pdf_export` at `annotation.py:1556-1614` to read the response draft content instead of passing `general_notes=""`:

1. **Primary path (JS-side, most accurate):** If the current client has Tab 3 initialised (Milkdown editor running), get markdown via:
   ```python
   markdown = await ui.run_javascript("window._getMilkdownMarkdown()")
   ```
   This returns the most up-to-date content directly from the running editor.

2. **Fallback path (CRDT Text field):** If the current client has NOT visited Tab 3 (no Milkdown editor running, `_getMilkdownMarkdown()` would return empty string):
   ```python
   markdown = state.crdt_doc.get_response_draft_markdown()
   ```
   This reads the Text field that was synced by whichever client last edited Tab 3.

3. **Pass the content to export:**
   ```python
   pdf_path = await export_annotation_pdf(
       html_content=raw_content,
       highlights=highlights,
       tag_colours=tag_colours,
       general_notes=markdown,  # Was: general_notes=""
       ...
   )
   ```

4. **Empty draft handling (AC6.2):** If both paths return empty string, the existing `_build_general_notes_section()` in `pdf_export.py:154-170` returns empty string when `not general_notes or not general_notes.strip()` — no extra section appears in the PDF. No changes needed to the export pipeline.

5. **Detection of Tab 3 state:** Use a flag on `PageState` (e.g., `has_milkdown_editor: bool = False`) set to `True` when Tab 3 is first rendered. The export handler checks this flag to choose the primary vs fallback path.

**Key architectural note — markdown-to-HTML conversion required:** The `general_notes` parameter in `export_annotation_pdf()` expects HTML content. `_build_general_notes_section()` at `pdf_export.py:154-170` calls `_html_to_latex_notes()` at `pdf_export.py:95-131`, which is a simple regex-based HTML-to-LaTeX converter (replaces `<p>`, `<strong>`, `<em>`, `<ul>`, etc. with LaTeX equivalents). It does NOT use Pandoc and cannot process markdown.

Therefore, the response draft markdown from Milkdown **must be converted to HTML before passing to `export_annotation_pdf()`**. Use Python's `markdown` library (e.g., `import markdown; html = markdown.markdown(md_text)`) or a similar converter. Add `markdown` to project dependencies if not already present. The conversion step goes in `_handle_pdf_export` between getting the markdown content and calling `export_annotation_pdf()`.

**Testing:**
Tests in Task 4 verify AC6.1, AC6.2, AC6.3.

**Verification:**
Run: `uv run ruff check src/promptgrimoire/pages/annotation.py && uvx ty check`
Expected: No lint or type errors

**Commit:** `feat: include response draft in PDF export`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Tests for PDF export with response draft

**Verifies:** three-tab-ui.AC6.1, three-tab-ui.AC6.2, three-tab-ui.AC6.3

**Files:**
- Modify: `tests/unit/test_annotation_doc.py` (unit tests for Text field)
- Create or modify: `tests/e2e/test_annotation_tabs.py` (E2E tests for export)

**Implementation:**

No code changes — this task adds tests verifying PDF export includes response draft content.

**Testing:**
Tests must verify each AC listed above:
- three-tab-ui.AC6.1: Export PDF includes response draft content
- three-tab-ui.AC6.2: Empty draft produces no extra section
- three-tab-ui.AC6.3: Export works without visiting Tab 3

Note: Unit tests for `response_draft_markdown` field (round-trip, empty default, coexistence) were already written in Phase 2 Task 3. Phase 7 Task 4 only adds E2E tests for the PDF export integration.

Write E2E tests in `tests/e2e/test_annotation_tabs.py`:

- `test_pdf_export_includes_response_draft` — Navigate to annotation page, create content and highlights. Switch to Respond tab, type "This is my response draft" in the Milkdown editor. Click "Export PDF". Verify the exported PDF (or the intermediate .tex file) contains "This is my response draft" (AC6.1).

- `test_pdf_export_empty_draft_no_extra_section` — Navigate to annotation page, create content and highlights. Do NOT visit Respond tab. Click "Export PDF". Verify the exported PDF does not contain a "General Notes" section (AC6.2).

- `test_pdf_export_without_visiting_tab3` — Open two browser contexts. Context 1 visits Respond tab and types "Response content". Context 2 stays on Annotate tab. Context 2 clicks "Export PDF". Verify the PDF includes "Response content" (via the CRDT Text field fallback) (AC6.3).

Follow existing test patterns from `tests/integration/test_pdf_export.py` for PDF verification. For E2E tests, may need to check the intermediate .tex file rather than parsing the PDF binary.

**Verification:**
Run: `uv run pytest tests/unit/test_annotation_doc.py -v -k response_draft_markdown && uv run pytest tests/e2e/test_annotation_tabs.py -v -k test_pdf_export`
Expected: All tests pass

**Commit:** `test: add tests for PDF export with response draft`

<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_A -->

---

## UAT Steps

1. [ ] Verify Phase 2 unit tests still pass: `uv run pytest tests/unit/test_annotation_doc.py -v -k response_draft_markdown`
2. [ ] Run E2E tests: `uv run pytest tests/e2e/test_annotation_tabs.py -v -k test_pdf_export`
3. [ ] Rebuild JS bundle: `cd src/promptgrimoire/static/milkdown && npm run build`
4. [ ] Start the app: `uv run python -m promptgrimoire`
5. [ ] Navigate to `/annotation`, create a workspace, add content
6. [ ] Create some highlights
7. [ ] Switch to "Respond" tab, type some content in the Milkdown editor
8. [ ] Click "Export PDF" (from header)
9. [ ] Verify: PDF includes the response draft content below the annotated document
10. [ ] Create a new workspace, add content but do NOT visit Respond tab
11. [ ] Click "Export PDF" — verify: PDF has no "General Notes" section (empty draft)
12. [ ] Open a second browser tab to the same workspace
13. [ ] In browser tab 1, visit Respond tab and type "Draft content from browser 1"
14. [ ] In browser tab 2 (still on Annotate tab, never visited Respond), click "Export PDF"
15. [ ] Verify: PDF includes "Draft content from browser 1" (server-side Text field fallback)

## Evidence Required
- [ ] Test output showing green for response_draft_markdown unit tests
- [ ] Test output showing green for PDF export E2E tests
- [ ] Screenshot or PDF showing response draft content in exported PDF
- [ ] Confirmation that empty draft produces clean PDF without extra section
