# PDF Paragraph Numbering — Phase 3: Endnote Cross-References

**Goal:** Add bidirectional hyperlinks between inline annotation superscripts and their endnote entries.

**Architecture:** Modify `\annot`, `\annotref`, and `\annotendnote` macros in `promptgrimoire-export.sty` to add `\phantomsection\label`/`\hyperref` pairs. Long-annotation (endnote) path gains bidirectional links. Short-annotation (margin) path unchanged. Counter values expand at `\write` time; label/hyperref commands deferred via `\noexpand`.

**Tech Stack:** LaTeX (`\hyperref`, `\label`, `\phantomsection`, `\noexpand`/`\write` expansion)

**Scope:** Phase 3 of 5 from original design

**Codebase verified:** 2026-03-24

---

## Acceptance Criteria Coverage

This phase implements and tests:

### pdf-para-numbering-417.AC2: Clickable endnote cross-references
- **pdf-para-numbering-417.AC2.1 Success:** Long annotations produce `\label{annot-inline:N}` at inline location and `\hyperref[annot-endnote:N]` wrapping superscript
- **pdf-para-numbering-417.AC2.2 Success:** Endnote entries contain `\label{annot-endnote:N}` and `\hyperref[annot-inline:N]` wrapping endnote number
- **pdf-para-numbering-417.AC2.3 Success:** Table-safe variants (`\annotref`/`\annotendnote`) produce matching label/hyperref pairs
- **pdf-para-numbering-417.AC2.4 Failure:** Short annotations (margin path) do NOT get hyperref linking

---

## UAT Steps

1. Start the app: `uv run run.py`
2. Navigate to a workspace with auto-numbering enabled and create a long annotation (long enough to trigger the endnote path — roughly 6+ lines of content)
3. Click Export PDF and wait for the download link
4. Download and open the PDF
5. Verify: the superscript annotation number in the body text is clickable — clicking it jumps to the corresponding endnote in the "Long Annotations" section
6. Verify: the annotation number in the endnote section is clickable — clicking it jumps back to the inline superscript in the body
7. Verify: short annotations (rendered in the margin) do NOT have clickable behaviour

## Evidence Required
- [ ] Generated `.tex` file contains `\label{annot-inline:N}` and `\hyperref[annot-endnote:N]` at inline locations
- [ ] Compiled PDF has working bidirectional links (visual inspection)
- [ ] Short annotations render unchanged (no clickable links)
- [ ] Test output from `uv run grimoire test smoke` showing green

---

## Reference Files for Subagents

- **LaTeX style file:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/src/promptgrimoire/export/promptgrimoire-export.sty` (212 lines, macros at 150-202)
- **Lua filter Table callback:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/src/promptgrimoire/export/filters/highlight.lua` (lines 276-399)
- **Integration test pattern:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/tests/integration/test_pdf_export.py`
- **Smoke test decorators:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/tests/conftest.py`
- **Testing guidelines:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/docs/testing.md`
- **Project conventions:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/CLAUDE.md`

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add bidirectional cross-references to `\annot`, `\annotref`, `\annotendnote`

**Verifies:** pdf-para-numbering-417.AC2.1, pdf-para-numbering-417.AC2.2, pdf-para-numbering-417.AC2.3, pdf-para-numbering-417.AC2.4

**Files:**
- Modify: `src/promptgrimoire/export/promptgrimoire-export.sty:150-202` (three macro modifications)

**Implementation:**

Modify the three annotation macros. The short-annotation path in `\annot` remains unchanged (AC2.4).

**`\annot` macro (lines 150-181) — modify the long-annotation path only:**

The long-annotation branch (lines 157-171) currently emits a superscript then writes content to the endnotes file. Add:
1. `\phantomsection\label{annot-inline:\theannotnum}` before the superscript (creates an anchor at the inline location)
2. Wrap the superscript in `\hyperref[annot-endnote:\theannotnum]{...}` (clicking jumps to endnote)
3. In the `\write` block: add `\noexpand\phantomsection` and `\noexpand\label{annot-endnote:\theannotnum}` before the content
4. In the `\write` block: wrap the endnote number in `\noexpand\hyperref[annot-inline:\theannotnum]{...}` (clicking jumps back to inline)

Replace the long-annotation branch (lines 158-171) with:

```latex
    % Long annotation → write to endnotes file, show stub in margin
    \phantomsection\label{annot-inline:\theannotnum}%
    \hyperref[annot-endnote:\theannotnum]{%
      \textsuperscript{\textcolor{#1}{\textbf{\theannotnum}}}%
    }%
    \marginalia[ysep=3pt]{%
      \fcolorbox{#1}{#1!20}{%
        \parbox{4.3cm}{\footnotesize\textbf{\theannotnum.} (see endnotes)}%
      }%
    }%
    \global\annothasendnotestrue
    \immediate\write\annotendfile{%
      \noexpand\phantomsection
      \noexpand\label{annot-endnote:\theannotnum}%
      \noexpand\par\noexpand\noindent
      \noexpand\hyperref[annot-inline:\theannotnum]{%
        \noexpand\textcolor{#1}{\noexpand\textbf{\theannotnum.}}%
      }%
      \unexpanded{#2}%
      \noexpand\par\noexpand\medskip
    }%
```

The short-annotation branch (lines 172-180) remains completely unchanged.

**`\write` expansion details:**
- `\theannotnum` expands at `\write` time → e.g., `3` (counter value captured)
- `\noexpand\label{annot-endnote:3}` → writes literal `\label{annot-endnote:3}` to file
- `\noexpand\hyperref[annot-inline:3]{...}` → writes literal `\hyperref[annot-inline:3]{...}` to file
- `\unexpanded{#2}` → writes content literally (existing pattern, unchanged)
- At `\input` time, `\label` and `\hyperref` execute, creating the cross-reference

**`\annotref` macro (lines 186-189) — add inline label and hyperref:**

Replace with:

```latex
\newcommand{\annotref}[1]{%
  \stepcounter{annotnum}%
  \phantomsection\label{annot-inline:\theannotnum}%
  \hyperref[annot-endnote:\theannotnum]{%
    \textsuperscript{\textcolor{#1}{\textbf{endnote \theannotnum}}}%
  }%
}
```

**`\annotendnote` macro (lines 194-202) — add endnote label and hyperref in `\write`:**

Replace with:

```latex
\newcommand{\annotendnote}[3]{%
  \global\annothasendnotestrue
  \immediate\write\annotendfile{%
    \noexpand\phantomsection
    \noexpand\label{annot-endnote:#2}%
    \noexpand\par\noexpand\noindent
    \noexpand\hyperref[annot-inline:#2]{%
      \noexpand\textcolor{#1}{\noexpand\textbf{#2.}}%
    }%
    \unexpanded{#3}%
    \noexpand\par\noexpand\medskip
  }%
}
```

Note: `#2` in `\annotendnote` is a `\numexpr` expression (e.g., `\the\numexpr\value{annotnum}-3+1\relax`) that expands to a number at `\write` time. The label/hyperref get the computed number.

**Verification:**

Run: `uv run grimoire test changed`
Expected: No test failures (LaTeX changes, not tested in unit lane)

**Commit:** `feat(export): add bidirectional cross-references to annotation macros (#417)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Tests for endnote cross-references

**Verifies:** pdf-para-numbering-417.AC2.1, pdf-para-numbering-417.AC2.2, pdf-para-numbering-417.AC2.3, pdf-para-numbering-417.AC2.4

**Files:**
- Create: `tests/unit/export/test_endnote_crossref.py` (smoke — `@requires_pandoc`)

**Note on test placement:** This file lives in `tests/unit/export/` but uses `@requires_pandoc` which auto-applies the `smoke` marker. These tests are excluded from the unit lane (`grimoire test all`) and only collected by `grimoire test smoke`. This matches the existing pattern in `tests/unit/export/test_markdown_to_latex.py` and `test_css_fidelity.py`.

**Testing:**

These tests require Pandoc + the Lua filter to produce LaTeX with `\annot`/`\annotref`/`\annotendnote` commands, then verify the commands contain the expected label/hyperref pairs. Use `@requires_pandoc` (auto-applies `smoke` marker). Follow the pattern in `tests/integration/test_pdf_export.py`.

Tests must verify each AC listed above:

- **pdf-para-numbering-417.AC2.1:** Given HTML with a long annotation (one that exceeds the `\annotmaxht` threshold), the LaTeX output contains:
  - `\label{annot-inline:` at the inline location
  - `\hyperref[annot-endnote:` wrapping the superscript
  - The endnotes file content (visible in generated `.tex` after two-pass compilation, or by checking `\write` output patterns in the LaTeX source) contains `\label{annot-endnote:` and `\hyperref[annot-inline:`

- **pdf-para-numbering-417.AC2.2:** Endnote entries contain both `\label{annot-endnote:N}` and `\hyperref[annot-inline:N]` wrapping the endnote number. **Note:** `\label`/`\hyperref` commands are generated at LaTeX compile time by the `\annot` macro, NOT present in the `.tex` source from `generate_tex_only()`. Two test approaches: (a) Read the `.sty` file directly and verify the `\annot` macro definition contains the expected `\noexpand\label{annot-endnote:` and `\noexpand\hyperref[annot-inline:` patterns in its `\write` block (static analysis). (b) Use `@requires_latexmk`, compile, then read the `.endnotes` auxiliary file from `tmp_path` and verify it contains `\label{annot-endnote:N}` and `\hyperref[annot-inline:N]`.

- **pdf-para-numbering-417.AC2.3:** Create a test with **multiple** annotation contents inside a table (triggers the Table callback path with `\annotref`/`\annotendnote`). Must test with 2+ annotations to verify label numbering stays consistent across the deferred execution boundary (a single-annotation test cannot detect off-by-one counter drift). The LaTeX output should contain `\label{annot-inline:` from `\annotref` and `\label{annot-endnote:` from `\annotendnote` with matching numbers.

- **pdf-para-numbering-417.AC2.4 (negative test):** Given HTML with only short annotations (below `\annotmaxht` threshold), the LaTeX output contains `\annot{` commands but NO `\label{annot-inline:` or `\hyperref[annot-endnote:` — confirming the margin path is unchanged.

Additional case:
- **Compilation success (`@requires_latexmk`):** Compile a document with bidirectional cross-references and verify PDF compilation completes without errors. Two-pass compilation (already handled by `latexmk`) resolves all label references.

**Verification:**

Run: `uv run grimoire test smoke`
Expected: New tests collected in smoke lane, all pass

**Commit:** `test(export): add tests for endnote cross-reference linking (#417)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
