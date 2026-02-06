"""Test that plain text newlines are preserved in PDF export."""

from promptgrimoire.export.pdf_export import _plain_text_to_html


class TestPlainTextToHtml:
    """Tests for _plain_text_to_html conversion."""

    def test_single_line(self) -> None:
        """Single line produces single paragraph."""
        result = _plain_text_to_html("Hello world")
        assert result == "<p>Hello world</p>"

    def test_multiple_lines(self) -> None:
        """Multiple lines produce multiple paragraphs."""
        result = _plain_text_to_html("Line one.\nLine two.")
        assert "<p>Line one.</p>" in result
        assert "<p>Line two.</p>" in result

    def test_empty_lines_preserved(self) -> None:
        """Empty lines produce empty paragraphs for spacing."""
        result = _plain_text_to_html("Line one.\n\nLine three.")
        assert result.count("<p>") == 3  # Line one, empty, Line three

    def test_special_chars_escaped_by_default(self) -> None:
        """HTML special characters are escaped by default."""
        result = _plain_text_to_html("a < b & c > d")
        assert "&lt;" in result
        assert "&amp;" in result
        assert "&gt;" in result

    def test_escape_true_explicit(self) -> None:
        """escape=True explicitly escapes special chars."""
        result = _plain_text_to_html("a < b & c > d", escape=True)
        assert "&lt;" in result
        assert "&amp;" in result
        assert "&gt;" in result

    def test_escape_false_preserves_raw(self) -> None:
        """escape=False preserves raw characters and adds structural marker.

        Issue #113: When markers need to be inserted, we must NOT escape first
        because escaping changes character counts (& becomes &amp;, 1 char -> 5).
        The data-structural attribute allows later escaping to identify our tags.
        """
        result = _plain_text_to_html("a < b & c > d", escape=False)
        assert "<" in result and "&lt;" not in result
        assert "&" in result and "&amp;" not in result
        assert ">" in result and "&gt;" not in result
        # Wraps in <p> with structural marker
        assert result == '<p data-structural="1">a < b & c > d</p>'

    def test_empty_input(self) -> None:
        """Empty input returns empty string."""
        assert _plain_text_to_html("") == ""
        assert _plain_text_to_html(None) == ""


class TestEscapeHtmlTextContent:
    """Tests for _escape_html_text_content function (Issue #113 fix).

    These tests use the actual flow: _plain_text_to_html(escape=False) creates
    HTML with data-structural markers, then _escape_html_text_content processes it.
    """

    def test_escapes_ampersand_in_text(self) -> None:
        """Ampersand in text content is escaped."""
        from promptgrimoire.export.latex import _escape_html_text_content

        # Use actual flow: _plain_text_to_html creates structural tags
        html = _plain_text_to_html("foo & bar", escape=False)
        result = _escape_html_text_content(html)
        assert result == "<p>foo &amp; bar</p>"

    def test_escapes_less_than_in_text(self) -> None:
        """Less-than in text content is escaped."""
        from promptgrimoire.export.latex import _escape_html_text_content

        html = _plain_text_to_html("a < b", escape=False)
        result = _escape_html_text_content(html)
        assert result == "<p>a &lt; b</p>"

    def test_escapes_user_tags_in_content(self) -> None:
        """User content that looks like tags is escaped."""
        from promptgrimoire.export.latex import _escape_html_text_content

        # User typed "<div>test</div>" as literal text
        html = _plain_text_to_html("<div>test</div>", escape=False)
        result = _escape_html_text_content(html)
        # The user's <div> is escaped, our <p> is preserved
        assert "<p>" in result and "</p>" in result
        assert "&lt;div&gt;" in result and "&lt;/div&gt;" in result

    def test_escapes_user_p_tags_in_content(self) -> None:
        """User content containing </p> is escaped, not treated as structural."""
        from promptgrimoire.export.latex import _escape_html_text_content

        # User typed "text </p> more" - the </p> is content, not a tag
        html = _plain_text_to_html("text </p> more", escape=False)
        result = _escape_html_text_content(html)
        # The user's </p> should be escaped
        assert "&lt;/p&gt;" in result

    def test_preserves_markers(self) -> None:
        """Annotation markers are preserved (they're ASCII)."""
        from promptgrimoire.export.latex import (
            _escape_html_text_content,
            _insert_markers_into_html,
        )

        # Actual flow: wrap without escape, insert markers, then escape
        html = _plain_text_to_html("jav&#x0A;ascript", escape=False)
        marked, _ = _insert_markers_into_html(
            html, [{"start_char": 4, "end_char": 9, "tag": "test"}]
        )
        result = _escape_html_text_content(marked)

        # & before marker gets escaped to &amp;
        assert "&amp;HLSTART0ENDHL" in result
        # Markers themselves are untouched
        assert "HLSTART0ENDHL" in result
        assert "HLEND0ENDHL" in result
        assert "ANNMARKER0ENDMARKER" in result

    def test_blns_xss_payload(self) -> None:
        """Full BLNS XSS payload with highlight markers is handled correctly."""
        from promptgrimoire.export.latex import (
            _escape_html_text_content,
            _insert_markers_into_html,
        )

        # Actual BLNS-like payload
        raw = 'jav&#x0A;ascript:alert("XSS")'
        html = _plain_text_to_html(raw, escape=False)
        # Highlight around "#x0A;" (chars 4-8)
        marked, _ = _insert_markers_into_html(
            html, [{"start_char": 4, "end_char": 9, "tag": "test"}]
        )
        result = _escape_html_text_content(marked)

        # & before marker is escaped
        assert "&amp;HLSTART0ENDHL" in result
        # Quotes in the payload are escaped
        assert "&quot;XSS&quot;" in result
        # The highlighted content #x0A; is wrapped correctly
        assert "HLSTART0ENDHL#x0A;HLEND0ENDHL" in result
