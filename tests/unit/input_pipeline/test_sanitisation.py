"""Tests for input pipeline sanitisation — issue #273.

ChatGPT exports wrap inter-word spaces as ``<span>&nbsp;</span>`` between
inline markup (``<strong>``, ``<em>``).  ``remove_empty_elements()`` must
preserve these — they carry semantically significant whitespace.  Stripping
them joins adjacent words: "a **precondition** for" → "a**precondition**for".
"""

from __future__ import annotations

from promptgrimoire.input_pipeline.sanitisation import remove_empty_elements


def _has_nbsp(html: str) -> bool:
    """Check for nbsp in either raw char or entity form."""
    return "\u00a0" in html or "&nbsp;" in html


class TestRemoveEmptyElementsPreservesNbsp:
    """remove_empty_elements must not strip nbsp-only spans (#273)."""

    def test_nbsp_entity_span_between_strong_tags_preserved(self) -> None:
        """ChatGPT pattern: <strong>word</strong><span>&nbsp;</span>next."""
        html = (
            "<p>a<span>&nbsp;</span>"
            "<strong>precondition</strong>"
            "<span>&nbsp;</span>for</p>"
        )
        result = remove_empty_elements(html)
        assert _has_nbsp(result), (
            "nbsp span stripped — spaces between bold and adjacent words lost"
        )

    def test_raw_nbsp_char_in_span_preserved(self) -> None:
        """Same pattern but with raw U+00A0 instead of entity."""
        html = (
            "<p>a<span>\u00a0</span><strong>bold</strong><span>\u00a0</span>after</p>"
        )
        result = remove_empty_elements(html)
        assert _has_nbsp(result), (
            "raw nbsp span stripped — spaces between bold and adjacent words lost"
        )

    def test_nbsp_span_between_em_tags_preserved(self) -> None:
        """Same pattern with <em> instead of <strong>."""
        html = (
            "<p>the<span>&nbsp;</span>"
            "<em>cognitive authority</em>"
            "<span>&nbsp;</span>defines</p>"
        )
        result = remove_empty_elements(html)
        assert _has_nbsp(result), "nbsp span between <em> tags stripped"

    def test_genuinely_empty_span_still_removed(self) -> None:
        """Truly empty spans (no text at all) should still be removed."""
        html = "<p>text</p><p><span></span></p>"
        result = remove_empty_elements(html)
        assert "<span>" not in result

    def test_regular_space_span_still_removed(self) -> None:
        """Spans with only ASCII spaces are formatting artefacts — remove them."""
        html = "<p>text</p><p><span>   </span></p>"
        result = remove_empty_elements(html)
        # The span is inside a paragraph that has no other content,
        # so the whole paragraph should be removed as empty
        assert "<span>" not in result


class TestRemoveEmptyElementsPreservesNbspInParagraph:
    """Paragraph-level nbsp preservation."""

    def test_nbsp_only_paragraph_preserved(self) -> None:
        """A paragraph containing only &nbsp; is a deliberate spacer."""
        html = "<p>content</p><p>&nbsp;</p><p>more</p>"
        result = remove_empty_elements(html)
        assert result.count("<p") == 3, (
            "nbsp-only paragraph removed — it may be a deliberate spacer"
        )
