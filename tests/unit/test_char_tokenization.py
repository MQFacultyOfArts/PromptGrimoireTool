"""Unit tests for character-based tokenization."""

import pytest

from promptgrimoire.pages.annotation import _process_text_to_char_spans
from tests.unit.conftest import CJK_TEST_CHARS


class TestProcessTextToCharSpans:
    """Tests for _process_text_to_char_spans function."""

    def test_empty_string_returns_empty(self) -> None:
        """Empty input returns empty string."""
        result, chars = _process_text_to_char_spans("")
        assert result == ""
        assert chars == []

    def test_single_word_ascii(self) -> None:
        """Single ASCII word creates spans for each character."""
        result, chars = _process_text_to_char_spans("Hello")
        assert chars == ["H", "e", "l", "l", "o"]
        assert 'data-char-index="0"' in result
        assert 'data-char-index="4"' in result
        assert ">H<" in result
        assert ">o<" in result

    def test_whitespace_gets_index(self) -> None:
        """Spaces are indexed as characters."""
        result, chars = _process_text_to_char_spans("a b")
        assert chars == ["a", " ", "b"]
        assert 'data-char-index="0"' in result  # 'a'
        assert 'data-char-index="1"' in result  # ' '
        assert 'data-char-index="2"' in result  # 'b'

    def test_multiple_spaces_preserved(self) -> None:
        """Multiple consecutive spaces each get their own index."""
        _result, chars = _process_text_to_char_spans("a  b")
        assert chars == ["a", " ", " ", "b"]
        assert len(chars) == 4

    def test_cjk_characters_split_individually(self) -> None:
        """CJK characters are each a separate unit."""
        result, chars = _process_text_to_char_spans("你好")
        assert chars == ["你", "好"]
        assert 'data-char-index="0"' in result
        assert 'data-char-index="1"' in result
        assert ">你<" in result
        assert ">好<" in result

    def test_mixed_cjk_and_ascii(self) -> None:
        """Mixed CJK and ASCII text tokenizes correctly."""
        _result, chars = _process_text_to_char_spans("Hello你好")
        assert chars == ["H", "e", "l", "l", "o", "你", "好"]
        assert len(chars) == 7

    def test_newline_creates_paragraph_break(self) -> None:
        """Newlines create paragraph breaks, chars continue indexing."""
        result, chars = _process_text_to_char_spans("ab\ncd")
        assert chars == ["a", "b", "c", "d"]  # Newline not indexed
        assert "</p>" in result
        assert 'data-para="0"' in result
        assert 'data-para="1"' in result

    def test_empty_line_preserved(self) -> None:
        """Empty lines create paragraphs with nbsp."""
        result, _chars = _process_text_to_char_spans("a\n\nb")
        assert "&nbsp;" in result
        assert 'data-para="1"' in result  # Empty line

    def test_html_special_chars_escaped(self) -> None:
        """HTML special characters are escaped."""
        result, chars = _process_text_to_char_spans("<>&")
        assert chars == ["<", ">", "&"]
        assert "&lt;" in result
        assert "&gt;" in result
        assert "&amp;" in result

    def test_non_breaking_space_indexed(self) -> None:
        """Non-breaking space (U+00A0) gets its own index."""
        _result, chars = _process_text_to_char_spans("a\u00a0b")
        assert chars == ["a", "\u00a0", "b"]
        assert len(chars) == 3

    def test_class_is_char_not_word(self) -> None:
        """Spans have class='char' not 'word'."""
        result, _chars = _process_text_to_char_spans("a")
        assert 'class="char"' in result
        assert 'class="word"' not in result


class TestCharTokenizationBLNS:
    """Tests using BLNS corpus for edge cases."""

    @pytest.mark.parametrize("char", CJK_TEST_CHARS[:20])  # Sample of CJK chars
    def test_cjk_char_from_blns(self, char: str) -> None:
        """Each CJK character from BLNS is tokenized individually."""
        result, chars = _process_text_to_char_spans(char)
        assert len(chars) == 1
        assert chars[0] == char
        assert 'data-char-index="0"' in result

    def test_rtl_arabic_tokenizes(self) -> None:
        """Arabic RTL text tokenizes character by character."""
        arabic = "مرحبا"
        _result, chars = _process_text_to_char_spans(arabic)
        assert len(chars) == 5
        assert all(c in chars for c in arabic)

    def test_rtl_hebrew_tokenizes(self) -> None:
        """Hebrew RTL text tokenizes character by character."""
        hebrew = "שלום"
        _result, chars = _process_text_to_char_spans(hebrew)
        assert len(chars) == 4

    def test_emoji_split_by_codepoint(self) -> None:
        """Emoji are split by Unicode code point (acceptable for MVP)."""
        _result, chars = _process_text_to_char_spans("\U0001f600")
        assert len(chars) == 1

    def test_ideographic_space_indexed(self) -> None:
        """Ideographic space (U+3000) is indexed."""
        _result, chars = _process_text_to_char_spans("a\u3000b")
        assert chars == ["a", "\u3000", "b"]

    def test_zero_width_joiner_indexed(self) -> None:
        """Zero-width joiner (U+200D) is indexed as a character."""
        _result, chars = _process_text_to_char_spans("a\u200db")
        assert chars == ["a", "\u200d", "b"]

    def test_control_chars_indexed(self) -> None:
        """Control characters are indexed but may render invisibly."""
        _result, chars = _process_text_to_char_spans("a\tb")
        assert chars == ["a", "\t", "b"]
