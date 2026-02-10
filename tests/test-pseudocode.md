# Test Pseudocode

Human-readable description of what each test does, organised by domain.
Maintained by project-claude-librarian at branch completion.

Overlapping tests and coverage gaps are documented intentionally --
they reveal where the test suite is redundant or incomplete.

> **Scope:** This file currently covers tests added or modified on the
> 134-lua-highlight branch. Existing tests from before this branch are
> not yet documented here.

## Highlight Span Insertion (Pre-Pandoc)

### No highlights leaves HTML unchanged
**File:** tests/unit/export/test_highlight_spans.py::TestAC1_4_NoHighlights
1. Pass HTML with an empty highlights list to compute_highlight_spans
2. Assert output HTML is identical to input
3. Pass empty HTML with a highlight; assert output is empty string

**Verifies:** The pipeline is a no-op when there is nothing to highlight

### Single-block highlight produces one span
**File:** tests/unit/export/test_highlight_spans.py::TestAC1_3_SingleBlockHighlight
1. Create HTML with one paragraph
2. Create a highlight covering "simple" (chars 0-6)
3. Call compute_highlight_spans
4. Parse output, find spans with data-hl attribute
5. Assert exactly 1 span, with data-hl="0", data-colors="tag-jurisdiction-light", text="simple"
6. Repeat for mid-text highlight ("world" in "hello world today")

**Verifies:** Highlights within a single block produce exactly one span with correct attributes

### 3+ overlapping highlights carry all indices and colours
**File:** tests/unit/export/test_highlight_spans.py::TestAC1_2_OverlappingHighlights
1. Create HTML with one paragraph
2. Create 3 overlapping highlights on the same word "text"
3. Call compute_highlight_spans
4. Find spans where data-hl contains all three indices "0,1,2"
5. Assert all three colour names appear in data-colors
6. Repeat with only 2 overlapping highlights; assert data-hl="0,1"

**Verifies:** Overlapping highlights merge into single spans with comma-separated indices/colours

### Cross-block highlight produces pre-split spans
**File:** tests/unit/export/test_highlight_spans.py::TestAC1_1_CrossBlockSplit
1. Create HTML with h1 followed by p
2. Create a highlight spanning from h1 through p (entire text)
3. Call compute_highlight_spans
4. Assert at least 2 spans are emitted
5. Assert one span contains "Title" and one contains "Body text"
6. All spans have data-hl="0"

**Verifies:** Highlights crossing block boundaries are split into separate spans per block

### No single span crosses a block boundary
**File:** tests/unit/export/test_highlight_spans.py::TestAC1_5_NoCrossBlockSpan
1. Create cross-block highlight (h2 into p)
2. Call compute_highlight_spans
3. For each output span, walk up to find its block ancestor
4. Assert every span is fully within one block element
5. Assert separate spans exist for "Heading" and "Body"

**Verifies:** Pandoc would silently destroy cross-block spans; the pipeline prevents this

### Edge cases: adjacent, entities, newlines, annotations
**File:** tests/unit/export/test_highlight_spans.py::TestEdgeCases
1. Adjacent non-overlapping highlights produce 2 separate spans with different data-hl values
2. HTML entity (&amp;) within highlighted range: span text contains the decoded character
3. data-annots appears on exactly one span (the last span of a highlight)
4. data-annots contains pre-formatted LaTeX (\annot{tag-jurisdiction}{...})
5. Newline characters in text: highlight spans correctly cover both lines
6. PANDOC_BLOCK_ELEMENTS constant contains all required block elements

**Verifies:** Correct behaviour under non-trivial HTML content

### format_annot_latex produces correct annotation strings
**File:** tests/unit/export/test_highlight_spans.py::TestFormatAnnotLatex
1. Basic: tag + author produces \annot{tag-jurisdiction}{\textbf{Jurisdiction}...Alice Jones}
2. Underscore tags: "key_issue" becomes "tag-key-issue" colour name and "Key Issue" display
3. Para ref "[45]" is included in margin content
4. ISO timestamp formatted as "26 Jan 2026 14:30"
5. Comments produce \par\hrulefill separator with author and text
6. Multiple comments each appear in output
7. LaTeX special characters (&) are escaped
8. Test UUID suffixes ("Alice Jones 1664E02D") are stripped from display names
9. Integration: data-annots attribute in compute_highlight_spans output contains pre-formatted LaTeX

**Verifies:** Annotation margin notes are correctly formatted as LaTeX

## Lua Filter (Pandoc Integration)

### Single highlight tier
**File:** tests/integration/test_highlight_lua_filter.py::TestSingleHighlight
1. Create HTML with span data-hl="0" data-colors="tag-jurisdiction-light"
2. Run Pandoc with highlight.lua filter
3. Assert LaTeX contains \highLight[tag-jurisdiction-light]{
4. Assert LaTeX contains \underLine[color=tag-jurisdiction-dark, height=1pt, bottom=-3pt]{
5. Assert "highlighted text" content is preserved

**Verifies:** Single highlight produces highlight background + 1pt underline in tag colour

### Two-highlight tier
**File:** tests/integration/test_highlight_lua_filter.py::TestTwoHighlights
1. Create HTML with span data-hl="0,1" and two colours
2. Run Pandoc with filter
3. Assert two nested \highLight wrappers
4. Assert outer underline is 2pt at -5pt, inner is 1pt at -3pt
5. Assert nesting order: jurisdiction (outer) wraps evidence (inner)

**Verifies:** Two highlights stack with distinct underline weights and correct nesting

### Three+ highlights (many-dark)
**File:** tests/integration/test_highlight_lua_filter.py::TestManyHighlights
1. Create HTML with span data-hl="0,1,2" and three colours
2. Run Pandoc with filter
3. Assert \underLine[color=many-dark, height=4pt, bottom=-5pt]{
4. Assert three nested \highLight wrappers
5. Assert NO individual dark colour underlines appear

**Verifies:** 3+ highlights collapse to single thick many-dark underline

### Annotation emission
**File:** tests/integration/test_highlight_lua_filter.py::TestAnnotation
1. Create HTML with span containing data-annots with pre-formatted \annot{} LaTeX
2. Run Pandoc with filter
3. Assert \annot{tag-jurisdiction} appears in output
4. Assert annotation content (author, tag name) is present
5. Assert annotation appears after all highlight/underline closing braces

**Verifies:** Annotations are emitted as raw LaTeX after the highlight wrapping

### Heading safety
**File:** tests/integration/test_highlight_lua_filter.py::TestHeading
1. Create h2 containing a highlighted span
2. Run Pandoc with filter
3. Assert \texorpdfstring{ appears (Pandoc auto-wraps for PDF bookmarks)

**Verifies:** Highlighted headings produce valid LaTeX (no \annot in \section{} args)

### No hl attribute (pass-through)
**File:** tests/integration/test_highlight_lua_filter.py::TestNoHlAttribute
1. Create HTML with span class="other" but no data-hl
2. Run Pandoc with filter
3. Assert no \highLight or \underLine in output
4. Assert text content preserved

**Verifies:** Non-highlight spans pass through without modification

### Edge cases: empty hl, empty colors
**File:** tests/integration/test_highlight_lua_filter.py::TestEdgeCases
1. Empty data-hl="": no highlights, no crash, text preserved
2. data-hl="0" but data-colors="": no highlights, no crash, text preserved

**Verifies:** Graceful degradation on malformed attributes

## Pipeline Cleanup Validation

### pylatexenc removed from main dependencies
**File:** tests/unit/export/test_pipeline_cleanup.py::TestAC4_1_PylatexencRemoved
1. Read pyproject.toml
2. Extract [project] dependencies section
3. Assert "pylatexenc" not in main deps
4. Assert "pylatexenc" IS still in dev deps (used by test helpers)

**Verifies:** Production dependency removed; dev dependency retained for structural LaTeX assertions

### latex.py deleted
**File:** tests/unit/export/test_pipeline_cleanup.py::TestAC4_2_LatexPyDeleted
1. Check src/promptgrimoire/export/latex.py path
2. Assert file does not exist

**Verifies:** Old monolithic module fully removed

### Old pipeline test files deleted
**File:** tests/unit/export/test_pipeline_cleanup.py::TestAC4_3_P4TestFilesDeleted
1. Parametrize over 7 deleted test file paths
2. Assert each file does not exist

**Verifies:** No orphaned tests from the old pipeline remain

### Old pipeline classes not importable
**File:** tests/unit/export/test_pipeline_cleanup.py::TestAC4_4_P4ClassesRemoved
1. Import promptgrimoire.export
2. Assert MarkerToken, MarkerTokenType, Region are not attributes of the module

**Verifies:** Old pipeline types are completely removed from the public API

### lark removed from dependencies
**File:** tests/unit/export/test_pipeline_cleanup.py::TestAC4_5_LarkRemoved
1. Read pyproject.toml
2. Assert "lark" not in main deps
3. Assert "lark" not in dev deps

**Verifies:** Lark dependency completely removed

### _format_annot replaced by format_annot_latex
**File:** tests/unit/export/test_pipeline_cleanup.py::TestAC4_6_FormatAnnotRemoved
1. Assert _format_annot not importable from export, preamble, or pandoc
2. Assert format_annot_latex IS importable from highlight_spans

**Verifies:** Annotation formatting function renamed and relocated

### Integration test file exists and resolves
**File:** tests/unit/export/test_pipeline_cleanup.py::TestAC5_3_IntegrationTestsExist
1. Assert tests/integration/test_highlight_latex_elements.py exists on disk
2. Import the module; assert no ImportError

**Verifies:** Integration tests survived the pipeline replacement

## Module Split Validation

### Line count constraints
**File:** tests/unit/export/test_module_split.py::TestAC3_1_LineCounts
1. Count lines in preamble.py; assert < 450
2. Count lines in pandoc.py; assert < 450
3. Assert latex.py does not exist (deleted in Phase 4)

**Verifies:** New modules stay manageable in size; old monolith removed

### Symbol placement matches DFD
**File:** tests/unit/export/test_module_split.py::TestAC3_2_SymbolPlacement
1. Import build_annotation_preamble from preamble; assert callable
2. Import generate_tag_colour_definitions from preamble; assert callable
3. Import convert_html_to_latex from pandoc; assert callable
4. Import convert_html_with_annotations from pandoc; assert callable

**Verifies:** Functions landed in the correct module per data flow design

### Public API imports resolve
**File:** tests/unit/export/test_module_split.py::TestAC3_3_PublicAPI
1. Import convert_html_to_latex from promptgrimoire.export
2. Import export_annotation_pdf from promptgrimoire.export
3. Import build_annotation_preamble from preamble
4. Import convert_html_with_annotations from pandoc
5. Import export_annotation_pdf from pdf_export

**Verifies:** Package-level re-exports work; no broken imports after restructuring

## Export Resilience

### \includegraphics stub after hyperref
**File:** tests/unit/test_export_image_stripping.py::TestIncludegraphicsStub
1. Generate preamble with build_annotation_preamble
2. Assert \renewcommand{\includegraphics} appears after all \usepackage calls
3. Assert the stub is NOT in UNICODE_PREAMBLE (too early)

**Verifies:** Image references cannot crash PDF compilation (corrupt-PDF regression)

### otherlanguage environment defined
**File:** tests/unit/test_export_image_stripping.py::TestOtherlanguageEnvironment
1. Generate preamble
2. Assert "otherlanguage" and "newenvironment" appear in preamble

**Verifies:** Pandoc's language markup for non-English content does not crash compilation

### Markdown images stripped before Pandoc
**File:** tests/unit/test_export_image_stripping.py::TestMarkdownImageStripping
1. Convert markdown with ![alt](url) to LaTeX via markdown_to_latex_notes
2. Assert \includegraphics not in output
3. Repeat with reference-style images ![alt][id]
4. Verify empty/whitespace markdown returns empty string

**Verifies:** Image syntax in response drafts cannot produce \includegraphics in LaTeX
