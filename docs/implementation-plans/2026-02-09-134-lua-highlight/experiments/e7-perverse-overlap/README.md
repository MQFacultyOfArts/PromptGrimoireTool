# E7: Perverse Overlapping Highlight Experiment

## Purpose

Exercises the FULL existing LaTeX annotation pipeline end-to-end with a pathologically
overlapping highlight scenario that crosses structural boundaries (heading into paragraph).

Pipeline stages tested:
1. `_insert_markers_into_html()` -- character-level marker insertion
2. Pandoc HTML-to-LaTeX conversion (markers survive as plain text)
3. `tokenize_markers()` -- Lark lexer extracts marker tokens
4. `build_regions()` -- state machine tracks active highlight sets
5. `_replace_markers_with_annots()` -> `walk_and_wrap()` -- AST-aware LaTeX wrapping
6. LuaLaTeX compilation with lua-ul (`\highLight`, `\underLine`)

## Test Case

```
Heading: "This is demo. With silly header."
Paragraph: "Foo bar the test text is going here but is very mixed up."
```

Four overlapping highlights:
- **hl0 (jurisdiction)**: chars 5-61 -- "is demo..." in heading through "going" in paragraph
- **hl1 (legal_issues)**: chars 19-71 -- "silly..." in heading through space after "but"
- **hl2 (ratio)**: chars 54-78 -- "is going..." through "very" in paragraph
- **hl3 (obiter)**: chars 68-70 -- just "but" in paragraph

This creates:
- Cross-heading/paragraph highlights (hl0, hl1 span from h1 into p)
- 2-way overlap (hl0 + hl1 in heading)
- 3-way overlap (hl0 + hl1 + hl2 in "is going")
- 3-way overlap with nested containment (hl1 + hl2 + hl3 on "but")
- Single highlight tail (hl2 alone on "is very")

## Results

### Compilation: SUCCESS

The PDF compiled without fatal errors. LuaLaTeX produced a 1-page PDF (17,196 bytes).

### Coloured Rectangles: 18

`mutool draw -F trace` found 18 `fill_path` operations with colour, confirming that
highlight backgrounds, underlines, and margin note boxes all rendered.

### Warnings

| Category | Count | Details |
|----------|-------|---------|
| Overfull hbox | 4 | Margin notes extending past right margin (94.15pt too wide) |
| hyperref Token warnings | 6 | `\highLight` and `\underLine` tokens inside `\section{}` PDF string |
| Fatal errors | 0 | None |

### Warnings — All Non-Issues in Production

1. **hyperref Token warnings (6)**: `\highLight`/`\underLine` inside `\section{...}` confuse
   hyperref's PDF bookmark generator. **Non-issue:** `\texorpdfstring{}` is already stripped
   by `_strip_texorpdfstring()` in the production pipeline. The Lua filter approach (recommended
   path forward) eliminates this entirely because Pandoc auto-wraps in `\texorpdfstring{}`
   before the Lua filter runs (proven in E2b).

2. **`\label{}` marker debris**: Pandoc generated
   `\label{this-hlstart0endhlis-demo.-with-hlstart1endhlsilly-header.}` because markers
   are in the heading text before Pandoc sees it. **Non-issue:** labels are unwanted in the
   production output and can be suppressed or stripped.

3. **Cross-paragraph boundary splitting**: Highlights spanning heading → paragraph are
   split at `\par` by `walk_and_wrap()`. **Working as designed.**

4. **Margin note overflow (4 overfull hbox)**: `\marginalia` notes exceeding right margin.
   **Cosmetic, expected** with this geometry when multiple annotations stack.

### Region Analysis

The pipeline correctly identified 9 regions:

| Region | Active Highlights | Text |
|--------|------------------|------|
| 0 | (none) | `\section{This ` |
| 1 | hl0 | `is demo. With ` |
| 2 | hl0, hl1 | `silly\nheader.}\label{...}` |
| 3 | hl0, hl1, hl2 | `is\ngoing` (3-way overlap, many-dark underline) |
| 4 | hl1, hl2 | ` here\n` |
| 5 | hl1, hl2, hl3 | `but` (3-way overlap with obiter) |
| 6 | hl1, hl2 | `\n` |
| 7 | hl2 | `is very` |
| 8 | (none) | `mixed up.\n` |

All 4 `\annot` margin notes were emitted at the correct region boundaries.

## Files

- `e7_perverse_test.py` -- Python script that runs the pipeline
- `e7_pipeline_output.txt` -- Full terminal output from the pipeline
- `e7_doc.tex` -- Complete LaTeX document with preamble
- `e7_doc.pdf` -- Compiled PDF output

## Visual Analysis (from PDF)

The rendered PDF confirms:

1. **Heading**: "is demo. With" has blue (jurisdiction) background. "silly header." has
   overlapping blue+orange (jurisdiction+legal_issues) with a stacked double underline.

2. **Paragraph body**:
   - "Foo bar the test text" -- blue+orange overlap (jurisdiction+legal_issues), stacked underlines
   - "is going" -- 3-way overlap (jurisdiction+legal_issues+ratio) with thick dark underline (many-dark)
   - Superscript "1" (jurisdiction annot) appears after "going"
   - "here" -- orange+green (legal_issues+ratio), stacked underlines
   - "but" -- 3-way overlap (legal_issues+ratio+obiter) with thick dark underline and pink tint
   - Superscripts "2" (obiter) and "3" (legal_issues) appear after "but"
   - "is very" -- green (ratio) alone with single underline
   - Superscript "4" (ratio) appears after "very"

3. **Margin notes**: All 4 annotations rendered in the right margin, properly numbered
   and colour-coded (1=Jurisdiction/blue, 2=Obiter/red, 3=Legal Issues/orange, 4=Ratio/green).
   Notes are stacked vertically via `marginalia` package.

4. **Underlines**: Single underlines visible for 1-highlight regions, stacked double underlines
   for 2-highlight regions, and thick dark underlines for 3+ highlight regions. All correct
   per the `generate_underline_wrapper()` logic.

## Conclusion

The existing pipeline handles perverse overlapping highlights **correctly**. The region
model (tokenize → build_regions → wrap) tracks arbitrary highlight overlap combinations
without error. All stacking tiers render as designed.

The warnings (hyperref, label debris) are artefacts of the marker-in-text approach and
are all non-issues: `\texorpdfstring` is already stripped in production, labels are
unwanted, and the recommended Lua filter approach eliminates both entirely.