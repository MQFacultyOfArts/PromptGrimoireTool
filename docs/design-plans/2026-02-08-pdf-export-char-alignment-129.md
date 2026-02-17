# PDF Export Character Alignment Design

## Summary

This design fixes broken PDF export by aligning character-position-based annotation placement between the UI and the export pipeline. Currently, the UI uses `extract_text_from_html` (a DOM walker) to count characters for client-side highlighting, while the export pipeline uses `_insert_markers_into_html` (a string-based parser) to insert annotation markers for LaTeX conversion. These two algorithms disagree on whitespace handling, causing highlights to appear at incorrect positions in exported PDFs. Worse, the export function reads from a deleted database column (`raw_content`), producing silent blank PDFs.

The fix introduces `insert_markers_into_dom`, a new function that reuses the same DOM-walking logic as `extract_text_from_html` to insert marker strings at character-accurate positions in HTML. This produces marked-up HTML that preserves all formatting (bold, headings, tables) while placing `HLSTART`/`HLEND`/`ANNMARKER` tokens exactly where the UI expects them. The existing Pandoc-based HTML-to-LaTeX conversion pipeline remains unchanged -- only the marker insertion step is replaced. Dead code paths for plain text handling, general notes (superseded by the Respond tab's response draft), and the old string-based marker insertion are removed. The work proceeds in four phases: implement and test the new function, wire it into the export pipeline, rename "general notes" to "response draft", and delete obsolete code.

## Definition of Done

1. PDF export always includes the source document with highlights and annotation comments at correct character positions, regardless of which tab the user is on when they click Export
2. If the Respond tab (Tab 3) has content, it's appended as an additional section; if empty, no extra section appears
3. `general_notes` is dead code — remove it (it was a stub for what became Tab 3's response draft)
4. `extract_text_from_html` is the single source of truth for character counting — both UI highlighting and LaTeX export use the same indices
5. Marker insertion walks the DOM using the same logic as `extract_text_from_html`, not raw HTML string processing
6. Export fails loudly when document content is missing (no silent empty PDFs)
7. Dead code removed: `_insert_markers_into_html`, `escape_text` path, `_plain_text_to_html`, `_escape_html_text_content`, `is_structured_html` detection, `general_notes` parameter/plumbing
8. All existing regression tests pass or are adapted; round-trip property test proves char index agreement

## Acceptance Criteria

### pdf-export-char-alignment.AC1: PDF includes source document with annotations
- **pdf-export-char-alignment.AC1.1 Success:** Export from Tab 1 (Annotate) produces PDF with source document body, highlights, and annotation comments in margins
- **pdf-export-char-alignment.AC1.2 Success:** Export from Tab 3 (Respond) produces the same source document body with highlights and comments
- **pdf-export-char-alignment.AC1.3 Success:** Highlights appear at correct character positions (marker text matches `extract_text_from_html` char slice)
- **pdf-export-char-alignment.AC1.4 Success:** CJK/Unicode content highlights at correct positions (characters indexed individually, not by byte)
- **pdf-export-char-alignment.AC1.5 Failure:** Export with no document content shows user-facing error notification, not a blank PDF
- **pdf-export-char-alignment.AC1.6 Failure:** `export_annotation_pdf` raises `ValueError` when highlights provided with empty content

### pdf-export-char-alignment.AC2: Response draft section
- **pdf-export-char-alignment.AC2.1 Success:** When Tab 3 has content, PDF includes a "Response Draft" section after the annotated document
- **pdf-export-char-alignment.AC2.2 Edge:** When Tab 3 is empty (never visited or no content typed), PDF has no Response Draft section
- **pdf-export-char-alignment.AC2.3 Success:** Export works regardless of whether the exporting user has visited Tab 3 (falls back to CRDT Text field)

### pdf-export-char-alignment.AC3: Character index agreement
- **pdf-export-char-alignment.AC3.1 Success:** Round-trip property: for any HTML, `extract_text_from_html(html)[start:end]` equals the text between HLSTART/HLEND in `insert_markers_into_dom(html, highlights)` output
- **pdf-export-char-alignment.AC3.2 Success:** Multi-block HTML (whitespace between `</p><p>`) does not cause index drift
- **pdf-export-char-alignment.AC3.3 Success:** `<br>` tags counted as single newline character (matching `extract_text_from_html`)
- **pdf-export-char-alignment.AC3.4 Success:** Whitespace runs collapsed to single space (matching `extract_text_from_html`)
- **pdf-export-char-alignment.AC3.5 Success:** Formatted spans (`<strong>`, `<em>`, etc.) preserved in output, markers at correct positions across tag boundaries

### pdf-export-char-alignment.AC4: Dead code removal
- **pdf-export-char-alignment.AC4.1 Success:** No references to `_insert_markers_into_html`, `_plain_text_to_html`, `_escape_html_text_content`, or `general_notes` (as export parameter) remain in source code
- **pdf-export-char-alignment.AC4.2 Success:** `ruff check` and `ty check` clean after removal
- **pdf-export-char-alignment.AC4.3 Success:** Full test suite passes

### pdf-export-char-alignment.AC5: Fixture regression
- **pdf-export-char-alignment.AC5.1 Success:** All HTML conversation fixtures (`tests/fixtures/*.html`, `*.html.gz`) pass through `insert_markers_into_dom` without error when given highlights at valid char positions from `extract_text_from_html`
- **pdf-export-char-alignment.AC5.2 Success:** Exported PDFs from fixture content undergo visual inspection (screenshots or PDF review) to confirm annotations appear at correct positions — not just "no crash" but "looks right"
- **pdf-export-char-alignment.AC5.3 Success:** i18n fixtures (Chinese Wikipedia, Japanese, Korean, Spanish) produce PDFs with correctly positioned CJK/diacritical highlights

## Glossary

- **CRDT**: Conflict-free Replicated Data Type -- a data structure that allows multiple users to edit the same document concurrently without conflicts, using merge rules instead of locks. PromptGrimoire uses `pycrdt` to enable real-time collaborative annotation.
- **DOM**: Document Object Model -- the tree representation of an HTML document. Walking the DOM means traversing this tree rather than processing raw HTML strings.
- **LexborHTMLParser**: The HTML parser from `selectolax` that builds a DOM tree from HTML strings. "Lexbor" refers to the underlying C library backend.
- **Pandoc**: Universal document converter. PromptGrimoire uses it to convert HTML to LaTeX before PDF compilation.
- **LaTeX**: Typesetting language for producing formatted documents. PromptGrimoire compiles LaTeX to PDF for annotation export.
- **Char spans**: `<span class="char" data-char-index="N">` wrappers injected by the UI to enable character-level text selection. The export pipeline does NOT use char spans -- it works with clean HTML.
- **Round-trip property**: A test that proves two functions agree by demonstrating that extracting text and then marking it produces the same character slices.
- **Marker strings**: Literal text tokens like `HLSTART{0}ENDHL` and `HLEND{0}ENDHL` inserted into HTML to mark highlight boundaries. Survive Pandoc conversion unchanged, then replaced with LaTeX commands.
- **Whitespace collapsing**: HTML rendering rule where consecutive whitespace characters (spaces, tabs, newlines) are collapsed to a single space. Both the UI and export must apply the same rule to agree on character positions.
- **Block tags**: HTML elements that render as blocks (e.g., `<p>`, `<div>`, `<h1>`). Whitespace-only text nodes between block tags are skipped during character counting.
- **Alembic**: Database schema migration tool for SQLAlchemy/SQLModel. Manages version-controlled changes to the PostgreSQL schema.
- **Selectolax**: Fast HTML parser library with Lexbor backend used in the input pipeline for DOM manipulation and text extraction.

## Architecture

### Problem

PDF export is broken. The `_handle_pdf_export` function (`annotation.py:1685-1688`) reads `doc.raw_content`, which was removed by Alembic migration `9a0b954d51bf`. The `hasattr` fallback silently returns `""`, producing blank PDFs with no source document and no annotations.

Even after fixing the data source, the existing `_insert_markers_into_html` (`latex.py:780-873`) counts characters by walking raw HTML strings, while the UI counts characters via `extract_text_from_html` (`html_input.py:374-450`) which walks the DOM. These two algorithms disagree on whitespace-only text nodes between blocks, `<br>` tags, and whitespace collapsing — causing annotation markers to drift from their correct positions.

### Solution

One DOM walk, one counting algorithm. A new function `insert_markers_into_dom` in `input_pipeline/html_input.py` walks the DOM using the same logic as `extract_text_from_html` (same `LexborHTMLParser`, same `_BLOCK_TAGS`, same `_STRIP_TAGS`, same `_WHITESPACE_RUN`) but inserts `HLSTART{n}ENDHL` / `HLEND{n}ENDHL` / `ANNMARKER{n}ENDMARKER` marker strings into text nodes at the correct character positions instead of extracting characters.

The output is the original HTML with all formatting preserved (bold, headings, speaker labels, tables) plus marker strings at character-index-accurate positions. This feeds into the existing Pandoc HTML-to-LaTeX conversion and marker replacement pipeline unchanged.

### Data flow (after fix)

```
doc.content (clean HTML from DB)
    |
    v
insert_markers_into_dom(html, highlights)
    |  Same DOM walk as extract_text_from_html
    |  Inserts HLSTART/HLEND/ANNMARKER at correct char positions
    |  Preserves all HTML formatting
    v
Marked HTML --> Pandoc HTML-to-LaTeX --> _replace_markers_with_annots
    |
    v
LaTeX with \highLight, \underLine, \annot commands
    +
response_draft_section (from Tab 3, if non-empty)
    |
    v
compile_latex --> PDF
```

### Contract: `insert_markers_into_dom`

```python
def insert_markers_into_dom(
    html: str,
    highlights: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Insert annotation markers into HTML at correct character positions.

    Walks the DOM using the same logic as extract_text_from_html
    (same whitespace rules, same block/strip tags, same collapse).
    Inserts HLSTART/HLEND/ANNMARKER text into DOM text nodes at
    positions matching the char indices from extract_text_from_html.

    Args:
        html: Clean HTML (from doc.content, no char spans).
        highlights: List of highlight dicts with start_char, end_char, tag, etc.

    Returns:
        (marked_html, marker_highlights) — same contract as the old
        _insert_markers_into_html for downstream compatibility.

    Raises:
        ValueError: If html is empty/None and highlights are non-empty.
    """
```

## Existing Patterns

`extract_text_from_html` (`html_input.py:374-450`) is the canonical character counter. It uses:

- `LexborHTMLParser` from selectolax for DOM parsing
- `_BLOCK_TAGS` (frozenset, 18 tags) for whitespace-only text node skipping
- `_STRIP_TAGS` (frozenset: script, style, noscript, template) for content exclusion
- `_WHITESPACE_RUN` (`re.compile(r"[\s\u00a0]+")`) for whitespace collapsing
- Recursive `_walk(node)` visiting `-text` nodes, `br` tags, and recursing into children

The JS client-side `_injectCharSpans` (`static/js/char_spans.js`) implements the same rules. Issue #129 established that these two must agree, with `test_matches_inject_char_spans` as the invariant test.

The new `insert_markers_into_dom` follows this same pattern — it lives in the same module, uses the same constants, and uses the same walk structure. The only difference: instead of `chars.extend(text)`, it splices marker strings into text node content at matching char indices.

The existing `_insert_markers_into_html` (`latex.py:780-873`) walks raw HTML strings character-by-character, which is a fundamentally different approach that cannot match the DOM-based counting. It is replaced, not adapted.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: New `insert_markers_into_dom` function + tests

**Goal:** Create the replacement marker insertion function with full test coverage, proving it agrees with `extract_text_from_html`.

**Components:**
- `insert_markers_into_dom` in `src/promptgrimoire/input_pipeline/html_input.py` — DOM-based marker insertion using same walk as `extract_text_from_html`
- Export in `src/promptgrimoire/input_pipeline/__init__.py`
- Tests in `tests/unit/input_pipeline/test_insert_markers.py` — adapted from `tests/unit/export/test_marker_insertion.py` plus new round-trip property test

**Dependencies:** None (new function, no changes to existing code yet)

**Done when:** Round-trip property test passes: for any HTML and any valid highlight range from `extract_text_from_html`, the text between HLSTART and HLEND markers in the output matches `"".join(chars[start:end])`. Existing marker insertion test cases (simple, multi-block, `<br>`, whitespace, CJK, formatted spans) all pass with the new function.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Wire new function into export pipeline

**Goal:** Replace the broken export data path. PDF export produces correct output.

**Components:**
- `_handle_pdf_export` in `src/promptgrimoire/pages/annotation.py` — use `doc.content` instead of `doc.raw_content`; add empty-content validation guard
- `convert_html_with_annotations` in `src/promptgrimoire/export/latex.py` — call `insert_markers_into_dom` instead of `_insert_markers_into_html`; remove `escape_text` parameter
- `export_annotation_pdf` in `src/promptgrimoire/export/pdf_export.py` — add `ValueError` when highlights provided with empty content; remove `is_structured_html` detection and plain-text path

**Dependencies:** Phase 1

**Done when:** Integration PDF export tests pass (`tests/integration/test_pdf_export.py`). Export from Tab 1 and Tab 3 both produce PDFs with source document, highlights, and annotation comments. Empty content triggers explicit error, not blank PDF.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Rename general_notes to response_draft

**Goal:** Remove the dead `general_notes` concept. The only notes section is Tab 3's response draft.

**Components:**
- `_build_general_notes_section` in `src/promptgrimoire/export/pdf_export.py` — rename to `_build_response_draft_section`; remove `general_notes` HTML parameter (keep only `latex_content` from Pandoc)
- `_html_to_latex_notes` in `src/promptgrimoire/export/pdf_export.py` — delete (was HTML-to-LaTeX for the old general_notes; Pandoc path via `markdown_to_latex_notes` replaces it)
- `_GENERAL_NOTES_TEMPLATE` in `src/promptgrimoire/export/pdf_export.py` — rename to `_RESPONSE_DRAFT_TEMPLATE`, rename section title to "Response Draft"
- `_DOCUMENT_TEMPLATE` in `src/promptgrimoire/export/pdf_export.py` — rename `{general_notes_section}` placeholder to `{response_draft_section}`
- `export_annotation_pdf` in `src/promptgrimoire/export/pdf_export.py` — remove `general_notes` parameter; rename `notes_latex` to `response_draft_latex`
- `general_notes` CRDT field in `src/promptgrimoire/crdt/annotation_doc.py` — keep in CRDT doc (backward compat with existing docs) but remove helper methods `get_general_notes`, `set_general_notes` if unused elsewhere
- Update callers in `annotation.py`

**Dependencies:** Phase 2

**Done when:** No references to `general_notes` remain in the export pipeline. `_html_to_latex_notes` deleted. All tests pass. Response draft from Tab 3 appears under "Response Draft" heading in PDF.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Delete dead code

**Goal:** Remove all code made redundant by the new approach.

**Components:**
- `_insert_markers_into_html` in `src/promptgrimoire/export/latex.py` (line 780-873) — delete
- `_escape_html_text_content` in `src/promptgrimoire/export/latex.py` (line 56-96) — delete
- `_plain_text_to_html` in `src/promptgrimoire/export/pdf_export.py` (line 51-93) — delete
- `_html_to_latex_notes` in `src/promptgrimoire/export/pdf_export.py` (if not already deleted in Phase 3) — delete
- `strip_scripts_and_styles` call path in `convert_html_with_annotations` if only used for the removed branch — verify and delete if dead
- `tests/unit/export/test_plain_text_conversion.py` — delete (tests `_plain_text_to_html`)
- `tests/unit/export/test_crlf_char_index_bug.py` — delete or adapt (tests alignment between old counter and another counter; structurally eliminated)
- Adapt `tests/unit/export/test_marker_insertion.py` — old tests for `_insert_markers_into_html` either migrated to Phase 1 tests or deleted

**Dependencies:** Phases 2 and 3

**Done when:** `ruff check` clean. `ty check` clean. Full test suite passes. No imports of deleted symbols remain.
<!-- END_PHASE_4 -->

## Additional Considerations

**Selectolax mutation:** `insert_markers_into_dom` needs to modify text node content in the parsed DOM. Selectolax (lexbor) supports `.text_content` assignment on nodes but may have limitations with text node splitting. If direct DOM mutation proves difficult, an alternative is to use the DOM walk to build a position map (`char_idx -> (text_node_content, offset)`) and then do string-level insertion on the serialised HTML using those precise byte offsets. The implementation plan should spike this early in Phase 1.

**CRDT `general_notes` field:** The field exists in persisted CRDT documents. Removing it from `AnnotationDocument.__init__` would break deserialization of existing docs. Phase 3 keeps the field in the CRDT schema but removes the Python helper methods and all export pipeline references.

**Existing test inventory:** 336+ tests across 7 files cover the marker pipeline. The investigator's full inventory (in this conversation's context) should be consulted during implementation planning to ensure no regression test is lost without deliberate decision.
