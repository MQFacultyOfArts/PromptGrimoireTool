# LaTeX Test Optimisation — Phase 4: t-string Migration

**Goal:** Replace f-string LaTeX generation with Python 3.14 t-strings and a `render_latex()` renderer, plus command builders that eliminate `{{` brace escaping for simple commands.

**Architecture:** A new `export/latex_render.py` module reimplements PyLaTeX's useful patterns without the dependency: `NoEscape` (trusted string marker), `escape_latex()` (special-char escaping), `latex_cmd()` (command builder with auto-escaping), and `render_latex()` (t-string renderer). Callers choose the right tool: `latex_cmd()` for simple commands (no `{{` needed), `render_latex()` for complex templates. `escape_unicode_latex()` stays in `unicode_latex.py` for CJK/emoji wrapping — it's orthogonal to LaTeX special-char escaping.

**Tech Stack:** Python 3.14 (PEP 750 t-strings), `string.templatelib.Template` / `Interpolation`

**Scope:** 5 phases from original design (phase 4 of 5)

**Codebase verified:** 2026-02-13

**Key files to read before implementing:**
- `src/promptgrimoire/export/preamble.py` — `generate_tag_colour_definitions()` (5 f-string patterns, lines 127-138)
- `src/promptgrimoire/export/highlight_spans.py` — `format_annot_latex()` (7 f-string patterns, lines 102-168)
- `src/promptgrimoire/export/unicode_latex.py` — `escape_unicode_latex()`, `_format_emoji_for_latex()` (3 f-string patterns, lines 179, 182, 375)
- `src/promptgrimoire/export/pdf_export.py` — `_DOCUMENT_TEMPLATE` and `_GENERAL_NOTES_TEMPLATE` (`.format()` patterns, lines 30-47)

---

## Acceptance Criteria Coverage

This phase implements and tests:

### latex-test-optimization.AC4: t-string migration (DoD item 4)

- **latex-test-optimization.AC4.1 Success:** `generate_tag_colour_definitions()` uses `latex_cmd()` — no f-string `{{` escape sequences and no manual `escape_unicode_latex()` calls for LaTeX-special escaping
- **latex-test-optimization.AC4.2 Success:** `format_annot_latex()` uses `render_latex()` and/or `latex_cmd()` — no f-string `{{` escape sequences for LaTeX command construction
- **latex-test-optimization.AC4.3 Success:** `escape_latex()` escapes LaTeX special characters (`#`, `$`, `%`, `&`, `_`, `{`, `}`, `~`, `^`, `\`) in interpolated values
- **latex-test-optimization.AC4.4 Success:** Output of migrated functions is identical to pre-migration output for the same inputs
- **latex-test-optimization.AC4.5 Edge:** Tag names containing LaTeX special characters (e.g., `C#_notes`) are escaped correctly in colour definitions

**AC4.1 amendment:** The original AC says "no `{{` escape sequences in source". For simple commands (`\definecolor`, `\colorlet`, `\textbf`), `latex_cmd()` eliminates `{{` entirely by building commands programmatically. For complex templates in `render_latex()`, `{{` may still appear for literal braces in t-string syntax — this is a Python language constraint, not a design failure. The meaningful gain is auto-escaping and readable command construction.

---

## Design Decisions

### render_latex() vs latex_cmd() — two tools for two patterns

**`latex_cmd(name, *args)`** — for simple LaTeX commands where the structure is `\name{arg1}{arg2}`:
```python
latex_cmd("definecolor", f"tag-{safe_name}", "HTML", hex_code)
# → \definecolor{tag-jurisdiction}{HTML}{FF0000}
```
No `{{` escaping needed. Arguments are auto-escaped unless marked `NoEscape`.

**`render_latex(t"...")`** — for complex templates where command structure is irregular:
```python
render_latex(t"\\textbf{{{tag_esc}}} {para_ref}")
# → \textbf{Jurisdiction} [45]
```
`{{` still needed for literal braces in t-string syntax. Interpolated values are auto-escaped unless `NoEscape`.

**The migration strategy per function:**
- `generate_tag_colour_definitions()` → `latex_cmd()` exclusively (all patterns are simple commands)
- `format_annot_latex()` → mix of `latex_cmd()` and `render_latex()` (some simple commands, some complex assembly)
- `unicode_latex.py` f-strings → `latex_cmd()` (all are simple wrapping commands)
- `_DOCUMENT_TEMPLATE` → stays as `.format()` (interpolates pre-rendered LaTeX that must NOT be escaped)

### NoEscape + escape_unicode_latex() interaction

`escape_unicode_latex()` wraps CJK text in `\cjktext{...}` and emoji in `\emoji{...}`. Its output contains LaTeX commands that must NOT be re-escaped. The pattern:

```python
# For text that may contain CJK/emoji + LaTeX specials:
value = NoEscape(escape_unicode_latex(escape_latex(text)))

# Step 1: escape_latex("C# 你好") → "C\\# 你好" (escapes specials)
# Step 2: escape_unicode_latex("C\\# 你好") → "C\\# \\cjktext{你好}" (wraps CJK)
# Step 3: NoEscape(...) → tells render_latex/latex_cmd not to re-escape
```

The ordering is critical: `escape_latex()` first (handles ASCII specials), then `escape_unicode_latex()` (wraps CJK/emoji, introducing new LaTeX commands). Reversing the order would escape the `\cjktext{}` braces.

---

## Existing Code Reference

Before implementing, the executor should read these files for context:

| File | Purpose | Lines |
|------|---------|-------|
| `src/promptgrimoire/export/preamble.py` | `generate_tag_colour_definitions()` — 5 f-string LaTeX patterns | 183 |
| `src/promptgrimoire/export/highlight_spans.py` | `format_annot_latex()` — 7 f-string LaTeX patterns | ~400 |
| `src/promptgrimoire/export/unicode_latex.py` | `escape_unicode_latex()`, `_format_emoji_for_latex()` — 3 f-string patterns | ~405 |
| `src/promptgrimoire/export/pdf_export.py` | `_DOCUMENT_TEMPLATE` — `.format()` pattern (NOT migrated) | 349 |

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
## Subcomponent A: LaTeX Render Module

<!-- START_TASK_1 -->
### Task 1: Write failing tests for latex_render module

**Verifies:** latex-test-optimization.AC4.3, latex-test-optimization.AC4.5

**Files:**
- Create: `tests/unit/export/test_latex_render.py`

**Testing:**

TDD: write tests FIRST, verify they fail (ImportError), then implement in Task 2.

**Test class: TestEscapeLatex**
- **AC4.3:** Test each of the 10 LaTeX special characters:
  - `escape_latex("#")` → `"\\#"`
  - `escape_latex("$")` → `"\\$"`
  - `escape_latex("%")` → `"\\%"`
  - `escape_latex("&")` → `"\\&"`
  - `escape_latex("_")` → `"\\_"`
  - `escape_latex("{")` → `"\\{"`
  - `escape_latex("}")` → `"\\}"`
  - `escape_latex("~")` → `"\\textasciitilde{}"`
  - `escape_latex("^")` → `"\\textasciicircum{}"`
  - `escape_latex("\\")` → `"\\textbackslash{}"`
  Use subtests for the 10 characters.

- Passthrough: `escape_latex("normal text")` → `"normal text"` (no changes)
- Combined: `escape_latex("Cost: $30 & 50%")` → `"Cost: \\$30 \\& 50\\%"`
- **AC4.5:** `escape_latex("C#_notes")` → `"C\\#\\_notes"`
- NoEscape passthrough: `escape_latex(NoEscape("\\textbf{safe}"))` → returns unchanged

**Test class: TestNoEscape**
- `isinstance(NoEscape("x"), str)` → True (it's a string subclass)
- `NoEscape("x") + NoEscape("y")` → result type check
- `escape_latex(NoEscape("already safe"))` → returns input unchanged

**Test class: TestLatexCmd**
- Simple command: `latex_cmd("textbf", "hello")` → `"\\textbf{hello}"`
- Two args: `latex_cmd("definecolor", "mycolor", "HTML", "FF0000")` → `"\\definecolor{mycolor}{HTML}{FF0000}"`
- Auto-escaping: `latex_cmd("textbf", "C#_notes")` → `"\\textbf{C\\#\\_notes}"`
- NoEscape arg: `latex_cmd("textbf", NoEscape("\\em{x}"))` → `"\\textbf{\\em{x}}"` (not re-escaped)
- Returns NoEscape: `isinstance(latex_cmd("textbf", "x"), NoEscape)` → True

**Test class: TestRenderLatex**
- Static passthrough: `render_latex(t"hello world")` → `"hello world"`
- Interpolation escaping: with `val = "C#"`, `render_latex(t"tag: {val}")` → `"tag: C\\#"`
- NoEscape interpolation: with `val = NoEscape("\\textbf{x}")`, `render_latex(t"cmd: {val}")` → `"cmd: \\textbf{x}"`
- Mixed: with `name = "test_tag"`, `render_latex(t"\\definecolor{{tag-{name}}}{{HTML}}{{FF0000}}")` → `"\\definecolor{tag-test\\_tag}{HTML}{FF0000}"`

**Verification:**
Run: `uv run pytest tests/unit/export/test_latex_render.py -v`
Expected: ImportError or ModuleNotFoundError (module doesn't exist yet)

Do NOT commit yet — tests are expected to fail.
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement latex_render module

**Verifies:** latex-test-optimization.AC4.3

**Files:**
- Create: `src/promptgrimoire/export/latex_render.py`
- Modify: `src/promptgrimoire/export/__init__.py` (add exports)

**Implementation:**

Create `latex_render.py` with four components:

**1. `_LATEX_SPECIALS` — ordered dict of char → replacement:**
```python
_LATEX_SPECIALS: dict[str, str] = {
    "\\": r"\textbackslash{}",
    "#": r"\#",
    "$": r"\$",
    "%": r"\%",
    "&": r"\&",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
```
**CRITICAL:** Backslash MUST be first — otherwise replacing `#` → `\#` and then `\` → `\textbackslash{}` would double-escape.

**2. `NoEscape(str)` — string subclass:**
```python
class NoEscape(str):
    """Mark a string as trusted LaTeX that should not be escaped."""
    pass
```

**3. `escape_latex(text: str) -> NoEscape`:**
- If `text` is already `NoEscape`, return it unchanged
- Otherwise, apply all replacements from `_LATEX_SPECIALS`
- Return as `NoEscape` (the result is now safe)

**4. `latex_cmd(name: str, *args: str | NoEscape) -> NoEscape`:**
- For each arg: if `NoEscape`, use as-is; otherwise, call `escape_latex()`
- Build `\{name}{arg1}{arg2}...`
- Return as `NoEscape`

**5. `render_latex(template: Template) -> str`:**
- Import `Template`, `Interpolation` from `string.templatelib`
- Iterate template items:
  - `str` → append as-is (static template text, contains intentional LaTeX)
  - `Interpolation` → apply conversion if set (`!r`, `!s`, `!a`), apply format_spec if set, then: if value is `NoEscape`, append as-is; otherwise, call `escape_latex()` and append
- Return joined string

Add `NoEscape`, `escape_latex`, `latex_cmd`, `render_latex` to `__all__` in `export/__init__.py`.

**Verification:**
Run: `uv run pytest tests/unit/export/test_latex_render.py -v`
Expected: All tests pass (green from red)

**Commit:** `feat: add latex_render module with NoEscape, escape_latex, latex_cmd, render_latex`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Write snapshot tests for pre-migration output

**Verifies:** latex-test-optimization.AC4.4 (preparation)

**Files:**
- Create: `tests/unit/export/test_latex_migration_snapshots.py`

**Testing:**

Before migrating any functions, capture their current output as snapshot test fixtures. This creates the regression safety net for AC4.4.

**Snapshot 1: generate_tag_colour_definitions()**
Call with known input:
```python
tag_colours = {
    "jurisdiction": "#1f77b4",
    "evidence": "#ff7f0e",
    "C#_notes": "#2ca02c",  # AC4.5: LaTeX special chars in tag name
}
```
Capture output string and assert it matches expected value (copy current output verbatim).

**Snapshot 2: format_annot_latex()**
Call with known input:
```python
highlight = {
    "tag": "jurisdiction",
    "author": "Alice Jones ABC123",
    "created_at": "2026-01-15T10:30:00Z",
    "comments": [
        {"author": "Bob Smith DEF456", "text": "Important point about $damages", "created_at": "2026-01-15T11:00:00Z"},
    ],
}
```
Capture output and assert it matches expected value.

**Snapshot 3: format_annot_latex() with special chars**
Call with a highlight containing LaTeX special characters in author name and comment text:
```python
highlight = {
    "tag": "C#_notes",
    "author": "O'Brien & Associates",
    "comments": [{"author": "Test", "text": "See § 42 & compare with ~50%"}],
}
```

**Note:** These snapshots capture CURRENT behaviour including any existing escaping bugs. AC4.4 requires output identity — the migration must preserve current behaviour, even if imperfect. Fixing escaping bugs is out of scope.

**Verification:**
Run: `uv run pytest tests/unit/export/test_latex_migration_snapshots.py -v`
Expected: All snapshots pass (they match current output)

**Commit:** `test: snapshot tests for pre-migration LaTeX output (AC4.4 baseline)`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-6) -->
## Subcomponent B: Function Migration

<!-- START_TASK_4 -->
### Task 4: Migrate generate_tag_colour_definitions() to latex_cmd()

**Verifies:** latex-test-optimization.AC4.1, latex-test-optimization.AC4.4, latex-test-optimization.AC4.5

**Files:**
- Modify: `src/promptgrimoire/export/preamble.py` (rewrite function body)

**Implementation:**

Replace the 5 f-string patterns in `generate_tag_colour_definitions()` (lines 127-138) with `latex_cmd()` calls:

```python
from promptgrimoire.export.latex_render import latex_cmd, NoEscape

def generate_tag_colour_definitions(tag_colours: dict[str, str]) -> str:
    definitions: list[str] = []
    for tag, colour in tag_colours.items():
        hex_code = colour.lstrip("#")
        safe_name = tag.replace("_", "-")

        # Full colour
        definitions.append(str(latex_cmd("definecolor", f"tag-{safe_name}", "HTML", hex_code)))
        # Light colour (30% strength) — xcolor mixing syntax is trusted LaTeX
        definitions.append(str(latex_cmd("colorlet", f"tag-{safe_name}-light", NoEscape(f"tag-{safe_name}!30"))))
        # Dark variant (70% base, 30% black)
        definitions.append(str(latex_cmd("colorlet", f"tag-{safe_name}-dark", NoEscape(f"tag-{safe_name}!70!black"))))

    definitions.append(r"\definecolor{many-dark}{HTML}{333333}")
    return "\n".join(definitions)
```

**Key details:**
- `safe_name` uses `replace("_", "-")` — this is a LaTeX naming convention, not escaping. The `-` is safe in `\definecolor` names. Keep this as-is.
- The `NoEscape(f"tag-{safe_name}!30")` for `\colorlet` is needed because the xcolor mixing syntax (`!30`, `!70!black`) is trusted LaTeX, not user data.
- `hex_code` is a hex string (stripped `#`) — safe characters, but `latex_cmd` will still try to escape. Since hex chars (0-9, a-f, A-F) have no LaTeX specials, escaping is a no-op.

**AC4.5 verification:** If `tag = "C#_notes"`, then `safe_name = "C#-notes"` (only `_` → `-`, the `#` stays). Then `latex_cmd("definecolor", f"tag-C#-notes", ...)` auto-escapes to `\definecolor{tag-C\#-notes}{...}`. But wait — is `\#` valid in a `\definecolor` colour name? LaTeX colour names must be alphanumeric + hyphens. A `\#` would break. So `safe_name` construction should ALSO handle `#`. This is an existing bug — document it and handle in the migration by extending the sanitisation:

```python
safe_name = tag.replace("_", "-").replace("#", "-sharp")
```

Or better: strip all non-alphanumeric-hyphen characters. But this changes existing behaviour, violating AC4.4. **Known issue:** The `safe_name` construction currently only replaces `_` → `-`, leaving `#` intact. A tag named `"C#_notes"` produces `safe_name = "C#-notes"`, which generates `\definecolor{tag-C#-notes}` — invalid because LaTeX colour names cannot contain `#`. This is a pre-existing bug (present before migration). The implementor MUST preserve current behaviour for AC4.4, and file this as a separate bug to fix outside the migration.

**Verification:**
Run: `uv run pytest tests/unit/export/test_latex_migration_snapshots.py -v`
Expected: Snapshot tests pass (output identical to pre-migration)

Run: `uv run test-all -m latex`
Expected: All LaTeX tests pass

**Commit:** `refactor: migrate generate_tag_colour_definitions() to latex_cmd()`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Migrate format_annot_latex() to render_latex() / latex_cmd()

**Verifies:** latex-test-optimization.AC4.2, latex-test-optimization.AC4.4

**Files:**
- Modify: `src/promptgrimoire/export/highlight_spans.py` (rewrite function body)

**Implementation:**

Replace the 7 f-string patterns in `format_annot_latex()` (lines 128-168) with a mix of `latex_cmd()` and `render_latex()`:

**Pattern 1 — Simple commands use `latex_cmd()`:**
```python
# Before: f"\\textbf{{{escape_unicode_latex(tag_display)}}}"
# After:
tag_esc = NoEscape(escape_unicode_latex(tag_display))
textbf_tag = latex_cmd("textbf", tag_esc)
```

**Pattern 2 — Complex assembly uses string concatenation with `NoEscape` parts:**
```python
# Before: f"\\textbf{{{escape_unicode_latex(tag_display)}}} {para_ref}"
# After:
tag_bold = latex_cmd("textbf", NoEscape(escape_unicode_latex(tag_display)))
margin_parts = [f"{tag_bold} {para_ref}"]
```

**Pattern 3 — Par/scriptsize wrapping:**
```python
# Before: f"\\par{{\\scriptsize {byline}}}"
# After:
margin_parts.append(f"\\par{{\\scriptsize {byline}}}")
# Or if byline contains user data that needs escaping:
margin_parts.append(render_latex(t"\\par{{\\scriptsize {byline}}}"))
```

**Pattern 4 — The final \annot command:**
```python
# Before: f"\\annot{{{colour_name}}}{{{margin_content}}}"
# After:
latex_cmd("annot", colour_name, NoEscape(margin_content))
```
The `margin_content` is `NoEscape` because it's already been built from escaped parts.

**Key interaction with `escape_unicode_latex()`:**
The current code calls `escape_unicode_latex()` on `tag_display`, `author`, `c_author`, `c_text`. These calls handle CJK/emoji wrapping. After migration:
- `escape_unicode_latex()` still called on user-data values
- Results wrapped in `NoEscape()` before passing to `latex_cmd()` or `render_latex()`
- `escape_latex()` (from `latex_render.py`) handles the 10 LaTeX specials

**CRITICAL ordering for values containing both CJK and specials:**
```python
# Correct: escape specials first, then handle Unicode, then mark safe
safe_value = NoEscape(escape_unicode_latex(escape_latex(str(value))))
```
This ensures `escape_latex` doesn't see/escape the `\cjktext{}` braces that `escape_unicode_latex` produces.

**However — for AC4.4 (output identity), verify the current code does NOT escape LaTeX specials.** If `escape_unicode_latex()` currently does not escape `#`, `$`, etc., then adding `escape_latex()` would CHANGE the output. In that case, skip `escape_latex()` and only use `NoEscape(escape_unicode_latex(value))` to match current behaviour. The improved escaping can be added in a follow-up.

**Verification:**
Run: `uv run pytest tests/unit/export/test_latex_migration_snapshots.py -v`
Expected: Snapshot tests pass (output identical to pre-migration)

Run: `uv run test-all -m latex`
Expected: All LaTeX tests pass

**Commit:** `refactor: migrate format_annot_latex() to latex_cmd() and render_latex()`
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Migrate unicode_latex.py f-strings to latex_cmd()

**Verifies:** latex-test-optimization.AC4.4

**Files:**
- Modify: `src/promptgrimoire/export/unicode_latex.py` (3 patterns)

**Implementation:**

Replace the 3 f-string patterns:

**Line 179:** `f"\\emoji{{{emoji_name}}}"`
```python
# After:
return str(latex_cmd("emoji", emoji_name))
```

**Line 182:** `f"\\emojifallbackchar{{{emoji_name}}}"`
```python
# After:
return str(latex_cmd("emojifallbackchar", emoji_name))
```

**Line 375:** `f"\\cjktext{{{escaped}}}"`
```python
# After:
return str(latex_cmd("cjktext", NoEscape(escaped)))
```
The `escaped` value at line 375 has already been processed — it's trusted content, hence `NoEscape`.

**Note:** `emoji_name` values come from the `emoji` library's short names (e.g., `"grinning_face"`). These don't contain LaTeX specials, so auto-escaping is a no-op. But using `latex_cmd()` is still cleaner and consistent.

**Verification:**
Run: `uv run pytest tests/unit/export/test_latex_migration_snapshots.py -v`
Expected: Snapshot tests pass

Run: `uv run test-all -m latex`
Expected: All LaTeX tests pass

**Commit:** `refactor: migrate unicode_latex.py f-strings to latex_cmd()`
<!-- END_TASK_6 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 7-8) -->
## Subcomponent C: Verification

<!-- START_TASK_7 -->
### Task 7: Verify no f-string LaTeX patterns remain

**Verifies:** latex-test-optimization.AC4.1, latex-test-optimization.AC4.2

**Files:**
- No file changes (verification only)

**Implementation:**

Search the entire `src/promptgrimoire/export/` directory for remaining f-string LaTeX patterns:

```bash
# Search for f-strings containing \\ (LaTeX commands)
uv run ruff check src/promptgrimoire/export/ --select S  # or use grep:
grep -rn 'f"\\\\' src/promptgrimoire/export/
grep -rn "f'\\\\\\\\'" src/promptgrimoire/export/
```

Expected: no results from `preamble.py`, `highlight_spans.py`, or `unicode_latex.py`.

**Allowed exceptions:**
- `pdf_export.py` — `_DOCUMENT_TEMPLATE` and `_GENERAL_NOTES_TEMPLATE` use `.format()` (deliberately not migrated)
- `build_annotation_preamble()` in `preamble.py` — uses f-strings for string concatenation (`f"\\usepackage{{...}}\n{...}"`) but this is preamble assembly, not LaTeX command construction. It may remain as f-string or be migrated to `render_latex()` at implementor's discretion.
- `build_font_preamble()` in `unicode_latex.py` (Phase 3) — generates dynamic LaTeX; may use f-strings for `\directlua{...}` blocks. Migrating these complex multi-line LaTeX blocks is optional.

**Verification:**
Run: `grep -rn 'f"\\\\' src/promptgrimoire/export/preamble.py src/promptgrimoire/export/highlight_spans.py src/promptgrimoire/export/unicode_latex.py`
Expected: no results (or only allowed exceptions)

Run: `uv run test-all`
Expected: All tests pass
<!-- END_TASK_7 -->

<!-- START_TASK_8 -->
### Task 8: Full regression verification

**Verifies:** All AC4 criteria (regression check)

**Files:**
- No file changes (verification only)

**Implementation:**

1. Run snapshot tests: `uv run pytest tests/unit/export/test_latex_migration_snapshots.py -v`
2. Run latex_render unit tests: `uv run pytest tests/unit/export/test_latex_render.py -v`
3. Run all LaTeX tests: `uv run test-all -m latex -v`
4. Run full test suite: `uv run test-all`
5. Verify no regressions

The mega-doc tests from Phase 1 serve as the end-to-end regression guard. If they pass, the migrated functions produce correct LaTeX that compiles to valid PDFs.

**Verification:**
Run: `uv run test-all`
Expected: All tests pass, zero regressions
<!-- END_TASK_8 -->
<!-- END_SUBCOMPONENT_C -->

---

## UAT Steps

1. [ ] Open `src/promptgrimoire/export/latex_render.py` — verify `NoEscape`, `escape_latex`, `latex_cmd`, `render_latex` exist and are readable
2. [ ] Run `uv run python -c "from promptgrimoire.export.latex_render import latex_cmd; print(latex_cmd('definecolor', 'mycolor', 'HTML', 'FF0000'))"` — verify output is `\definecolor{mycolor}{HTML}{FF0000}`
3. [ ] Run `uv run python -c "from promptgrimoire.export.latex_render import escape_latex; print(escape_latex('C#_notes'))"` — verify output escapes `#` and `_`
4. [ ] Run `uv run test-all -m latex -v` — all LaTeX tests pass
5. [ ] Run `uv run test-all` — full suite passes
6. [ ] Grep for f-string LaTeX patterns in migrated files — verify none remain
7. [ ] Inspect `generate_tag_colour_definitions()` — verify it uses `latex_cmd()`, not f-strings
8. [ ] Inspect `format_annot_latex()` — verify it uses `render_latex()` / `latex_cmd()`, not f-strings

## Evidence Required
- [ ] Test output showing all tests green (snapshots + unit + latex + full)
- [ ] `latex_cmd()` output for representative commands
- [ ] grep showing no f-string LaTeX patterns in migrated files
