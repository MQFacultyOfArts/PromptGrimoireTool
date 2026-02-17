# Issue #134: Replace Python LaTeX String Manipulation with Lua Filter Pipeline

## Summary

Replace the post-Pandoc marker-in-text pipeline (Lark tokenizer, region builder, pylatexenc AST walker) with a pre-Pandoc HTML span insertion + Pandoc Lua filter approach. Split `latex.py` (1,708 lines) into focused modules aligned with the DFD. Delete ~900 lines and the `pylatexenc` dependency.

## Definition of Done

1. Replace marker-in-text pipeline with pre-Pandoc HTML span insertion + Pandoc Lua filter
2. Split `latex.py` into focused modules aligned with the DFD (no file >~400 lines)
3. Delete Process 4 entirely (~900 lines) and the `pylatexenc` dependency
4. Preserve public API (`convert_html_with_annotations`, `export_annotation_pdf`, `build_annotation_preamble`)
5. All existing fixtures produce equivalent PDF output
6. The "one, two, many" stacking model works for 0, 1, 2, 3+ overlapping highlights
7. Annotation margin notes still render at correct positions

## Acceptance Criteria

### AC1: Pre-Pandoc region computation (DoD items 1, 6)

- **134-lua-highlight.AC1.1**: Given overlapping highlights spanning a block boundary (`<h1>` into `<p>`), the HTML span insertion produces non-overlapping `<span>` elements pre-split at the block boundary, each with `data-hl` listing active highlight indices and `data-colors` listing active colours.
- **134-lua-highlight.AC1.2**: Given 3+ overlapping highlights on the same text, the span carries `data-hl="0,1,2"` and `data-colors="blue,orange,green"` (comma-separated, matching input order).
- **134-lua-highlight.AC1.3**: Given a highlight that doesn't cross any block boundary, a single `<span>` is emitted wrapping the full range.
- **134-lua-highlight.AC1.4**: Given text with no highlights, no `<span>` elements are inserted.
- **134-lua-highlight.AC1.5** (failure): Given a cross-block highlight, the span is NOT left crossing the block boundary (Pandoc would silently destroy it).

### AC2: Pandoc Lua filter rendering (DoD items 1, 6, 7)

- **134-lua-highlight.AC2.1**: Given a span with `hl="0"` and `colors="blue"`, the Lua filter emits `\highLight[tag-jurisdiction-light]{\underLine[color=tag-jurisdiction-dark, height=1pt, bottom=-3pt]{text}}` (single highlight tier).
- **134-lua-highlight.AC2.2**: Given a span with `hl="0,1"` and `colors="blue,orange"`, the filter emits nested `\highLight` with stacked `\underLine` (2-highlight tier: 2pt outer, 1pt inner).
- **134-lua-highlight.AC2.3**: Given a span with `hl="0,1,2"` and 3+ colours, the filter emits nested `\highLight` with single thick `\underLine[color=many-dark, height=4pt, bottom=-5pt]` (many tier).
- **134-lua-highlight.AC2.4**: Given a span with `annot` attribute, the filter emits `\annot{tag-name}{\textbf{Tag Name}\par{\scriptsize Author}}` as `RawInline` after the highlighted content.
- **134-lua-highlight.AC2.5**: Given a highlighted span inside a heading, Pandoc auto-wraps in `\texorpdfstring{}` (no special handling in filter). Verified by E2b experiment.
- **134-lua-highlight.AC2.6** (failure): Given a span with NO `hl` attribute, the filter passes it through unchanged.

### AC3: Module split (DoD item 2)

- **134-lua-highlight.AC3.1**: `latex.py` is split into modules where no single file exceeds ~400 lines.
- **134-lua-highlight.AC3.2**: Module boundaries align with DFD processes (marker insertion, Pandoc conversion, preamble/document assembly).
- **134-lua-highlight.AC3.3**: All imports from `pdf_export.py` and `annotation.py` continue to resolve (public API preserved via `__init__.py` re-exports or updated imports).

### AC4: Deletion and cleanup (DoD items 3, 4)

- **134-lua-highlight.AC4.1**: `pylatexenc` is removed from `pyproject.toml` dependencies.
- **134-lua-highlight.AC4.2**: All Process 4 functions are deleted: `tokenize_markers`, `build_regions`, `walk_and_wrap`, `_wrap_region_ast`, `_classify_node`, `_classify_macro`, `_walk_nodes`, `_split_text_at_boundaries`, `generate_highlighted_latex`, `generate_underline_wrapper`, `generate_highlight_wrapper`, `_wrap_content_with_nested_highlights`, `_wrap_content_with_highlight`, `_replace_markers_with_annots`, `_move_annots_outside_restricted`, `_brace_depth_at`, `_find_closing_brace_at_depth`, `_find_matching_brace`, `_extract_env_boundaries`, `_extract_annot_command`, `_strip_texorpdfstring`.
- **134-lua-highlight.AC4.3**: Process 4 test files are deleted: `test_region_builder.py`, `test_latex_generator.py`, `test_walk_and_wrap.py`, `test_marker_lexer.py`, `test_overlapping_highlights.py`.
- **134-lua-highlight.AC4.4**: `MarkerToken`, `MarkerTokenType`, `Region` classes are deleted.
- **134-lua-highlight.AC4.5**: The Lark grammar (`_MARKER_GRAMMAR`) and marker constants (`HLSTART_TEMPLATE`, `HLEND_TEMPLATE`, etc.) are deleted.
- **134-lua-highlight.AC4.6**: `_format_annot` is deleted from Python (annotation formatting moves to Lua filter).

### AC5: Visual equivalence (DoD item 5)

- **134-lua-highlight.AC5.1**: The Lawlis v R fixture produces a PDF with identical highlight rectangles (verified via `mutool draw -F trace` colour rectangle count).
- **134-lua-highlight.AC5.2**: The E7 perverse overlap test case (4 overlapping highlights, heading boundary) produces equivalent output through the new pipeline.
- **134-lua-highlight.AC5.3**: All integration tests in `test_highlight_latex_elements.py` pass with the new pipeline.

## Glossary

| Term | Definition |
|------|-----------|
| **Region** | A contiguous text span with a constant set of active highlights. Created by splitting overlapping highlights at every start/end boundary. |
| **Pre-split** | Splitting highlight `<span>` elements at HTML block boundaries (`<h1>`, `<p>`, `<li>`, etc.) before Pandoc processes them. Required because Pandoc silently destroys cross-block spans. |
| **Stacking tier** | The visual rendering for N active highlights: 1=single colour+underline, 2=nested colours+stacked underlines, 3+=nested colours+thick many-dark underline. |
| **Process 4** | DFD Process 4 "Replace Markers with Highlights" — the tokenizer, region builder, and pylatexenc walker pipeline being eliminated. |
| **Marker-in-text** | Current approach: `HLSTART{n}ENDHL` / `HLEND{n}ENDHL` text sentinels inserted into HTML, surviving Pandoc as literal text, then parsed post-Pandoc. |
| **Lua filter** | A Pandoc filter written in Lua that transforms the AST during conversion. Runs between HTML parsing and LaTeX output. |

---

## Architecture

### Current Pipeline (from DFD `00-data-flow.md`)

```
HTML + highlights[]
    ↓ P2: _insert_markers_into_html()
HTML with HLSTART/HLEND/ANNMARKER text sentinels
    ↓ P3: Pandoc HTML→LaTeX
LaTeX with marker text preserved verbatim
    ↓ P4: tokenize_markers() → build_regions() → walk_and_wrap()
LaTeX with \highLight/\underLine/\annot commands     ← 900 lines, pylatexenc
    ↓ P5: Assemble document
Complete .tex
    ↓ P6: LuaLaTeX
PDF
```

### Proposed Pipeline

```
HTML + highlights[]
    ↓ P2 (rewritten): compute_highlight_spans()
HTML with <span data-hl="0,1" data-colors="blue,orange" data-annots="..."> elements
    ↓ P3 (extended): Pandoc HTML→LaTeX + highlight_filter.lua
LaTeX with \highLight/\underLine/\annot commands     ← Lua filter, ~100 lines
    ↓ P5: Assemble document (unchanged)
Complete .tex
    ↓ P6: LuaLaTeX (unchanged)
PDF
```

**Key change:** Region computation moves from post-Pandoc (Python, operating on fragile LaTeX text) to pre-Pandoc (Python, operating on HTML DOM we fully control). The Lua filter handles only rendering (converting span attributes to LaTeX commands), not overlap resolution.

### Module Structure After Refactor

```
src/promptgrimoire/export/
├── __init__.py              # Re-exports public API
├── highlight_spans.py       # NEW: P2 — compute_highlight_spans() + pre-split logic (~300 lines)
├── pandoc.py                # RENAMED from parts of latex.py: P3 — convert_html_to_latex() (~150 lines)
├── preamble.py              # NEW: P5 — colour defs, annotation preamble, templates (~200 lines)
├── pdf_export.py            # EXISTING: orchestration (unchanged or minor updates)
├── pdf.py                   # EXISTING: compilation (unchanged)
├── html_normaliser.py       # EXISTING (unchanged)
├── list_normalizer.py       # EXISTING (unchanged)
├── unicode_latex.py         # EXISTING (unchanged)
├── marker_constants.py      # DELETED (markers no longer used)
├── filters/
│   ├── highlight.lua        # NEW: Pandoc Lua filter for highlight/underline/annot wrapping (~120 lines)
│   ├── libreoffice.lua      # EXISTING (unchanged)
│   └── legal.lua            # EXISTING (unchanged)
└── platforms/               # EXISTING (unchanged)
```

**`latex.py` is deleted.** Its contents are distributed:
- P2 functions → `highlight_spans.py`
- P3 functions → `pandoc.py`
- P4 functions → deleted (replaced by `filters/highlight.lua`)
- P5 functions → `preamble.py`
- Orchestration (`convert_html_with_annotations`) → `pandoc.py` or `pdf_export.py`

## Existing Patterns Followed

### HTML DOM manipulation for highlight processing

The existing `_insert_markers_into_html()` already walks the DOM and maps character positions to byte offsets. The new `compute_highlight_spans()` uses the same character-position-to-DOM-node mapping but produces `<span>` elements instead of text sentinels.

### Pandoc Lua filters

The project already uses Lua filters (`libreoffice.lua`, `legal.lua`) passed to Pandoc via `--lua-filter`. The new `highlight.lua` follows the same pattern and is loaded the same way.

### "One, two, many" stacking

The stacking model is already implemented in `generate_underline_wrapper()` and `generate_highlight_wrapper()`. The Lua filter reimplements the same logic, validated by E6A and E7 experiments.

### Flat span + comma-separated attributes (E6A)

The DOM walker emits `<span data-hl="0,1" data-colors="blue,orange">`. Pandoc strips the `data-` prefix, giving the Lua filter `hl="0,1"` and `colors="blue,orange"`. This was validated in E5 and E6A.

## Implementation Phases

### Phase 1: Extract preamble and Pandoc modules from latex.py

**What:** Move P5 functions (colour definitions, annotation preamble, templates, `_escape_latex`, `_format_timestamp`) to `preamble.py`. Move P3 functions (`convert_html_to_latex`, `_fix_invalid_newlines`) to `pandoc.py`. Move `convert_html_with_annotations` to `pandoc.py`. Update all imports.

**Why first:** Pure mechanical refactor with no behaviour change. Creates the module structure that later phases build on. All existing tests must pass with only import path changes.

**Risk:** Import chain breakage. Mitigated by updating `__init__.py` re-exports.

### Phase 2: Implement pre-Pandoc highlight span insertion

**What:** Create `highlight_spans.py` with `compute_highlight_spans()`. This function takes HTML + highlight list, walks the DOM, identifies block boundaries, splits overlapping highlights into non-overlapping regions, and inserts `<span>` elements with `data-hl`, `data-colors`, and `data-annots` attributes.

**Why:** This is the core algorithmic change — moving region computation from post-Pandoc LaTeX text to pre-Pandoc HTML DOM. Must be correct before the Lua filter can consume it.

**Reuses:** Character-position-to-DOM-node mapping from `_insert_markers_into_html()`. The region-splitting algorithm is conceptually identical to `build_regions()` but operates on character ranges rather than token streams.

### Phase 3: Implement Pandoc Lua filter for highlight rendering

**What:** Create `filters/highlight.lua`. The filter's `Span` callback reads `hl`, `colors`, and `annots` attributes, generates nested `\highLight[color]{...}` + `\underLine[...]{...}` wrapping per the stacking model, and emits `\annot{}` commands as `RawInline("latex", ...)`.

**Why:** Replaces the entire Process 4 pipeline. The Lua filter runs inside Pandoc, after HTML parsing but before LaTeX output, so it has access to the structured AST rather than fragile LaTeX text.

**Validated by:** E2b (headings + texorpdfstring), E6A (stacking model), E7 (perverse overlaps).

### Phase 4: Wire new pipeline and delete old code

**What:** Update `convert_html_with_annotations` to call `compute_highlight_spans()` instead of `_insert_markers_into_html()`, pass `highlight.lua` to Pandoc, and remove the call to `_replace_markers_with_annots()`. Delete all Process 4 functions, classes, constants, and the Lark grammar. Delete `_strip_texorpdfstring()` (Lua filter handles headings natively). Remove `pylatexenc` from `pyproject.toml`. Delete Process 4 test files. Update remaining tests.

**Why last:** This is the irreversible step. Phases 1-3 are additive (new modules alongside old code). Phase 4 cuts over and deletes.

**Risk:** Visual regression. Mitigated by running all fixture tests and comparing `mutool` rectangle counts before/after.

## Additional Considerations

### Annotation metadata passing

The Lua filter needs annotation metadata (tag name, author, comments) to emit `\annot{}` commands. Two options:

**Option A (span attributes):** Encode annotation data in span attributes: `data-annots='[{"tag":"jurisdiction","author":"Alice","comment":"..."}]'` (JSON in attribute). The Lua filter parses the JSON.

**Option B (sidecar file):** Write a JSON file alongside the HTML, pass its path to the Lua filter via `--metadata`. The filter reads it on init.

**Recommendation:** Option A for simplicity. Pandoc's Lua API can parse JSON via `pandoc.json.decode()`. Keeps the pipeline self-contained (no temp files for metadata).

### Colour definitions

The Lua filter needs to know tag colour names (e.g., `tag-jurisdiction-light`) to generate `\highLight[tag-jurisdiction-light]{...}`. These colour names are currently generated by `generate_tag_colour_definitions()` in the preamble.

**Approach:** The Lua filter uses the same naming convention (`tag-{slug}-light`, `tag-{slug}-dark`) as the preamble generator. No coordination needed beyond following the naming pattern. The preamble defines the colours; the filter references them by name.

### `_strip_texorpdfstring` elimination

Currently `_strip_texorpdfstring()` runs post-Pandoc to strip `\texorpdfstring{}` wrappers. With the Lua filter approach, Pandoc auto-wraps highlighted heading content in `\texorpdfstring{}` (E2b proved this), and since we already disable PDF bookmarks (`bookmarks=false` in preamble), the `\texorpdfstring` wrapper is harmless. The function can be deleted.

### `\label{}` handling

Pandoc generates `\label{}` from heading text. With the old marker approach, marker text leaked into labels. With the new span approach, the span content is clean text (no markers), so labels are clean. If labels are still unwanted, suppress via Pandoc flag or a one-line Lua filter addition.

### Test migration

| Old test file | Fate | Replacement |
|---|---|---|
| `test_region_builder.py` | DELETE | `test_highlight_spans.py` — tests region computation in HTML DOM |
| `test_latex_generator.py` | DELETE | Lua filter tested via integration (Pandoc round-trip) |
| `test_walk_and_wrap.py` | DELETE | Lua filter tested via integration |
| `test_marker_lexer.py` | DELETE | No replacement needed (no lexer) |
| `test_overlapping_highlights.py` | DELETE | `test_highlight_spans.py` + integration tests |
| `test_marker_insertion.py` | REWRITE | Tests for `compute_highlight_spans()` |
| `test_plain_text_conversion.py` | UPDATE imports | Functions move to `highlight_spans.py` |
| `test_latex_string_functions.py` | UPDATE imports | Functions move to `preamble.py` |
| `test_crlf_char_index_bug.py` | REWRITE | Tests for `compute_highlight_spans()` |
| `test_css_fidelity.py` | UPDATE imports | `convert_html_to_latex` moves to `pandoc.py` |
| `test_chatbot_fixtures.py` | UPDATE imports | `convert_html_to_latex` moves to `pandoc.py` |
| `test_pdf_export.py` | UPDATE imports | `convert_html_to_latex` moves to `pandoc.py` |
| `test_highlight_latex_elements.py` | KEEP | Integration test, exercises full pipeline |
