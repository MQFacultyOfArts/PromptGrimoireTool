# Dead End: \annot with \par inside longtable + luatexja

**Date:** 2026-03-15
**Issue:** [#351](https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/351)
**Design plan:** `docs/design-plans/2026-03-15-annot-in-tables-cjk-crash-351.md`

## Problem

PDF export hangs for 39+ minutes (1.25GB RAM, 100% CPU) when a document has CJK text AND annotations inside HTML tables. Five student retries caused OOM server crash.

## Root Cause

`\annot` macro contains `\par` (via `\marginalia` → `\parbox`). When `luatexja-fontspec` is loaded (CJK documents), `\par` inside longtable `l`-column cells triggers pathological interaction between `luatexja`'s `hpack_filter`/`post_linebreak_filter` callbacks and LuaTeX's paragraph builder. Without CJK, the same construct compiles in 1.7s with no errors.

**Innocent bystanders:** `\highLight` and `\underLine` (lua-ul) work correctly in tables with CJK. Only `\annot` is the problem.

## Isolation Evidence

| Condition | Time | Result |
|-----------|------|--------|
| Full (highlights + annots in tables + CJK) | 39 min | Hang |
| Highlights in tables, NO annot, CJK | 5.8s | Success |
| Annot in tables, NO highlights, CJK | >120s | Hang |
| Everything, NO CJK | 1.7s | Success |

## Approaches Tried (Dead Ends)

### 1. Move whole \annot after \end{longtable} (Python post-processor)

Stripped `\annot{...}{...}` from inside longtable and dumped after table end.

**Why it failed:** The `\annot` macro is monolithic — it contains both the superscript reference number AND the margin/endnote content. Moving the whole thing removes the superscript from the table cell. Numbers appear jammed together after the table with no visual connection to the highlighted text.

### 2. Raw \immediate\write in Lua filter

Tried to replicate the `.sty`'s endnote write mechanism directly in the Lua filter output, escaping `\par` with `\noexpand\par`.

**Why it failed:** `gsub("\\par", "\\noexpand\\par")` is too broad — matches `\parbox`, `\partial`, etc. Also `\immediate\write` expansion semantics are subtle; content with `\par` and other commands requires `\unexpanded{}` (an e-TeX primitive) which can't be easily replicated from string concatenation in Lua.

### 3. Equal-width p{} columns for width-less tables

Replaced `l` columns with equal-proportion `p{0.24\textwidth}` per column.

**Why it failed:** Column 1 (row numbers like "1", "2") gets the same width as column 4 (paragraph-length explanations). Massive visual waste. Content-aware proportional widths needed instead.

### 4. Strip CJK fonts to test (bad experiment design)

Commented out CJK font loading to test if highlights in tables work without CJK.

**Why it failed as a test:** Document still contains CJK characters — they can't render without the fonts, so the compilation fails for a different reason. Useless as an isolation test. Need a separate document without CJK content to test the non-CJK case.

## Working Solution

Split `\annot` into two new macros:

- `\annotref{colour}` — superscript only, table-safe (no `\par`)
- `\annotendnote{colour}{num}{content}` — endnote write using `\unexpanded`, emitted after table

Lua filter `Table` callback in `highlight.lua` walks already-transformed RawInlines, replaces `\annot` with `\annotref` inline, defers `\annotendnote` after table. Pandoc processes filters bottom-up (Span before Table), so the Table callback operates on RawInlines, not Spans.
