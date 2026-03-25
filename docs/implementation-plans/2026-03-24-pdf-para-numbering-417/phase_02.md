# PDF Paragraph Numbering — Phase 2: LaTeX Paragraph Number Rendering

**Goal:** Convert paragraph number markers into visible left-margin numbers in the PDF.

**Architecture:** `\paranumber{N}` LaTeX command defined in `promptgrimoire-export.sty` uses `\llap` for margin placement. `highlight.lua` Span callback gains a `paranumber` attribute check before the `hl` nil-guard, emitting `\paranumber{N}` as `RawInline`.

**Tech Stack:** LaTeX (`\llap`, `\textcolor`, `\textsf`), Lua (Pandoc filter)

**Scope:** Phase 2 of 5 from original design

**Codebase verified:** 2026-03-24

---

## Acceptance Criteria Coverage

This phase implements and tests:

### pdf-para-numbering-417.AC1: Left-margin paragraph numbers
- **pdf-para-numbering-417.AC1.1 Success:** HTML passed to Pandoc contains `<span data-paranumber="N">` at the start of each auto-numbered paragraph
- **pdf-para-numbering-417.AC1.4 Success:** LaTeX output contains `\paranumber{N}` matching the paragraph map
- **pdf-para-numbering-417.AC1.5 Success:** Paragraph numbers render in the PDF left margin as small grey sans-serif text

---

## UAT Steps

1. Start the app: `uv run run.py`
2. Navigate to a workspace with auto-numbering enabled (paragraph numbers visible in left margin)
3. Click Export PDF and wait for the download link
4. Download and open the PDF
5. Verify: small grey numbers appear in the left margin next to each paragraph, matching the on-screen numbers
6. Verify: body text is not shifted or indented by the margin numbers

## Evidence Required
- [ ] Generated `.tex` file contains `\paranumber{N}` commands
- [ ] Compiled PDF shows grey margin numbers (visual inspection)
- [ ] Test output from `uv run grimoire test smoke` showing green

---

## Reference Files for Subagents

- **LaTeX style file:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/src/promptgrimoire/export/promptgrimoire-export.sty` (212 lines)
- **Lua filter:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/src/promptgrimoire/export/filters/highlight.lua` (453 lines)
- **Integration test pattern:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/tests/integration/test_pdf_export.py` (lines 173-268 use `generate_tex_only()`)
- **Smoke test decorators:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/tests/conftest.py` (`requires_pandoc`, `requires_latexmk`)
- **Testing guidelines:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/docs/testing.md`
- **Project conventions:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/CLAUDE.md`

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Add `\paranumber` command to `promptgrimoire-export.sty`

**Verifies:** pdf-para-numbering-417.AC1.5

**Files:**
- Modify: `src/promptgrimoire/export/promptgrimoire-export.sty:202-203` (add command between `\annotendnote` definition and font setup section)

**Implementation:**

Add the following after line 202 (after `\annotendnote` closing brace) and before line 204 (the font setup section comment):

```latex
% =============================================================================
% Paragraph numbering (left-margin display for auto-numbered paragraphs)
% =============================================================================

% \paranumber{N} — places a small grey paragraph number in the left margin.
% Uses \llap to move the number left of the current position without consuming
% horizontal space.  \leavevmode ensures we are in horizontal mode (required
% at paragraph start before \llap).
\newcommand{\paranumber}[1]{%
  \leavevmode\llap{\textcolor{gray}{\scriptsize\textsf{#1}\quad}}%
}
```

**Key details:**
- `\leavevmode` — enters horizontal mode (required before `\llap` at paragraph start, no-op if already in horizontal mode)
- `\llap{...}` — typesets content to the left of current position without consuming width
- `\textcolor{gray}{...}` — uses `xcolor` package (already loaded at line 8)
- `\scriptsize` — small size to avoid visual dominance
- `\textsf{#1}` — sans-serif for contrast against body serif text
- `\quad` — spacing between number and body text

**Verification:**

Run: `uv run grimoire test changed`
Expected: No test failures (this is a LaTeX definition, not tested in isolation)

**Commit:** `feat(export): add \paranumber LaTeX command for margin numbers (#417)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Handle `paranumber` attribute in `highlight.lua` Span callback

**Verifies:** pdf-para-numbering-417.AC1.4

**Files:**
- Modify: `src/promptgrimoire/export/filters/highlight.lua:103-108` (add paranumber check before hl nil-guard)

**Implementation:**

At line 103 (after `if FORMAT ~= "latex" then return el end` and before the `hl` nil-guard comment), insert:

```lua
  -- Paragraph number marker: emit \paranumber{N} and return.
  -- Must be checked BEFORE the hl nil-guard because paranumber spans
  -- have no hl attribute and would otherwise be returned unchanged.
  local paranumber = el.attributes["paranumber"]
  if paranumber ~= nil and paranumber ~= "" then
    return pandoc.RawInline("latex", "\\paranumber{" .. paranumber .. "}")
  end
```

This goes between line 102 (`if FORMAT ~= "latex" then return el end`) and line 104 (the current `-- Guard: no hl attribute means pass through unchanged` comment).

**Key details:**
- The paranumber span is empty (`<span data-paranumber="N"></span>`), so we return a single `RawInline` — no need to preserve `el.content`.
- Pandoc strips the `data-` prefix from HTML attributes, so `data-paranumber` becomes `paranumber` in the Lua filter.
- The `return` ensures the paranumber span doesn't fall through to highlight processing.
- This check must go before the `hl` nil-guard (line 105-108) because paranumber spans have no `hl` attribute.

**Verification:**

Run: `uv run grimoire test changed`
Expected: No test failures

**Commit:** `feat(export): handle paranumber attribute in Lua Span filter (#417)`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Integration tests for `\paranumber` in LaTeX output

**Verifies:** pdf-para-numbering-417.AC1.1, pdf-para-numbering-417.AC1.4, pdf-para-numbering-417.AC1.5

**Files:**
- Create: `tests/unit/export/test_paranumber_latex.py` (smoke — `@requires_pandoc`)

**Note on test placement:** This file lives in `tests/unit/export/` but uses `@requires_pandoc` which auto-applies the `smoke` marker. These tests are excluded from the unit lane (`grimoire test all`) and only collected by `grimoire test smoke`. This matches the existing pattern in `tests/unit/export/test_markdown_to_latex.py` and `test_css_fidelity.py`.

**Testing:**

These tests require Pandoc to run the Lua filter, so use `@requires_pandoc` decorator (auto-applies `smoke` marker). Follow the pattern in `tests/integration/test_pdf_export.py` lines 173-268 — call `generate_tex_only()` or `convert_html_with_annotations()` and assert on `.tex` content.

Tests must verify each AC listed above:

- **pdf-para-numbering-417.AC1.4:** Given HTML with `<span data-paranumber="1"></span><span data-paranumber="2"></span>` markers (as produced by Phase 1), the LaTeX output from `convert_html_with_annotations()` contains `\paranumber{1}` and `\paranumber{2}` at the correct positions.
- **pdf-para-numbering-417.AC1.1 (end-to-end):** Given HTML with multiple paragraphs and a valid `word_to_legal_para` map, calling `convert_html_with_annotations()` produces LaTeX with `\paranumber{N}` for each numbered paragraph (tests the full Phase 1 + Phase 2 pipeline).
- **pdf-para-numbering-417.AC1.5 (smoke/compilation):** Using `@requires_latexmk`, compile a document with `\paranumber` commands and verify PDF compilation succeeds without errors. This confirms the `.sty` command works with the LaTeX toolchain. (This is a compilation-success test, not a visual assertion.)

Additional cases:
- HTML with no paranumber spans: LaTeX output contains no `\paranumber` commands
- HTML with paranumber spans AND highlight spans: both `\paranumber{N}` and highlight LaTeX (`\underLine`, `\annot`) appear correctly

**Verification:**

Run: `uv run grimoire test smoke`
Expected: New tests collected in smoke lane, all pass

**Commit:** `test(export): add integration tests for paranumber LaTeX rendering (#417)`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
