"""Unit tests for character-based tokenization."""

from promptgrimoire.pages.annotation import _process_text_to_char_spans


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
