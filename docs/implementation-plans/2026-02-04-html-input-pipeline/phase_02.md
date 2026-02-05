# HTML Input Pipeline - Phase 2: CRDT/UI Rename (word → char)

**Goal:** Rename all word-based indexing to character-based indexing throughout CRDT and UI layers.

**Architecture:** Clean break from word-based to char-based indexing. Export layer already has migration shims.

**Tech Stack:** Python, pycrdt

**Scope:** Phase 2 of 8 from original design

**Codebase verified:** 2026-02-05

---

## Codebase Verification Findings

| Assumption | Result | Actual |
|------------|--------|--------|
| `annotation_doc.py` with word fields | ✓ Confirmed | `src/promptgrimoire/crdt/annotation_doc.py` - 14 locations |
| `_ClientState` in `annotation.py` | ✓ Confirmed | Lines 50-80, has `cursor_word`, `selection_start`, `selection_end` |
| Tests with word references | ✓ Confirmed | 50+ references across 7 test files |
| Export layer shims exist | ✓ Confirmed | `latex.py` lines 805-1035 have fallback patterns |

**Critical paths:**
- CRDT: `src/promptgrimoire/crdt/annotation_doc.py`
- UI: `src/promptgrimoire/pages/annotation.py`
- Tests: `tests/unit/test_annotation_doc.py`, `tests/unit/test_highlight_document_id.py`, `tests/integration/test_workspace_*.py`

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Rename word → char in CRDT layer (annotation_doc.py)

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py`

**Step 1: Update add_highlight() function (lines 196-230)**

Find the `add_highlight` function and rename parameters:

**Change from:**
```python
def add_highlight(
    self,
    start_word: int,
    end_word: int,
    tag: str,
    ...
```

**To:**
```python
def add_highlight(
    self,
    start_char: int,
    end_char: int,
    tag: str,
    ...
```

**Update docstring (lines 208-209) from:**
```python
        start_word: Starting word index (inclusive).
        end_word: Ending word index (exclusive).
```

**To:**
```python
        start_char: Starting character index (inclusive).
        end_char: Ending character index (exclusive).
```

**Update highlight_data dict (lines 227-228) from:**
```python
    highlight_data = {
        ...
        "start_word": start_word,
        "end_word": end_word,
        ...
    }
```

**To:**
```python
    highlight_data = {
        ...
        "start_char": start_char,
        "end_char": end_char,
        ...
    }
```

**Step 2: Update get_all_highlights() docstring and sort key (lines 301-304)**

**Change from:**
```python
        """Get all highlights, sorted by start_word."""
        ...
        return sorted(highlights, key=lambda h: h.get("start_word", 0))
```

**To:**
```python
        """Get all highlights, sorted by start_char."""
        ...
        return sorted(highlights, key=lambda h: h.get("start_char", 0))
```

**Step 3: Update get_highlights_for_document() docstring and sort key (lines 313-318)**

**Change from:**
```python
        """Get highlights for a specific document, sorted by start_word."""
        ...
        return sorted(doc_highlights, key=lambda h: h.get("start_word", 0))
```

**To:**
```python
        """Get highlights for a specific document, sorted by start_char."""
        ...
        return sorted(doc_highlights, key=lambda h: h.get("start_char", 0))
```

**Step 4: Update update_selection() function (lines 424-440)**

**Change from:**
```python
def update_selection(
    self,
    client_id: str,
    start_word: int | None,
    end_word: int | None,
    name: str,
    color: str,
) -> None:
    """Update the selection for a client.

    Args:
        ...
        start_word: Starting word index of selection (None to clear).
        end_word: Ending word index of selection (None to clear).
        ...
    """
    ...
    if start_word is not None and end_word is not None:
        selection = {"start_word": start_word, "end_word": end_word}
```

**To:**
```python
def update_selection(
    self,
    client_id: str,
    start_char: int | None,
    end_char: int | None,
    name: str,
    color: str,
) -> None:
    """Update the selection for a client.

    Args:
        ...
        start_char: Starting char index of selection (None to clear).
        end_char: Ending char index of selection (None to clear).
        ...
    """
    ...
    if start_char is not None and end_char is not None:
        selection = {"start_char": start_char, "end_char": end_char}
```

**Step 5: Verify CRDT module compiles**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run python -c "from promptgrimoire.crdt.annotation_doc import AnnotationDocument; print('OK')"
```

Expected: Prints "OK" without errors

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Rename word → char in UI layer (annotation.py)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py`

**Step 1: Update _ClientState class (lines 50-80)**

**Change from:**
```python
class _ClientState:
    """State for a connected client."""

    def __init__(self, callback: Any, color: str, name: str) -> None:
        self.callback = callback
        self.color = color
        self.name = name
        self.cursor_word: int | None = None
        self.selection_start: int | None = None
        self.selection_end: int | None = None

    def set_cursor(self, word_index: int | None) -> None:
        """Update cursor position."""
        self.cursor_word = word_index

    def to_cursor_dict(self) -> dict[str, Any]:
        """Get cursor as dict for CSS generation."""
        return {"word": self.cursor_word, "name": self.name, "color": self.color}

    def to_selection_dict(self) -> dict[str, Any]:
        """Get selection as dict for CSS generation."""
        return {
            "start_word": self.selection_start,
            "end_word": self.selection_end,
            "name": self.name,
            "color": self.color,
        }
```

**To:**
```python
class _ClientState:
    """State for a connected client."""

    def __init__(self, callback: Any, color: str, name: str) -> None:
        self.callback = callback
        self.color = color
        self.name = name
        self.cursor_char: int | None = None
        self.selection_start: int | None = None
        self.selection_end: int | None = None

    def set_cursor(self, char_index: int | None) -> None:
        """Update cursor position."""
        self.cursor_char = char_index

    def to_cursor_dict(self) -> dict[str, Any]:
        """Get cursor as dict for CSS generation."""
        return {"char": self.cursor_char, "name": self.name, "color": self.color}

    def to_selection_dict(self) -> dict[str, Any]:
        """Get selection as dict for CSS generation."""
        return {
            "start_char": self.selection_start,
            "end_char": self.selection_end,
            "name": self.name,
            "color": self.color,
        }
```

**Step 2: Update _build_highlight_css() (lines 272-281)**

**Change docstring and extraction from:**
```python
    # Each highlight has start_word, end_word
    ...
    start = int(hl.get("start_word", 0))
    end = int(hl.get("end_word", 0))
```

**To:**
```python
    # Each highlight has start_char, end_char
    ...
    start = int(hl.get("start_char", 0))
    end = int(hl.get("end_char", 0))
```

**Step 3: Update selection CSS extraction (lines 356-357)**

**Change from:**
```python
    start = sel.get("start_word")
    end = sel.get("end_word")
```

**To:**
```python
    start = sel.get("start_char")
    end = sel.get("end_char")
```

**Step 4: Update card building (lines 587-607)**

**Change from:**
```python
    start_word = highlight.get("start_word", 0)
    ...
    data-start-word="{start_word}" data-end-word="{end_word}"
```

**To:**
```python
    start_char = highlight.get("start_char", 0)
    ...
    data-start-char="{start_char}" data-end-char="{end_char}"
```

(Update variable names and HTML attributes throughout this section)

**Step 5: Update goto function parameters (line 652)**

**Change from:**
```python
    sc: int = start_word, ec: int = end_word
```

**To:**
```python
    sc: int = start_char, ec: int = end_char
```

**Step 6: Update add_highlight call (lines 782-797)**

**Change docstring from:**
```python
    # end_word is exclusive
```

**To:**
```python
    # end_char is exclusive
```

**Change function call from:**
```python
    start_word=start, end_word=end
```

**To:**
```python
    start_char=start, end_char=end
```

**Step 7: Verify UI module compiles**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run python -c "from promptgrimoire.pages.annotation import create_annotation_page; print('OK')"
```

Expected: Prints "OK" without errors

<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: Update unit tests for char-based indexing

**Files:**
- Modify: `tests/unit/test_annotation_doc.py`
- Modify: `tests/unit/test_highlight_document_id.py`
- Modify: `tests/unit/export/test_marker_insertion.py`

**Step 1: Update test_annotation_doc.py**

Search and replace all occurrences:
- `start_word=` → `start_char=`
- `end_word=` → `end_char=`
- `"start_word"` → `"start_char"`
- `"end_word"` → `"end_char"`

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && sed -i 's/start_word/start_char/g; s/end_word/end_char/g' tests/unit/test_annotation_doc.py
```

**Step 2: Update test_highlight_document_id.py**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && sed -i 's/start_word/start_char/g; s/end_word/end_char/g' tests/unit/test_highlight_document_id.py
```

**Step 3: Update test_marker_insertion.py**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && sed -i 's/start_word/start_char/g; s/end_word/end_char/g' tests/unit/export/test_marker_insertion.py
```

**Step 4: Run unit tests to verify**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run pytest tests/unit/test_annotation_doc.py tests/unit/test_highlight_document_id.py tests/unit/export/test_marker_insertion.py -v
```

Expected: All tests pass

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update integration tests and commit

**Files:**
- Modify: `tests/integration/test_workspace_crud.py`
- Modify: `tests/integration/test_workspace_persistence.py`
- Modify: `tests/integration/test_pdf_pipeline.py`
- Modify: `tests/integration/test_pdf_export.py`
- Modify: `tests/integration/test_cross_env_highlights.py`

**Step 1: Batch update all integration test files**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && for f in tests/integration/test_workspace_crud.py tests/integration/test_workspace_persistence.py tests/integration/test_pdf_pipeline.py tests/integration/test_pdf_export.py tests/integration/test_cross_env_highlights.py; do sed -i 's/start_word/start_char/g; s/end_word/end_char/g' "$f"; done
```

**Step 2: Run integration tests to verify**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run pytest tests/integration/ -v -k "not slow"
```

Expected: All tests pass

**Step 3: Run full test suite**

Run:
```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && uv run test-debug
```

Expected: All tests pass (or only unrelated skips)

**Step 4: Commit**

```bash
cd /home/brian/people/Brian/PromptGrimoire/.worktrees/html-input-pipeline && git add src/promptgrimoire/crdt/annotation_doc.py src/promptgrimoire/pages/annotation.py tests/ && git commit -m "refactor: rename word-based indexing to char-based

- Rename start_word/end_word to start_char/end_char in CRDT layer
- Rename cursor_word to cursor_char in UI layer
- Update all test files to use new field names
- Export layer shims in latex.py will handle transition

Part of #106 HTML input pipeline

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

---

## Phase 2 Completion Criteria

- [ ] CRDT layer (`annotation_doc.py`) uses `start_char`/`end_char`
- [ ] UI layer (`annotation.py`) uses `cursor_char` and char-based selection
- [ ] All unit tests updated and passing
- [ ] All integration tests updated and passing
- [ ] HTML attributes use `data-start-char`/`data-end-char`
- [ ] Changes committed

## Notes

- Export layer (`latex.py`) already has fallback shims that check for both `start_char` and `start_word`
- These shims can be cleaned up in Phase 6 once all layers are migrated
- No database migration needed - highlights stored in CRDT, not SQL
