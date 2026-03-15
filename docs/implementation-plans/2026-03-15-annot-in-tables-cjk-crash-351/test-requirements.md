# Test Requirements: annot-in-tables-cjk-crash-351

Maps each acceptance criterion to automated tests or documented human verification.

---

## AC1: CJK + annotated table export completes

| AC | Description | Test Type | Test File | What the Test Verifies |
|----|-------------|-----------|-----------|------------------------|
| AC1.1 | Workspace with CJK text and annotated table content produces a valid PDF | smoke (slow) | `tests/integration/test_cjk_annotated_table_export.py` | `generate_tex_only()` + `compile_latex()` on Yuki workspace fixture produces a non-empty PDF file (>0 bytes). Marked `@requires_full_latexmk` + `@pytest.mark.slow`, runs in BLNS+Slow and smoke lanes. |
| AC1.2 | Compilation completes within 30 seconds (was 39 minutes) | smoke (slow) | `tests/integration/test_cjk_annotated_table_export.py` | Same test as AC1.1. Wraps `generate_tex_only()` + `compile_latex()` in `time.monotonic()` and asserts total elapsed < 30s. |
| AC1.3 | Non-CJK documents with annotated tables continue to compile correctly | integration | `tests/integration/test_cjk_annotated_table_export.py` | `generate_tex_only()` pipeline with minimal HTML fixture (non-CJK variant or the CJK fixture which exercises the same code path) generates `.tex` successfully without crash or timeout. |
| AC1.4 | Documents with no annotations in tables are unaffected | integration | `tests/integration/test_highlight_lua_filter.py` | Table with NO annotations passes through unchanged -- output contains `\begin{longtable}` with no `\annotref` or `\annotendnote`. Confirms the `Table` callback returns early when `#deferred == 0`. |

## AC2: Annotation rendering in tables

| AC | Description | Test Type | Test File | What the Test Verifies |
|----|-------------|-----------|-----------|------------------------|
| AC2.1 | Superscript annotation numbers appear inline next to highlighted text in table cells | integration | `tests/integration/test_highlight_lua_filter.py` | Table with one annotated cell -- assert `\annotref{` appears inside the longtable environment (between `\begin{longtable}` and `\end{longtable}`). |
| AC2.1 (pipeline) | Same criterion verified through full pipeline | integration | `tests/integration/test_cjk_annotated_table_export.py` | `generate_tex_only()` output contains `\annotref{` in the generated `.tex` content. |
| AC2.2 | Annotation content appears in the "Long Annotations" endnotes section | integration | `tests/integration/test_highlight_lua_filter.py` | Same test as AC2.1 -- assert `\annotendnote{` appears AFTER `\end{longtable}` in the Pandoc output. |
| AC2.2 (pipeline) | Same criterion verified through full pipeline | integration | `tests/integration/test_cjk_annotated_table_export.py` | `generate_tex_only()` output contains `\annotendnote{` in the generated `.tex` content. |
| AC2.3 | Annotation numbering is sequential across both table and non-table annotations | unit (smoke) | `tests/unit/export/test_annot_in_tables.py` | Mixed document: annotation before table, annotation in table, annotation after table. Parses `.tex` output for `\annot`, `\annotref`, `\annotendnote` commands and verifies counter values are sequential (1, 2, 3) with no gaps or resets. Marked `@requires_pandoc`. |
| AC2.4 | Multiple annotations in the same table cell each get their own superscript number | unit (smoke) | `tests/unit/export/test_annot_in_tables.py` | Table with 2 annotated cells -- asserts 2 `\annotref{` inside the table and 2 `\annotendnote{` after it, with matching sequential numbers. Marked `@requires_pandoc`. |

## AC3: Table column wrapping

| AC | Description | Test Type | Test File | What the Test Verifies |
|----|-------------|-----------|-----------|------------------------|
| AC3.1 | Tables without HTML width attributes render with wrapping `p{}` columns | unit | `tests/unit/export/test_css_fidelity.py` | `convert_html_to_latex()` with a width-less table -- assert longtable column spec contains `p{` (not `l` columns). Uses `libreoffice.lua` filter. |
| AC3.2 | Column widths are proportional to content length | unit | `tests/unit/export/test_css_fidelity.py` | Same test as AC3.1 -- parse `p{X.XX\textwidth}` values from output and verify the column with longer content gets a larger proportion. |
| AC3.3 | Tables with explicit HTML width attributes are unaffected | unit | `tests/unit/export/test_css_fidelity.py` | Table WITH HTML width attributes -- assert output matches existing behaviour (existing tests already cover this; add one explicit regression test confirming no interference from the new code path). |
| AC3.4 | Table header rows render for width-less tables | unit | `tests/unit/export/test_css_fidelity.py` | Table with `<thead>` and `<tbody>` -- assert output contains `\toprule`, `\midrule`, `\endhead`. Also verify `\begingroup\small` and `\endgroup` wrap the table. |

## AC4: Regression guards

| AC | Description | Test Type | Test File | What the Test Verifies |
|----|-------------|-----------|-----------|------------------------|
| AC4.1 | Generated `.tex` contains no `\annot{` inside `\begin{longtable}...\end{longtable}` | unit (smoke) | `tests/unit/export/test_annot_in_tables.py` | `convert_html_to_latex()` with both `highlight.lua` and `libreoffice.lua` filters on HTML containing a table with annotations. Extracts all `\begin{longtable}...\end{longtable}` regions and asserts none contain `\annot{`. Only `\annotref{` is allowed. Marked `@requires_pandoc`. |
| AC4.2 | E2E test exports PDF from the rehydrated CJK workspace via the UI and asserts download completes | e2e | `tests/e2e/test_cjk_export.py` | Seeds a workspace with CJK + annotated table content via `db_fixtures.py`. Navigates to annotation page, clicks export PDF, asserts download completes using `export_annotation_tex_text()` helper. Verifies downloaded `.tex` content contains `\annotref{`. Uses `E2E_SKIP_LATEXMK=1` short-circuit (no actual compilation). |
| AC4.3 | Full compilation test -- `generate_tex_only` + `compile_latex()` on the CJK workspace fixture, asserts completion within 30 seconds and non-empty PDF | smoke (slow) | `tests/integration/test_cjk_annotated_table_export.py` | Same test as AC1.1/AC1.2. Decorated with `@requires_full_latexmk` + `@pytest.mark.slow`. Runs in BLNS+Slow lane (after Task 1 lane filter fix) and smoke lane. Module-scoped fixture compiles once, multiple assertions check PDF existence, size, and timing. |

## AC5: Rehydrated workspace

| AC | Description | Test Type | Test File | What the Test Verifies |
|----|-------------|-----------|-----------|------------------------|
| AC5.1 | Workspace `ead417b9` exports a valid, non-empty PDF via the pipeline | smoke (slow) | `tests/integration/test_cjk_annotated_table_export.py` | Loads Yuki workspace JSON fixture (`workspace_cjk_yuki.json`), rehydrates workspace data, runs `generate_tex_only()` + `compile_latex()`, asserts PDF exists and is non-empty. This is the same test as AC1.1/AC4.3 -- the Yuki fixture IS workspace `ead417b9`. |

---

## Summary by Test Lane

| Lane | Test Files | ACs Covered |
|------|-----------|-------------|
| Unit (xdist) | `tests/unit/export/test_css_fidelity.py` | AC3.1, AC3.2, AC3.3, AC3.4 |
| Smoke (serial, `@requires_pandoc`) | `tests/unit/export/test_annot_in_tables.py` | AC2.3, AC2.4, AC4.1 |
| Integration (xdist) | `tests/integration/test_highlight_lua_filter.py` | AC1.4, AC2.1, AC2.2 |
| Smoke (serial, `@requires_pandoc`) | `tests/integration/test_cjk_annotated_table_export.py` (`TestCjkAnnotatedTablePipeline`) | AC1.3, AC2.1 (pipeline), AC2.2 (pipeline) |
| BLNS+Slow (serial) | `tests/integration/test_cjk_annotated_table_export.py` (`@pytest.mark.slow`) | AC1.1, AC1.2, AC4.3, AC5.1 |
| Smoke (serial) | `tests/integration/test_cjk_annotated_table_export.py` (`@requires_full_latexmk`) | AC1.1, AC1.2, AC4.3, AC5.1 |
| E2E (Playwright) | `tests/e2e/test_cjk_export.py` | AC4.2 |

## Human Verification Not Required

All acceptance criteria map to automated tests. No manual verification entries are needed -- every AC is covered by at least one automated test across the unit, integration, smoke, slow, or E2E lanes.
