# Character-Based Tokenization Implementation Plan

**Goal:** Update all tests to work with character-based indexing and add CJK/BLNS test coverage

**Architecture:** Update E2E helpers and test assertions from word-based to character-based indices, add parameterized tests using existing CJK_TEST_CHARS from conftest.py

**Tech Stack:** Python, pytest, Playwright (sync API)

**Scope:** Phase 5 of 6 from design plan

**Codebase verified:** 2026-02-02

---

<!-- START_TASK_1 -->
### Task 1: Update `annotation_helpers.py` functions

**Files:**
- Modify: `tests/e2e/annotation_helpers.py:24-42` (select_words, create_highlight)
- Modify: `tests/e2e/annotation_helpers.py:87` (setup_workspace_with_content wait_for_selector)

**Step 1: Rename `select_words()` to `select_chars()`**

Lines 24-42 currently:
```python
def select_words(page: Page, start_word: int, end_word: int) -> None:
    """Select a range of words using click and shift-click.

    Args:
        page: Playwright page object
        start_word: Index of first word to select
        end_word: Index of last word to select (inclusive)
    """
    start_locator = page.locator(f"[data-word-index='{start_word}']")
    end_locator = page.locator(f"[data-word-index='{end_word}']")

    start_locator.scroll_into_view_if_needed()
    start_locator.click()

    end_locator.scroll_into_view_if_needed()
    end_locator.click(modifiers=["Shift"])
```

Change to:
```python
def select_chars(page: Page, start_char: int, end_char: int) -> None:
    """Select a range of characters using click and shift-click.

    Args:
        page: Playwright page object
        start_char: Index of first character to select
        end_char: Index of last character to select (inclusive)
    """
    start_locator = page.locator(f"[data-char-index='{start_char}']")
    end_locator = page.locator(f"[data-char-index='{end_char}']")

    start_locator.scroll_into_view_if_needed()
    expect(start_locator).to_be_visible(timeout=5000)  # Ensure visible before click
    start_locator.click()

    end_locator.scroll_into_view_if_needed()
    end_locator.click(modifiers=["Shift"])
```

**Note:** The `expect` import already exists in annotation_helpers.py from `playwright.sync_api` - no import changes needed.

**Step 2: Update `create_highlight()` function**

Update parameter names and internal call:
```python
def create_highlight(page: Page, start_char: int, end_char: int) -> None:
    """Create a highlight by selecting characters and clicking tag button."""
    select_chars(page, start_char, end_char)
    # ... rest of function
```

**Step 3: Keep old function as alias (optional, for migration)**

```python
# Deprecated alias for backwards compatibility during migration
select_words = select_chars
```

**Step 4: Update `setup_workspace_with_content()` (line 87)**

Change the wait_for_selector call:
```python
# OLD:
page.wait_for_selector("[data-word-index]")

# NEW:
page.wait_for_selector("[data-char-index]")
```

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update E2E annotation test selectors

**Files:**
- Modify: `tests/e2e/test_annotation_basics.py`
- Modify: `tests/e2e/test_annotation_cards.py`
- Modify: `tests/e2e/test_annotation_sync.py`
- Modify: `tests/e2e/test_annotation_highlights.py`
- Modify: `tests/e2e/test_annotation_workflows.py`
- Modify: `tests/e2e/test_annotation_collab.py`

**Step 1: Update selector strings**

Search and replace in all files:
- `data-word-index` → `data-char-index`
- `select_words(` → `select_chars(`
- `start_word` → `start_char` (in function calls)
- `end_word` → `end_char` (in function calls)

**Step 2: Update index values for character-based selection**

The index values will need recalculating. For example, if test content is "Hello world":
- Word indices: "Hello"=0, "world"=1
- Character indices: H=0, e=1, l=2, l=3, o=4, space=5, w=6, o=7, r=8, l=9, d=10

Update test assertions accordingly. Example:
```python
# OLD: Select words 0-1 (both words)
select_words(page, 0, 1)

# NEW: Select chars 0-10 (all 11 characters including space)
select_chars(page, 0, 10)
```

**Step 3: Update wait_for_selector calls**

```python
# OLD:
page.wait_for_selector("[data-word-index]")

# NEW:
page.wait_for_selector("[data-char-index]")
```

**Step 4: Update locator queries**

```python
# OLD:
word = page.locator("[data-word-index='0']")

# NEW:
char = page.locator("[data-char-index='0']")
```

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add CJK character selection tests

**Files:**
- Create: `tests/e2e/test_annotation_cjk.py`

**Step 1: Create new test file for CJK selection**

```python
"""E2E tests for CJK character selection in annotation system."""
import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.annotation_helpers import select_chars, create_highlight, setup_workspace_with_content


@pytest.mark.e2e
def test_chinese_character_selection(page: Page, app_server: str) -> None:
    """Verify Chinese characters can be selected individually."""
    # 你好世界 = "Hello world" in Chinese (4 characters)
    content = "你好世界"
    setup_workspace_with_content(page, app_server, content)

    # Wait for character spans
    page.wait_for_selector("[data-char-index]")

    # Select middle two characters: 好世 (indices 1-2)
    select_chars(page, 1, 2)

    # Verify selection spans correct characters
    char_1 = page.locator("[data-char-index='1']")
    char_2 = page.locator("[data-char-index='2']")
    expect(char_1).to_be_visible()
    expect(char_2).to_be_visible()


@pytest.mark.e2e
def test_japanese_mixed_script(page: Page, app_server: str) -> None:
    """Verify Japanese mixed script (hiragana + kanji) selection."""
    # こんにちは世界 = "Hello world" in Japanese (7 characters)
    content = "こんにちは世界"
    setup_workspace_with_content(page, app_server, content)

    page.wait_for_selector("[data-char-index]")

    # Each character should have its own index
    for i in range(7):
        char = page.locator(f"[data-char-index='{i}']")
        expect(char).to_be_visible()


@pytest.mark.e2e
def test_korean_character_selection(page: Page, app_server: str) -> None:
    """Verify Korean Hangul selection."""
    # 안녕하세요 = "Hello" in Korean (5 syllables/characters)
    content = "안녕하세요"
    setup_workspace_with_content(page, app_server, content)

    page.wait_for_selector("[data-char-index]")

    # Create highlight across first 3 characters
    create_highlight(page, 0, 2)

    # Verify highlight applied (background-color will be rgba(...) when highlighted)
    char_0 = page.locator("[data-char-index='0']")
    expect(char_0).to_have_css("background-color", re.compile(r"rgba\("))


@pytest.mark.e2e
def test_cjk_mixed_with_ascii(page: Page, app_server: str) -> None:
    """Verify mixed CJK and ASCII text selection."""
    content = "Hello 世界 World"  # 16 characters total
    setup_workspace_with_content(page, app_server, content)

    page.wait_for_selector("[data-char-index]")

    # Select the CJK portion (indices 6-7: 世界)
    select_chars(page, 6, 7)

    char_6 = page.locator("[data-char-index='6']")
    char_7 = page.locator("[data-char-index='7']")
    expect(char_6).to_be_visible()
    expect(char_7).to_be_visible()
```

**Step 2: Run CJK tests**

```bash
uv run pytest tests/e2e/test_annotation_cjk.py -v
```

**Expected:** All tests pass

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add BLNS edge case tests

**Files:**
- Create: `tests/e2e/test_annotation_blns.py`

**Step 1: Create BLNS test file**

```python
"""E2E tests for BLNS edge cases in annotation system."""
import pytest
from playwright.sync_api import Page, expect

from tests.conftest import CJK_TEST_CHARS
from tests.e2e.annotation_helpers import select_chars, setup_workspace_with_content


@pytest.mark.e2e
@pytest.mark.parametrize("cjk_char", CJK_TEST_CHARS[:10])  # Test first 10 CJK chars
def test_individual_cjk_characters(
    page: Page, app_server: str, cjk_char: str
) -> None:
    """Verify individual CJK characters from BLNS can be selected."""
    setup_workspace_with_content(page, app_server, cjk_char)
    page.wait_for_selector("[data-char-index]")

    char_span = page.locator("[data-char-index='0']")
    expect(char_span).to_be_visible()
    expect(char_span).to_have_text(cjk_char)


@pytest.mark.e2e
def test_rtl_arabic_text(page: Page, app_server: str) -> None:
    """Verify RTL Arabic text can be selected."""
    # Arabic "Hello" - characters still indexed left-to-right in DOM
    content = "مرحبا"
    setup_workspace_with_content(page, app_server, content)

    page.wait_for_selector("[data-char-index]")

    # Should have 5 character spans
    for i in range(5):
        char = page.locator(f"[data-char-index='{i}']")
        expect(char).to_be_visible()


@pytest.mark.e2e
def test_rtl_hebrew_text(page: Page, app_server: str) -> None:
    """Verify RTL Hebrew text can be selected."""
    content = "שלום"  # "Hello" in Hebrew (4 characters)
    setup_workspace_with_content(page, app_server, content)

    page.wait_for_selector("[data-char-index]")

    # Select all Hebrew characters
    select_chars(page, 0, 3)


@pytest.mark.e2e
def test_hard_whitespace_nbsp(page: Page, app_server: str) -> None:
    """Verify non-breaking spaces are individually selectable."""
    # Non-breaking space between words (U+00A0)
    content = "Hello\u00A0World"  # 11 characters, nbsp at index 5
    setup_workspace_with_content(page, app_server, content)

    page.wait_for_selector("[data-char-index]")

    # The nbsp should have its own index
    nbsp_span = page.locator("[data-char-index='5']")
    expect(nbsp_span).to_be_visible()


@pytest.mark.e2e
def test_ideographic_space(page: Page, app_server: str) -> None:
    """Verify ideographic space (U+3000) is selectable."""
    content = "你\u3000好"  # Chinese with ideographic space
    setup_workspace_with_content(page, app_server, content)

    page.wait_for_selector("[data-char-index]")

    # Should have 3 character spans: 你(0), space(1), 好(2)
    for i in range(3):
        char = page.locator(f"[data-char-index='{i}']")
        expect(char).to_be_visible()
```

**Step 2: Run BLNS tests**

```bash
uv run pytest tests/e2e/test_annotation_blns.py -v
```

**Expected:** All tests pass

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Update unit tests for marker insertion

**Files:**
- Modify: `tests/unit/export/test_marker_insertion.py`

**Step 1: Update test fixtures from word to character indices**

Update all test highlight dictionaries:
```python
# OLD:
highlights = [{"start_word": 1, "tag": "test"}]

# NEW:
highlights = [{"start_char": 6, "tag": "test"}]  # 'w' in "Hello world"
```

**Step 2: Add CJK marker insertion test**

```python
def test_cjk_character_markers():
    """Verify markers insert at correct positions in CJK text."""
    html = "你好世界"  # 4 characters
    highlights = [
        {"start_char": 1, "end_char": 3, "tag": "test", "color": "#FF0000"}
    ]
    result, ordered = _insert_markers_into_html(html, highlights)

    # Marker should appear before char 1 (好) and after char 2 (世)
    assert "HLSTART" in result
    assert "HLEND" in result
```

**Step 3: Run marker tests**

```bash
uv run pytest tests/unit/export/test_marker_insertion.py -v
```

**Expected:** All tests pass

**Step 4: Commit Phase 5 changes**

```bash
git add tests/e2e/annotation_helpers.py \
        tests/e2e/test_annotation_*.py \
        tests/e2e/test_annotation_cjk.py \
        tests/e2e/test_annotation_blns.py \
        tests/unit/export/test_marker_insertion.py
git commit -m "$(cat <<'EOF'
test(annotation): update tests for character-based tokenization

- Rename select_words() -> select_chars() in annotation_helpers.py
- Update all E2E tests: data-word-index -> data-char-index
- Add test_annotation_cjk.py for CJK character selection
- Add test_annotation_blns.py for BLNS edge cases (RTL, nbsp)
- Update marker insertion tests for character indices

Part of Issue #101: CJK unicode support

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_5 -->

---

## Phase 5 UAT Steps

1. [ ] Run all E2E annotation tests: `uv run pytest tests/e2e/test_annotation_*.py -v`
2. [ ] Run CJK tests: `uv run pytest tests/e2e/test_annotation_cjk.py -v`
3. [ ] Run BLNS tests: `uv run pytest tests/e2e/test_annotation_blns.py -v`
4. [ ] Run marker tests: `uv run pytest tests/unit/export/test_marker_insertion.py -v`
5. [ ] Run full test suite: `uv run pytest -v`

## Evidence Required

- [ ] All E2E annotation tests pass
- [ ] CJK tests pass (Chinese, Japanese, Korean selection)
- [ ] BLNS tests pass (RTL, hard whitespace)
- [ ] Marker insertion tests pass
- [ ] No `data-word-index` in test files (grep verification)
