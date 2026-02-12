"""Tests for input_pipeline public API after char-span removal.

Verifies:
- css-highlight-api.AC5.1: removed functions not in __all__
- css-highlight-api.AC5.2: importing removed functions raises ImportError
- css-highlight-api.AC5.3: extract_text_from_html remains available
"""

import pytest

import promptgrimoire.input_pipeline as pkg


class TestCharSpanFunctionsRemoved:
    """Verify char-span functions are removed from the public API (AC5.1, AC5.2)."""

    @pytest.mark.parametrize(
        "name",
        ["inject_char_spans", "strip_char_spans", "extract_chars_from_spans"],
    )
    def test_not_in_all(self, name: str) -> None:
        """AC5.1: removed functions must not appear in __all__."""
        assert name not in pkg.__all__

    def test_inject_char_spans_not_importable_from_package(self) -> None:
        """AC5.2: from promptgrimoire.input_pipeline import inject_char_spans fails."""
        assert not hasattr(pkg, "inject_char_spans")

    def test_strip_char_spans_not_importable_from_package(self) -> None:
        """AC5.2: from promptgrimoire.input_pipeline import strip_char_spans fails."""
        assert not hasattr(pkg, "strip_char_spans")

    def test_extract_chars_from_spans_not_importable(self) -> None:
        """AC5.2: extract_chars_from_spans not on package."""
        assert not hasattr(pkg, "extract_chars_from_spans")


class TestExtractTextFromHtmlAvailable:
    """Verify extract_text_from_html remains available and functional (AC5.3)."""

    def test_importable_from_html_input(self) -> None:
        """AC5.3: extract_text_from_html is importable from html_input module."""
        from promptgrimoire.input_pipeline.html_input import extract_text_from_html

        assert callable(extract_text_from_html)

    def test_produces_correct_output(self) -> None:
        """AC5.3: extract_text_from_html produces correct character list."""
        from promptgrimoire.input_pipeline.html_input import extract_text_from_html

        chars = extract_text_from_html("<p>Hello</p>")
        assert "".join(chars) == "Hello"

    def test_handles_empty_input(self) -> None:
        """AC5.3: extract_text_from_html handles empty input."""
        from promptgrimoire.input_pipeline.html_input import extract_text_from_html

        assert extract_text_from_html("") == []

    def test_handles_br_tags(self) -> None:
        """AC5.3: extract_text_from_html handles br tags as newlines."""
        from promptgrimoire.input_pipeline.html_input import extract_text_from_html

        chars = extract_text_from_html("<p>A<br>B</p>")
        assert "".join(chars) == "A\nB"
