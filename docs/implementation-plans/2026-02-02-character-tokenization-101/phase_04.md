# Character-Based Tokenization Implementation Plan

**Goal:** Update PDF export marker insertion to use character-based indexing

**Architecture:** Replace `_WORD_PATTERN.finditer()` regex-based word iteration with character-by-character iteration, ensuring export tokenization matches UI tokenization exactly

**Tech Stack:** Python, regex

**Scope:** Phase 4 of 6 from design plan

**Codebase verified:** 2026-02-02

---

<!-- START_TASK_1 -->
### Task 1: Update `_WORD_PATTERN` constant and docstring

**Files:**
- Modify: `src/promptgrimoire/export/latex.py:485-488`

**Step 1: Remove or update the pattern constant**

Lines 485-488 currently:
```python
# Pattern for words - matches str.split() behavior (non-whitespace sequences)
# The UI tokenizes words with line.split() so we must use the same tokenization
# to ensure highlight word indices match between UI and export.
_WORD_PATTERN = re.compile(r"\S+")
```

Change to:
```python
# Character-based tokenization pattern.
# The UI tokenizes by character (including whitespace), so export must match exactly.
# This pattern is no longer used - kept for reference. Character iteration is now inline.
# _WORD_PATTERN = re.compile(r"\S+")  # DEPRECATED
```

Or simply delete the constant if no longer needed after refactoring.

**Step 2: Verify the constant is no longer referenced**

```bash
grep -n "_WORD_PATTERN" src/promptgrimoire/export/latex.py
```

After Task 2 completion, this should return no matches (or only the comment).

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Refactor `_insert_markers_into_html()` for character iteration

**Files:**
- Modify: `src/promptgrimoire/export/latex.py:690-786`

**Step 1: Update function docstring (lines 690-708)**

Change from:
```python
def _insert_markers_into_html(
    html: str, highlights: list[dict]
) -> tuple[str, list[dict]]:
    """Insert annotation and highlight markers into HTML at correct word positions.

    Uses str.split() tokenization (via \\S+ regex) to match the UI's word indexing.
    The UI creates word indices with line.split(), so we must match that exactly.
```

To:
```python
def _insert_markers_into_html(
    html: str, highlights: list[dict]
) -> tuple[str, list[dict]]:
    """Insert annotation and highlight markers into HTML at correct character positions.

    Uses character-by-character iteration to match the UI's character indexing.
    The UI creates character indices by iterating each character (including whitespace),
    so we must match that exactly for highlights to align between UI and export.
```

**Step 2: Update field name references in lookup building (lines 725-733)**

Change from:
```python
    for h in sorted_highlights:
        start = int(h.get("start_word", 0))
        end = int(h.get("end_word", start + 1))
        last_word = end - 1 if end > start else start
```

To:
```python
    for h in sorted_highlights:
        # Support both old field names (start_word) and new (start_char) for migration
        start = int(h.get("start_char", h.get("start_word", 0)))
        end = int(h.get("end_char", h.get("end_word", start + 1)))
        last_char = end - 1 if end > start else start
```

**Step 3: Update variable naming (line 737)**

Change from:
```python
    word_idx = 0
```

To:
```python
    char_idx = 0
```

**Step 4: Replace regex iteration with character iteration (lines 759-779)**

The current code:
```python
        for match in _WORD_PATTERN.finditer(text):
            # Add text before this word
            text_result.append(text[text_pos : match.start()])

            # Insert HLSTART markers before this word
            if word_idx in start_markers:
                for marker_idx, _ in start_markers[word_idx]:
                    text_result.append(_HLSTART_TEMPLATE.format(marker_idx))

            # Add the word
            text_result.append(match.group(0))

            # Insert HLEND then ANNMARKER after this word
            if word_idx in end_markers:
                for marker_idx in end_markers[word_idx]:
                    text_result.append(_HLEND_TEMPLATE.format(marker_idx))
                    text_result.append(_MARKER_TEMPLATE.format(marker_idx))

            text_pos = match.end()
            word_idx += 1
```

Replace with character iteration:
```python
        for char in text:
            # Insert HLSTART markers before this character
            if char_idx in start_markers:
                for marker_idx, _ in start_markers[char_idx]:
                    text_result.append(_HLSTART_TEMPLATE.format(marker_idx))

            # Add the character
            text_result.append(char)

            # Insert HLEND then ANNMARKER after this character
            if char_idx in end_markers:
                for marker_idx in end_markers[char_idx]:
                    text_result.append(_HLEND_TEMPLATE.format(marker_idx))
                    text_result.append(_MARKER_TEMPLATE.format(marker_idx))

            char_idx += 1
```

**Note on newline handling:** The function processes HTML that has already been structured by the UI with paragraph tags. Within each text segment between HTML tags:
- Any characters (including any remaining whitespace) get character indices
- Newlines (`\n`) are typically not present in text segments because the UI converts them to `<p>` tags during `_process_text_to_char_spans()`
- If somehow present in a text segment, they would get indices like any other character
- The `char_idx` increments for each character in text content (not for HTML tags)

**Step 5: Update remaining variable references**

Throughout the function, update:
- `word_idx` → `char_idx`
- `last_word` → `last_char`
- `start_markers[word_idx]` → `start_markers[char_idx]`
- `end_markers[word_idx]` → `end_markers[char_idx]`

**Step 6: Run type check**

```bash
uvx ty check src/promptgrimoire/export/latex.py
```

**Expected:** No errors

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update marker insertion tests

**Files:**
- Modify: `tests/unit/export/test_marker_insertion.py`

**Step 1: Update test fixtures to use character indices**

Line 27 currently:
```python
highlights = [{"start_word": 1, "tag": "test"}]
```

Change to:
```python
# "Hello world" - 'w' is at index 6 (H=0, e=1, l=2, l=3, o=4, space=5, w=6)
highlights = [{"start_char": 6, "tag": "test"}]
```

Lines 37-38 currently:
```python
{"start_word": 1, "tag": "a"},
{"start_word": 3, "tag": "b"},
```

Update to use character indices appropriate for the test input.

**Step 2: Update test assertions**

The tests verify marker positions. Update expected output to match character-based marker insertion.

For example, if testing `"Hello world"` with a highlight at character 6 (`w`):
- Marker should appear before/after `w`
- Result: `Hello HLSTART0ENDHLwHLEND0ENDHLANNMARKER0ENDMARKERorld`

**Step 3: Add CJK test case**

Add a test for CJK text to verify character-based indexing works:

```python
def test_cjk_character_indexing():
    """Verify CJK characters are indexed individually."""
    html = "你好世界"  # "Hello world" in Chinese, 4 characters
    highlights = [{"start_char": 1, "end_char": 3, "tag": "test", "color": "#FF0000"}]
    result, ordered = _insert_markers_into_html(html, highlights)
    # Characters: 你(0) 好(1) 世(2) 界(3)
    # Highlight covers indices 1-2 (好世)
    assert "HLSTART" in result
    assert "好" in result  # Character at index 1 should be highlighted
    assert "世" in result  # Character at index 2 should be highlighted
```

**Step 4: Run tests**

```bash
uv run pytest tests/unit/export/test_marker_insertion.py -v
```

**Expected:** All tests pass

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update other word-based references in latex.py

**Files:**
- Modify: `src/promptgrimoire/export/latex.py`

**Step 1: Update `build_para_ref()` function (lines 945-950)**

Search for other word-based references:
```bash
grep -n "start_word\|end_word\|last_word" src/promptgrimoire/export/latex.py
```

Update any found references to support both old and new field names or migrate to new names.

**Step 2: Update docstrings and comments**

Lines to update:
- Line 705, 715: Docstring mentions `start_word` and `end_word`
- Line 713: Comment "Sort by start_word, then by tag"
- Line 764: Comment about "this word"
- Line 771: Comment about "this word"
- Line 1037: Docstring mentions `start_word, end_word`

Change comments from "word" to "character" terminology.

**Step 3: Run full type check and lint**

```bash
uvx ty check src/promptgrimoire/export/latex.py && uv run ruff check src/promptgrimoire/export/latex.py
```

**Expected:** No errors

**Step 4: Commit Phase 4 changes**

```bash
git add src/promptgrimoire/export/latex.py tests/unit/export/test_marker_insertion.py
git commit -m "$(cat <<'EOF'
refactor(export): switch marker insertion to character-based indexing

- Replace _WORD_PATTERN regex iteration with character iteration
- Update _insert_markers_into_html() for character-by-character processing
- Support both start_word/start_char field names for migration
- Update variable names: word_idx -> char_idx
- Add CJK test case for character indexing
- Update existing tests to use character indices

Part of Issue #101: CJK unicode support

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_4 -->

---

## Phase 4 UAT Steps

1. [ ] Run grep to verify no `_WORD_PATTERN.finditer` calls remain
2. [ ] Run type check: `uvx ty check src/promptgrimoire/export/latex.py`
3. [ ] Run lint: `uv run ruff check src/promptgrimoire/export/latex.py`
4. [ ] Run marker tests: `uv run pytest tests/unit/export/test_marker_insertion.py -v`
5. [ ] Run all latex tests: `uv run pytest tests/unit/export/ -v`

## Evidence Required

- [ ] Type check passes
- [ ] Lint passes
- [ ] All marker insertion tests pass
- [ ] CJK test case passes
- [ ] No `_WORD_PATTERN.finditer` in grep output
