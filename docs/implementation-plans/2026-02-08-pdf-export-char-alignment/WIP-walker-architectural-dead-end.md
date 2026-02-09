# WIP: walk_and_wrap Full-AST Rewrite — Architectural Dead End

**Date:** 2026-02-09
**Branch:** milkdown-crdt-spike
**State:** Uncommitted changes in `latex.py` (the broken rewrite). Safe to `git checkout -- src/promptgrimoire/export/latex.py` to revert.

## What We Tried

Replaced the `tokenize → build_regions → per-region _wrap_region_ast` pipeline with a
full-AST approach:

1. `tokenize_markers()` (kept) — extract marker tokens from LaTeX
2. `build_highlight_map()` (new) — strip markers, build position→active-highlights interval map
3. Parse FULL stripped LaTeX with pylatexenc — all braces match
4. `_walk_full_ast()` — walk complete AST with position-aware wrapping

### What Worked

- 21/21 `test_walk_and_wrap.py` unit tests passed immediately
- Section arguments handled correctly (highlight inside `\section{...}` works)
- Boundary macros (`\setcounter`, `\tightlist`, `\item`) correctly excluded from wrapping
- Annot commands correctly placed outside restricted contexts
- PDF grew from 8KB (fatal error) to 40KB (partial success)

### What Broke: Escaped Braces

The fundamental issue: `\}` (escaped closing brace) inside text wrapped in `\highLight{...}`.

Example from the Lawlis fixture — pandoc produces:
```latex
\href{https://...}{Copyright \}& ...}
```

When the walker wraps this text at a structural boundary (`&`), it produces:
```latex
\highLight[colour]{\href{https://...}{Copyright \}}& ...
```

The `\}` consumes the closing brace of `\highLight`, producing "File ended while
scanning use of `\highLight`".

This is **unfixable at the string level**. Any approach that wraps LaTeX text in
`\highLight{...}` by string manipulation will break on escaped braces, because
the escaping is only meaningful to the TeX engine, not to a text parser.

## Why pylatexenc Is the Wrong Tool

pylatexenc (v2) is designed for **extracting text from LaTeX for indexing**, not for
**producing valid LaTeX**. From its own docs:

> "latexwalker was designed to extract useful text for indexing for text database
> searches of LaTeX content."

Key limitations:
- Doesn't understand all macro argument patterns (needed `MacroSpec` additions for `\href`, `\setcounter`, etc.)
- Tolerant parsing hides errors — malformed input produces a valid-looking AST that generates broken output
- No round-trip guarantee: parse → reconstruct ≠ original

The approach of "parse LaTeX in Python, walk AST, emit modified LaTeX" is fundamentally
fighting the tool's design.

## Two Alternative Approaches

### Option A: LuaLaTeX Package (compile-time node manipulation)

**Insight:** We already use LuaLaTeX. lua-ul (`\highLight`) already works at the
**node level** via Lua callbacks. Instead of string-wrapping text in Python, we
could handle highlighting entirely at compile time.

**How lua-ul works internally:**
1. `\highLight{text}` sets a **LuaTeX attribute** on the nodes within the group
2. Lua callback (`pre_append_to_vlist_filter`) scans the node list for attribute boundaries
3. At boundaries, it **injects `\leaders\vrule`** nodes to create the yellow background
4. No string manipulation — it works on the compiled node tree

**Proposed approach:**
1. Keep marker insertion in Python (HLSTART/HLEND in HTML → survive pandoc → appear in LaTeX as text)
2. Write a custom `.lua` file that registers a callback (e.g. `pre_linebreak_filter`)
3. The callback scans glyph nodes for marker text (HLSTART5ENDHL etc.)
4. When it finds a start marker: remove marker glyphs, begin setting highlight attribute on subsequent nodes
5. When it finds an end marker: remove marker glyphs, stop setting the attribute
6. lua-ul's existing callback picks up the attributes and applies the highlighting

**Advantages:**
- TeX engine handles all brace matching, macro expansion, escaped chars
- Markers are just text — they survive any LaTeX structure
- No Python LaTeX parsing at all
- Works with any macro, environment, or structure pandoc produces
- lua-ul already does the hard part (node-level highlight rendering)

**Risks:**
- Marker text spans multiple glyph nodes — need multi-glyph pattern matching
- Markers might get split across lines or hyphenated (unlikely but possible)
- Lua debugging is harder than Python debugging
- Need to handle `\annot` margin notes too (not just highlights)
- `\par` / blank line boundary rules still need enforcement at the Lua level

**Key resource:** lua-ul source at `~/.TinyTeX/texmf-dist/tex/lualatex/lua-ul/lua-ul.lua`
shows exactly how attribute-based node manipulation works (see `add_underline_hlist`).

### Option B: unified-latex (Node.js AST manipulation)

**Package:** `@unified-latex/unified-latex` on npm

**Insight:** The project already has Node.js dependencies (Milkdown editor, various
JS bundles in `static/`). unified-latex is a proper LaTeX parser/manipulator designed
for **round-trip AST transformation** — unlike pylatexenc which is text-extraction-only.

**Proposed approach:**
1. After pandoc produces LaTeX, pass it to a Node.js script using unified-latex
2. Parse into AST, find marker text nodes, inject `\highLight` wrapper nodes at the AST level
3. Serialize back to LaTeX string
4. The AST handles brace escaping correctly because it's designed for round-trip

**Advantages:**
- Proper round-trip LaTeX AST (unlike pylatexenc)
- AST-level injection means escaped braces are handled correctly
- Active project with good documentation
- Runs in the same Node.js environment we already have

**Risks:**
- Adds a Node.js subprocess to the export pipeline (currently pure Python + pandoc + latexmk)
- Another dependency to maintain
- Need to verify it handles all pandoc output correctly
- Cross-language boundary (Python → Node.js → back) adds complexity

## Recommendation

**Option A (LuaLaTeX package) is architecturally cleaner:**
- Zero new dependencies (LuaLaTeX is already the compiler)
- No cross-language boundary
- Works at the correct abstraction level (compiled nodes, not source strings)
- lua-ul proves this approach works for highlighting

**Option B (unified-latex) is lower risk:**
- AST manipulation in JavaScript is more familiar/debuggable than Lua callbacks
- Round-trip parsing is a solved problem in this library
- Doesn't require understanding LuaTeX internals

Both are better than pylatexenc string manipulation.

## Current State of walk_and_wrap

The committed version (at `fde4b68`) has the **old** per-region approach:
- `tokenize_markers` → `build_regions` → per-region `_wrap_region_ast`
- Plus `_move_annots_outside_restricted` safety net

The uncommitted changes have the **broken** full-AST rewrite:
- `build_highlight_map` → full parse → `_walk_full_ast`
- 21/21 unit tests pass but PDF compilation fails on escaped braces

**Action:** Revert uncommitted changes (`git checkout -- src/promptgrimoire/export/latex.py`).
The old pipeline works for most cases; only the 2 cross-heading highlights (hl5, hl9) fail.

## What Still Works (12 known failures, pre-existing)

- **2 highlight boundary drift failures** (hl5, hl9) — cross-heading highlights
- **10 tofu failures** — fixed in `fde4b68` (font fallback for `\href` context), need retest

The 10 tofu failures may already be fixed by commit `fde4b68`. The 2 highlight failures
need one of the alternative approaches above.

## Files from This Session

New functions written (in uncommitted latex.py, for reference if needed):
- `build_highlight_map()` — strips markers, builds position→highlight interval map
- `_active_at()` — looks up active highlights at a position
- `_collect_split_positions()` — collects structural boundary positions in text
- `_emit_text_with_highlights()` — wraps text segments with highlight commands
- `_walk_full_ast()` — recursive AST walker
- `_emit_section_macro()`, `_emit_inline_macro()`, `_emit_environment()` — node handlers
- `_BOUNDARY_MACRO_NAMES` — frozenset of macros that must not be wrapped

These could be adapted for a future approach but the core architecture is wrong.
