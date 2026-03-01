# Paragraph Numbering Implementation Plan — Phase 2: Mapping Builder

**Goal:** Pure function that walks document HTML and produces a char-offset-to-paragraph-number mapping, plus auto-detection of source numbering.

**Architecture:** New file `paragraph_map.py` in `input_pipeline/` mirrors the canonical selectolax traversal from `html_input.py` but additionally tracks paragraph boundaries. Two modes: auto-number (sequential) and source-number (`<li value>` attributes). A detection function inspects HTML to recommend the mode.

**Tech Stack:** selectolax (LexborHTMLParser), same traversal as `extract_text_from_html()`

**Scope:** Phase 2 of 7 from original design

**Codebase verified:** 2026-02-27

---

## Acceptance Criteria Coverage

This phase implements and tests:

### paragraph-numbering-191.AC1: Auto-numbered documents get sequential paragraph numbers
- **paragraph-numbering-191.AC1.1 Success:** Plain prose document (`<p>` elements) gets sequential numbers starting at 1
- **paragraph-numbering-191.AC1.2 Success:** Document with mixed block elements (`<p>`, `<blockquote>`, `<li>`) numbers all of them sequentially
- **paragraph-numbering-191.AC1.3 Success:** `<br><br>+` sequences within a block create new paragraph numbers
- **paragraph-numbering-191.AC1.4 Edge:** Single `<br>` within a block does NOT create a new paragraph number
- **paragraph-numbering-191.AC1.5 Edge:** Headers (`<h1>`-`<h6>`) are skipped — not numbered
- **paragraph-numbering-191.AC1.6 Edge:** Empty/whitespace-only blocks are skipped — not numbered
- **paragraph-numbering-191.AC1.7 Edge:** Pasted markdown (converts to `<br>`-heavy HTML) produces sensible numbering

### paragraph-numbering-191.AC2: Source-numbered documents use `<li value>` attributes
- **paragraph-numbering-191.AC2.1 Success:** AustLII document with `<li value="1">` through `<li value="42">` shows those numbers
- **paragraph-numbering-191.AC2.2 Success:** Gaps in source numbering are preserved (e.g. values 1, 2, 5, 6)
- **paragraph-numbering-191.AC2.3 Edge:** Non-numbered block elements between numbered `<li>` items have no paragraph number

### paragraph-numbering-191.AC3: Auto-detection on paste-in (partial — detection function only)
- **paragraph-numbering-191.AC3.1 Success:** HTML with 2+ `<li value>` elements detected as source-numbered
- **paragraph-numbering-191.AC3.2 Success:** HTML with 0-1 `<li value>` elements detected as auto-numbered

### paragraph-numbering-191.AC8: Char-offset alignment
- **paragraph-numbering-191.AC8.1 Success:** Mapping builder char offsets match `extract_text_from_html()` output positions exactly

---

## Reference Files

The executor MUST read these before implementing:
- `src/promptgrimoire/input_pipeline/html_input.py` — canonical traversal logic (`extract_text_from_html` at ~line 149, `walk_and_map` at ~line 254, `_BLOCK_TAGS` at ~line 37, `_WHITESPACE_RUN` regex, `_STRIP_TAGS` set)
- `tests/unit/input_pipeline/test_text_extraction.py` — existing tests showing expected char-offset behavior
- `CLAUDE.md` — testing conventions, async fixture rule

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Create `paragraph_map.py` with `build_paragraph_map()`

**Verifies:** paragraph-numbering-191.AC1.1, AC1.2, AC1.3, AC1.4, AC1.5, AC1.6, AC2.1, AC2.2, AC2.3, AC8.1

**Files:**
- Create: `src/promptgrimoire/input_pipeline/paragraph_map.py`
- Modify: `src/promptgrimoire/input_pipeline/__init__.py` (export new functions)

**Implementation:**

Create `paragraph_map.py` with function:

```python
def build_paragraph_map(html: str, *, auto_number: bool = True) -> dict[int, int]:
```

This function mirrors the selectolax traversal from `extract_text_from_html()` in `html_input.py`. It MUST use identical logic:
- Same `LexborHTMLParser` setup (`tree.body` or `tree.root`)
- Same `node.child`/`node.next` sibling walk
- Same `_STRIP_TAGS` skipping (script, style, noscript, template)
- Same `_BLOCK_TAGS` whitespace-only text node skipping
- Same `_WHITESPACE_RUN` collapsing
- Same `<br>` → single `"\n"` character accounting

Import shared constants from `html_input.py`:
```python
from promptgrimoire.input_pipeline.html_input import (
    _BLOCK_TAGS,
    _STRIP_TAGS,
    _WHITESPACE_RUN,
)
```

**Paragraph-numbering elements** (new constant in this file):
```python
_PARA_TAGS = frozenset(("p", "li", "blockquote", "div"))
```
These are the block elements that receive paragraph numbers in auto-number mode. Headers (`h1`-`h6`) are explicitly excluded per AC1.5.

**Auto-number mode (`auto_number=True`):**
- Track `current_para = 0` and `char_offset = 0`
- When entering a `_PARA_TAGS` element that contains non-whitespace text: increment `current_para`, record `{char_offset_at_first_text: current_para}`
- Track consecutive `<br>` siblings. When 2+ `<br>` are followed by text content: increment `current_para`, record new mapping entry at the text that follows
- Skip elements with only whitespace content (AC1.6)
- Skip headers entirely — they don't get numbers (AC1.5)

**Source-number mode (`auto_number=False`):**
- Walk identically for char-offset tracking
- When encountering `<li>` element with `value` attribute: extract `int(value)`, record `{char_offset_at_first_text: para_number}`
- Non-numbered elements get no entry in the map (AC2.3)
- Gaps in numbering are preserved naturally (AC2.2)

**Return:** `dict[int, int]` mapping char-offset-of-block-start to paragraph number.

**Critical constraint:** The char offsets in the returned dict must be valid indices into `extract_text_from_html(html)` output. Every key `k` must satisfy `0 <= k < len(extract_text_from_html(html))`.

**Verification:**
```bash
uvx ty check
uv run ruff check src/promptgrimoire/input_pipeline/paragraph_map.py
```

**Commit:** `feat: add build_paragraph_map() with auto-number and source-number modes`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add `detect_source_numbering()`

**Verifies:** paragraph-numbering-191.AC3.1, AC3.2

**Files:**
- Modify: `src/promptgrimoire/input_pipeline/paragraph_map.py`

**Implementation:**

Add to `paragraph_map.py`:

```python
def detect_source_numbering(html: str) -> bool:
```

Uses selectolax to parse HTML and count `<li>` elements with explicit `value` attributes. Returns `True` if 2+ found (threshold from design AC3.1/AC3.2).

Implementation: parse with `LexborHTMLParser`, use `tree.css("li[value]")` selector to find matching elements, return `len(matches) >= 2`.

Export from `__init__.py`.

**Verification:**
```bash
uvx ty check
```

**Commit:** `feat: add detect_source_numbering() for auto-detection of AustLII documents`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Unit tests for mapping builder and detection

**Verifies:** paragraph-numbering-191.AC1.1, AC1.2, AC1.3, AC1.4, AC1.5, AC1.6, AC1.7, AC2.1, AC2.2, AC2.3, AC3.1, AC3.2, AC8.1

**Files:**
- Create: `tests/unit/input_pipeline/test_paragraph_map.py`

**Testing:**

Tests must verify each AC listed above. Organise as test classes:

**`TestAutoNumberParagraphs`:**
- AC1.1: `<p>First</p><p>Second</p><p>Third</p>` → map has 3 entries, values 1, 2, 3
- AC1.2: `<p>Text</p><blockquote>Quote</blockquote><ul><li>Item</li></ul>` → sequential numbers across element types
- AC1.3: `<p>Line one<br><br>Line two</p>` → 2 paragraph numbers (br-br split)
- AC1.4: `<p>Line one<br>Line two</p>` → 1 paragraph number (single br, no split)
- AC1.5: `<h1>Title</h1><p>Body</p>` → only body gets a number (header skipped)
- AC1.6: `<p>   </p><p>Real content</p>` → only "Real content" gets a number
- AC1.7: Markdown-style HTML with `<br><br>` breaks → sensible numbering

**`TestSourceNumberParagraphs`:**
- AC2.1: `<ol><li value="1">...</li>...<li value="42">...</li></ol>` → map entries with values 1-42
- AC2.2: `<ol><li value="1">...</li><li value="5">...</li></ol>` → gap preserved (1, 5)
- AC2.3: `<ol><li value="1">...</li></ol><p>Unnumbered</p>` → paragraph block has no entry

**`TestDetectSourceNumbering`:**
- AC3.1: HTML with 3 `<li value>` elements → returns `True`
- AC3.2: HTML with 0 or 1 `<li value>` elements → returns `False`

**`TestCharOffsetAlignment`:**
- AC8.1: For several HTML samples, verify every key in `build_paragraph_map()` output is a valid index into `extract_text_from_html()` output AND that the character at that index is the first char of the expected block element's text content

**Verification:**
```bash
uv run pytest tests/unit/input_pipeline/test_paragraph_map.py -v
```
Expected: All tests pass.

**Commit:** `test: add comprehensive tests for paragraph mapping builder`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

---

## UAT Steps

1. [ ] Run unit tests: `uv run pytest tests/unit/input_pipeline/test_paragraph_map.py -v` — all pass
2. [ ] Start the app: `uv run python -m promptgrimoire`
3. [ ] No visible change yet (mapping builder exists but is not wired into save path)

## Evidence Required
- [ ] Test output showing all paragraph map tests green
- [ ] Type check clean: `uvx ty check`
