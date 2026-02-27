# Paragraph Numbering Implementation Plan — Phase 4: Document Left Margin Display

**Goal:** Paragraph numbers visible in the left margin of the rendered document.

**Architecture:** A new function `inject_paragraph_attributes()` in `paragraph_map.py` walks the document HTML (same selectolax traversal, char-offset aligned) and adds `data-para="N"` attributes to block elements. Called in `_render_document_with_highlights()` before `ui.html()`. CSS `::before` pseudo-element displays the number, following the existing `data-speaker` pattern.

**Tech Stack:** selectolax, NiceGUI `ui.html()`, CSS `::before`

**Scope:** Phase 4 of 7 from original design

**Codebase verified:** 2026-02-27

---

## Acceptance Criteria Coverage

This phase implements and tests:

### paragraph-numbering-191.AC4: Paragraph numbers display in document left margin
- **paragraph-numbering-191.AC4.1 Success:** Auto-numbered document shows sequential numbers in left margin
- **paragraph-numbering-191.AC4.2 Success:** Source-numbered document shows source numbers in left margin
- **paragraph-numbering-191.AC4.3 Edge:** Margin numbers don't overlap with document content

---

## Reference Files

The executor MUST read these before implementing:
- `src/promptgrimoire/input_pipeline/paragraph_map.py` — Phase 2 output, shared traversal constants
- `src/promptgrimoire/pages/annotation/document.py` — `_render_document_with_highlights()` (~line 176), `ui.html()` call (~line 250)
- `src/promptgrimoire/pages/annotation/css.py` — `_PAGE_CSS` constant (~line 28), `data-speaker` CSS pattern
- `src/promptgrimoire/input_pipeline/html_input.py` — traversal constants `_BLOCK_TAGS`, `_STRIP_TAGS`, `_WHITESPACE_RUN`
- `CLAUDE.md` — testing conventions

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Create `inject_paragraph_attributes()` function

**Verifies:** paragraph-numbering-191.AC4.1, AC4.2

**Files:**
- Modify: `src/promptgrimoire/input_pipeline/paragraph_map.py`
- Modify: `src/promptgrimoire/input_pipeline/__init__.py` (export new function)

**Implementation:**

Add to `paragraph_map.py`:

```python
def inject_paragraph_attributes(html: str, paragraph_map: dict[str, int]) -> str:
```

This function:
1. Parses HTML with `LexborHTMLParser`
2. Walks the DOM with the same traversal as `build_paragraph_map()` (identical char-offset accounting)
3. At each block element whose char offset is a key in `paragraph_map`, adds `data-para="N"` attribute to that element
4. Returns the modified HTML string via `tree.html` (selectolax serialisation)

If `paragraph_map` is empty, return the HTML unchanged (no DOM parsing overhead).

**Key constraint:** The traversal must use the same char-offset logic as `build_paragraph_map()`. The block element identified at offset `k` must be the same element that was numbered at offset `k` during map building.

**For `<br><br>+` pseudo-paragraphs:** These don't have a wrapping block element to attach `data-para` to. Option: inject a `<span data-para="N">` wrapper around the text following the `<br><br>` sequence. The CSS `::before` works on any element with the attribute.

Export from `__init__.py`.

**Verification:**
```bash
uvx ty check
```

**Commit:** `feat: add inject_paragraph_attributes() for pre-render attribute injection`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add paragraph number CSS

**Verifies:** paragraph-numbering-191.AC4.1, AC4.2, AC4.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/css.py` (~lines 28-40, `.doc-container` block, and new rules)

**Implementation:**

Add CSS rules to `_PAGE_CSS`:

1. **Increase left padding** on `.doc-container` to make room for numbers:
   ```css
   .doc-container {
       padding-left: 3.5rem;  /* Was 1rem — extra space for paragraph numbers */
   }
   ```

2. **Paragraph number `::before` pseudo-element:**
   ```css
   .doc-container [data-para] {
       position: relative;
   }
   .doc-container [data-para]::before {
       content: attr(data-para);
       position: absolute;
       left: -3rem;
       width: 2.5rem;
       text-align: right;
       font-family: "Fira Code", "Consolas", monospace;
       font-size: 0.75rem;
       color: #999;
       line-height: inherit;
       user-select: none;
       pointer-events: none;
   }
   ```

**Key details:**
- `position: absolute` + `left: -3rem` places numbers in the left padding area
- `user-select: none` prevents numbers from being selected when copying text
- `pointer-events: none` prevents numbers from interfering with text selection
- `text-align: right` aligns multi-digit numbers neatly
- Monospace font for consistent number width
- Grey colour (`#999`) — subtle, doesn't compete with document text
- `line-height: inherit` — aligns with the document's line height

**Verification:**
```bash
uvx ty check
```

**Commit:** `feat: add CSS for paragraph number margin display`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Wire injection into document rendering

**Verifies:** paragraph-numbering-191.AC4.1, AC4.2

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/document.py` (~line 250, `ui.html()` call)

**Implementation:**

In `_render_document_with_highlights()`, before the `ui.html()` call, inject paragraph attributes:

```python
from promptgrimoire.input_pipeline.paragraph_map import inject_paragraph_attributes

# Before: ui.html(doc.content, sanitize=False)
# After:
rendered_html = inject_paragraph_attributes(doc.content, doc.paragraph_map)
ui.html(rendered_html, sanitize=False)
```

The `doc.paragraph_map` comes from the `WorkspaceDocument` record loaded earlier in the function. If the map is empty `{}`, the function returns content unchanged.

**Verification:**
```bash
uvx ty check
```

**Commit:** `feat: wire paragraph attribute injection into document rendering`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_4 -->
### Task 4: Unit tests for attribute injection

**Verifies:** paragraph-numbering-191.AC4.1, AC4.2, AC4.3

**Files:**
- Modify: `tests/unit/input_pipeline/test_paragraph_map.py` (add to existing file from Phase 2)

**Testing:**

Add test class `TestInjectParagraphAttributes`:

- AC4.1: Auto-numbered HTML (`<p>A</p><p>B</p><p>C</p>`) with map `{"0": 1, "2": 2, "4": 3}` → output HTML has `data-para="1"`, `data-para="2"`, `data-para="3"` on the `<p>` elements
- AC4.2: Source-numbered HTML (AustLII `<li value="5">`) with map `{"0": 5}` → output has `data-para="5"` on the `<li>`
- AC4.3: Verify the output HTML does NOT add attributes to headers (`<h1>`) or elements not in the map — **Note:** AC4.3 (visual overlap check) cannot be fully verified by unit tests; the CSS-level non-overlap is verified via manual UAT below
- Empty map `{}` → returns HTML unchanged
- Verify the `data-para` values are strings (CSS `attr()` reads string values)

**Verification:**
```bash
uv run pytest tests/unit/input_pipeline/test_paragraph_map.py -v
```
Expected: All tests pass (Phase 2 + Phase 4 tests).

**Commit:** `test: add tests for paragraph attribute injection`
<!-- END_TASK_4 -->

---

## UAT Steps

1. [ ] Run unit tests: `uv run pytest tests/unit/input_pipeline/test_paragraph_map.py -v` — all pass (Phase 2 + Phase 4 tests)
2. [ ] Type check clean: `uvx ty check`
3. [ ] Start the app: `uv run python -m promptgrimoire`
4. [ ] Open a workspace with a document that has a populated `paragraph_map` (from Phase 3 paste-in)
5. [ ] Verify: sequential paragraph numbers appear in the left margin (AC4.1)
6. [ ] Open a workspace with an AustLII document (source-numbered) — verify: source numbers appear in left margin (AC4.2)
7. [ ] Verify: margin numbers do not overlap with document content — numbers sit in the left padding area, text starts after the number column (AC4.3)
8. [ ] Verify: numbers are NOT selectable when copying document text (CSS `user-select: none`)

## Evidence Required
- [ ] Test output showing all paragraph map tests green (Phase 2 + Phase 4)
- [ ] Screenshot showing margin numbers on an auto-numbered document
- [ ] Screenshot showing margin numbers on a source-numbered document
- [ ] Visual confirmation that numbers don't overlap content
