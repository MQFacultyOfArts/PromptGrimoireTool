---
source: tests/helpers/latex_parse.py, pylatexenc
fetched: 2026-02-07
library: pylatexenc
summary: Why LaTeX export tests use AST parsing instead of string matching
---

# LaTeX Test AST Validation

## Problem

LaTeX export tests originally used string matching to validate output:

```python
assert r"\highLight[tag-jurisdiction-light]{text}" in result
assert result.count(r"\underLine") == 2
assert r"\definecolor{tag-alpha}{HTML}{1f77b4}" in result
```

This approach has structural blind spots:

1. **Unbalanced braces pass** — `\highLight[a]{text` (missing closing brace) still contains the substring `\highLight[a]{text`
2. **Wrong nesting passes** — `\highLight[a]{\underLine[b]{` with interleaved closing braces matches both substrings individually
3. **Malformed arguments pass** — `\definecolor{tag-alpha}{HTML}` (missing third argument) still matches a substring check for the colour name
4. **Fragile to whitespace** — any formatting change breaks exact string equality even if the LaTeX is semantically identical

## Solution

Parse generated LaTeX into an AST using pylatexenc's `LatexWalker`, then query the tree structurally. A test helper module (`tests/helpers/latex_parse.py`) wraps pylatexenc with the project's custom macro definitions.

### Why pylatexenc

pylatexenc is already a project dependency (used in production code for environment boundary detection in `latex.py`). It provides:

- `LatexWalker` — tokeniser + parser that produces a typed node tree
- `MacroSpec` — declares argument patterns so the parser knows `\highLight` takes `[optional]{mandatory}` while `\definecolor` takes `{name}{model}{value}`
- Tolerant parsing mode — doesn't crash on unknown macros, which matters because test fragments aren't complete documents

### Custom macro context

The parser must know the argument structure of each custom macro. Without this, `\highLight[tag-a-light]{text}` would be parsed as the macro `\highLight` with no arguments, followed by loose text `[tag-a-light]{text}`.

```python
MacroSpec("highLight",   "[{")    # optional + 1 mandatory
MacroSpec("underLine",   "[{")    # optional + 1 mandatory
MacroSpec("annot",       "{")     # 1 mandatory
MacroSpec("definecolor", "{{{")   # 3 mandatory
MacroSpec("colorlet",    "{{")    # 2 mandatory
MacroSpec("cjktext",     "{")     # 1 mandatory
MacroSpec("emoji",       "{")     # 1 mandatory
```

The argument spec string uses pylatexenc's shorthand: `[` = optional argument, `{` = mandatory argument. So `"[{"` means "one optional, one mandatory" and `"{{{"` means "three mandatory."

These specs must match what the export pipeline actually generates. If a macro's signature changes in production, the test parser must be updated to match, otherwise tests will silently misparse.

## Helper API

All helpers live in `tests/helpers/latex_parse.py`.

### `parse_latex(text) -> list`

Parses a LaTeX fragment into a node list. Configures `LatexWalker` with the custom macro context and tolerant parsing.

### `find_macros(nodes, name) -> list[LatexMacroNode]`

Recursively searches the entire node tree (including inside macro arguments and group nodes) for macros with the given name. Returns them in document order.

### `get_opt_arg(node) -> str | None`

Extracts the flattened text content of a macro's optional `[...]` argument. Returns `None` if no optional argument exists.

### `require_opt_arg(node) -> str`

Like `get_opt_arg` but asserts the argument exists. Use in tests where the optional argument is structurally required (e.g., `\underLine` always has a colour spec). This avoids `str | None` type narrowing noise in every test.

### `get_body_text(node) -> str`

Extracts the flattened text of the first mandatory `{...}` argument. Recurses through nested macros to reach leaf text — so `\highLight[a]{\underLine[b]{deep}}` returns `"deep"`.

### `get_mandatory_args(node) -> list[str]`

Extracts flattened text of all mandatory arguments. Needed for macros with multiple mandatory args:

- `\definecolor{tag-alpha}{HTML}{1f77b4}` → `["tag-alpha", "HTML", "1f77b4"]`
- `\colorlet{tag-alpha-dark}{tag-alpha!70!black}` → `["tag-alpha-dark", "tag-alpha!70!black"]`

## Example: before and after

**Before (string matching):**

```python
def test_single_highlight_1pt_underline(self):
    result = wrapper("text")
    assert r"\underLine[color=tag-alpha-dark, height=1pt, bottom=-3pt]{text}" in result
```

Passes if the substring appears anywhere, even inside a broken structure.

**After (AST validation):**

```python
def test_single_highlight_1pt_underline(self):
    result = wrapper("text")
    nodes = parse_latex(result)
    uls = find_macros(nodes, "underLine")

    assert len(uls) == 1
    opt = require_opt_arg(uls[0])
    assert "tag-alpha-dark" in opt
    assert "height=1pt" in opt
    assert get_body_text(uls[0]) == "text"
```

This verifies:
- Exactly one `\underLine` macro exists (not zero, not duplicates)
- It has a parseable optional argument containing the expected colour and thickness
- Its mandatory argument contains the expected text
- The macro's braces are balanced (the parser would fail otherwise)

## What's not covered

- **Full document compilation** — `TestCompilationValidation` in `test_latex_string_functions.py` compiles a complete document with LuaLaTeX. That test stays as-is; it validates the entire toolchain, not individual function output.
- **Timestamp formatting** — `TestFormatTimestamp` tests a pure string function with no LaTeX structure.
- **Semantic correctness** — AST parsing confirms structural validity, not that the right colour was chosen for a given tag. The tests still assert specific values (`"tag-alpha-dark"`, `"height=1pt"`) for that.

## Related

- [#84](https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/84) — Fix highlights spanning environment boundaries (introduced pylatexenc to production code)
- [#88](https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/88) — Migrate tests to AST validation (this work)
- [lua-ul-reference.md](lua-ul-reference.md) — Lua-UL package reference (defines `\highLight`, `\underLine`)
