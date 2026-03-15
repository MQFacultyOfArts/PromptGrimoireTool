# Fix: \annot in longtable cells crashes LuaTeX with CJK fonts

**GitHub Issue:** [#351](https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/351)

## Summary

PromptGrimoire exports annotated workspaces to PDF via a LaTeX pipeline. Annotations — coloured highlights with attached comments — are represented in LaTeX as `\annot` macro calls. This macro uses `\par` (a paragraph break command) internally, which is safe in normal document flow but illegal inside table cells in LuaTeX. When a workspace contains both CJK text (which loads `luatexja-fontspec`) and annotations inside table cells, the interaction between `luatexja`'s line-breaking callbacks and LuaTeX's paragraph builder causes the engine to hang indefinitely — in the reported case, 39 minutes consuming 1.25 GB of RAM with no output.

The fix splits `\annot` into two safe macros: `\annotref` (superscript reference number, table-safe) and `\annotendnote` (annotation content written to endnotes after the table closes). A Lua filter intercepts table content during the Pandoc transformation pass, replaces each `\annot` with `\annotref` inline, and defers the corresponding `\annotendnote` to after the table. A secondary fix addresses table column overflow: tables without explicit HTML widths are now measured and converted to proportional `p{}` columns that wrap correctly.

## Definition of Done

1. PDF export completes successfully for documents with CJK text and annotated table content
2. Annotation superscript numbers appear inline in table cells; annotation content appears in the Long Annotations endnotes section
3. Longtable columns without explicit HTML widths use content-aware `p{}` columns instead of `l` columns, preventing text overflow
4. A compilation timeout guard test prevents regression (CJK + annotated tables must compile within a reasonable bound)
5. The rehydrated workspace `ead417b9` exports without crash

## Acceptance Criteria

### annot-in-tables-cjk-crash-351.AC1: CJK + annotated table export completes
- **annot-in-tables-cjk-crash-351.AC1.1 Success:** Workspace with CJK text and annotated table content produces a valid PDF
- **annot-in-tables-cjk-crash-351.AC1.2 Success:** Compilation completes within 30 seconds (was 39 minutes)
- **annot-in-tables-cjk-crash-351.AC1.3 Success:** Non-CJK documents with annotated tables continue to compile correctly
- **annot-in-tables-cjk-crash-351.AC1.4 Edge:** Documents with no annotations in tables are unaffected

### annot-in-tables-cjk-crash-351.AC2: Annotation rendering in tables
- **annot-in-tables-cjk-crash-351.AC2.1 Success:** Superscript annotation numbers appear inline next to highlighted text in table cells
- **annot-in-tables-cjk-crash-351.AC2.2 Success:** Annotation content appears in the "Long Annotations" endnotes section
- **annot-in-tables-cjk-crash-351.AC2.3 Success:** Annotation numbering is sequential across both table and non-table annotations
- **annot-in-tables-cjk-crash-351.AC2.4 Edge:** Multiple annotations in the same table cell each get their own superscript number

### annot-in-tables-cjk-crash-351.AC3: Table column wrapping
- **annot-in-tables-cjk-crash-351.AC3.1 Success:** Tables without HTML width attributes render with wrapping `p{}` columns
- **annot-in-tables-cjk-crash-351.AC3.2 Success:** Column widths are proportional to content length
- **annot-in-tables-cjk-crash-351.AC3.3 Success:** Tables with explicit HTML width attributes are unaffected
- **annot-in-tables-cjk-crash-351.AC3.4 Success:** Table header rows render for width-less tables

### annot-in-tables-cjk-crash-351.AC4: Regression guards
- **annot-in-tables-cjk-crash-351.AC4.1 Success:** Generated `.tex` contains no `\annot{` inside `\begin{longtable}...\end{longtable}` (unit test)
- **annot-in-tables-cjk-crash-351.AC4.2 Guard:** E2E test exports PDF from the rehydrated CJK workspace via the UI and asserts download completes (normal E2E, uses `generate_tex_only` short-circuit)
- **annot-in-tables-cjk-crash-351.AC4.3 Guard (slow):** Full compilation test — `generate_tex_only` + `compile_latex()` on the CJK workspace fixture, asserts completion within 30 seconds and non-empty PDF. Marked `@pytest.mark.slow`, runs in BLNS+Slow lane.

### annot-in-tables-cjk-crash-351.AC5: Rehydrated workspace
- **annot-in-tables-cjk-crash-351.AC5.1 Success:** Workspace `ead417b9` exports a valid, non-empty PDF via the pipeline

## Glossary

- **`\annot`**: Custom LaTeX macro in `promptgrimoire-export.sty` that renders annotation highlight + margin note. Contains `\par` internally, making it unsafe inside table cells.
- **`\annotref`**: New macro (this fix). Emits only the superscript annotation number; no `\par`, table-safe.
- **`\annotendnote`**: New macro (this fix). Writes annotation content to endnotes file using `\unexpanded`. Emitted after `\end{longtable}`.
- **`\par`**: LaTeX paragraph-break primitive. Illegal inside horizontal-mode contexts like table cells; triggers the LuaTeX hang.
- **luatexja / luatexja-fontspec**: LaTeX package for CJK typesetting in LuaTeX. Registers `hpack_filter` and `post_linebreak_filter` callbacks that interact pathologically with `\par` inside table cells.
- **longtable**: LaTeX package for multi-page tables. `l` columns don't wrap; `p{width}` columns do.
- **Lua filter**: Lua script run by Pandoc during conversion. `highlight.lua` transforms highlight spans into LaTeX commands; `libreoffice.lua` handles table column widths and speaker turn environments.
- **`_move_annots_outside_restricted()`**: Existing Python function in `pandoc.py` that moves `\annot` out of brace-restricted contexts. Does not handle table cell boundaries — that gap is addressed by the Lua filter `Table` callback.
- **BLNS+Slow lane**: Dedicated test lane for `@pytest.mark.slow` tests. Runs serially. The full LuaTeX compilation test belongs here.

## Architecture

### Root Cause

The `\annot` LaTeX macro (defined in `promptgrimoire-export.sty`) contains `\par` via `\marginalia` and `\parbox`. When emitted inside longtable `l`-column cells AND `luatexja-fontspec` is loaded (CJK documents), the `\par` triggers pathological interaction between `luatexja`'s `hpack_filter`/`post_linebreak_filter` callbacks and LuaTeX's paragraph builder. Result: 39-minute hang, 1.25GB RAM, no PDF output.

The existing `_move_annots_outside_restricted()` in `pandoc.py` moves `\annot` out of brace-depth restrictions (`\textbf{}`, `\section{}`), but does not detect table cell boundaries (`&` / `\\` in LaTeX).

### Fix Approach

Split `\annot` into two new macros when inside table context:

- **`\annotref{colour}`** — emits only `\stepcounter{annotnum}\textsuperscript{...}`. Safe in table cells (no `\par`).
- **`\annotendnote{colour}{num}{content}`** — writes annotation content to the endnotes file using `\unexpanded` for safe `\par` handling. Emitted after `\end{longtable}` where `\par` is allowed.

The Lua filter (`highlight.lua`) gains a `Table` callback that walks already-transformed table content, finds `\annot` RawInlines, replaces each with `\annotref` inline, and collects `\annotendnote` commands for emission after the table.

### Secondary Fix: Table Column Overflow

Pandoc generates `@{}llll@{}` (non-wrapping `l` columns) for tables without explicit HTML width attributes. The `libreoffice.lua` `Table` callback previously returned early for these tables. Now it measures maximum content length per column across all rows and generates proportional `p{}` columns. Tables are also wrapped in `\small` for better fit in the narrow text column (A4 with 6cm annotation margin).

## Existing Patterns

### Annotation mobility (already implemented)

`_move_annots_outside_restricted()` in `pandoc.py:179-246` already moves `\annot` out of brace-restricted contexts. The `Header` callback in `highlight.lua:176-187` does the same for headings using `extract_annots()`. This design extends the same pattern to table context.

### Endnote mechanism (already implemented)

`\annot` in `promptgrimoire-export.sty:150-181` already has a long-annotation path: annotations exceeding `\annotmaxht` are written to `\jobname.endnotes` via `\immediate\write` with `\unexpanded`. The new `\annotendnote` macro reuses this mechanism.

### Content-aware table rendering (extending existing)

`libreoffice.lua:92-162` already generates custom longtable LaTeX for tables with HTML width attributes. The content-aware column width calculation extends this to tables without widths.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: LaTeX Macros and Lua Filter Table Callback

**Goal:** Move `\annot` out of table cells in the Lua filter, keeping superscript references inline.

**Components:**
- `src/promptgrimoire/export/promptgrimoire-export.sty` — add `\annotref` and `\annotendnote` macros
- `src/promptgrimoire/export/filters/highlight.lua` — add `Table` callback with `_find_matching_brace_str` helper, `table_safe_rawinline` handler, and deferred annot collection

**Dependencies:** None

**Done when:** The CJK workspace (`ead417b9`) generates a `.tex` file with no `\annot` inside longtable environments, superscript `\annotref` commands appear in table cells, and `\annotendnote` commands appear after each table. Compilation completes in <30 seconds.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Content-Aware Table Column Widths

**Goal:** Prevent table text overflow by generating wrapping `p{}` columns when no HTML widths are specified.

**Components:**
- `src/promptgrimoire/export/filters/libreoffice.lua` — replace early return for width-less tables with content-length measurement and proportional `p{}` column generation. Add header row rendering. Wrap tables in `\small`.

**Dependencies:** Phase 1 (table rendering changes should be tested together)

**Done when:** Tables without HTML width attributes render with wrapping columns. The 183-austlii fixture table renders without overflow. Existing tables with explicit widths are unaffected.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Test Fixtures and Regression Tests

**Goal:** Add test fixtures and regression guards across unit, integration, and slow test lanes.

**Components:**
- Test fixture: minimal HTML with CJK + table + highlights (derived from workspace `ead417b9`), plus workspace JSON for full-pipeline tests
- Unit test (`tests/unit/export/`): generated `.tex` contains `\annotref` in longtable cells, `\annotendnote` after tables, no `\annot{` inside longtable (AC4.1)
- Unit test (`tests/unit/export/`): content-aware `p{}` columns generated for width-less tables, header rows present (AC3.1, AC3.2, AC3.4)
- Integration test (`tests/integration/`): full `generate_tex_only` pipeline with CJK workspace fixture produces valid TeX without `\annot` in tables (AC2.1-AC2.3)
- Slow test (`@pytest.mark.slow`, BLNS+Slow lane): `generate_tex_only` + `compile_latex()` on CJK fixture, asserts completion within 30s and non-empty PDF (AC1.1, AC1.2, AC4.3, AC5.1)
- E2E test (`tests/e2e/`): export PDF from rehydrated CJK workspace via UI, assert download completes (AC4.2). Uses `set_latexmk_short_circuit` to avoid actual compilation in normal E2E runs.

**Dependencies:** Phases 1-2

**Done when:** All tests pass across all lanes. A future change that re-introduces `\annot` inside longtable cells fails the unit guard test.
<!-- END_PHASE_3 -->

## Additional Considerations

**Scope:** This fix only changes rendering for `\annot` inside tables. `\highLight` and `\underLine` (lua-ul) work correctly in tables even with CJK — they are not modified.

**Non-CJK documents:** `\annot` in tables without CJK fonts compiles correctly (tested: 1.7s, zero errors). The Lua filter `Table` callback applies unconditionally — this is safe because moving annotations to endnotes is valid regardless of CJK, and avoids conditional logic that could miss edge cases.

**Concurrent export protection:** The server crash was exacerbated by 5 concurrent LuaTeX processes. Export mutex/rate limiting is a separate concern (not in scope for this fix).

**Batch export CLI:** Filed as [#350](https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/350) for proactive smoke-testing of all workspaces.
