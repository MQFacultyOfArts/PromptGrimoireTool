# PDF Export Character Alignment — Phase 1: `insert_markers_into_dom` + Tests

**Goal:** Create the replacement marker insertion function with full test coverage, proving it agrees with `extract_text_from_html`.

**Architecture:** Two-pass DOM walk + string insertion. Walk the DOM with the same logic as `extract_text_from_html` to build a position map (char index → text node + offset), then insert marker strings into the serialised HTML at computed byte positions. Uses `node.html` for HTML-encoded text (for string matching) and `node.text_content` for decoded text (for character counting). Proven by `spike_two_pass.py` (13/13 tests pass).

**Tech Stack:** Python 3.14, selectolax (LexborHTMLParser), pytest

**Scope:** Phase 1 of 4 from original design

**Codebase verified:** 2026-02-08

---

## Acceptance Criteria Coverage

This phase implements and tests:

### pdf-export-char-alignment.AC3: Character index agreement
- **pdf-export-char-alignment.AC3.1 Success:** Round-trip property: for any HTML, `extract_text_from_html(html)[start:end]` equals the text between HLSTART/HLEND in `insert_markers_into_dom(html, highlights)` output
- **pdf-export-char-alignment.AC3.2 Success:** Multi-block HTML (whitespace between `</p><p>`) does not cause index drift
- **pdf-export-char-alignment.AC3.3 Success:** `<br>` tags counted as single newline character (matching `extract_text_from_html`)
- **pdf-export-char-alignment.AC3.4 Success:** Whitespace runs collapsed to single space (matching `extract_text_from_html`)
- **pdf-export-char-alignment.AC3.5 Success:** Formatted spans (`<strong>`, `<em>`, etc.) preserved in output, markers at correct positions across tag boundaries

### pdf-export-char-alignment.AC1: PDF includes source document with annotations (partial)
- **pdf-export-char-alignment.AC1.3 Success:** Highlights appear at correct character positions (marker text matches `extract_text_from_html` char slice)
- **pdf-export-char-alignment.AC1.4 Success:** CJK/Unicode content highlights at correct positions (characters indexed individually, not by byte)

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Create shared marker constants module

**Verifies:** None (infrastructure)

**Files:**
- Create: `src/promptgrimoire/export/marker_constants.py`

**Implementation:**

Create a new module that holds the marker format strings and compiled patterns, currently defined at `src/promptgrimoire/export/latex.py:527-532`. The new module re-exports the same constants so both `latex.py` and the new `insert_markers_into_dom` can import from a single source.

```python
"""Marker format constants for annotation export.

These marker strings are inserted into HTML at character positions matching
the UI's extract_text_from_html character indexing. They survive Pandoc
HTML-to-LaTeX conversion as plain text, then get replaced with LaTeX
annotation commands by the marker pipeline.

Shared between:
- input_pipeline/html_input.py (insert_markers_into_dom)
- export/latex.py (marker replacement pipeline)
"""

from __future__ import annotations

import re

# Unique marker format that survives Pandoc conversion
# Format: ANNMARKER{index}ENDMARKER for annotation insertion point
# Format: HLSTART{index}ENDHL and HLEND{index}ENDHL for highlight boundaries
MARKER_TEMPLATE = "ANNMARKER{}ENDMARKER"
MARKER_PATTERN = re.compile(r"ANNMARKER(\d+)ENDMARKER")
HLSTART_TEMPLATE = "HLSTART{}ENDHL"
HLEND_TEMPLATE = "HLEND{}ENDHL"
HLSTART_PATTERN = re.compile(r"HLSTART(\d+)ENDHL")
HLEND_PATTERN = re.compile(r"HLEND(\d+)ENDHL")
```

Note: The constants are public (no underscore prefix) because they are now a shared API. The private underscored copies in `latex.py` (lines 527-532) are intentionally left in place during this phase to avoid coupling Phase 1 to the export pipeline. **Phase 4 Task 2** deletes those private copies and updates the Lark grammar comment to reference this shared module, completing the single-source-of-truth migration.

**Verification:**

Run: `uv run ruff check src/promptgrimoire/export/marker_constants.py`
Expected: Clean (no errors)

Run: `uvx ty check`
Expected: Clean

**Commit:** `feat: add shared marker constants module`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement `insert_markers_into_dom`

**Verifies:** pdf-export-char-alignment.AC3.1, AC3.2, AC3.3, AC3.4, AC3.5, AC1.3, AC1.4

**Files:**
- Modify: `src/promptgrimoire/input_pipeline/html_input.py` (append after `extract_text_from_html` at line 451)
- Modify: `src/promptgrimoire/input_pipeline/__init__.py` (add export)

**Implementation:**

Add `insert_markers_into_dom` to `html_input.py` after `extract_text_from_html` (line 451). The function uses the proven two-pass approach from `spike_two_pass.py`:

**Pass 1 — DOM walk to build position map:**

Walk the DOM with the same logic as `extract_text_from_html` (same `_BLOCK_TAGS`, `_STRIP_TAGS`, `_WHITESPACE_RUN`, same `LexborHTMLParser`, same child/next iteration). For each text node visited, record:
- `html_text`: `node.html` (HTML-encoded, e.g. `A &amp; B`)
- `decoded_text`: `node.text_content` (decoded, e.g. `A & B`)
- `collapsed_text`: after `_WHITESPACE_RUN.sub(" ", decoded_text)`
- `char_start`: starting char index in the stream
- `char_end`: ending char index (exclusive)

**Pass 2 — Find text nodes in serialised HTML and insert markers:**

1. Search for each text node's `html_text` in the original HTML string sequentially (advancing search position to maintain document order)
2. For each highlight, find which text node contains `start_char` and `end_char`
3. Map collapsed-text offset to HTML byte offset using `_collapsed_to_html_offset()` (walks decoded and HTML text in parallel, handles entities via `_html_char_length()`)
4. Build list of `(byte_offset, marker_string)` insertions
5. Sort insertions by byte offset descending, insert back-to-front

**Contract:**

```python
def insert_markers_into_dom(
    html: str,
    highlights: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Insert annotation markers into HTML at correct character positions.

    Walks the DOM using the same logic as extract_text_from_html
    (same whitespace rules, same block/strip tags, same collapse).
    Inserts HLSTART/HLEND/ANNMARKER text into the serialised HTML at
    positions matching the char indices from extract_text_from_html.

    Args:
        html: Clean HTML (from doc.content, no char spans).
        highlights: List of highlight dicts with start_char, end_char, tag, etc.
            Supports both start_char/end_char and legacy start_word/end_word fields.

    Returns:
        (marked_html, ordered_highlights) — marked HTML with markers inserted,
        and highlights in marker order (same contract as _insert_markers_into_html).

    Raises:
        ValueError: If html is empty/None and highlights are non-empty.
    """
```

**Key helper functions** (private, same file):

- `_TextNodeInfo` — dataclass with `html_text`, `decoded_text`, `collapsed_text`, `char_start`, `char_end`
- `_walk_and_map(html)` — pass 1, returns `(chars, text_nodes)` — shares walk logic with `extract_text_from_html` via identical structure
- `_find_text_node_offsets(html, text_nodes)` — pass 2a, returns byte offsets of each text node in serialised HTML
- `_collapsed_to_html_offset(html_text, decoded_text, collapsed_offset)` — maps collapsed offset to HTML byte offset
- `_html_char_length(html_text, html_pos, decoded_char)` — determines entity byte length

Import marker constants from the new shared module:

```python
from promptgrimoire.export.marker_constants import (
    HLEND_TEMPLATE,
    HLSTART_TEMPLATE,
    MARKER_TEMPLATE,
)
```

**Backward compatibility:** Support `start_word`/`end_word` field names as aliases for `start_char`/`end_char` (matching existing `_insert_markers_into_html` behaviour at `latex.py:835-843`).

**Export in `__init__.py`:** Add `insert_markers_into_dom` to both the import block and `__all__`.

**Verification:**

Run: `uv run ruff check src/promptgrimoire/input_pipeline/html_input.py`
Expected: Clean

Run: `uvx ty check`
Expected: Clean

**Commit:** `feat: implement insert_markers_into_dom with two-pass approach`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Tests for `insert_markers_into_dom`

**Verifies:** pdf-export-char-alignment.AC3.1, AC3.2, AC3.3, AC3.4, AC3.5, AC1.3, AC1.4

**Files:**
- Create: `tests/unit/input_pipeline/test_insert_markers.py`

**Testing:**

Tests must verify each AC listed above. Adapt test cases from the proven spike (`spike_two_pass.py`, 13 tests) plus the existing `tests/unit/export/test_marker_insertion.py` patterns.

**AC3.1 — Round-trip property:**
For each test case, verify that `extract_text_from_html(html)[start:end]` equals the text extracted between HLSTART/HLEND markers in `insert_markers_into_dom(html, highlights)` output. This is the core correctness property.

Test cases to cover:

1. **Simple paragraph** — `<p>Hello world</p>`, highlight `[0:5]` → `"Hello"`
2. **Multi-paragraph** — `<p>Hello</p><p>World</p>`, two highlights
3. **Formatted spans** (AC3.5) — `<p>Hello <strong>bold</strong> text</p>`, highlight on `"bold"` — tags preserved, markers at correct positions
4. **Cross-tag boundary** (AC3.5) — `<p>Hello <strong>bold</strong> world</p>`, highlight spanning tag boundary
5. **Whitespace collapsing** (AC3.4) — `<p>Hello   world</p>`, highlight on collapsed text
6. **CJK characters** (AC1.4) — `<p>你好世界</p>`, highlight on `"你好"` — char-indexed, not byte-indexed
7. **`<br>` tag** (AC3.3) — `<p>Line one<br>Line two</p>`, highlight before br
8. **Block whitespace skipping** (AC3.2) — `<div>\n  <p>Hello</p>\n  <p>World</p>\n</div>`, whitespace between blocks doesn't drift indices
9. **Table content** — `<table><tr><td>Cell 1</td></tr></table>`
10. **Heading + paragraph** — `<h1>Title</h1><p>Body text</p>`
11. **HTML entities** (AC3.1 + AC1.3) — `<p>A &amp; B</p>`, highlight on `"A & B"` — entity byte length handled
12. **Multiple entities** — `<p>x &lt; y &amp; y &gt; z</p>`, highlight on single entity char
13. **Entity at highlight boundary** — `<p>Hello &amp; world</p>`, highlight starting at entity
14. **Empty highlights** — Returns unchanged HTML
15. **Empty HTML with highlights** — Raises `ValueError`
16. **Backward compat** — `start_word`/`end_word` fields work as aliases
17. **ANNMARKER present** — Verify annotation marker inserted at end of each highlight

For each test, extract text between HLSTART and HLEND markers, strip HTML tags, decode entities, collapse whitespace, and compare with `extract_text_from_html(html)[start:end]`. This is the round-trip property.

**Test patterns:** Follow existing patterns in `tests/unit/input_pipeline/test_char_spans.py` — plain class-based tests, no fixtures needed (pure functions).

**Verification:**

Run: `uv run pytest tests/unit/input_pipeline/test_insert_markers.py -v`
Expected: All tests pass

Run: `uv run test-debug`
Expected: No regressions

**Commit:** `test: add tests for insert_markers_into_dom`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
