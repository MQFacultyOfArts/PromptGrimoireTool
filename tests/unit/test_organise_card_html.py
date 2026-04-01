"""Unit tests for Organise tab card HTML rendering (#457).

Tests the pure function ``_render_organise_card_html()`` which renders
a single organise highlight card body as an HTML string. No NiceGUI, no DB.

Verifies: vue-annotation-sidebar-457.AC9.1, AC9.2 (SortableJS contract),
          AC9.3 (locate)
"""

from __future__ import annotations

import html

import pytest


def _render(**kwargs: object) -> str:
    """Shortcut to import and call the function under test."""
    from promptgrimoire.pages.annotation.organise import _render_organise_card_html

    defaults: dict[str, object] = {
        "tag_display": "Jurisdiction",
        "color": "#FF0000",
        "display_author": "Alice",
        "text": "Some highlighted text",
        "comments": [],
    }
    defaults.update(kwargs)
    return _render_organise_card_html(**defaults)  # type: ignore[arg-type]


class TestOrganiseCardHtml:
    """Pure function tests for _render_organise_card_html()."""

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
        assert "border-left:2px" not in result

    def test_long_text_uses_css_overflow(self) -> None:
        long_text = "x" * 300
        result = _render(text=long_text)
        assert "max-height" in result
        assert "overflow" in result

    def test_empty_text_no_text_div(self) -> None:
        result = _render(text="")
        assert "pre-wrap" not in result

    def test_color_applied_to_tag(self) -> None:
        result = _render(color="#00FF00", tag_display="Reasons")
        assert "color:#00FF00" in result or "color: #00FF00" in result

    def test_no_data_testid_on_body(self) -> None:
        """data-testid goes on the NiceGUI wrapper, not in the HTML body."""
        result = _render()
        assert 'data-testid="organise-card"' not in result

    @pytest.mark.parametrize(
        ("comment_author", "comment_text"),
        [
            ("", "orphan comment"),
            ("Author", ""),
        ],
    )
    def test_comment_edge_cases(self, comment_author: str, comment_text: str) -> None:
        """Comments with empty text should be skipped."""
        result = _render(comments=[(comment_author, comment_text)])
        if not comment_text:
            assert comment_author not in result or comment_author == ""
        else:
            assert comment_text in result
