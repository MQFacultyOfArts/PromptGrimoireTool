# PDF Export Character Alignment — Phase 3: Rename general_notes to response_draft

**Goal:** Remove the dead `general_notes` concept from the export pipeline. The only notes section is Tab 3's response draft.

**Architecture:** Rename `general_notes` parameter/templates/functions to `response_draft` throughout the export pipeline. Delete the redundant regex-based `_html_to_latex_notes` converter (Pandoc already handles HTML→LaTeX for the main pipeline). Keep the `general_notes` CRDT field for backward compatibility with existing serialised documents but remove unused helper methods.

**Tech Stack:** Python 3.14, NiceGUI, pytest

**Scope:** Phase 3 of 4 from original design

**Codebase verified:** 2026-02-08

---

## Acceptance Criteria Coverage

This phase implements and tests:

### pdf-export-char-alignment.AC2: Response draft section
- **pdf-export-char-alignment.AC2.1 Success:** When Tab 3 has content, PDF includes a "Response Draft" section after the annotated document
- **pdf-export-char-alignment.AC2.2 Edge:** When Tab 3 is empty (never visited or no content typed), PDF has no Response Draft section
- **pdf-export-char-alignment.AC2.3 Success:** Export works regardless of whether the exporting user has visited Tab 3 (falls back to CRDT Text field)

**Note on AC2.3:** This is structurally guaranteed by the existing CRDT fallback in `annotation.py:1700-1718`. When Tab 3 has not been visited, `_handle_pdf_export` falls back to `state.crdt_doc.get_response_draft_markdown()` at line 1717-1718. Task 2 in this phase preserves this fallback path when renaming `notes_latex` to `response_draft_latex` in the production caller. No new implementation is needed — the criterion is verified by the existing code path being preserved and by UAT.

### pdf-export-char-alignment.AC4: Dead code removal (partial)
- **pdf-export-char-alignment.AC4.1 Success:** No references to `_insert_markers_into_html`, `_plain_text_to_html`, `_escape_html_text_content`, or `general_notes` (as export parameter) remain in source code

---

<!-- START_TASK_1 -->
### Task 1: Rename templates and section builder in `pdf_export.py`

**Verifies:** pdf-export-char-alignment.AC2.1, AC2.2

**Files:**
- Modify: `src/promptgrimoire/export/pdf_export.py:32-49` (templates)
- Modify: `src/promptgrimoire/export/pdf_export.py:97-230` (`_html_to_latex_notes` and `_build_general_notes_section`)

**Implementation:**

1. **Rename `_GENERAL_NOTES_TEMPLATE`** (line 46-49) to `_RESPONSE_DRAFT_TEMPLATE`. Change the section title from `General Notes` to `Response Draft`:
   ```python
   # Response draft section template
   _RESPONSE_DRAFT_TEMPLATE = r"""
   \section*{{Response Draft}}
   {content}
   """
   ```

2. **Rename `{general_notes_section}` placeholder** in `_DOCUMENT_TEMPLATE` (line 40) to `{response_draft_section}`.

3. **Delete `_html_to_latex_notes`** (lines 97-153 entirely). This is a redundant regex-based HTML→LaTeX converter; the main pipeline uses Pandoc for HTML→LaTeX conversion.

4. **Rename and simplify `_build_general_notes_section`** (lines 198-230) to `_build_response_draft_section`. Remove the `general_notes` HTML parameter and the HTML conversion path. The function now only accepts pre-converted LaTeX:

   ```python
   def _build_response_draft_section(
       response_draft_latex: str = "",
   ) -> str:
       """Build the LaTeX response draft section.

       Args:
           response_draft_latex: Pre-converted LaTeX content from Pandoc
               markdown conversion (via markdown_to_latex_notes).

       Returns:
           LaTeX section string, empty if no content.
       """
       if not response_draft_latex or not response_draft_latex.strip():
           return ""

       return _RESPONSE_DRAFT_TEMPLATE.format(content=response_draft_latex)
   ```

**Verification:**

Run: `uv run ruff check src/promptgrimoire/export/pdf_export.py`
Expected: Clean

Run: `uvx ty check`
Expected: Clean (callers updated in Task 2)

**Commit:** `refactor: rename general_notes to response_draft in export templates`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update `export_annotation_pdf` signature and callers

**Verifies:** pdf-export-char-alignment.AC2.1, AC2.2, AC4.1

**Files:**
- Modify: `src/promptgrimoire/export/pdf_export.py:256-340` (`export_annotation_pdf`)
- Modify: `src/promptgrimoire/pages/annotation.py:1726-1734` (production caller)

**Implementation:**

1. **Update `export_annotation_pdf` signature** (lines 256-266):
   - Remove `general_notes: str = ""` parameter (line 260)
   - Rename `notes_latex: str = ""` to `response_draft_latex: str = ""` (line 261)

2. **Update the internal call** at line 331-333. Change:
   ```python
   notes_section = _build_general_notes_section(
       general_notes, latex_content=notes_latex
   )
   ```
   To:
   ```python
   notes_section = _build_response_draft_section(
       response_draft_latex=response_draft_latex,
   )
   ```

3. **Update the `_DOCUMENT_TEMPLATE.format` call** at line 336-340. Change `general_notes_section=notes_section` to `response_draft_section=notes_section`.

4. **Update the docstring** of `export_annotation_pdf` (lines 267-283) to remove the `general_notes` parameter documentation and rename `notes_latex` to `response_draft_latex`.

5. **Update the production caller** in `annotation.py` at lines 1726-1734. Change:
   ```python
   pdf_path = await export_annotation_pdf(
       html_content=raw_content,
       highlights=highlights,
       tag_colours=tag_colours,
       general_notes="",
       notes_latex=notes_latex,
       word_to_legal_para=None,
       filename=f"workspace_{workspace_id}",
   )
   ```
   To:
   ```python
   pdf_path = await export_annotation_pdf(
       html_content=html_content,
       highlights=highlights,
       tag_colours=tag_colours,
       response_draft_latex=notes_latex,
       word_to_legal_para=None,
       filename=f"workspace_{workspace_id}",
   )
   ```
   Note: `raw_content` was renamed to `html_content` in Phase 2 Task 1.

**Verification:**

Run: `uv run ruff check src/promptgrimoire/export/pdf_export.py src/promptgrimoire/pages/annotation.py`
Expected: Clean

Run: `uvx ty check`
Expected: Clean

**Commit:** `refactor: remove general_notes parameter from export_annotation_pdf`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Remove unused CRDT helper methods and update tests

**Verifies:** pdf-export-char-alignment.AC4.1 (partial)

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py:110-140` (remove `get_general_notes` and `set_general_notes`)
- Modify: `tests/unit/test_annotation_doc.py:8-67` (`TestGeneralNotes` class and all `get_general_notes`/`set_general_notes` references)

**Implementation:**

1. **Delete `get_general_notes`** (lines 110-116) and **`set_general_notes`** (lines 122-140) from `AnnotationDocument`. These methods are only called from tests (verified by grep), never from production code.

2. **Update `test_annotation_doc.py`** — Remove the entire `TestGeneralNotes` class (lines 8-67). These tests exercise `get_general_notes()` and `set_general_notes()` exclusively. The `general_notes` property is still tested implicitly by tests that exercise CRDT document sync (which remain in other test classes in the same file). Also update any other references to `set_general_notes`/`get_general_notes` later in the file (lines 218, 222, 278, 284, 310-314, 331, 341, 349) — replace with direct CRDT Text manipulation or remove the assertions.

   **Important:** Both the production code deletion and test updates must be in the same commit to avoid a broken test suite between commits.

**Keep:**
- The `general_notes` CRDT field declaration at line 64: `self.doc["general_notes"] = Text()`
- The `general_notes` property at lines 90-93

These must remain for backward compatibility — existing serialised CRDT documents contain this key, and removing it would break deserialisation. The property remains available for any future use.

**Verification:**

Run: `uv run ruff check src/promptgrimoire/crdt/annotation_doc.py`
Expected: Clean

Run: `uv run pytest tests/unit/test_annotation_doc.py -v`
Expected: All remaining tests pass

Run: `uv run test-debug`
Expected: No regressions

**Commit:** `refactor: remove unused get/set_general_notes methods and update tests`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update tests for renamed export pipeline

**Verifies:** pdf-export-char-alignment.AC2.1, AC2.2, AC4.1

**Files:**
- Modify: `tests/unit/export/test_markdown_to_latex.py:106-136` (rename test class, update assertions)
- Modify: `tests/integration/test_pdf_export.py:177-196` (update `test_export_with_general_notes`)
- Modify: `tests/conftest.py:323-369` (`pdf_exporter` fixture)

**Implementation:**

Note: `test_annotation_doc.py` updates are handled in Task 3 (same commit as the CRDT helper method deletion to avoid a broken test suite between commits).

1. **`test_markdown_to_latex.py`** — Rename `TestBuildGeneralNotesSectionWithLatex` (line 106) to `TestBuildResponseDraftSection`. Update all calls from `_build_general_notes_section(...)` to `_build_response_draft_section(...)`. Update import. Change assertion `"General Notes" in result` to `"Response Draft" in result` (lines 118, 125). Remove `test_html_fallback_still_works` (line 121-126) and `test_latex_content_takes_precedence` (line 128-135) — both test the removed HTML path.

2. **`test_pdf_export.py`** — Rename `test_export_with_general_notes` (line 177) to `test_export_with_response_draft`. Change it to pass `response_draft_latex` instead of `general_notes`:
   ```python
   async def test_export_with_response_draft(self, tmp_path: Path) -> None:
       """export_annotation_pdf should include response draft section."""
       html = "<p>Document text here.</p>"
       highlights: list[dict] = []
       tag_colours = {"jurisdiction": "#1f77b4"}
       response_draft_latex = r"These are \textbf{response draft} notes."

       pdf_path = await export_annotation_pdf(
           html_content=html,
           highlights=highlights,
           tag_colours=tag_colours,
           response_draft_latex=response_draft_latex,
           output_dir=tmp_path,
       )

       assert pdf_path.exists()
       tex_path = tmp_path / "annotated_document.tex"
       tex_content = tex_path.read_text()
       assert "Response Draft" in tex_content
   ```

3. **`conftest.py`** — Update `pdf_exporter` fixture (lines 323-369):
   - Rename parameter `general_notes` to `response_draft_latex` in the inner `_export` function signature (line 327)
   - Remove `acceptance_criteria` parameter and the HTML composition logic (lines 328, 344-351) — this used the HTML path which is now removed
   - Pass `response_draft_latex=response_draft_latex` to `export_annotation_pdf` (line 366) instead of `general_notes=notes_content`
   - Update docstring

**Testing:**

Tests must verify each AC listed above:

- pdf-export-char-alignment.AC2.1: Test that `export_annotation_pdf` with non-empty `response_draft_latex` produces a PDF with "Response Draft" section heading
- pdf-export-char-alignment.AC2.2: Test that `export_annotation_pdf` with empty `response_draft_latex` produces a PDF with no "Response Draft" section
- pdf-export-char-alignment.AC4.1: Verify no `general_notes` references remain in export code (grep check)

**Verification:**

Run: `uv run pytest tests/unit/export/test_markdown_to_latex.py -v`
Expected: All tests pass

Run: `uv run pytest tests/integration/test_pdf_export.py -v` (if Pandoc/LaTeX available)
Expected: All tests pass

Run: `uv run test-debug`
Expected: No regressions

**Commit:** `test: update tests for general_notes → response_draft rename`
<!-- END_TASK_4 -->

---

## UAT Steps

After all tasks in this phase are complete and tests pass:

### Automated verification (pdf-export-char-alignment.AC2.1, AC2.2, AC4.1)

1. `uv run test-debug` — all tests pass, no regressions
2. `uv run pytest tests/unit/export/test_markdown_to_latex.py -v` — renamed test class passes
3. `uv run pytest tests/unit/test_annotation_doc.py -v` — remaining CRDT tests pass after method removal

### Manual verification (pdf-export-char-alignment.AC2.1, AC2.2, AC2.3)

1. [ ] Start the app: `uv run python -m promptgrimoire`
2. [ ] Navigate to: `/annotation`
3. [ ] Paste a document, add highlights
4. [ ] Switch to Tab 3 (Respond), type some response content
5. [ ] Click Export PDF
6. [ ] Verify: PDF has a "Response Draft" section (not "General Notes") after the annotated document (AC2.1)

7. [ ] Create a new workspace, paste a document, add highlights, do NOT visit Tab 3
8. [ ] Click Export PDF
9. [ ] Verify: PDF has no "Response Draft" section (AC2.2, AC2.3 — export succeeds even without visiting Tab 3)

**Evidence Required:**
- [ ] Screenshot or PDF showing "Response Draft" heading when Tab 3 has content
- [ ] Screenshot or PDF showing no extra section when Tab 3 was never visited
- [ ] Test output showing all green for `test_annotation_doc.py` and `test_markdown_to_latex.py`
