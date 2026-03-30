"""Tests for _render_compact_header_html pure function.

Verifies HTML output correctness and XSS defense-in-depth escaping.
"""

from __future__ import annotations

from promptgrimoire.pages.annotation.cards import _render_compact_header_html


class TestRenderCompactHeaderHtml:
    """Unit tests for the compact header HTML rendering function."""

    def test_colour_dot_present_with_escaped_colour(self) -> None:
        result = _render_compact_header_html(
            tag_display="Important",
            color="#FF0000",
            initials="AB",
            para_ref="",
            comment_count=0,
        )
        assert (
            "background-color:#FF0000;" in result
            or "background-color: #FF0000;" in result.replace(" ", "")
        )
        assert "border-radius:50%;" in result.replace(" ", "")

    def test_tag_display_html_escaped(self) -> None:
        """XSS defense-in-depth: tag names must be escaped."""
        result = _render_compact_header_html(
            tag_display='<script>alert("xss")</script>',
            color="#999",
            initials="AB",
            para_ref="",
            comment_count=0,
        )
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_initials_html_escaped(self) -> None:
        result = _render_compact_header_html(
            tag_display="Tag",
            color="#999",
            initials='<img src=x onerror="alert(1)">',
            para_ref="",
            comment_count=0,
        )
        assert "<img" not in result
        assert "&lt;img" in result

    def test_comment_badge_hidden_when_zero(self) -> None:
        result = _render_compact_header_html(
            tag_display="Tag",
            color="#999",
            initials="AB",
            para_ref="",
            comment_count=0,
        )
        assert 'data-testid="comment-count"' not in result

    def test_comment_badge_shown_when_positive(self) -> None:
        result = _render_compact_header_html(
            tag_display="Tag",
            color="#999",
            initials="AB",
            para_ref="",
            comment_count=3,
        )
        assert 'data-testid="comment-count"' in result
        assert ">3</span>" in result

    def test_para_ref_hidden_when_empty(self) -> None:
        result = _render_compact_header_html(
            tag_display="Tag",
            color="#999",
            initials="AB",
            para_ref="",
            comment_count=0,
        )
        assert "font-mono" not in result

    def test_para_ref_shown_when_nonempty(self) -> None:
        result = _render_compact_header_html(
            tag_display="Tag",
            color="#999",
            initials="AB",
            para_ref="p.42",
            comment_count=0,
        )
        assert "font-mono" in result
        assert "p.42" in result

    def test_para_ref_html_escaped(self) -> None:
        result = _render_compact_header_html(
            tag_display="Tag",
            color="#999",
            initials="AB",
            para_ref='<b>"bold"</b>',
            comment_count=0,
        )
        assert "<b>" not in result
        assert "&lt;b&gt;" in result

    def test_spacer_present(self) -> None:
        result = _render_compact_header_html(
            tag_display="Tag",
            color="#999",
            initials="AB",
            para_ref="",
            comment_count=0,
        )
        assert "flex-grow:1;" in result.replace(" ", "")

    def test_container_has_flex_layout(self) -> None:
        result = _render_compact_header_html(
            tag_display="Tag",
            color="#999",
            initials="AB",
            para_ref="",
            comment_count=0,
        )
        assert "display:flex;" in result.replace(" ", "")
        assert "align-items:center;" in result.replace(" ", "")

    def test_colour_in_style_escaped(self) -> None:
        """Color value is escaped in style attributes (defense-in-depth)."""
        result = _render_compact_header_html(
            tag_display="Tag",
            color='"><script>x</script>',
            initials="AB",
            para_ref="",
            comment_count=0,
        )
        assert "<script>" not in result
