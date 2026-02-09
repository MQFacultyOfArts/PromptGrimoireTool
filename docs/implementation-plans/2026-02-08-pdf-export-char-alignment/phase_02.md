# PDF Export Character Alignment — Phase 2: Wire New Function into Export Pipeline

**Goal:** Replace the broken export data path. PDF export produces correct output using `insert_markers_into_dom`.

**Architecture:** Three changes: (1) `_handle_pdf_export` reads `doc.content` instead of deleted `doc.raw_content`, (2) `convert_html_with_annotations` calls `insert_markers_into_dom` instead of `_insert_markers_into_html` and drops the `escape_text` parameter, (3) `export_annotation_pdf` adds a `ValueError` guard for empty content with highlights and removes the plain-text detection/path.

**Tech Stack:** Python 3.14, NiceGUI, selectolax, Pandoc, pytest

**Scope:** Phase 2 of 4 from original design

**Codebase verified:** 2026-02-08

---

## Acceptance Criteria Coverage

This phase implements and tests:

### pdf-export-char-alignment.AC1: PDF includes source document with annotations
- **pdf-export-char-alignment.AC1.1 Success:** Export from Tab 1 (Annotate) produces PDF with source document body, highlights, and annotation comments in margins
- **pdf-export-char-alignment.AC1.2 Success:** Export from Tab 3 (Respond) produces the same source document body with highlights and comments
- **pdf-export-char-alignment.AC1.5 Failure:** Export with no document content shows user-facing error notification, not a blank PDF
- **pdf-export-char-alignment.AC1.6 Failure:** `export_annotation_pdf` raises `ValueError` when highlights provided with empty content

### pdf-export-char-alignment.AC5: Fixture regression (partial)
- **pdf-export-char-alignment.AC5.1 Success:** All HTML conversation fixtures (`tests/fixtures/*.html`, `*.html.gz`) pass through `insert_markers_into_dom` without error when given highlights at valid char positions from `extract_text_from_html`
- **pdf-export-char-alignment.AC5.2 Success:** Exported PDFs from fixture content undergo visual inspection (screenshots or PDF review) to confirm annotations appear at correct positions — not just "no crash" but "looks right"
- **pdf-export-char-alignment.AC5.3 Success:** i18n fixtures (Chinese Wikipedia, Japanese, Korean, Spanish) produce PDFs with correctly positioned CJK/diacritical highlights

**Note:** AC5.2 and AC5.3 are UAT-only criteria requiring visual PDF inspection. They cannot be verified by automated tests. Verification is via the UAT steps below after Task 4 completes.

---

<!-- START_TASK_1 -->
### Task 1: Fix `_handle_pdf_export` to use `doc.content`

**Verifies:** pdf-export-char-alignment.AC1.1, AC1.2

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py:1681-1696` (the `raw_content` block)

**Implementation:**

Replace the broken `doc.raw_content` reference at `annotation.py:1681-1688` with `doc.content`. The current code:

```python
# Get document's original raw_content (preserves newlines)
# NOTE: raw_content removed in Phase 1, will be fixed in Phase 6 with
# proper plain-text extraction
doc = await get_document(state.document_id)
raw_content = cast(
    "str",
    doc.raw_content if doc and hasattr(doc, "raw_content") else "",
)
```

Replace with:

```python
doc = await get_document(state.document_id)
if doc is None or not doc.content:
    notification.dismiss()
    ui.notify(
        "No document content to export. Please paste or upload content first.",
        type="warning",
    )
    return
html_content = doc.content
```

Then update the `export_annotation_pdf` call at line 1727 to use `html_content` instead of `raw_content`.

Also remove the DEBUG logging block at lines 1690-1696 (it logs `raw_content` diagnostics that are no longer relevant).

**Verification:**

Run: `uv run ruff check src/promptgrimoire/pages/annotation.py`
Expected: Clean

Run: `uvx ty check`
Expected: Clean

**Commit:** `fix: use doc.content instead of deleted doc.raw_content for PDF export`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Wire `insert_markers_into_dom` into `convert_html_with_annotations`

**Verifies:** pdf-export-char-alignment.AC1.1, AC1.2

**Files:**
- Modify: `src/promptgrimoire/export/latex.py:1252-1317` (`convert_html_with_annotations`)

**Implementation:**

Replace the call to `_insert_markers_into_html` at line 1300 with `insert_markers_into_dom`. The new function handles HTML normalization internally (it parses the DOM), so the `escape_text` parameter and the conditional `strip_scripts_and_styles` / `_escape_html_text_content` blocks are no longer needed.

Changes to `convert_html_with_annotations`:

1. **Remove `escape_text` parameter** from the function signature (line 1258)
2. **Remove conditional HTML normalization** block (lines 1289-1294). `strip_scripts_and_styles` and `fix_midword_font_splits` should be called unconditionally since `doc.content` is always HTML. However, `insert_markers_into_dom` works on clean HTML, so keep `strip_scripts_and_styles` as a pre-processing step BEFORE calling `insert_markers_into_dom`.
3. **Replace `_insert_markers_into_html` call** (line 1300) with:
   ```python
   from promptgrimoire.input_pipeline import insert_markers_into_dom
   marked_html, marker_highlights = insert_markers_into_dom(html, highlights)
   ```
4. **Remove `_escape_html_text_content` call** (lines 1306-1307) — no longer needed since DOM parser handles entities natively.
5. Keep `_strip_control_chars` (line 1311) — still needed for BLNS-style content.

The resulting function body becomes:
```python
async def convert_html_with_annotations(
    html: str,
    highlights: list[dict],
    tag_colours: dict[str, str],
    filter_path: Path | None = None,
    word_to_legal_para: dict[int, int | None] | None = None,
) -> str:
    # ... docstring ...

    # Strip script/style tags from browser copy-paste content
    html = strip_scripts_and_styles(html)

    # Fix mid-word font tag splits from LibreOffice RTF export
    html = fix_midword_font_splits(html)

    # Insert markers at character positions matching extract_text_from_html
    marked_html, marker_highlights = insert_markers_into_dom(html, highlights)

    # Strip control characters that are invalid in LaTeX AFTER markers are placed
    marked_html = _strip_control_chars(marked_html)

    # Convert to LaTeX
    latex = await convert_html_to_latex(marked_html, filter_path=filter_path)

    # Replace markers with annots
    return _replace_markers_with_annots(latex, marker_highlights, word_to_legal_para)
```

**Verification:**

Run: `uv run ruff check src/promptgrimoire/export/latex.py`
Expected: Clean

Run: `uvx ty check`
Expected: Clean

**Commit:** `feat: wire insert_markers_into_dom into convert_html_with_annotations`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Simplify `export_annotation_pdf` — remove plain-text path, add ValueError guard

**Verifies:** pdf-export-char-alignment.AC1.5, AC1.6

**Files:**
- Modify: `src/promptgrimoire/export/pdf_export.py:256-355` (`export_annotation_pdf`)

**Implementation:**

1. **Add ValueError guard** at the top of the function body (after the docstring):
   ```python
   if highlights and (not html_content or not html_content.strip()):
       raise ValueError(
           "Cannot insert annotation markers into empty content. "
           "Provide document content or remove highlights."
       )
   ```

2. **Remove `is_structured_html` detection** (lines 299-303) — no longer needed since `doc.content` is always HTML.

3. **Remove plain-text path** (lines 308-314) — no `_plain_text_to_html` call, no `escape_text_after_markers` flag.

4. **Simplify to single path:** Always call `preprocess_for_export(html_content)`.

5. **Remove `escape_text` kwarg** from the `convert_html_with_annotations` call (line 324).

The resulting function body becomes:
```python
async def export_annotation_pdf(
    html_content: str,
    highlights: list[dict[str, Any]],
    tag_colours: dict[str, str],
    general_notes: str = "",
    notes_latex: str = "",
    word_to_legal_para: dict[int, int | None] | None = None,
    output_dir: Path | None = None,
    user_id: str | None = None,
    filename: str = "annotated_document",
) -> Path:
    # ... docstring ...

    if highlights and (not html_content or not html_content.strip()):
        raise ValueError(
            "Cannot insert annotation markers into empty content. "
            "Provide document content or remove highlights."
        )

    # Preprocess HTML: detect platform, remove chrome, inject speaker labels
    processed_html = preprocess_for_export(html_content) if html_content else ""

    # Convert HTML to LaTeX body with annotations
    latex_body = await convert_html_with_annotations(
        html=processed_html,
        highlights=highlights,
        tag_colours=tag_colours,
        filter_path=_LIBREOFFICE_FILTER,
        word_to_legal_para=word_to_legal_para,
    )

    # ... rest unchanged (preamble, notes, assembly, compile) ...
```

Note: Keep the `general_notes` and `notes_latex` parameters for now — they are cleaned up in Phase 3.

**Verification:**

Run: `uv run ruff check src/promptgrimoire/export/pdf_export.py`
Expected: Clean

Run: `uvx ty check`
Expected: Clean

**Commit:** `fix: simplify export_annotation_pdf, add ValueError for empty content`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update callers and adapt existing tests

**Verifies:** pdf-export-char-alignment.AC1.1, AC1.5, AC1.6, AC5.1

**Files:**
- Modify: `tests/integration/test_pdf_export.py` — update any tests that pass `escape_text` parameter
- Create: `tests/unit/export/test_empty_content_guard.py` — tests for ValueError guard
- Modify: Any other callers of `convert_html_with_annotations` that pass `escape_text`

**Implementation:**

Search for all callers of `convert_html_with_annotations` and `export_annotation_pdf` that pass `escape_text` or rely on the plain-text path. Update them:

1. Remove `escape_text=True` or `escape_text=False` from all call sites
2. Update test assertions that expect the old plain-text wrapping behaviour

**Testing:**

Tests must verify each AC listed above:

- pdf-export-char-alignment.AC1.5: Test that `export_annotation_pdf` with empty `html_content` and non-empty `highlights` raises `ValueError` with descriptive message
- pdf-export-char-alignment.AC1.6: Test the specific `ValueError` message contains "empty content"
- pdf-export-char-alignment.AC5.1: Create a parametrised test that loads each HTML fixture from `tests/fixtures/`, runs `extract_text_from_html` to get valid char positions, creates synthetic highlights at those positions, and passes them through `insert_markers_into_dom`. Verify no errors raised. Use both `.html` and `.html.gz` fixtures.

Follow project testing patterns (class-based, pytest parametrise).

**Verification:**

Run: `uv run pytest tests/unit/export/test_empty_content_guard.py -v`
Expected: All tests pass

Run: `uv run test-debug`
Expected: No regressions

Run: `uv run pytest tests/integration/test_pdf_export.py -v` (if Pandoc/LaTeX available)
Expected: All tests pass

**Commit:** `test: update export tests for new marker insertion pipeline`
<!-- END_TASK_4 -->

---

## UAT Steps

After all tasks in this phase are complete and tests pass:

### Automated verification (pdf-export-char-alignment.AC1.1, AC1.5, AC1.6, AC5.1)

1. `uv run test-debug` — all tests pass, no regressions
2. `uv run pytest tests/unit/export/test_empty_content_guard.py -v` — ValueError guard tests green

### Manual verification (pdf-export-char-alignment.AC5.2, AC5.3)

1. [ ] Start the app: `uv run python -m promptgrimoire`
2. [ ] Navigate to: `/annotation`
3. [ ] Paste or upload an HTML document with highlights applied
4. [ ] Click Export PDF
5. [ ] Verify: PDF opens and highlights appear at correct character positions (not shifted or missing)

**Evidence Required:**
- [ ] Screenshot or PDF showing highlights at correct positions
- [ ] Test output showing all green for `test_empty_content_guard.py`

**For AC5.3 (i18n):** If CJK fixture content is available, repeat steps 3-5 with Chinese/Japanese/Korean text and verify highlights land on the correct characters (not shifted by multi-byte encoding).
