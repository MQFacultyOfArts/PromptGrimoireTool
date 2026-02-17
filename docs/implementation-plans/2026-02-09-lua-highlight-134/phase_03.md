# 134-lua-highlight Implementation Plan — Phase 3: Implement Pandoc Lua filter for highlight rendering

**Goal:** Create `filters/highlight.lua` that reads `hl`, `colors`, and `annots` span attributes and emits nested `\highLight`/`\underLine`/`\annot` LaTeX commands using the "one, two, many" stacking model.

**Architecture:** The Lua filter's `Span` callback reads comma-separated attribute values that Pandoc exposes (stripping the `data-` prefix from HTML). It generates nested `\highLight[tag-{slug}-light]{...}` wrappers and `\underLine[color=tag-{slug}-dark, ...]` commands using `pandoc.RawInline("latex", ...)`. Annotation metadata arrives pre-formatted as LaTeX via the `annots` attribute — the filter emits it as-is. Spans without `hl` attributes pass through unchanged.

**Tech Stack:** Lua (Pandoc filter API), Python 3.14 for integration tests

**Scope:** Phase 3 of 4 from original design

**Codebase verified:** 2026-02-09

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 134-lua-highlight.AC2: Pandoc Lua filter rendering (DoD items 1, 6, 7)
- **134-lua-highlight.AC2.1 Success:** Given a span with `hl="0"` and `colors="blue"`, the Lua filter emits `\highLight[tag-jurisdiction-light]{\underLine[color=tag-jurisdiction-dark, height=1pt, bottom=-3pt]{text}}` (single highlight tier).
- **134-lua-highlight.AC2.2 Success:** Given a span with `hl="0,1"` and `colors="blue,orange"`, the filter emits nested `\highLight` with stacked `\underLine` (2-highlight tier: 2pt outer, 1pt inner).
- **134-lua-highlight.AC2.3 Success:** Given a span with `hl="0,1,2"` and 3+ colours, the filter emits nested `\highLight` with single thick `\underLine[color=many-dark, height=4pt, bottom=-5pt]` (many tier).
- **134-lua-highlight.AC2.4 Success:** Given a span with `annot` attribute, the filter emits `\annot{tag-name}{\textbf{Tag Name}\par{\scriptsize Author}}` as `RawInline` after the highlighted content.
- **134-lua-highlight.AC2.5 Success:** Given a highlighted span inside a heading, Pandoc auto-wraps in `\texorpdfstring{}` (no special handling in filter). Verified by E2b experiment.
- **134-lua-highlight.AC2.6 Failure:** Given a span with NO `hl` attribute, the filter passes it through unchanged.

---

## Design Decisions

1. **Annotation metadata arrives pre-formatted as LaTeX** in `data-annots` attribute. Phase 2's `compute_highlight_spans()` calls a Python formatting function (adapted from `_format_annot()`) that produces complete `\annot{colour}{content}` strings. The Lua filter emits these as `RawInline("latex", annot_str)` without any LaTeX text escaping. This keeps all unicode-to-LaTeX escaping in Python (via `escape_unicode_latex()` from `unicode_latex.py`).
2. **`highlight.lua` is a standalone filter**, separate from `libreoffice.lua`. The highlight filter applies to all annotated documents regardless of origin platform. Phase 4 extends `convert_html_to_latex()` to accept multiple `--lua-filter` paths.
3. **Testing via Pandoc round-trip** — Python tests invoke `pandoc` as a subprocess with test HTML and the Lua filter, asserting on LaTeX output. This tests actual Pandoc behaviour (attribute stripping, `\texorpdfstring` wrapping) rather than a simulated Lua environment.

---

**TDD note:** Tasks 1-2 build the Lua filter incrementally, Task 3 writes Pandoc round-trip integration tests. The implementor SHOULD test each task's output manually during development (e.g., run `pandoc` with the filter against sample HTML). Task 3 provides the automated test suite covering all ACs. Lua filter testing requires Pandoc subprocess invocation, so pure unit tests aren't practical — integration tests in Task 3 are the primary verification mechanism.

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Create `highlight.lua` with stacking model

**Verifies:** 134-lua-highlight.AC2.1, 134-lua-highlight.AC2.2, 134-lua-highlight.AC2.3, 134-lua-highlight.AC2.6

**Files:**
- Create: `src/promptgrimoire/export/filters/highlight.lua`

**Implementation:**

Create `src/promptgrimoire/export/filters/highlight.lua` with a single `Span(el)` callback function:

1. **Guard clause:** If `el.attributes["hl"]` is nil, return `el` unchanged (AC2.6).

2. **Parse attributes:**
   - Split `el.attributes["colors"]` on commas to get a list of colour names (e.g., `{"tag-jurisdiction-light", "tag-evidence-light"}`). Each colour name has `-light` and `-dark` variants — the `colors` attribute contains the `-light` names.
   - Count the number of active highlights: `count = #colors_list`.

3. **Build highlight wrapping (innermost first):**
   - For each colour in `colors_list` (reversed — highest index first = innermost), emit `\highLight[{colour}]{` as `RawInline("latex", ...)` open and `}` as close.
   - The wrapping order is: outermost highlight (lowest index) wraps innermost (highest index), matching `generate_highlight_wrapper()` in `latex.py`.

4. **Build underline wrapping** based on count:
   - `count == 1`: Single underline: `\underLine[color={dark_colour}, height=1pt, bottom=-3pt]{...}`
     - Derive dark colour name by replacing `-light` with `-dark` in the colour name.
   - `count == 2`: Stacked underlines:
     - Outer (index 0): `\underLine[color={dark_0}, height=2pt, bottom=-5pt]{...}`
     - Inner (index 1): `\underLine[color={dark_1}, height=1pt, bottom=-3pt]{...}`
   - `count >= 3`: Single thick underline: `\underLine[color=many-dark, height=4pt, bottom=-5pt]{...}`

5. **Assemble result:** Build a `pandoc.List` with:
   - Underline open RawInline(s)
   - Highlight open RawInlines (outer to inner)
   - `el.content` (the original span content)
   - Highlight close RawInlines (inner to outer)
   - Underline close RawInline(s)
   - Return the list (replaces the Span in the AST)

**Helper function:** `split_csv(str)` — splits a comma-separated string into a Lua table using `string.gmatch(str, "[^,]+")`.

**Helper function:** `light_to_dark(colour_name)` — replaces `-light` suffix with `-dark` (e.g., `tag-jurisdiction-light` → `tag-jurisdiction-dark`). Uses `string.gsub(name, "-light$", "-dark")`.

**Testing:**

Tests in Task 3 below.

**Commit:** `feat: add highlight.lua Pandoc filter with stacking model`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add annotation emission to `highlight.lua`

**Verifies:** 134-lua-highlight.AC2.4, 134-lua-highlight.AC2.5

**Files:**
- Modify: `src/promptgrimoire/export/filters/highlight.lua`

**Implementation:**

After building the highlight+underline wrapped content (from Task 1), check for the `annots` attribute:

1. If `el.attributes["annots"]` is not nil and not empty:
   - The value is a pre-formatted LaTeX string (e.g., `\annot{tag-jurisdiction}{...}`), produced by Python's annotation formatter in Phase 2.
   - Append `pandoc.RawInline("latex", annots_value)` to the result list, AFTER the closing braces of the highlight/underline wrapping.

2. For AC2.5 (heading safety): No special handling needed. Pandoc automatically wraps the entire Span content (including our RawInline outputs) in `\texorpdfstring{}` when the span is inside a heading. This was validated in E2b experiment.

**Testing:**

Tests in Task 3 below.

**Commit:** `feat: add annotation emission to highlight.lua`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Write Pandoc round-trip integration tests for highlight.lua

**Verifies:** 134-lua-highlight.AC2.1, 134-lua-highlight.AC2.2, 134-lua-highlight.AC2.3, 134-lua-highlight.AC2.4, 134-lua-highlight.AC2.5, 134-lua-highlight.AC2.6

**Files:**
- Create: `tests/integration/test_highlight_lua_filter.py`

**Implementation:**

Create a test helper function `run_pandoc_with_filter(html: str) -> str` that:
1. Writes the HTML to a temporary file
2. Runs `pandoc -f html+native_divs -t latex --no-highlight --lua-filter <path_to_highlight.lua>` as a subprocess
3. Returns the LaTeX stdout

The filter path is `Path(__file__).parents[2] / "src" / "promptgrimoire" / "export" / "filters" / "highlight.lua"` (or computed relative to the project root).

**Testing:**

Tests must verify each AC:

- **AC2.1 test (single highlight):** HTML `<p><span data-hl="0" data-colors="tag-jurisdiction-light">highlighted text</span></p>`. Assert LaTeX contains `\highLight[tag-jurisdiction-light]{` and `\underLine[color=tag-jurisdiction-dark, height=1pt, bottom=-3pt]{`.

- **AC2.2 test (two highlights):** HTML with `data-hl="0,1" data-colors="tag-jurisdiction-light,tag-evidence-light"`. Assert: nested `\highLight` (two), stacked `\underLine` with outer 2pt/-5pt and inner 1pt/-3pt using both dark colours.

- **AC2.3 test (three+ highlights, many tier):** HTML with `data-hl="0,1,2" data-colors="tag-jurisdiction-light,tag-evidence-light,tag-ratio-light"`. Assert: three nested `\highLight` wrappers, single `\underLine[color=many-dark, height=4pt, bottom=-5pt]`.

- **AC2.4 test (annotation):** HTML with `data-hl="0" data-colors="tag-jurisdiction-light" data-annots="\\annot{tag-jurisdiction}{\\textbf{Jurisdiction}\\par{\\scriptsize Alice}}"`. Assert: LaTeX output contains the `\annot{...}` string AFTER the closing highlight braces.

- **AC2.5 test (heading):** HTML `<h2><span data-hl="0" data-colors="tag-jurisdiction-light">heading text</span></h2>`. Assert: LaTeX output contains `\texorpdfstring{` wrapping the highlighted content (Pandoc does this automatically).

- **AC2.6 test (no hl attribute):** HTML `<p><span class="other">plain text</span></p>`. Assert: no `\highLight` or `\underLine` in output. The span passes through unchanged.

- **Edge case: empty colors list.** HTML with `data-hl=""`. Assert: filter does not crash, no highlight wrapping applied.

Run: `uv run pytest tests/integration/test_highlight_lua_filter.py -v`
Expected: All tests pass.

**Commit:** `test: add Pandoc round-trip integration tests for highlight.lua AC2.1–AC2.6`
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->
