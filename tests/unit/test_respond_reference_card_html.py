"""Unit tests for Respond tab reference card HTML rendering (#457).

Tests the pure function ``_render_reference_card_html()`` which renders
a single highlight reference card as an HTML string. No NiceGUI, no DB.

Verifies: vue-annotation-sidebar-457.AC8.1, AC8.3
"""

from __future__ import annotations

import html

import pytest


def _render(**kwargs: object) -> str:
    """Shortcut to import and call the function under test."""
    from promptgrimoire.pages.annotation.respond import _render_reference_card_html

    defaults: dict[str, object] = {
        "tag_display": "Jurisdiction",
        "color": "#FF0000",
        "display_author": "Alice",
        "text": "Some highlighted text",
        "para_ref": "",
        "comments": [],
    }
    defaults.update(kwargs)
    return _render_reference_card_html(**defaults)  # type: ignore[arg-type]


class TestReferenceCardHtml:
    """Pure function tests for _render_reference_card_html()."""

    def test_basic_rendering_contains_tag_display(self) -> None:
        result = _render(tag_display="Legal Issues")
        assert "Legal Issues" in result

    def test_basic_rendering_contains_color(self) -> None:
        result = _render(color="#3498db")
        assert "#3498db" in result

    def test_basic_rendering_contains_author(self) -> None:
        result = _render(display_author="Bob Smith")
        assert "Bob Smith" in result

    def test_basic_rendering_contains_text(self) -> None:
        result = _render(text="The appellant was convicted")
        assert "The appellant was convicted" in result

    def test_xss_escaping_tag_display(self) -> None:
        result = _render(tag_display='<script>alert("xss")</script>')
        assert "<script>" not in result
        assert html.escape('<script>alert("xss")</script>') in result

    def test_xss_escaping_author(self) -> None:
        result = _render(display_author='<img onerror="alert(1)">')
        assert 'onerror="alert(1)"' not in result
        assert html.escape('<img onerror="alert(1)">') in result

    def test_xss_escaping_text(self) -> None:
        result = _render(text="<script>steal()</script>")
        assert "<script>" not in result
        assert html.escape("<script>steal()</script>") in result

    def test_xss_escaping_comment_text(self) -> None:
        result = _render(comments=[("Author", '<script>alert("xss")</script>')])
        assert "<script>" not in result

    def test_xss_escaping_comment_author(self) -> None:
        result = _render(comments=[('<img onerror="alert(1)">', "comment text")])
        assert 'onerror="alert(1)"' not in result

    def test_comments_two_rendered(self) -> None:
        result = _render(
            comments=[
                ("Alice", "First comment"),
                ("Bob", "Second comment"),
            ]
        )
        assert "First comment" in result
        assert "Second comment" in result
        assert "Alice" in result
        assert "Bob" in result

    def test_comments_empty_not_rendered(self) -> None:
        result = _render(comments=[])
        # No comment section markers present
        assert "border-left: 2px" not in result

    def test_para_ref_present(self) -> None:
        result = _render(para_ref="¶3")
        assert "¶3" in result

    def test_para_ref_absent(self) -> None:
        result = _render(para_ref="")
        # Para ref section should not appear
        assert "font-mono" not in result

    def test_long_text_uses_css_overflow(self) -> None:
        long_text = "x" * 300
        result = _render(text=long_text)
        # Should use CSS max-height for overflow, not JS expand/collapse
        assert "max-height" in result
        assert "overflow" in result

    def test_empty_text_no_text_div(self) -> None:
        result = _render(text="")
        # No text preview div when text is empty
        assert "pre-wrap" not in result

    def test_data_testid_respond_reference_card(self) -> None:
        """The outer element must not carry data-testid (moved to wrapper)."""
        # The pure function renders the BODY of the card.
        # data-testid="respond-reference-card" is on the NiceGUI wrapper.
        # The HTML body should not duplicate it.
        result = _render()
        assert 'data-testid="respond-reference-card"' not in result

    def test_color_applied_to_border_and_tag(self) -> None:
        result = _render(color="#00FF00", tag_display="Reasons")
        # Color should appear in tag styling
        assert "color:#00FF00" in result or "color: #00FF00" in result

    @pytest.mark.parametrize(
        ("comment_author", "comment_text"),
        [
            ("", "orphan comment"),  # empty author
            ("Author", ""),  # empty text — should be skipped
        ],
    )
    def test_comment_edge_cases(self, comment_author: str, comment_text: str) -> None:
        """Comments with empty text should be skipped (matching current behaviour)."""
        result = _render(comments=[(comment_author, comment_text)])
        if not comment_text:
            # Empty comment text: comment should not appear
            assert comment_author not in result or comment_author == ""
        else:
            # Non-empty text: comment should appear regardless of author
            assert comment_text in result
