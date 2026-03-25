# PDF Paragraph Numbering — Phase 4: Verification and Edge Cases

**Goal:** Verify para_ref in endnotes, test edge cases, and confirm no layout regressions.

**Architecture:** Test-only phase. No new production code. Verifies Phases 1-3 work correctly together and handles boundary conditions.

**Tech Stack:** pytest, `@requires_pandoc`, `@requires_latexmk`

**Scope:** Phase 4 of 5 from original design

**Codebase verified:** 2026-03-24

---

## Acceptance Criteria Coverage

This phase implements and tests:

### pdf-para-numbering-417.AC3: No layout changes
- **pdf-para-numbering-417.AC3.1 Success:** Existing export tests pass without modification
- **pdf-para-numbering-417.AC3.2 Success:** `format_annot_latex()` output with `para_ref` survives endnote `\write` path (para refs visible in endnotes)

---

## Reference Files for Subagents

- **format_annot_latex():** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/src/promptgrimoire/export/latex_format.py` (lines 19-98)
- **Existing para_ref tests:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/tests/unit/export/test_latex_string_functions.py` (lines 194-203, 343-352)
- **Existing span tests:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/tests/unit/export/test_highlight_spans.py` (lines 310-323)
- **Integration test pattern:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/tests/integration/test_pdf_export.py`
- **Paragraph marker function (Phase 1):** `src/promptgrimoire/input_pipeline/paragraph_map.py` (new function `inject_paragraph_markers_for_export()`)
- **Testing guidelines:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/docs/testing.md`
- **Project conventions:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/CLAUDE.md`

---

<!-- START_TASK_1 -->
### Task 1: Regression check — existing export tests pass

**Verifies:** pdf-para-numbering-417.AC3.1

**Files:** None (no modifications)

**Implementation:** No code changes. Run the existing test suites to confirm Phases 1-3 introduced no regressions.

**Verification:**

Run: `uv run grimoire test all`
Expected: All existing tests pass without modification

Run: `uv run grimoire test smoke`
Expected: All existing smoke tests pass without modification

**Commit:** No commit (verification only)
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Edge case and verification tests

**Verifies:** pdf-para-numbering-417.AC3.2

**Files:**
- Create: `tests/unit/export/test_paragraph_numbering_edge_cases.py` (unit + smoke)

**Testing:**

This file contains both pure unit tests and `@requires_pandoc` smoke tests. Follow patterns from `test_highlight_spans.py` (helpers, no database) and `test_pdf_export.py` (generate_tex_only pattern).

Tests must verify each AC listed above:

- **pdf-para-numbering-417.AC3.2 (para_ref in endnote write path):** Using `@requires_pandoc`, call `convert_html_with_annotations()` (or `generate_tex_only()`) with highlights that include `para_ref` values and are long enough to trigger the endnote path. Verify the LaTeX output contains `\annot{...}{...` where the second argument includes the para_ref string (e.g., `[3]`). This confirms para_ref survives the `\unexpanded{#2}` write path.

Additional edge case tests (unit, no Pandoc required):

- **Empty paragraph map:** Call `inject_paragraph_markers_for_export(html, {})` — returns HTML unchanged.
- **Document with no annotations:** Call `compute_highlight_spans(html, [], {})` — returns HTML unchanged. Then call `inject_paragraph_markers_for_export()` — paranumber markers still injected (paragraph numbering is independent of annotations).
- **Only short annotations (no endnotes):** Using `@requires_pandoc`, export with only short annotations. LaTeX output should contain `\annot{` but NOT `\label{annot-endnote:` (short path has no cross-references, confirming AC2.4 from Phase 3).
- **Mixed short and long annotations:** Using `@requires_pandoc`, export with both short and long annotations. Verify long annotations have `\label`/`\hyperref` pairs while short annotations do not.
- **br-br pseudo-paragraph with paranumber:** Call `inject_paragraph_markers_for_export()` on HTML with `<br><br>` pseudo-paragraphs. Verify `<span data-paranumber="N"></span>` appears inside the `<span data-para="N">` wrapper.

**Verification:**

Run: `uv run grimoire test run tests/unit/export/test_paragraph_numbering_edge_cases.py`
Expected: All tests pass

Run: `uv run grimoire test smoke`
Expected: Pandoc-dependent tests collected in smoke lane, all pass

**Commit:** `test(export): add edge case and verification tests for paragraph numbering (#417)`
<!-- END_TASK_2 -->
