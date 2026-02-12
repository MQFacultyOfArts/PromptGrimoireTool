# LaTeX Test Optimisation — Phase 2: Extract `.sty` Package

**Goal:** Move all static LaTeX from Python string constants into `promptgrimoire-export.sty`, shared between production and tests.

**Architecture:** Static preamble content (packages, commands, environments, macros, font setup, speaker colours) moves to a `.sty` file stored in `src/promptgrimoire/export/`. The pipeline copies this `.sty` to the output directory before each compilation. Python retains only dynamic content (per-document tag colour definitions) and the document template.

**Tech Stack:** LaTeX `.sty` package authoring, Python 3.14

**Scope:** 5 phases from original design (phase 2 of 5)

**Codebase verified:** 2026-02-12

**Key files to read before implementing:**
- `src/promptgrimoire/export/preamble.py` — `ANNOTATION_PREAMBLE_BASE` (lines 25-109), `build_annotation_preamble()` (lines 146-165)
- `src/promptgrimoire/export/unicode_latex.py` — `UNICODE_PREAMBLE` (lines 12-117)
- `src/promptgrimoire/export/pdf_export.py` — pipeline orchestration, `_DOCUMENT_TEMPLATE` (lines 30-41)
- `src/promptgrimoire/export/pdf.py` — `compile_latex()` (lines 65-128)
- `docs/lualatex/subfiles-reference.md` — subfiles package reference (for .sty loading mechanics)

---

## Acceptance Criteria Coverage

This phase implements and tests:

### latex-test-optimization.AC2: `.sty` extraction (DoD items 2, 6)

- **latex-test-optimization.AC2.1 Success:** `promptgrimoire-export.sty` compiles in a minimal `\documentclass{article}\usepackage{promptgrimoire-export}\begin{document}Test\end{document}` without errors
- **latex-test-optimization.AC2.2 Success:** Production `export_annotation_pdf()` output is byte-identical to pre-extraction output for a reference document (same preamble content, just different packaging)
- **latex-test-optimization.AC2.3 Success:** The `.sty` file contains all static preamble content: package declarations, fixed commands, environments, and macros
- **latex-test-optimization.AC2.4 Failure:** Removing the `.sty` from the output directory causes `compile_latex()` to fail with a clear error (not a silent fallback)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
## Subcomponent A: Create `.sty` File

<!-- START_TASK_1 -->
### Task 1: Create promptgrimoire-export.sty

**Verifies:** latex-test-optimization.AC2.3

**Files:**
- Create: `src/promptgrimoire/export/promptgrimoire-export.sty`

**Implementation:**
Create the `.sty` file containing ALL static LaTeX content currently spread across `ANNOTATION_PREAMBLE_BASE` (preamble.py:25-109) and `UNICODE_PREAMBLE` (unicode_latex.py:12-117).

The `.sty` must begin with `\NeedsTeXFormat{LaTeX2e}` and `\ProvidesPackage{promptgrimoire-export}[2026/02/12 PromptGrimoire annotation export]`.

Content to include (in this order):

1. **Package dependencies** — convert `\usepackage{...}` to `\RequirePackage{...}` (standard .sty practice):
   - xcolor (needed for colour definitions within the .sty)
   - amsmath, microtype, marginalia, longtable, booktabs, array, calc
   - hyperref (with hidelinks)
   - changepage, luacolor, lua-ul, luabidi, fancyvrb
   - geometry (a4paper, margins)
   - mdframed (framemethod=tikz)
   - luatexja-fontspec, emoji

2. **Fixed commands:**
   - `\renewcommand{\includegraphics}[2][]{[image]}`
   - `\providecommand{\tightlist}{...}`
   - `\newcommand{\emojifallbackchar}[1]{[#1]}`

3. **Environment definitions:**
   - `otherlanguage` no-op (the `\makeatletter` / `\makeatother` block)
   - `userturn` mdframed environment
   - `assistantturn` mdframed environment

4. **Paragraph formatting:**
   - `\setlength{\parindent}{0pt}`
   - `\setlength{\parskip}{0.5\baselineskip}`
   - `\setlength{\emergencystretch}{3em}`
   - `\setcounter{secnumdepth}{-\maxdimen}`

5. **Static colour definitions:**
   - `\definecolor{usercolor}{HTML}{1a4f8b}`
   - `\definecolor{assistantcolor}{HTML}{2d5f1e}`
   - `\definecolor{many-dark}{HTML}{8B0000}`
   - `\colorlet{many-light}{many-dark!15}`

6. **Annotation macro:**
   - `\newcounter{annotnum}`
   - `\newcommand{\annot}[2]{...}` (the full marginnote annotation command)

7. **Font setup (from UNICODE_PREAMBLE):**
   - luatexja parameter configuration (`\ltjsetparameter{jacharrange={-2}}`)
   - `\directlua{luaotfload.add_fallback("mainfallback", {...})}` — the complete font fallback chain
   - CJK font setup (`\setmainjfont`, `\setsansjfont`, `\newjfontfamily\notocjk`)
   - `\setemojifont{Noto Color Emoji}`
   - `\setmainfont{TeX Gyre Termes}[RawFeature={fallback=mainfallback}]`

8. **CJK text command:**
   - `\newcommand{\cjktext}[1]{\notocjk{#1}}` (or the existing conditional definition)

End with `\endinput`.

**CRITICAL:** Copy the LaTeX content EXACTLY from the existing Python string constants. Do not paraphrase, reformat, or "improve" the LaTeX — any change risks breaking compilation. Diff the `.sty` content against the combined `ANNOTATION_PREAMBLE_BASE` + `UNICODE_PREAMBLE` + speaker colours to ensure nothing was lost or altered.

**Verification:**
No direct test yet — verified by Task 3.

**Commit:** `feat: create promptgrimoire-export.sty with all static preamble content`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Write guard test for `.sty` compilation

**Verifies:** latex-test-optimization.AC2.1

**Files:**
- Modify: `tests/integration/test_pdf_export.py` (add guard test)

**Testing:**
Create a test `test_sty_compiles_standalone` (or add to existing compilation test class):
- AC2.1: Write a minimal `.tex` document to a temp directory:
  ```latex
  \documentclass{article}
  \usepackage{promptgrimoire-export}
  \begin{document}
  Test
  \end{document}
  ```
- Copy `promptgrimoire-export.sty` to the same temp directory
- Call `compile_latex()` on the `.tex` file
- Assert: PDF is created without errors

Use `@requires_latexmk` decorator.

**Verification:**
Run: `uv run pytest tests/integration/test_pdf_export.py -k test_sty_compiles -v`
Expected: Test fails initially (`.sty` not yet integrated into pipeline). After Task 3, it should pass.
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
## Subcomponent B: Pipeline Integration

<!-- START_TASK_3 -->
### Task 3: Integrate `.sty` into the export pipeline

**Verifies:** latex-test-optimization.AC2.2, latex-test-optimization.AC2.3

**Files:**
- Modify: `src/promptgrimoire/export/preamble.py` (replace string constants with `.sty` loading)
- Modify: `src/promptgrimoire/export/pdf_export.py` (copy `.sty` to output directory)
- Modify: `src/promptgrimoire/export/unicode_latex.py` (remove `UNICODE_PREAMBLE` constant)

**Implementation:**

**Step 1: Update `pdf_export.py` to copy `.sty` before compilation.**

Add a helper that copies `promptgrimoire-export.sty` from the package directory to the output directory. The `.sty` source path is `Path(__file__).parent / "promptgrimoire-export.sty"`. Call this helper in both `generate_tex_only()` and `export_annotation_pdf()` before writing the `.tex` file.

```python
_STY_SOURCE = Path(__file__).parent / "promptgrimoire-export.sty"

def _ensure_sty_in_dir(output_dir: Path) -> None:
    """Copy promptgrimoire-export.sty to the output directory for latexmk."""
    dest = output_dir / "promptgrimoire-export.sty"
    if not dest.exists():
        shutil.copy2(_STY_SOURCE, dest)
```

Call `_ensure_sty_in_dir(output_dir)` before `tex_path.write_text(document)`.

**Step 2: Update `build_annotation_preamble()` in `preamble.py`.**

Remove `ANNOTATION_PREAMBLE_BASE` constant. Remove the import of `UNICODE_PREAMBLE` from `unicode_latex`. Replace the string concatenation with:

```python
def build_annotation_preamble(tag_colours: dict[str, str]) -> str:
    colour_defs = generate_tag_colour_definitions(tag_colours)
    return f"\\usepackage{{promptgrimoire-export}}\n{colour_defs}"
```

The `.sty` handles everything except dynamic tag colours. The `\usepackage{xcolor}` is now in the `.sty` (as `\RequirePackage{xcolor}`), so it doesn't need to be emitted separately.

**Step 3: Remove `UNICODE_PREAMBLE` from `unicode_latex.py`.**

Delete the `UNICODE_PREAMBLE` constant (lines 12-117). Keep all other content in `unicode_latex.py` (escape functions, `_REQUIRED_SCRIPTS`, etc.) — these are used elsewhere and are not preamble content.

**CRITICAL regression check:** After this change, the output of `build_annotation_preamble()` should produce a document that compiles identically to before. The content is the same — just packaged in a `.sty` file instead of inline strings.

**Verification:**
Run: `uv run test-all -m latex`
Expected: ALL existing tests pass (mega-doc tests from Phase 1 serve as the safety net)

Run: `uv run pytest tests/integration/test_pdf_export.py -k test_sty_compiles -v`
Expected: Guard test passes

**Commit:** `refactor: integrate promptgrimoire-export.sty into export pipeline`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Test `.sty` removal failure path

**Verifies:** latex-test-optimization.AC2.4

**Files:**
- Modify: `tests/integration/test_pdf_export.py` (add failure test)

**Testing:**
Create a test `test_missing_sty_raises_error`:
- AC2.4: Set up a valid `.tex` document that uses `\usepackage{promptgrimoire-export}` in a temp directory
- Do NOT copy the `.sty` file to that directory
- Call `compile_latex()` on the `.tex` file
- Assert: Raises `LaTeXCompilationError` (not a silent fallback)

This ensures the `.sty` dependency is explicit — removing it breaks compilation clearly.

**Verification:**
Run: `uv run pytest tests/integration/test_pdf_export.py -k test_missing_sty -v`
Expected: Test passes (compilation fails as expected when `.sty` is missing)

**Commit:** `test: verify missing .sty causes compilation failure`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 5-6) -->
## Subcomponent C: Regression Verification and Cleanup

<!-- START_TASK_5 -->
### Task 5: Verify production output parity

**Verifies:** latex-test-optimization.AC2.2

**Files:**
- No file changes (verification only)

**Implementation:**
Verify that the `.sty` extraction produces identical output:

1. Run the full LaTeX test suite: `uv run test-all -m latex -v`
2. Run the full test suite: `uv run test-all`
3. Verify no test regressions

The mega-doc tests from Phase 1 are the primary regression guard. If they pass, the preamble content is functionally identical.

For a manual spot-check (optional): export a reference document via `generate_tex_only()` and diff the `.tex` content against a pre-extraction baseline. The preamble section should differ only in structure (`\usepackage{promptgrimoire-export}` vs inline content), not in LaTeX semantics.

**Verification:**
Run: `uv run test-all`
Expected: All tests pass, zero regressions
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Update mega-document infrastructure to copy `.sty`

**Verifies:** latex-test-optimization.AC2.1 (in test context)

**Files:**
- Modify: `tests/integration/conftest.py` (update `compile_mega_document()` to copy `.sty`)

**Implementation:**
The `compile_mega_document()` function (from Phase 1, Task 5) writes `.tex` files to a temp directory and compiles them. After Phase 2, the `.sty` must also be present in that directory.

Update `compile_mega_document()` to call the same `_ensure_sty_in_dir()` helper (or copy the `.sty` directly) before calling `compile_latex()`.

If `generate_tex_only()` is used within `compile_mega_document()`, it may already handle the `.sty` copy (since Task 3 added it to the pipeline). Verify this — if the mega-doc builder constructs `.tex` files manually (bypassing `generate_tex_only()`), it needs its own `.sty` copy step.

**Verification:**
Run: `uv run pytest tests/integration/test_mega_doc_infrastructure.py -v`
Expected: Infrastructure test passes (mega-doc compiles with `.sty`)

Run: `uv run test-all -m latex`
Expected: All mega-doc tests pass

**Commit:** `fix: ensure .sty is copied for mega-document test compilation`
<!-- END_TASK_6 -->
<!-- END_SUBCOMPONENT_C -->

---

## UAT Steps

1. [ ] Open `src/promptgrimoire/export/promptgrimoire-export.sty` — verify it's readable LaTeX
2. [ ] Run `uv run test-all -m latex -v` — all LaTeX tests pass
3. [ ] Run `uv run test-all` — full suite passes
4. [ ] Verify `ANNOTATION_PREAMBLE_BASE` is gone from `preamble.py`
5. [ ] Verify `UNICODE_PREAMBLE` is gone from `unicode_latex.py`
6. [ ] Verify `build_annotation_preamble()` now emits `\usepackage{promptgrimoire-export}` + tag colours only

## Evidence Required
- [ ] Test output showing all tests green
- [ ] `.sty` file contents showing complete static preamble
