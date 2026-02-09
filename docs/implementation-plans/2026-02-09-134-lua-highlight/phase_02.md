# 134-lua-highlight Implementation Plan — Phase 2: Implement pre-Pandoc highlight span insertion

**Goal:** Create `highlight_spans.py` with `compute_highlight_spans()` that transforms HTML + highlight list into HTML with `<span data-hl="..." data-colors="..." data-annots="...">` elements, pre-split at block boundaries for Pandoc safety.

**Architecture:** Reuse the character-position-to-DOM-node mapping from `input_pipeline/html_input.py`. Compute non-overlapping regions from overlapping highlights (same concept as `build_regions()` but operating on character ranges). Insert flat `<span>` elements with comma-separated attribute lists. Split spans at HTML block boundaries because Pandoc silently destroys cross-block spans (E5 experiment proved this).

**Tech Stack:** Python 3.14, selectolax (existing dependency)

**Scope:** Phase 2 of 4 from original design

**Codebase verified:** 2026-02-09

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 134-lua-highlight.AC1: Pre-Pandoc region computation (DoD items 1, 6)
- **134-lua-highlight.AC1.1 Success:** Given overlapping highlights spanning a block boundary (`<h1>` into `<p>`), the HTML span insertion produces non-overlapping `<span>` elements pre-split at the block boundary, each with `data-hl` listing active highlight indices and `data-colors` listing active colours.
- **134-lua-highlight.AC1.2 Success:** Given 3+ overlapping highlights on the same text, the span carries `data-hl="0,1,2"` and `data-colors="blue,orange,green"` (comma-separated, matching input order).
- **134-lua-highlight.AC1.3 Success:** Given a highlight that doesn't cross any block boundary, a single `<span>` is emitted wrapping the full range.
- **134-lua-highlight.AC1.4 Success:** Given text with no highlights, no `<span>` elements are inserted.
- **134-lua-highlight.AC1.5 Failure:** Given a cross-block highlight, the span is NOT left crossing the block boundary (Pandoc would silently destroy it).

---

## Design Decisions

1. **New `PANDOC_BLOCK_ELEMENTS` constant** includes `p`, `h1`–`h6`, and all structural block elements. Separate from `_BLOCK_TAGS` in `html_input.py` which serves whitespace collapsing.
2. **`highlight_spans.py` lives in `export/`** — it's Pandoc-specific export preparation, not general input processing.
3. **Imports `walk_and_map` and `extract_text_from_html` from `html_input.py`** to reuse character-position mapping rather than duplicating. **Note:** `_walk_and_map` is currently a private function (underscore prefix). As part of Task 1, rename it to `walk_and_map` (remove underscore) to make it a public function of `html_input.py`, since it is now used by two modules. Update the existing call site in `html_input.py` accordingly.

---

**TDD note:** Tasks 1-2 build the implementation, Task 3 writes all tests. The implementor SHOULD write tests incrementally during Tasks 1-2 (e.g., test the region algorithm as soon as Task 1 is committed, then add block-splitting tests in Task 2). Task 3 ensures complete AC coverage and edge cases. If the implementor prefers strict TDD, they may write failing tests before each implementation step within the subcomponent.

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Create `highlight_spans.py` with region computation algorithm

**Verifies:** 134-lua-highlight.AC1.2, 134-lua-highlight.AC1.3, 134-lua-highlight.AC1.4

**Files:**
- Create: `src/promptgrimoire/export/highlight_spans.py`

**Implementation:**

**First**, rename `_walk_and_map` to `walk_and_map` in `src/promptgrimoire/input_pipeline/html_input.py` (remove the leading underscore). Update the single existing call site within the same file (`insert_markers_into_dom` calls it at line ~725). This makes it a public function since it is now consumed by two modules.

**Then**, create `src/promptgrimoire/export/highlight_spans.py` with:

1. **`PANDOC_BLOCK_ELEMENTS`** — frozenset of HTML tag names that Pandoc treats as block-level. Must include: `p`, `h1`, `h2`, `h3`, `h4`, `h5`, `h6`, `blockquote`, `div`, `li`, `ul`, `ol`, `table`, `tr`, `td`, `th`, `section`, `article`, `aside`, `header`, `footer`, `figure`, `figcaption`, `pre`, `dl`, `dt`, `dd`.

2. **`compute_highlight_spans(html: str, highlights: list[dict[str, Any]], tag_colours: dict[str, str], word_to_legal_para: dict[int, int | None] | None = None) -> str`** — main entry point. Takes:
   - `html`: clean HTML (no char spans)
   - `highlights`: list of highlight dicts with `start_char`, `end_char`, `tag`, `author`, `para_ref`, `text`, `comments`
   - `tag_colours`: mapping of tag slug → hex colour (e.g. `{"jurisdiction": "#3366cc"}`)
   - `word_to_legal_para`: optional mapping of char index → legal paragraph number, used to resolve `para_ref` for annotation margin notes. When provided, each highlight's `start_char` is looked up in this mapping to determine its paragraph reference, which is then passed to `format_annot_latex()` (Phase 4 Task 1) when building the `data-annots` attribute.

   Returns HTML with `<span>` elements inserted. If `highlights` is empty, returns `html` unchanged.

3. **Region computation logic** (internal):
   - Sort highlights by `start_char`
   - Collect all boundary points: every `start_char` and `end_char` from all highlights
   - At each boundary, compute the set of active highlights
   - Each contiguous range with a constant active set becomes one region
   - For each region, emit a `<span>` with:
     - `data-hl="0,1,2"` — comma-separated highlight indices (from sorted order)
     - `data-colors="tag-jurisdiction-light,tag-evidence-light"` — comma-separated LaTeX colour names derived from tag slugs via `tag_colours` dict. Use the naming convention `tag-{slug}-light` / `tag-{slug}-dark`.
     - `data-annots='[{"tag":"jurisdiction","author":"Alice","para_ref":5}]'` — JSON array with annotation metadata, only for the LAST span of each highlight (where ANNMARKER would have gone). Only include if there are annotations to render.

4. **Imports needed:**
   - `from __future__ import annotations`
   - `import json`
   - `from typing import Any`
   - `from selectolax.parser import HTMLParser` (for DOM manipulation)
   - `from promptgrimoire.input_pipeline.html_input import walk_and_map, extract_text_from_html` (note: `_walk_and_map` is renamed to `walk_and_map` as part of this task — see Design Decision 3)

**Key algorithm detail:** The region computation is similar to `build_regions()` in `latex.py` but operates on character ranges rather than tokens. Instead of scanning a token stream, build an event list of (char_position, highlight_index, "start"|"end") tuples, sort by position, then sweep through creating regions where the active set is constant.

**Testing:**

Tests in Task 3 below.

**Commit:** `feat: add highlight_spans.py with compute_highlight_spans region algorithm`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add block boundary pre-splitting

**Verifies:** 134-lua-highlight.AC1.1, 134-lua-highlight.AC1.5

**Files:**
- Modify: `src/promptgrimoire/export/highlight_spans.py`

**Implementation:**

After computing regions (character ranges with active highlight sets), split any region that crosses a block boundary.

The approach:
1. After `_walk_and_map` gives us character positions and their DOM nodes, identify the character positions where block boundaries occur. A block boundary is the character position at the start of a text node that is a direct child (or descendant) of a `PANDOC_BLOCK_ELEMENTS` tag, where the preceding character was in a different block element.
2. For each region, check if it crosses any block boundary. If so, split it at each boundary — producing multiple spans with the same `data-hl` and `data-colors` but covering different character ranges within different block elements.
3. The `data-annots` attribute goes only on the LAST sub-span of the split (the one nearest the end of the highlight).

**DOM insertion approach:** After computing all split regions, walk the HTML DOM with selectolax. For each region, find the text node(s) it covers and wrap the relevant text in a `<span>`. Since selectolax is read-only for tree manipulation, use a string-based insertion approach similar to `insert_markers_into_dom` — compute byte offsets and insert `<span>` open/close tags back-to-front.

**Testing:**

Tests in Task 3 below.

**Commit:** `feat: add block boundary pre-splitting to compute_highlight_spans`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Write tests for compute_highlight_spans

**Verifies:** 134-lua-highlight.AC1.1, 134-lua-highlight.AC1.2, 134-lua-highlight.AC1.3, 134-lua-highlight.AC1.4, 134-lua-highlight.AC1.5

**Files:**
- Create: `tests/unit/export/test_highlight_spans.py`

**Testing:**

Create test file verifying each AC:

- **AC1.1 test:** HTML with `<h1>Title</h1><p>Body text</p>`. Highlight spanning from the heading into the paragraph (e.g., char 0 to char 14). Assert: output contains TWO `<span>` elements — one inside the `<h1>` and one inside the `<p>` — each with `data-hl="0"` and appropriate `data-colors`.

- **AC1.2 test:** HTML `<p>overlapping text here</p>`. Three highlights covering overlapping ranges. Assert: the overlap region's `<span>` has `data-hl="0,1,2"` and `data-colors` listing all three colour names.

- **AC1.3 test:** HTML `<p>simple highlight</p>`. One highlight covering a substring that doesn't cross any block boundary. Assert: exactly one `<span>` wrapping the range.

- **AC1.4 test:** HTML `<p>no highlights</p>`. Empty highlight list. Assert: output is identical to input (no `<span>` elements added).

- **AC1.5 test (failure mode):** HTML `<h2>Heading</h2><p>Body</p>`. Highlight spanning across both. Assert: NO single `<span>` crosses the `</h2><p>` boundary. Each block element gets its own `<span>`.

- **Additional edge case tests:**
  - CRLF in text (the CRLF char index bug, rewritten from `test_crlf_char_index_bug.py`)
  - HTML entities in highlighted range (`&amp;` etc.)
  - Adjacent non-overlapping highlights produce separate spans
  - Annotation metadata (`data-annots`) appears on the last span of a highlight

Run: `uv run pytest tests/unit/export/test_highlight_spans.py -v`
Expected: All tests pass.

**Commit:** `test: add tests for compute_highlight_spans AC1.1–AC1.5`
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->
