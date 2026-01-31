# Unicode Robustness Implementation Plan - Phase 2

**Goal:** Create unicode range detection utilities for CJK and emoji

**Architecture:** Pure Python functions using Unicode codepoint ranges for CJK detection, emoji library for emoji detection (handles ZWJ sequences, skin tones correctly)

**Tech Stack:** Python, emoji library (PyPI)

**Scope:** Phase 2 of 7 from design plan

**Codebase verified:** 2026-01-31

---

<!-- START_SUBCOMPONENT_A (tasks 1-4) -->

<!-- START_TASK_1 -->
### Task 1: Add emoji dependency to pyproject.toml

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/pyproject.toml`

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

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat(deps): add emoji library for unicode detection (#101)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create unicode_latex.py with CJK detection

**Files:**
- Create: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/src/promptgrimoire/export/unicode_latex.py`
- Create: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/tests/unit/test_unicode_handling.py`

**Step 1: Write failing test for `is_cjk()`**

```python
"""Tests for unicode detection and LaTeX escaping."""

from promptgrimoire.export.unicode_latex import is_cjk


class TestIsCJK:
    """Test CJK character detection."""

    def test_cjk_unified_ideograph(self) -> None:
        """Detects CJK Unified Ideographs (U+4E00-U+9FFF)."""
        assert is_cjk("世")  # U+4E16
        assert is_cjk("界")  # U+754C

    def test_hiragana(self) -> None:
        """Detects Hiragana (U+3040-U+309F)."""
        assert is_cjk("あ")  # U+3042
        assert is_cjk("ん")  # U+3093

    def test_katakana(self) -> None:
        """Detects Katakana (U+30A0-U+30FF)."""
        assert is_cjk("ア")  # U+30A2
        assert is_cjk("ン")  # U+30F3

    def test_hangul(self) -> None:
        """Detects Hangul syllables (U+AC00-U+D7AF)."""
        assert is_cjk("한")  # U+D55C
        assert is_cjk("글")  # U+AE00

    def test_ascii_not_cjk(self) -> None:
        """ASCII characters are not CJK."""
        assert not is_cjk("A")
        assert not is_cjk("1")
        assert not is_cjk("!")

    def test_emoji_not_cjk(self) -> None:
        """Emoji are not CJK (handled separately)."""
        assert not is_cjk("🎉")
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

Expected: All 6 tests pass

**Step 5: Commit**

```bash
git add src/promptgrimoire/export/unicode_latex.py tests/unit/test_unicode_handling.py
git commit -m "feat(export): add is_cjk() for CJK character detection (#101)"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add is_emoji() using emoji library

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/src/promptgrimoire/export/unicode_latex.py`
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/101-cjk-blns/tests/unit/test_unicode_handling.py`

**Step 1: Write failing tests for `is_emoji()`**

Add to `tests/unit/test_unicode_handling.py`:

```python
from promptgrimoire.export.unicode_latex import is_cjk, is_emoji


class TestIsEmoji:
    """Test emoji detection using emoji library."""

    def test_single_emoji(self) -> None:
        """Detects simple single-codepoint emoji."""
        assert is_emoji("🎉")
        assert is_emoji("😀")
        assert is_emoji("❤")

    def test_emoji_with_skin_tone(self) -> None:
        """Detects emoji with skin tone modifier."""
        assert is_emoji("👍🏽")  # U+1F44D + U+1F3FD
        assert is_emoji("👋🏻")

    def test_zwj_sequence(self) -> None:
        """Detects ZWJ sequences (family, profession emoji)."""
        assert is_emoji("👨‍👩‍👧‍👦")  # Family
        assert is_emoji("👩‍🚀")  # Woman astronaut

    def test_ascii_not_emoji(self) -> None:
        """ASCII characters are not emoji."""
        assert not is_emoji("A")
        assert not is_emoji("1")
        assert not is_emoji(" ")

    def test_cjk_not_emoji(self) -> None:
        """CJK characters are not emoji."""
        assert not is_emoji("世")
        assert not is_emoji("あ")

    def test_multi_char_string_not_emoji(self) -> None:
        """Multi-character strings that aren't ZWJ sequences are not emoji."""
        assert not is_emoji("AB")
        assert not is_emoji("🎉🎊")  # Two separate emoji
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

Expected: All 6 tests pass

**Step 5: Commit**

```bash
git add src/promptgrimoire/export/unicode_latex.py tests/unit/test_unicode_handling.py
git commit -m "feat(export): add is_emoji() using emoji library (#101)"
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
from promptgrimoire.export.unicode_latex import is_cjk, is_emoji, get_emoji_spans


class TestGetEmojiSpans:
    """Test emoji span extraction for wrapping."""

    def test_no_emoji(self) -> None:
        """Returns empty list for text without emoji."""
        assert get_emoji_spans("Hello world") == []

    def test_single_emoji(self) -> None:
        """Returns span for single emoji."""
        spans = get_emoji_spans("Hello 🎉!")
        assert len(spans) == 1
        assert spans[0] == (6, 7, "🎉")

    def test_multiple_emoji(self) -> None:
        """Returns spans for multiple emoji."""
        spans = get_emoji_spans("A 🎉 B 🎊 C")
        assert len(spans) == 2
        assert spans[0] == (2, 3, "🎉")
        assert spans[1] == (6, 7, "🎊")

    def test_zwj_sequence_single_span(self) -> None:
        """ZWJ sequence returns single span with correct length."""
        spans = get_emoji_spans("Family: 👨‍👩‍👧‍👦!")
        assert len(spans) == 1
        start, end, emoji_char = spans[0]
        assert emoji_char == "👨‍👩‍👧‍👦"
        assert end - start == len("👨‍👩‍👧‍👦")

    def test_skin_tone_modifier(self) -> None:
        """Skin tone modifier is part of the same span."""
        spans = get_emoji_spans("Thumbs 👍🏽!")
        assert len(spans) == 1
        start, end, emoji_char = spans[0]
        assert emoji_char == "👍🏽"
```

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

Expected: All 5 tests pass

**Step 5: Commit**

```bash
git add src/promptgrimoire/export/unicode_latex.py tests/unit/test_unicode_handling.py
git commit -m "feat(export): add get_emoji_spans() for position tracking (#101)"
```
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_A -->

## Phase 2 Verification

**Done when:**
- [ ] `is_cjk()` correctly identifies CJK ranges (ideographs, hiragana, katakana, hangul)
- [ ] `is_emoji()` correctly identifies emoji (including ZWJ sequences)
- [ ] `get_emoji_spans()` returns correct positions for wrapping
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
```
