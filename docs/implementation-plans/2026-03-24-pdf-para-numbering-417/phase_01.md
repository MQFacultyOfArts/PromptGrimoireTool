# PDF Paragraph Numbering — Phase 1: Paragraph Number Injection

**Goal:** Inject paragraph number markers into export HTML so they survive Pandoc conversion.

**Architecture:** New function `inject_paragraph_markers_for_export()` in `paragraph_map.py` converts `word_to_legal_para` to a string-keyed map, calls existing `inject_paragraph_attributes()` to add `data-para` DOM attributes, then regex-inserts `<span data-paranumber="N"></span>` after each opening tag with `data-para`. Wired into `convert_html_with_annotations()` in `pandoc.py` after `compute_highlight_spans()`.

**Tech Stack:** Python, selectolax (via existing `inject_paragraph_attributes()`), regex

**Scope:** Phase 1 of 5 from original design

**Codebase verified:** 2026-03-24

---

## Acceptance Criteria Coverage

This phase implements and tests:

### pdf-para-numbering-417.AC1: Left-margin paragraph numbers
- **pdf-para-numbering-417.AC1.1 Success:** HTML passed to Pandoc contains `<span data-paranumber="N">` at the start of each auto-numbered paragraph
- **pdf-para-numbering-417.AC1.2 Success:** No markers injected when `word_to_legal_para` is None (autonumbering off)
- **pdf-para-numbering-417.AC1.3 Success:** No markers injected for empty paragraph map
- **pdf-para-numbering-417.AC1.6 Edge:** Paragraphs with highlight spans at position 0 still get the paranumber marker before the highlight

---

## Reference Files for Subagents

- **Testing patterns:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/tests/unit/export/test_highlight_spans.py` (pure function tests with helpers, parametrize)
- **Testing guidelines:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/docs/testing.md`
- **Existing paragraph map tests:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/tests/unit/test_paragraph_map.py`
- **Project conventions:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/CLAUDE.md`

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Unit tests for `inject_paragraph_markers_for_export()`

**Verifies:** pdf-para-numbering-417.AC1.1, pdf-para-numbering-417.AC1.2, pdf-para-numbering-417.AC1.3, pdf-para-numbering-417.AC1.6

**Files:**
- Create: `tests/unit/export/test_paragraph_markers.py` (unit)

**Testing:**

Write failing tests first (TDD). Follow the pattern in `test_highlight_spans.py` — pure function tests with helper functions, no database.

Tests must verify each AC listed above:

- **pdf-para-numbering-417.AC1.1:** Given HTML with multiple paragraphs and a valid `word_to_legal_para` map, the returned HTML contains `<span data-paranumber="N"></span>` at the start of each auto-numbered paragraph (after the opening tag, before content). Verify with selectolax CSS selector `span[data-paranumber]` to extract markers and assert correct numbering.
- **pdf-para-numbering-417.AC1.2:** Given `word_to_legal_para=None`, the function returns the input HTML unchanged (identity check).
- **pdf-para-numbering-417.AC1.3:** Given `word_to_legal_para={}` (empty dict), the function returns the input HTML unchanged.
- **pdf-para-numbering-417.AC1.6:** Given HTML where a highlight `<span data-hl="...">` starts at character position 0 of a paragraph, call `inject_paragraph_markers_for_export()` and verify the `<span data-paranumber="N"></span>` appears before the highlight `<span>` in DOM order. Use selectolax to parse output and check child node ordering within the paragraph element.

Additional cases to cover:
- Single paragraph: one marker inserted
- Mixed content (paragraphs, blockquotes): markers on all block elements with data-para
- br-br pseudo-paragraphs: markers appear inside the `<span data-para="N">` wrapper

**Verification:**

Run: `uv run grimoire test run tests/unit/export/test_paragraph_markers.py`
Expected: Tests fail (function doesn't exist yet)

**Commit:** `test(export): add failing unit tests for paragraph marker injection (#417)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement `inject_paragraph_markers_for_export()` and wire up in pandoc.py

**Verifies:** pdf-para-numbering-417.AC1.1, pdf-para-numbering-417.AC1.2, pdf-para-numbering-417.AC1.3, pdf-para-numbering-417.AC1.6

**Files:**
- Modify: `src/promptgrimoire/input_pipeline/paragraph_map.py` (add new function after `inject_paragraph_attributes()`, ~line 550)
- Modify: `src/promptgrimoire/export/pandoc.py:373-374` (add call after `compute_highlight_spans()`)

**Implementation:**

**New function in `paragraph_map.py`:**

Create `inject_paragraph_markers_for_export(html: str, word_to_legal_para: dict[int, int | None] | None) -> str`:

1. Guard clause: if `word_to_legal_para` is `None` or empty, return `html` unchanged (AC1.2, AC1.3).
2. Convert `word_to_legal_para` to the `dict[str, int]` format expected by `inject_paragraph_attributes()`: `{str(k): v for k, v in word_to_legal_para.items() if v is not None}`. This uses the same paragraph map as the web view, ensuring PDF numbers match the on-screen display. Keys are stringified char offsets; `None` values (skipped elements) are filtered out.
3. Call `inject_paragraph_attributes(html, paragraph_map)` to add `data-para` attributes to block elements via selectolax DOM.
4. Regex-insert `<span data-paranumber="N"></span>` after each opening tag that has a `data-para="N"` attribute. The regex pattern matches `(<[^>]+\sdata-para="(\d+)"[^>]*>)` and replaces with `\1<span data-paranumber="\2"></span>`.
5. Return the modified HTML.

**Important details:**
- `word_to_legal_para` is `dict[int, int | None]` where keys are char offsets and values are paragraph numbers (or `None` for skipped elements). Using it directly (rather than re-deriving via `build_paragraph_map_for_json()`) ensures the PDF paragraph numbers always match the on-screen display.
- The regex operates on serialised HTML after `inject_paragraph_attributes()` completes, so `data-para` attributes are guaranteed to be present.
- `<span data-paranumber="N"></span>` is an empty span — its only purpose is to carry the attribute through Pandoc's AST for the Lua filter (Phase 2).
- The regex naturally handles br-br pseudo-paragraphs because `inject_paragraph_attributes()` wraps those in `<span data-para="N">`, which the regex also matches.

**Wire-up in `pandoc.py`:**

In `convert_html_with_annotations()`, after line 373 (after `compute_highlight_spans()` returns `span_html`) and before line 375 (filter list construction), add:

```python
# Inject paragraph number markers for PDF margin display
span_html = inject_paragraph_markers_for_export(span_html, word_to_legal_para)
```

Import `inject_paragraph_markers_for_export` from `promptgrimoire.input_pipeline.paragraph_map`.

**Verification:**

Run: `uv run grimoire test run tests/unit/export/test_paragraph_markers.py`
Expected: All tests pass

Run: `uv run grimoire test changed`
Expected: New and existing tests pass

**Commit:** `feat(export): inject paragraph number markers into export HTML (#417)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
