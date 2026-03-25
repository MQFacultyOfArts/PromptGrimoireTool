# PDF Paragraph Numbering in Export Design

**GitHub Issue:** #417

## Summary

The PDF export pipeline already supports annotation highlighting and endnotes, but two visual elements present in the on-screen workspace do not carry through to the exported PDF: paragraph numbers in the left margin, and clickable navigation between inline annotation markers and their corresponding endnotes. This design adds both.

Paragraph numbers are injected into the HTML that gets passed to Pandoc as empty `<span>` elements carrying a `data-paranumber` attribute. Pandoc preserves these spans through its AST; the existing Lua filter `Span` callback is extended to emit a new `\paranumber{}` LaTeX command, which uses `\llap` to place a small grey number in the left margin without disturbing text flow. Endnote cross-references are added entirely within the LaTeX layer: the existing `\annot` macro gains `\label` and `\hyperref` commands at both the inline and endnote sites, creating bidirectional PDF hyperlinks using the `hyperref` package that is already loaded. The two features are independent of each other and share no new abstractions.

## Definition of Done

1. **Left-margin paragraph numbers in PDF body** — When autonumbering is on, the exported PDF shows small grey paragraph numbers in the left margin, matching the on-screen display. Source-number mode is excluded (list numbers already visible as ordered list items).

2. **Clickable endnote cross-references** — Long annotations that get deferred to the endnotes section have bidirectional hyperlinks: superscript in body jumps to endnote, endnote number jumps back to body location. Uses the already-loaded `hyperref` package.

3. **No layout changes** — Existing PDF layout, margin/endnote split, and annotation rendering are preserved. These are additions only.

## Acceptance Criteria

### pdf-para-numbering-417.AC1: Left-margin paragraph numbers
- **pdf-para-numbering-417.AC1.1 Success:** HTML passed to Pandoc contains `<span data-paranumber="N">` at the start of each auto-numbered paragraph
- **pdf-para-numbering-417.AC1.2 Success:** No markers injected when `word_to_legal_para` is None (autonumbering off)
- **pdf-para-numbering-417.AC1.3 Success:** No markers injected for empty paragraph map
- **pdf-para-numbering-417.AC1.4 Success:** LaTeX output contains `\paranumber{N}` matching the paragraph map
- **pdf-para-numbering-417.AC1.5 Success:** Paragraph numbers render in the PDF left margin as small grey sans-serif text
- **pdf-para-numbering-417.AC1.6 Edge:** Paragraphs with highlight spans at position 0 still get the paranumber marker before the highlight

### pdf-para-numbering-417.AC2: Clickable endnote cross-references
- **pdf-para-numbering-417.AC2.1 Success:** Long annotations produce `\label{annot-inline:N}` at inline location and `\hyperref[annot-endnote:N]` wrapping superscript
- **pdf-para-numbering-417.AC2.2 Success:** Endnote entries contain `\label{annot-endnote:N}` and `\hyperref[annot-inline:N]` wrapping endnote number
- **pdf-para-numbering-417.AC2.3 Success:** Table-safe variants (`\annotref`/`\annotendnote`) produce matching label/hyperref pairs
- **pdf-para-numbering-417.AC2.4 Failure:** Short annotations (margin path) do NOT get hyperref linking

### pdf-para-numbering-417.AC3: No layout changes
- **pdf-para-numbering-417.AC3.1 Success:** Existing export tests pass without modification
- **pdf-para-numbering-417.AC3.2 Success:** `format_annot_latex()` output with `para_ref` survives endnote `\write` path (para refs visible in endnotes)

## Glossary

- **`\annot` macro**: Custom LaTeX command in `promptgrimoire-export.sty` that handles annotation rendering — short annotations go in the margin, long annotations are deferred to an endnotes section.
- **`\annotref` / `\annotendnote`**: Table-safe variants of `\annot` used inside `longtable` cells, where margin note macros break.
- **`word_to_legal_para`**: The paragraph map passed through the export pipeline — maps character offsets to paragraph numbers. `None` when autonumbering is off.
- **`\write` / endnote deferral**: LaTeX technique where content is written to an auxiliary file during compilation and `\input` back at the end of the document.
- **`\hyperref` / `\label`**: Standard LaTeX cross-referencing — `\label` marks a destination, `\hyperref` creates a clickable link to it. Bidirectional when both sites have labels.
- **`\llap`**: LaTeX command that places its argument to the left of the current position without consuming horizontal space — used for margin numbers.
- **`\phantomsection`**: Creates a linkable anchor at the current position, required before `\label` in contexts without numbered elements.
- **`\noexpand`**: LaTeX primitive that defers macro expansion inside `\write`, so commands are written literally and execute when the file is later `\input`ed.
- **`para_ref`**: Paragraph reference string (e.g. `[3]`) stored on annotations, indicating which paragraph the annotation belongs to.
- **source-number mode**: Alternative numbering mode where paragraphs use original source numbers from `<li value="N">`. Excluded from margin numbers because list item numbers are already visible.

## Architecture

Two independent additions to the existing PDF export pipeline, sharing no new abstractions between them.

**Paragraph numbers** flow through the existing Pandoc span-attribute mechanism. After `compute_highlight_spans()` inserts highlight `<span>` elements, a new function injects `<span data-paranumber="N"></span>` marker spans at the start of each numbered paragraph. Pandoc preserves span attributes; the existing Lua `Span` callback in `highlight.lua` gains a `paranumber` check that emits `\paranumber{N}` as raw LaTeX. The `\paranumber` command uses `\llap` to place a small grey sans-serif number in the left margin without affecting text flow.

**Endnote cross-references** modify the `\annot` macro in `promptgrimoire-export.sty`. The long-annotation path (endnote deferral) gains `\label`/`\hyperref` bidirectional linking: a `\label{annot-inline:N}` at the inline location with a `\hyperref[annot-endnote:N]` wrapping the superscript, and a `\label{annot-endnote:N}` in the endnote file with a `\hyperref[annot-inline:N]` wrapping the endnote number. Counter values are expanded at `\write` time; label/hyperref commands are deferred via `\noexpand`. Short annotations (margin path) do not get linking — the margin note is visually adjacent, so linking adds no value.

**Paragraph references in endnotes** are already present: `format_annot_latex()` puts `para_ref` (e.g. `[3]`) on line 1 of annotation content, and this flows through `\unexpanded{#2}` in the `\write`. This is a verification point, not new work.

## Existing Patterns

**Span attribute injection:** The highlight span pipeline (`compute_highlight_spans()` in `src/promptgrimoire/export/highlight_spans.py`) inserts `<span data-hl="..." data-colors="..." data-annots="...">` elements. Pandoc converts these to `Span` AST nodes with attributes (stripping the `data-` prefix). The Lua `Span` callback in `highlight.lua` reads these attributes and emits LaTeX. The paragraph number injection follows this exact pattern — a new `data-paranumber` attribute handled by the same callback.

**Paragraph attribute injection:** `inject_paragraph_attributes()` in `src/promptgrimoire/input_pipeline/paragraph_map.py` already adds `data-para` attributes to block elements for the web view. The new export function reuses this, then regex-inserts marker spans after each opening tag with `data-para`.

**Endnote file mechanism:** The `\annot` macro in `src/promptgrimoire/export/promptgrimoire-export.sty` writes long annotation content to `\jobname.endnotes` via `\immediate\write`, flushed by `\flushannotendnotes` at document end. The cross-reference addition modifies this existing mechanism rather than introducing a new one.

**Table-safe variants:** `\annotref` and `\annotendnote` in the `.sty` file, coordinated by the `Table` callback in `highlight.lua`, handle annotations inside `longtable` cells. These gain the same `\label`/`\hyperref` pattern.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Paragraph Number Injection

**Goal:** Inject paragraph number markers into export HTML so they survive Pandoc conversion.

**Components:**
- `inject_paragraph_markers_for_export()` in `src/promptgrimoire/input_pipeline/paragraph_map.py` — calls existing `inject_paragraph_attributes()` then regex-inserts `<span data-paranumber="N"></span>` after each opening tag with `data-para`
- Wire-up in `src/promptgrimoire/export/pandoc.py` `convert_html_with_annotations()` — call the new function after `compute_highlight_spans()` when `word_to_legal_para` is provided

**Dependencies:** None (first phase)

**Covers:** pdf-para-numbering-417.AC1.1, pdf-para-numbering-417.AC1.2, pdf-para-numbering-417.AC1.3

**Done when:** Marker spans appear in the HTML passed to Pandoc at correct paragraph positions, and do not appear when `word_to_legal_para` is `None`.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: LaTeX Paragraph Number Rendering

**Goal:** Convert paragraph number markers into visible left-margin numbers in the PDF.

**Components:**
- `\paranumber{N}` command in `src/promptgrimoire/export/promptgrimoire-export.sty` — uses `\leavevmode\llap{\textcolor{gray}{\scriptsize\textsf{N}\quad}}` for small grey left-margin placement
- `paranumber` attribute handling in `Span` callback in `src/promptgrimoire/export/filters/highlight.lua` — check must be placed **before** the existing `hl` nil-guard (which returns early for non-highlight spans); emits `\paranumber{N}` as `RawInline` when `el.attributes["paranumber"]` is present

**Dependencies:** Phase 1 (markers in HTML)

**Covers:** pdf-para-numbering-417.AC1.1, pdf-para-numbering-417.AC1.4, pdf-para-numbering-417.AC1.5

**Done when:** `generate_tex_only()` with a paragraph map produces LaTeX containing `\paranumber{N}` at correct positions. Smoke test compiles PDF without errors.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Endnote Cross-References

**Goal:** Add bidirectional hyperlinks between inline annotation superscripts and their endnote entries.

**Components:**
- Modified `\annot` macro in `src/promptgrimoire/export/promptgrimoire-export.sty`:
  - Long-annotation (endnote) path: add `\phantomsection\label{annot-inline:N}` at inline location, wrap superscript in `\hyperref[annot-endnote:N]`; write `\phantomsection\label{annot-endnote:N}` and `\hyperref[annot-inline:N]` wrapper to endnotes file
  - Short-annotation (margin) path: unchanged
- Modified `\annotref` macro — same inline label + hyperref pattern
- Modified `\annotendnote` macro — same endnote label + hyperref pattern

**Dependencies:** None (independent of Phases 1-2, but sequenced for review clarity)

**Covers:** pdf-para-numbering-417.AC2.1, pdf-para-numbering-417.AC2.2, pdf-para-numbering-417.AC2.3, pdf-para-numbering-417.AC2.4

**Done when:** LaTeX output contains `\label{annot-inline:N}` and `\hyperref[annot-endnote:N]` at inline locations, and endnotes file content contains matching back-links. Smoke test compiles PDF without errors.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Verification and Edge Cases

**Goal:** Verify para_ref in endnotes, test edge cases, and confirm no layout regressions.

**Components:**
- Verification test that `format_annot_latex()` output with `para_ref` survives the endnote `\write` path
- Edge case tests: empty paragraph map, document with no annotations, document with only short annotations (no endnotes section), mixed short and long annotations
- Regression check: existing export tests continue to pass (no layout changes)

**Dependencies:** Phases 1-3

**Covers:** pdf-para-numbering-417.AC3.1, pdf-para-numbering-417.AC3.2, pdf-para-numbering-417.AC1.6

**Done when:** All edge cases tested, existing export tests pass, para_ref verified in endnote output.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Documentation

**Goal:** Update user-facing guide to document paragraph numbering in PDF export.

**Components:**
- `src/promptgrimoire/docs/scripts/using_promptgrimoire.py` — add section on paragraph numbering appearing in exported PDFs and endnote cross-reference behaviour
- `uv run grimoire docs build` — verify docs build succeeds

**Dependencies:** Phases 1-4

**Done when:** Documentation reflects new behaviour, docs build passes.
<!-- END_PHASE_5 -->

## Additional Considerations

**`\write` expansion safety:** Counter values (`\the\value{annotnum}`) expand at `\write` time, capturing the correct annotation number. All LaTeX commands (`\label`, `\hyperref`, `\phantomsection`) are deferred via `\noexpand` to execute at `\input` time when the endnotes file is read. This is the standard LaTeX pattern for deferred file content.

**Two-pass compilation:** `\label`/`\hyperref` cross-references require two LaTeX passes to resolve. The existing `latexmk` build already runs multiple passes (for page numbers, TOC, etc.), so no build configuration change is needed.

**Source-number mode exclusion:** In auto-number mode, the paragraph map only contains entries for `<p>`, `<div>`, and `<blockquote>` elements (not `<li>`). In source-number mode, paragraph numbers are already visible as ordered list item numbers via `normalize_list_values()` → Pandoc `\setcounter{enumi}`. No margin numbers are injected for source-number documents.
