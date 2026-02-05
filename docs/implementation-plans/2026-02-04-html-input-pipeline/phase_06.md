# HTML Input Pipeline - Phase 6: Export Integration

**Goal:** Update PDF export pipeline to work with new HTML-based content (with char spans) instead of `raw_content`.

**Architecture:** Strip char spans from `content` field before passing to LaTeX pipeline. Remove `raw_content` usage from export path. Optionally clean up migration shims in `latex.py`.

**Tech Stack:** selectolax (for span stripping), existing LaTeX pipeline

**Scope:** Phase 6 of 8 from original design

**Codebase verified:** 2026-02-05

---

## Codebase Verification Findings

| Assumption | Result | Actual |
|------------|--------|--------|
| pdf_export.py exists | ✓ Confirmed | `src/promptgrimoire/export/pdf_export.py` (330 lines) |
| raw_content usage | ✓ Confirmed | `annotation.py:1355` fetches from doc, passes to export |
| latex.py shims | ✓ Confirmed | Lines 809, 823, 1034 have `get("start_char", get("start_word", 0))` |
| #76 tests exist | ✓ Confirmed | `tests/integration/test_pdf_export.py` (265 lines, active) |
| E2E tests | + Found | `tests/e2e/test_pdf_export.py` (stubbed, needs fixture rewrite) |

**Export Pipeline Flow:**
```
annotation.py:1355 → raw_content fetched
                   ↓
pdf_export.py → preprocess or wrap in <p>
                   ↓
latex.py → insert markers, Pandoc → LaTeX
                   ↓
pdf.py → compile_latex() → PDF
```

**Critical Update:** After Phase 5, documents store HTML in `content` field (with char spans). Export must strip spans before processing.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Update export path to use content instead of raw_content

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py`

**Step 1: Find the _handle_pdf_export() function**

Look for the PDF export handler around line 1340-1400 in annotation.py. Find the line:

```python
raw_content = doc.raw_content if doc else ""
```

**Step 2: Update to strip char spans from content**

Replace the raw_content fetching with:

```python
from promptgrimoire.input_pipeline.html_input import strip_char_spans

# ... inside _handle_pdf_export() ...

# Get content and strip char spans for export
if doc:
    # Strip char span wrappers but keep document structure
    html_content = strip_char_spans(doc.content)
else:
    html_content = ""
```

**Step 3: Update the variable name in subsequent code**

Change all references from `raw_content` to `html_content` in this function. There should be:
- Debug logging (line ~1357): `raw_content length=` → `html_content length=`
- Export call (line ~1367): `html_content=raw_content` → `html_content=html_content`

**Step 4: Verify syntax**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run python -c "from promptgrimoire.pages.annotation import create_annotation_page; print('OK')"
```

Expected: Prints "OK"

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update text extraction for highlighting

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py`

**Step 1: Find text extraction code**

Find the line around 1003 that extracts characters for highlighting:

```python
_, state.document_chars = _process_text_to_char_spans(doc.raw_content)
```

**Step 2: Update to extract text from HTML content**

Since the content now has char spans, we can extract text directly. Add a helper function and update:

```python
from promptgrimoire.input_pipeline.html_input import extract_text_from_char_range

# Add helper to extract all characters from content
def _extract_all_chars_from_content(html_with_spans: str) -> list[str]:
    """Extract character list from HTML with char spans."""
    from selectolax.lexbor import LexborHTMLParser
    tree = LexborHTMLParser(html_with_spans)
    chars = []
    for span in tree.css('span.char[data-char-index]'):
        text = span.text()
        if text:
            chars.append(text)
    return chars

# Then update the extraction:
state.document_chars = _extract_all_chars_from_content(doc.content)
```

**Step 3: Verify highlighting still works**

This is critical for text selection. Run related tests:

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run pytest tests/unit/ -v -k "highlight or char" --tb=short
```

Expected: Tests pass

<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: Clean up migration shims in latex.py (optional)

**Files:**
- Modify: `src/promptgrimoire/export/latex.py`

**Step 1: Identify shim locations**

The shims are at three locations:
- Line 809: `h.get("start_char", h.get("start_word", 0))`
- Line 823: Same pattern
- Line 1034: Same pattern

**Step 2: Simplify to use only start_char/end_char**

Since Phase 2 renamed all fields to `start_char`/`end_char`, the fallbacks to `start_word`/`end_word` are no longer needed.

**At line 809:**

Change from:
```python
key=lambda h: (
    h.get("start_char", h.get("start_word", 0)),
    h.get("tag", ""),
),
```

To:
```python
key=lambda h: (
    h.get("start_char", 0),
    h.get("tag", ""),
),
```

**At line 823:**

Change from:
```python
start = int(h.get("start_char", h.get("start_word", 0)))
end = int(h.get("end_char", h.get("end_word", start + 1)))
```

To:
```python
start = int(h.get("start_char", 0))
end = int(h.get("end_char", start + 1))
```

**At line 1034:**

Change from:
```python
start_char = int(highlight.get("start_char", highlight.get("start_word", 0)))
end_char = int(highlight.get("end_char", highlight.get("end_word", start_char)))
```

To:
```python
start_char = int(highlight.get("start_char", 0))
end_char = int(highlight.get("end_char", start_char))
```

**Step 3: Update comments**

Remove or update comments that mention the migration:

Change:
```python
# Support both old field names (start_word) and new (start_char) for migration
```

To:
```python
# Use character indices for highlight positions
```

**Step 4: Verify export still works**

Run the PDF export integration tests:

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run pytest tests/integration/test_pdf_export.py -v
```

Expected: All tests pass

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Run full export test suite and commit

**Files:**
- None (testing only)

**Step 1: Run all PDF-related tests**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run pytest tests/integration/test_pdf_export.py tests/integration/test_pdf_pipeline.py -v
```

Expected: All tests pass

**Step 2: Run full test suite**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run test-debug
```

Expected: All tests pass (or only unrelated skips)

**Step 3: Manual export test**

Start the app and test PDF export:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run python -m promptgrimoire
```

Test:
1. Create workspace with HTML content (paste from chatbot)
2. Add some highlights
3. Click "Export PDF"
4. Verify PDF generates correctly with highlights

**Step 4: Commit**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && git add src/promptgrimoire/pages/annotation.py src/promptgrimoire/export/latex.py && git commit -m "refactor(export): update PDF pipeline to use content field

- Strip char spans from content before export
- Remove raw_content dependency in export path
- Update text extraction for highlighting
- Clean up start_word/end_word migration shims in latex.py

Part of #106 HTML input pipeline

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

---

## Phase 6 Completion Criteria

- [ ] Export uses `content` field instead of `raw_content`
- [ ] Char spans stripped before passing to LaTeX pipeline
- [ ] Text extraction for highlighting updated
- [ ] Migration shims in latex.py cleaned up (optional)
- [ ] All PDF export integration tests pass
- [ ] Manual PDF export test succeeds
- [ ] Changes committed

## Technical Notes

### Why Strip Char Spans?

The `content` field now stores HTML like:
```html
<p><span class="char" data-char-index="0">H</span><span class="char" data-char-index="1">e</span>...</p>
```

The export pipeline expects clean HTML:
```html
<p>Hello...</p>
```

`strip_char_spans()` uses selectolax's `unwrap()` to remove span wrappers while preserving text content.

### Export Pipeline After Phase 6

```
WorkspaceDocument.content (HTML with char spans)
           ↓
    strip_char_spans()
           ↓
    Clean HTML (no char spans)
           ↓
    preprocess_for_export() (remove chrome)
           ↓
    _insert_markers_into_html() (at char positions)
           ↓
    Pandoc → LaTeX → PDF
```

### Migration Shim Cleanup

The shims (`get("start_char", get("start_word", 0))`) were added during the word→char migration in Issue #76. Since Phase 2 renames all fields to `start_char`/`end_char`, the fallbacks are no longer needed.

**Risk:** If any old highlight data exists with `start_word` fields, it would break. However:
1. This is pre-launch, no production data
2. CRDT-stored highlights get rewritten when modified
3. Integration tests verify the new path works
