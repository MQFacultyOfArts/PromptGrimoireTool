"""Tests for unicode detection and LaTeX escaping.

Uses parameterized fixtures derived from BLNS corpus for comprehensive coverage.
"""

import emoji as emoji_lib
import pytest

from tests.unit.conftest import (
    ASCII_TEST_STRINGS,
    BLNS_BY_CATEGORY,
    CJK_TEST_CHARS,
    EMOJI_TEST_STRINGS,
)


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
        [
            s
            for s in BLNS_BY_CATEGORY.get("Emoji", [])
            if len(emoji_lib.emoji_list(s)) > 1
        ][:3],
    )
    def test_blns_emoji_lines_extract_all(self, blns_emoji_line: str) -> None:
        """BLNS emoji lines with multiple emoji extract all of them."""
        from promptgrimoire.export.unicode_latex import get_emoji_spans

        expected_count = len(emoji_lib.emoji_list(blns_emoji_line))
        spans = get_emoji_spans(blns_emoji_line)
        assert len(spans) == expected_count, (
            f"Expected {expected_count} emoji in {blns_emoji_line!r}, got {len(spans)}"
        )


class TestEscapeUnicodeLaTeX:
    """Test unicode-aware LaTeX escaping."""

    def test_ascii_special_chars_escaped(self) -> None:
        """ASCII special characters are escaped."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        assert escape_unicode_latex("a & b") == r"a \& b"
        assert escape_unicode_latex("100%") == r"100\%"
        assert escape_unicode_latex("$10") == r"\$10"

    def test_cjk_wrapped_in_font_command(self) -> None:
        """CJK text is wrapped in \\cjktext{} command."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        result = escape_unicode_latex("Hello 世界")
        assert "\\cjktext{世界}" in result
        assert "Hello " in result

    def test_multiple_cjk_runs_wrapped_separately(self) -> None:
        """Multiple CJK runs are wrapped separately."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        result = escape_unicode_latex("A 世界 B 中文 C")
        assert result.count("\\cjktext{") == 2

    def test_mixed_cjk_scripts(self) -> None:
        """Different CJK scripts (Chinese, Japanese, Korean) wrapped."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        result = escape_unicode_latex("日本語 한글 中文")
        # All should be wrapped (language-agnostic for now)
        assert "\\cjktext{" in result

    def test_emoji_wrapped_in_emoji_command(self) -> None:
        """Emoji is wrapped in \\emoji{} command."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        result = escape_unicode_latex("Test 🎉!")
        # Emoji library converts to name format
        assert "\\emoji{" in result

    def test_pure_ascii_unchanged(self) -> None:
        """Pure ASCII without special chars passes through."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        assert escape_unicode_latex("Hello world") == "Hello world"

    def test_mixed_cjk_emoji_ascii(self) -> None:
        """Mixed content handles all types correctly."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        result = escape_unicode_latex("Hello 世界 🎉!")
        assert "\\cjktext{世界}" in result
        assert "\\emoji{" in result
        assert "Hello " in result

    def test_control_chars_stripped(self) -> None:
        """ASCII control characters (0x00-0x1F except whitespace) are stripped."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        # Characters like ^A (0x01), ^B (0x02), etc. are invalid in LaTeX
        text_with_controls = "Hello\x01\x02\x03World"
        result = escape_unicode_latex(text_with_controls)
        assert result == "HelloWorld"

    def test_whitespace_preserved(self) -> None:
        """Tab, newline, carriage return are preserved (valid whitespace)."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        assert escape_unicode_latex("a\tb") == "a\tb"
        assert escape_unicode_latex("a\nb") == "a\nb"
        assert escape_unicode_latex("a\r\nb") == "a\r\nb"

    def test_blns_c0_control_chars_handled(self) -> None:
        """BLNS non-whitespace C0 controls string is handled safely."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        # BLNS line: characters 0x01-0x08, 0x0E-0x1F (excluding whitespace)
        blns_c0_controls = (
            "\x01\x02\x03\x04\x05\x06\x07\x08"
            "\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f"
        )
        result = escape_unicode_latex(f"Before{blns_c0_controls}After")
        # All control chars stripped, text preserved
        assert result == "BeforeAfter"

    def test_blns_c1_control_chars_handled(self) -> None:
        """BLNS non-whitespace C1 controls (U+0080-U+009F) are stripped."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        # C1 controls: 0x80-0x9F (often misinterpreted as Windows-1252)
        c1_controls = "".join(chr(c) for c in range(0x80, 0xA0))
        result = escape_unicode_latex(f"Before{c1_controls}After")
        # All C1 control chars stripped, text preserved
        assert result == "BeforeAfter"

    def test_del_char_stripped(self) -> None:
        """DEL character (0x7F) is stripped."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        result = escape_unicode_latex("Before\x7fAfter")
        assert result == "BeforeAfter"


class TestEmojiValidation:
    """Test emoji name validation and fallback."""

    def test_valid_emoji_uses_emoji_command(self) -> None:
        """Valid LaTeX emoji names use \\emoji{} command."""
        from promptgrimoire.export.unicode_latex import _format_emoji_for_latex

        # "grinning-face" is a standard emoji name
        result = _format_emoji_for_latex("grinning-face")
        assert result == "\\emoji{grinning-face}"

    def test_invalid_emoji_uses_fallback(self) -> None:
        """Invalid emoji names fall back to placeholder with name."""
        from promptgrimoire.export.unicode_latex import _format_emoji_for_latex

        # "united-states" is NOT valid - LaTeX expects "flag-united-states" or "us"
        result = _format_emoji_for_latex("united-states")
        assert result == "\\emojifallbackchar{united-states}"

    def test_flag_aliases_work(self) -> None:
        """Country aliases like 'us', 'gb' work as valid names."""
        from promptgrimoire.export.unicode_latex import _format_emoji_for_latex

        # "us" is a valid alias for flag-united-states
        result = _format_emoji_for_latex("us")
        assert result == "\\emoji{us}"

    def test_load_emoji_names_returns_frozenset(self) -> None:
        """_load_latex_emoji_names returns a frozenset."""
        from promptgrimoire.export.unicode_latex import _load_latex_emoji_names

        names = _load_latex_emoji_names()
        assert isinstance(names, frozenset)
        # Should have many emoji names if emoji package is installed
        if names:  # Only check if kpsewhich found the file
            assert len(names) > 100
            assert "grinning-face" in names
            assert "us" in names  # alias


class TestStyFileContent:
    """Test that promptgrimoire-export.sty contains required unicode support."""

    @pytest.fixture
    def sty_content(self) -> str:
        """Read the .sty file content for assertions."""
        from promptgrimoire.export.pdf_export import _STY_SOURCE

        return _STY_SOURCE.read_text(encoding="utf-8")

    def test_sty_includes_fontspec(self, sty_content: str) -> None:
        """The .sty file includes fontspec (always needed)."""
        assert "RequirePackage{fontspec}" in sty_content

    def test_sty_does_not_load_luatexja(self, sty_content: str) -> None:
        """luatexja-fontspec is conditional via build_font_preamble()."""
        assert "RequirePackage{luatexja-fontspec}" not in sty_content

    def test_sty_includes_emoji_package(self, sty_content: str) -> None:
        """The .sty file includes emoji package."""
        assert "RequirePackage{emoji}" in sty_content

    def test_sty_provides_cjktext_passthrough(self, sty_content: str) -> None:
        """The .sty provides \\cjktext as pass-through default.

        build_font_preamble() overrides with \\renewcommand when CJK is detected.
        """
        assert "\\providecommand{\\cjktext}[1]{#1}" in sty_content

    def test_sty_does_not_contain_directlua(self, sty_content: str) -> None:
        """Font fallback chain is now dynamic via build_font_preamble(), not in .sty."""
        assert "\\directlua" not in sty_content

    def test_sty_sets_emoji_font(self, sty_content: str) -> None:
        """The .sty file sets emoji font (Noto Color Emoji)."""
        assert "Noto Color Emoji" in sty_content


def _generate_blns_test_cases() -> list[tuple[str, str]]:
    """Generate (category, line) tuples for parameterized BLNS testing."""
    from tests.unit.conftest import BLNS_BY_CATEGORY

    cases = []
    for category, lines in BLNS_BY_CATEGORY.items():
        for i, line in enumerate(lines):
            # Create a unique test ID: "category[index]"
            test_id = f"{category}[{i}]"
            cases.append((test_id, line))
    return cases


class TestBLNSCorpusEscaping:
    """Parameterized tests for BLNS corpus - each line tested individually.

    When a test fails, the test ID shows exactly which category and line
    caused the failure (e.g., "C0 Controls[2]").
    """

    @pytest.mark.parametrize(
        ("test_id", "blns_line"),
        _generate_blns_test_cases(),
        ids=lambda x: x if isinstance(x, str) and "[" in x else None,
    )
    def test_escape_handles_blns_line(self, test_id: str, blns_line: str) -> None:
        """escape_unicode_latex handles this BLNS line without error."""
        from promptgrimoire.export.unicode_latex import escape_unicode_latex

        # Should not raise
        result = escape_unicode_latex(blns_line)

        # Result should be a string
        assert isinstance(result, str), f"Expected str for {test_id}"

        # Result should not contain any control characters
        for c in result:
            cp = ord(c)
            # Allow only printable ASCII, tab, newline, CR, or high Unicode
            if cp < 0x20:
                assert c in "\t\n\r", f"Control U+{cp:04X} in {test_id}"
            assert cp != 0x7F, f"DEL in {test_id}"
            assert not (0x80 <= cp <= 0x9F), f"C1 U+{cp:04X} in {test_id}"

    @pytest.mark.parametrize(
        ("test_id", "blns_line"),
        _generate_blns_test_cases(),
        ids=lambda x: x if isinstance(x, str) and "[" in x else None,
    )
    def test_strip_handles_blns_line(self, test_id: str, blns_line: str) -> None:
        """_strip_control_chars handles this BLNS line without error."""
        from promptgrimoire.export.unicode_latex import _strip_control_chars

        # Should not raise
        result = _strip_control_chars(blns_line)

        # Result should be a string with no control chars
        assert isinstance(result, str)
        for c in result:
            cp = ord(c)
            if cp < 0x20:
                assert c in "\t\n\r", f"Control char U+{cp:04X} in result for {test_id}"
            assert cp != 0x7F, f"DEL in result for {test_id}"
            assert not (0x80 <= cp <= 0x9F), f"C1 control U+{cp:04X} for {test_id}"
