# CSS Custom Highlight API — Phase 2: JS Text Walker Module

**Goal:** Extract the validated JS text walker from the demo into a standalone static module, with automated JS/Python parity tests.

**Architecture:** Move JS functions from `highlight_api_demo.py` string constants into `static/annotation-highlight.js`. Parity tests use Playwright to run JS `walkTextNodes()` in a real browser and compare char counts against Python `extract_text_from_html()`. Edge-case fixtures created for AC7.2/AC7.3.

**Tech Stack:** JavaScript (browser), Playwright (parity testing), Python selectolax (server-side text extraction).

**Scope:** Phase 2 of 6 from original design.

**Codebase verified:** 2026-02-12

---

## Acceptance Criteria Coverage

This phase implements and tests:

### css-highlight-api.AC7: JS/Python text walker parity
- **css-highlight-api.AC7.1 Success:** For every `tests/fixtures/workspace_*.html` fixture, JS `walkTextNodes()` total char count equals Python `extract_text_from_html()` char count
- **css-highlight-api.AC7.2 Edge:** Fixtures containing `<br>` elements, nested tables, empty `<p>` tags, and `&nbsp;` entities produce matching counts
- **css-highlight-api.AC7.3 Edge:** Fixture with zero text content (empty HTML) produces 0 chars from both JS and Python

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create static/annotation-highlight.js

**Verifies:** None (infrastructure — provides the module that Task 2 tests)

**Files:**
- Create: `src/promptgrimoire/static/annotation-highlight.js`
- Modify: `src/promptgrimoire/pages/highlight_api_demo.py` — update to load from static file instead of inline JS constants

**Implementation:**

Create `annotation-highlight.js` containing the functions currently embedded in `highlight_api_demo.py`:

From `_TEXT_WALKER_JS` (lines 48-99):
- `SKIP_TAGS` constant (Set)
- `BLOCK_TAGS` constant (Set)
- `walkTextNodes(root)` — returns flat array of `{node, startChar, endChar}` objects (one per text node). Total char count is `result[result.length - 1].endChar` (or 0 if empty).

From `_APPLY_HIGHLIGHTS_JS` (lines 102-177):
- `charOffsetToRange(textNodes, startChar, endChar)` — returns `StaticRange`
- `findLocalOffset(textNode, collapsedOffset)` — maps collapsed offset to raw text position
- `applyHighlights(container, highlightData)` — registers highlights in `CSS.highlights`
- `region_priority(tag)` — returns highlight priority for a tag

From `_SELECTION_JS` (lines 180-236):
- `rangePointToCharOffset(textNodes, node, offset)` — converts DOM range point to flat char offset
- `countCollapsed(text, rawOffset)` — count collapsed whitespace characters
- `setupSelection(container)` — mouseup listener that emits `hl_demo_selection` events

All functions should be in the global scope (no ES modules) for compatibility with NiceGUI's `<script src="...">` loading.

Then update `highlight_api_demo.py` to load from the static file:
- Remove `_TEXT_WALKER_JS`, `_APPLY_HIGHLIGHTS_JS`, `_SELECTION_JS` string constants
- Replace `ui.add_body_html(f"<script>{all_js}</script>")` with `ui.add_body_html('<script src="/static/annotation-highlight.js"></script>')`
- Verify demo page still works (all highlighting and selection detection functional)

**Verification:**
Run: `uv run python -m promptgrimoire` then navigate to `/demo/highlight-api`
Expected: Demo page renders highlights and selection detection works identically to before

**Commit:** `refactor: extract JS text walker from demo into static/annotation-highlight.js`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: JS/Python parity tests with edge-case fixtures

**Verifies:** css-highlight-api.AC7.1, css-highlight-api.AC7.2, css-highlight-api.AC7.3

**Files:**
- Create: `tests/fixtures/workspace_edge_cases.html` (edge-case fixture for AC7.2)
- Create: `tests/fixtures/workspace_empty.html` (empty fixture for AC7.3)
- Create: `tests/integration/test_text_walker_parity.py`

**Implementation:**

**Edge-case fixture** (`workspace_edge_cases.html`): A small HTML document containing:
- `<br>` elements (both mid-paragraph and between blocks)
- Nested `<table>` with `<td>` content
- Empty `<p></p>` tags
- `&nbsp;` entities (both standalone and mixed with regular text)
- Whitespace-heavy sections (multiple spaces, tabs, newlines in source)

**Empty fixture** (`workspace_empty.html`): Minimal valid HTML with no text content (e.g. `<html><body></body></html>`).

**Parity test** (`test_text_walker_parity.py`):

The test is parameterised over all `tests/fixtures/workspace_*.html` files (glob pattern). For each fixture:

1. **Python side:** Read the HTML file, run `extract_text_from_html(html)`, get `len(result)` as the Python char count
2. **Playwright side:** Create a page, set the HTML as content via `page.set_content(html)`, inject `annotation-highlight.js` via `page.add_script_tag(path=...)`, run `page.evaluate("(() => { const nodes = walkTextNodes(document.body); return nodes.length ? nodes[nodes.length - 1].endChar : 0; })()")` to get JS char count
3. **Assert:** Python char count equals JS char count

Note on Playwright usage: These tests use `page.set_content()` to load fixtures directly — no running NiceGUI server needed. However, `page.evaluate()` is used here because this is an integration test validating JS/Python algorithm parity, not an E2E user interaction test. The "no JS injection" rule from docs/testing.md applies to E2E tests simulating user behaviour, not to integration tests that need to invoke JS functions directly.

The test file should use `pytest.mark.parametrize` with a fixture discovery function that globs `tests/fixtures/workspace_*.html`. Mark tests with `@pytest.mark.e2e` since they require Playwright browser.

**Testing:**

Tests must verify each AC listed above:
- css-highlight-api.AC7.1: Parameterised test passes for `workspace_lawlis_v_r.html` — JS and Python char counts match
- css-highlight-api.AC7.2: Parameterised test passes for `workspace_edge_cases.html` — char counts match despite `<br>`, nested tables, empty `<p>`, `&nbsp;`
- css-highlight-api.AC7.3: Parameterised test passes for `workspace_empty.html` — both return 0

**Verification:**
Run: `uv run pytest tests/integration/test_text_walker_parity.py -v`
Expected: All parameterised tests pass, each showing matching char counts

**Commit:** `test: add JS/Python text walker parity tests with edge-case fixtures`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
