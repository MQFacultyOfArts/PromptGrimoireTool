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
