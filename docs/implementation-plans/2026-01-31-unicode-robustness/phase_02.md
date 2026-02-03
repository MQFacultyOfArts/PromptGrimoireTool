# Unicode Robustness Implementation Plan - Phase 2

**Goal:** Create unicode range detection utilities for CJK and emoji

**Architecture:** Pure Python functions using Unicode codepoint ranges for CJK detection, emoji library for emoji detection (handles ZWJ sequences, skin tones correctly). Tests use parameterized fixtures extracted from BLNS corpus.

**Tech Stack:** Python, emoji library (PyPI), pytest parameterization

**Scope:** Phase 2 of 7 from design plan

**Codebase verified:** 2026-02-01

---

<!-- START_SUBCOMPONENT_A (tasks 1-4) -->

<!-- START_TASK_1 -->
### Task 1: Add emoji dependency and BLNS test fixtures to conftest.py

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/pyproject.toml`
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/tests/conftest.py`

**Step 1: Add emoji to dependencies**

Add `emoji` to the dependencies list (around line 25):

```toml
dependencies = [
    ...existing deps...,
    "emoji>=2.0.0",
]
```

**Step 2: Sync dependencies**

Run: `uv sync`

Expected: Success, emoji library installed

**Step 3: Add BLNS-derived test fixtures to conftest.py**

Add after `BLNS_INJECTION_SUBSET` definition:

```python
import emoji as emoji_lib

# =============================================================================
# Unicode Test Fixtures (derived from BLNS corpus)
# =============================================================================

def _extract_cjk_chars_from_blns() -> list[str]:
    """Extract individual CJK characters from BLNS Two-Byte Characters category.

    Returns unique CJK characters for parameterized testing.
    """
    cjk_chars: set[str] = set()
    for s in BLNS_BY_CATEGORY.get("Two-Byte Characters", []):
        for char in s:
            cp = ord(char)
            # CJK Unified Ideographs
            if 0x4E00 <= cp <= 0x9FFF:
                cjk_chars.add(char)
            # Hiragana
            elif 0x3040 <= cp <= 0x309F:
                cjk_chars.add(char)
            # Katakana
            elif 0x30A0 <= cp <= 0x30FF:
                cjk_chars.add(char)
            # Hangul Syllables
            elif 0xAC00 <= cp <= 0xD7AF:
                cjk_chars.add(char)
            # CJK Unified Ideographs Extension A
            elif 0x3400 <= cp <= 0x4DBF:
                cjk_chars.add(char)
    return sorted(cjk_chars)


def _extract_emoji_from_blns() -> list[str]:
    """Extract individual emoji from BLNS Emoji category.

    Returns unique emoji strings (including ZWJ sequences) for parameterized testing.
    """
    emoji_set: set[str] = set()
    for s in BLNS_BY_CATEGORY.get("Emoji", []):
        # Use emoji library to find all emoji in the string
        for match in emoji_lib.emoji_list(s):
            emoji_set.add(match["emoji"])
    return sorted(emoji_set)


# Extracted test data from BLNS corpus
CJK_TEST_CHARS: list[str] = _extract_cjk_chars_from_blns()
EMOJI_TEST_STRINGS: list[str] = _extract_emoji_from_blns()

# ASCII strings for negative testing (from BLNS Reserved Strings)
ASCII_TEST_STRINGS: list[str] = [
    s for s in BLNS_BY_CATEGORY.get("Reserved Strings", [])
    if s.isascii() and len(s) > 0
][:10]  # Take first 10
```

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock tests/conftest.py
git commit -m "feat(deps): add emoji library and BLNS-derived unicode fixtures (#101)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create unicode_latex.py with CJK detection

**Files:**
- Create: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/src/promptgrimoire/export/unicode_latex.py`
- Create: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/tests/unit/test_unicode_handling.py`

**Step 1: Write failing parameterized test for `is_cjk()`**

```python
"""Tests for unicode detection and LaTeX escaping.

Uses parameterized fixtures derived from BLNS corpus for comprehensive coverage.
"""

import pytest

from tests.conftest import ASCII_TEST_STRINGS, CJK_TEST_CHARS, EMOJI_TEST_STRINGS


class TestIsCJK:
    """Test CJK character detection using BLNS-derived fixtures."""

    @pytest.mark.parametrize("char", CJK_TEST_CHARS)
    def test_detects_cjk_from_blns(self, char: str) -> None:
        """Detects CJK characters extracted from BLNS Two-Byte Characters."""
        from promptgrimoire.export.unicode_latex import is_cjk

        assert is_cjk(char), f"Failed to detect CJK char: {char!r} (U+{ord(char):04X})"

    @pytest.mark.parametrize("text", ASCII_TEST_STRINGS)
    def test_ascii_not_cjk(self, text: str) -> None:
        """ASCII strings from BLNS are not CJK."""
        from promptgrimoire.export.unicode_latex import is_cjk

        # Test first character only (is_cjk takes single char)
        if text:
            assert not is_cjk(text[0]), f"ASCII char detected as CJK: {text[0]!r}"

    @pytest.mark.parametrize("emoji", EMOJI_TEST_STRINGS[:5])
    def test_emoji_not_cjk(self, emoji: str) -> None:
        """Emoji from BLNS are not CJK (handled separately)."""
        from promptgrimoire.export.unicode_latex import is_cjk

        # Emoji can be multi-codepoint; is_cjk only handles single chars
        # For multi-char emoji, is_cjk should return False
        assert not is_cjk(emoji), f"Emoji detected as CJK: {emoji!r}"

    def test_multi_char_string_returns_false(self) -> None:
        """Multi-character strings return False (is_cjk expects single char)."""
        from promptgrimoire.export.unicode_latex import is_cjk

        assert not is_cjk("世界")  # Two CJK chars
        assert not is_cjk("AB")  # Two ASCII chars
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_unicode_handling.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'promptgrimoire.export.unicode_latex'`

**Step 3: Write minimal implementation**

Create `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/src/promptgrimoire/export/unicode_latex.py`:

```python
"""Unicode detection and LaTeX escaping for CJK and emoji."""

from __future__ import annotations


def is_cjk(char: str) -> bool:
    """Check if a single character is CJK (Chinese, Japanese, Korean).

    Detects:
    - CJK Unified Ideographs (U+4E00-U+9FFF)
    - Hiragana (U+3040-U+309F)
    - Katakana (U+30A0-U+30FF)
    - Hangul Syllables (U+AC00-U+D7AF)
    - CJK Unified Ideographs Extension A (U+3400-U+4DBF)

    Args:
        char: A single character to check.

    Returns:
        True if character is in a CJK range, False otherwise.
    """
    if len(char) != 1:
        return False

    cp = ord(char)

    # CJK Unified Ideographs
    if 0x4E00 <= cp <= 0x9FFF:
        return True

    # Hiragana
    if 0x3040 <= cp <= 0x309F:
        return True

    # Katakana
    if 0x30A0 <= cp <= 0x30FF:
        return True

    # Hangul Syllables
    if 0xAC00 <= cp <= 0xD7AF:
        return True

    # CJK Unified Ideographs Extension A
    if 0x3400 <= cp <= 0x4DBF:
        return True

    return False
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_unicode_handling.py::TestIsCJK -v`

Expected: All parameterized tests pass

**Step 5: Commit**

```bash
git add src/promptgrimoire/export/unicode_latex.py tests/unit/test_unicode_handling.py
git commit -m "feat(export): add is_cjk() with BLNS-parameterized tests (#101)"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add is_emoji() using emoji library

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/src/promptgrimoire/export/unicode_latex.py`
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/tests/unit/test_unicode_handling.py`

**Step 1: Write failing parameterized tests for `is_emoji()`**

Add to `tests/unit/test_unicode_handling.py`:

```python
class TestIsEmoji:
    """Test emoji detection using BLNS-derived fixtures."""

    @pytest.mark.parametrize("emoji", EMOJI_TEST_STRINGS)
    def test_detects_emoji_from_blns(self, emoji: str) -> None:
        """Detects emoji extracted from BLNS Emoji category."""
        from promptgrimoire.export.unicode_latex import is_emoji

        assert is_emoji(emoji), f"Failed to detect emoji: {emoji!r}"

    @pytest.mark.parametrize("text", ASCII_TEST_STRINGS)
    def test_ascii_not_emoji(self, text: str) -> None:
        """ASCII strings from BLNS are not emoji."""
        from promptgrimoire.export.unicode_latex import is_emoji

        assert not is_emoji(text), f"ASCII detected as emoji: {text!r}"

    @pytest.mark.parametrize("char", CJK_TEST_CHARS[:10])
    def test_cjk_not_emoji(self, char: str) -> None:
        """CJK characters from BLNS are not emoji."""
        from promptgrimoire.export.unicode_latex import is_emoji

        assert not is_emoji(char), f"CJK detected as emoji: {char!r}"

    def test_multiple_separate_emoji_not_single(self) -> None:
        """Multiple separate emoji is not a single emoji."""
        from promptgrimoire.export.unicode_latex import is_emoji

        assert not is_emoji("🎉🎊")  # Two separate emoji
        assert not is_emoji("😀😃")  # Two separate emoji
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_unicode_handling.py::TestIsEmoji -v`

Expected: FAIL with `ImportError: cannot import name 'is_emoji'`

**Step 3: Write minimal implementation**

Add to `unicode_latex.py` (after imports):

```python
import emoji as emoji_lib


def is_emoji(text: str) -> bool:
    """Check if text is a single emoji (including ZWJ sequences).

    Uses the emoji library to correctly handle:
    - Single codepoint emoji
    - Emoji with skin tone modifiers
    - ZWJ sequences (family, profession emoji)

    Args:
        text: Text to check.

    Returns:
        True if text is exactly one RGI emoji, False otherwise.
    """
    return emoji_lib.is_emoji(text)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_unicode_handling.py::TestIsEmoji -v`

Expected: All parameterized tests pass

**Step 5: Commit**

```bash
git add src/promptgrimoire/export/unicode_latex.py tests/unit/test_unicode_handling.py
git commit -m "feat(export): add is_emoji() with BLNS-parameterized tests (#101)"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add get_emoji_spans() for position tracking

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/src/promptgrimoire/export/unicode_latex.py`
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/tests/unit/test_unicode_handling.py`

**Step 1: Write failing tests for `get_emoji_spans()`**

Add to `tests/unit/test_unicode_handling.py`:

```python
class TestGetEmojiSpans:
    """Test emoji span extraction for wrapping."""

    def test_no_emoji(self) -> None:
        """Returns empty list for text without emoji."""
        from promptgrimoire.export.unicode_latex import get_emoji_spans

        assert get_emoji_spans("Hello world") == []

    @pytest.mark.parametrize("emoji", EMOJI_TEST_STRINGS[:10])
    def test_single_emoji_in_text(self, emoji: str) -> None:
        """Returns span for single emoji embedded in text."""
        from promptgrimoire.export.unicode_latex import get_emoji_spans

        text = f"Hello {emoji}!"
        spans = get_emoji_spans(text)
        assert len(spans) == 1
        start, end, found_emoji = spans[0]
        assert found_emoji == emoji
        assert text[start:end] == emoji

    def test_multiple_emoji(self) -> None:
        """Returns spans for multiple emoji."""
        from promptgrimoire.export.unicode_latex import get_emoji_spans

        spans = get_emoji_spans("A 🎉 B 🎊 C")
        assert len(spans) == 2
        assert spans[0][2] == "🎉"
        assert spans[1][2] == "🎊"

    @pytest.mark.parametrize(
        "blns_emoji_line",
        [s for s in BLNS_BY_CATEGORY.get("Emoji", []) if len(emoji_lib.emoji_list(s)) > 1][:3],
    )
    def test_blns_emoji_lines_extract_all(self, blns_emoji_line: str) -> None:
        """BLNS emoji lines with multiple emoji extract all of them."""
        from promptgrimoire.export.unicode_latex import get_emoji_spans

        expected_count = len(emoji_lib.emoji_list(blns_emoji_line))
        spans = get_emoji_spans(blns_emoji_line)
        assert len(spans) == expected_count, (
            f"Expected {expected_count} emoji in {blns_emoji_line!r}, got {len(spans)}"
        )
```

Note: Add `import emoji as emoji_lib` and `from tests.conftest import BLNS_BY_CATEGORY` to imports.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_unicode_handling.py::TestGetEmojiSpans -v`

Expected: FAIL with `ImportError: cannot import name 'get_emoji_spans'`

**Step 3: Write minimal implementation**

Add to `unicode_latex.py`:

```python
def get_emoji_spans(text: str) -> list[tuple[int, int, str]]:
    """Get positions of all emoji in text.

    Args:
        text: Text to scan for emoji.

    Returns:
        List of (start, end, emoji) tuples for each emoji found.
        Positions are character indices (not byte offsets).
    """
    matches = emoji_lib.emoji_list(text)
    return [(m["match_start"], m["match_end"], m["emoji"]) for m in matches]
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_unicode_handling.py::TestGetEmojiSpans -v`

Expected: All tests pass

**Step 5: Commit**

```bash
git add src/promptgrimoire/export/unicode_latex.py tests/unit/test_unicode_handling.py
git commit -m "feat(export): add get_emoji_spans() for position tracking (#101)"
```
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_A -->

## Phase 2 Verification

**Done when:**
- [ ] `is_cjk()` passes all BLNS-derived parameterized tests
- [ ] `is_emoji()` passes all BLNS-derived parameterized tests
- [ ] `get_emoji_spans()` correctly extracts positions from BLNS emoji lines
- [ ] All unit tests pass
- [ ] Type checking passes (`uvx ty check`)

**Verification commands:**

```bash
# Run all Phase 2 tests
uv run pytest tests/unit/test_unicode_handling.py -v

# Type check
uvx ty check src/promptgrimoire/export/unicode_latex.py

# Verify imports work
uv run python -c "from promptgrimoire.export.unicode_latex import is_cjk, is_emoji, get_emoji_spans; print('OK')"

# Show parameterized test count
uv run pytest tests/unit/test_unicode_handling.py --collect-only | grep "test session starts" -A 5
```
