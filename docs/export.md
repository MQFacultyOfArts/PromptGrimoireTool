# PDF Export / LaTeX

*Last updated: 2026-02-15*

PDF export uses TinyTeX for portable, consistent LaTeX compilation.

## Setup

```bash
# Install TinyTeX and required packages
uv run python scripts/setup_latex.py
```

This installs TinyTeX to `~/.TinyTeX` and the required packages:
- `lua-ul` - highlighting with LuaLaTeX
- `fontspec` - system font support
- `luacolor` - color support
- `todonotes` - margin notes
- `geometry` - page layout
- `marginalia` - auto-stacking margin notes (LuaLaTeX)
- `latexmk` - build automation

## Configuration

The `APP__LATEXMK_PATH` env var overrides the default TinyTeX path if needed. Leave empty to use TinyTeX.

## Architecture

- `src/promptgrimoire/export/pdf.py` - `get_latexmk_path()` resolves latexmk location, `compile_latex()` compiles .tex to PDF (async)
- `src/promptgrimoire/export/pdf_export.py` - `export_annotation_pdf()` full pipeline, `generate_tex_only()` for .tex without compilation (used by tests)
- `src/promptgrimoire/export/promptgrimoire-export.sty` - Static LaTeX preamble (packages, commands, environments, macros). Copied to output dir by `ensure_sty_in_dir()` before compilation
- `scripts/setup_latex.py` - installs TinyTeX and packages
- Does NOT fall back to system PATH - TinyTeX only for consistency

**Note:** `compile_latex()` is async and uses `asyncio.create_subprocess_exec()` for non-blocking compilation.

## LaTeX Rendering Utilities (`latex_render.py`)

Safe LaTeX string construction without f-string injection risks. Two patterns:

- `latex_cmd("definecolor", "mycolor", "HTML", "FF0000")` -- for simple `\name{arg1}{arg2}` commands. Arguments auto-escaped unless `NoEscape`.
- `render_latex(t"\\textbf{{{val}}}")` -- for complex templates using Python 3.14 t-strings. Interpolated values auto-escaped unless `NoEscape`.

Public API: `NoEscape`, `escape_latex`, `latex_cmd`, `render_latex`.

**Invariant:** No f-strings for LaTeX generation in the export module. A guard test (`tests/unit/export/test_no_fstring_latex.py`) enforces this.

## Dynamic Font Loading (`unicode_latex.py`)

Font loading is demand-driven based on document content:

1. `detect_scripts(body_text)` scans text for non-Latin Unicode scripts (Hebrew, Arabic, CJK, etc.)
2. `build_font_preamble(scripts)` emits only the `\directlua` fallback fonts needed for detected scripts
3. `build_annotation_preamble(tag_colours, body_text="")` orchestrates: loads `.sty`, generates font preamble, emits colour definitions

`FONT_REGISTRY` maps OpenType script tags to font names. `SCRIPT_TAG_RANGES` maps script tags to Unicode codepoint ranges. Latin fonts are always included.

## Highlight Pipeline (Pandoc + Lua Filter)

The annotation export uses a pre-Pandoc span injection + Lua filter pipeline (Issue #134) to handle arbitrarily nested and overlapping highlights:

1. **Region computation** - `compute_highlight_spans()` in `highlight_spans.py` computes non-overlapping regions from overlapping highlights using an event-sweep algorithm, then inserts `<span data-hl="..." data-colors="..." data-annots="...">` elements into clean HTML
2. **Block boundary splitting** - Boundary detection in `span_boundaries.py`. Spans are pre-split at block element boundaries (p, h1-h6, li, etc.) and inline formatting boundaries (b, em, code, etc.) because Pandoc silently destroys cross-boundary spans
3. **Pandoc conversion** - HTML to LaTeX with `highlight.lua` Lua filter included
4. **Lua filter rendering** - `highlight.lua` reads span attributes and emits nested `\highLight` / `\underLine` / `\annot` LaTeX commands using a "one, two, many" stacking model:
   - 1 highlight: single 1pt underline in tag's dark colour
   - 2 highlights: stacked 2pt outer + 1pt inner underlines
   - 3+ highlights: single 4pt underline in many-dark colour
5. **Post-processing** - `\annot` commands (which contain `\par`) are moved outside restricted LaTeX contexts (e.g. `\section{}` arguments)

Key files:
- `highlight_spans.py` - `compute_highlight_spans()`, `_HlRegion`, region computation + DOM insertion
- `latex_format.py` - `format_annot_latex()` annotation LaTeX formatting
- `span_boundaries.py` - `_detect_block_boundaries()`, `_detect_inline_boundaries()`, `PANDOC_BLOCK_ELEMENTS`
- `filters/highlight.lua` - Pandoc Lua filter for highlight/annotation rendering
- `pandoc.py` - `convert_html_with_annotations()` orchestrator, `convert_html_to_latex()` Pandoc subprocess
- `preamble.py` - `build_annotation_preamble()`, colour definitions
- `promptgrimoire-export.sty` - Static preamble: `\annot` macro, speaker environments, package loading

**Note:** Pandoc strips the `data-` prefix from HTML attributes in Lua filters (e.g. `data-hl` becomes `hl`).
