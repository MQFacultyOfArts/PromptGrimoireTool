"""Unit tests for LaTeX export with annotations."""

from __future__ import annotations

from promptgrimoire.export.latex import (
    _escape_latex,
    _format_annot,
    _format_timestamp,
    _insert_markers_into_html,
    _replace_markers_with_annots,
    build_annotation_preamble,
    generate_tag_colour_definitions,
)


class TestEscapeLatex:
    """Tests for _escape_latex function."""

    def test_escape_ampersand(self) -> None:
        """Ampersand should be escaped."""
        assert _escape_latex("A & B") == r"A \& B"

    def test_escape_percent(self) -> None:
        """Percent should be escaped."""
        assert _escape_latex("100%") == r"100\%"

    def test_escape_dollar(self) -> None:
        """Dollar sign should be escaped."""
        assert _escape_latex("$100") == r"\$100"

    def test_escape_underscore(self) -> None:
        """Underscore should be escaped."""
        assert _escape_latex("foo_bar") == r"foo\_bar"

    def test_escape_hash(self) -> None:
        """Hash should be escaped."""
        assert _escape_latex("#1") == r"\#1"

    def test_escape_curly_braces(self) -> None:
        """Curly braces should be escaped."""
        assert _escape_latex("{x}") == r"\{x\}"


class TestFormatTimestamp:
    """Tests for _format_timestamp function."""

    def test_valid_iso_timestamp(self) -> None:
        """Valid ISO timestamp should be formatted."""
        result = _format_timestamp("2026-01-26T14:30:00+00:00")
        assert "26" in result
        assert "Jan" in result
        assert "2026" in result
        assert "14:30" in result

    def test_invalid_timestamp_returns_empty(self) -> None:
        """Invalid timestamp should return empty string."""
        assert _format_timestamp("not-a-date") == ""

    def test_empty_timestamp_returns_empty(self) -> None:
        """Empty timestamp should return empty string."""
        assert _format_timestamp("") == ""


class TestGenerateTagColourDefinitions:
    """Tests for generate_tag_colour_definitions function."""

    def test_single_tag(self) -> None:
        """Single tag should produce one definecolor."""
        result = generate_tag_colour_definitions({"jurisdiction": "#1f77b4"})
        assert r"\definecolor{tag-jurisdiction}{HTML}{1f77b4}" in result

    def test_multiple_tags(self) -> None:
        """Multiple tags should produce multiple definecolors."""
        result = generate_tag_colour_definitions(
            {
                "jurisdiction": "#1f77b4",
                "legal_issues": "#d62728",
            }
        )
        assert r"\definecolor{tag-jurisdiction}{HTML}{1f77b4}" in result
        assert r"\definecolor{tag-legal-issues}{HTML}{d62728}" in result

    def test_underscore_converted_to_dash(self) -> None:
        """Underscores in tag names should become dashes."""
        result = generate_tag_colour_definitions({"my_tag_name": "#ffffff"})
        assert "tag-my-tag-name" in result

    def test_hash_stripped_from_colour(self) -> None:
        """Hash should be stripped from colour value."""
        result = generate_tag_colour_definitions({"tag": "#AABBCC"})
        assert "{AABBCC}" in result
        assert "##" not in result


class TestBuildAnnotationPreamble:
    """Tests for build_annotation_preamble function."""

    def test_includes_xcolor(self) -> None:
        """Preamble should include xcolor package."""
        result = build_annotation_preamble({"tag": "#000000"})
        assert r"\usepackage{xcolor}" in result

    def test_includes_marginnote(self) -> None:
        """Preamble should include marginnote package."""
        result = build_annotation_preamble({"tag": "#000000"})
        assert r"\usepackage{marginnote}" in result

    def test_includes_geometry(self) -> None:
        """Preamble should include geometry package with wide right margin."""
        result = build_annotation_preamble({"tag": "#000000"})
        assert r"\usepackage[" in result
        assert "right=6cm" in result

    def test_includes_annot_command(self) -> None:
        """Preamble should define annot command."""
        result = build_annotation_preamble({"tag": "#000000"})
        assert r"\newcommand{\annot}" in result

    def test_includes_colour_definitions(self) -> None:
        """Preamble should include colour definitions."""
        result = build_annotation_preamble({"jurisdiction": "#1f77b4"})
        assert r"\definecolor{tag-jurisdiction}" in result


class TestFormatAnnot:
    """Tests for _format_annot function."""

    def test_basic_annotation(self) -> None:
        """Basic annotation should produce valid annot command."""
        highlight = {
            "tag": "jurisdiction",
            "author": "Alice",
            "text": "The court held",
            "comments": [],
            "created_at": "2026-01-26T14:30:00+00:00",
        }
        result = _format_annot(highlight)
        assert r"\annot{tag-jurisdiction}" in result
        assert "Jurisdiction" in result  # Tag display name
        assert "Alice" in result

    def test_with_paragraph_reference(self) -> None:
        """Annotation with para ref should include it."""
        highlight = {
            "tag": "reasons",
            "author": "Bob",
            "text": "reasoning here",
            "comments": [],
        }
        result = _format_annot(highlight, para_ref="[45]")
        assert "[45]" in result

    def test_with_comments(self) -> None:
        """Annotation with comments should include them."""
        highlight = {
            "tag": "decision",
            "author": "Alice",
            "text": "decision text",
            "comments": [
                {"author": "Bob", "text": "Good point"},
                {"author": "Carol", "text": "I agree"},
            ],
        }
        result = _format_annot(highlight)
        assert "Bob" in result
        assert "Good point" in result
        assert "Carol" in result
        assert "I agree" in result

    def test_escapes_special_characters_in_author(self) -> None:
        """Special characters in author should be escaped."""
        highlight = {
            "tag": "tag",
            "author": "User & Co",
            "text": "some text",
            "comments": [],
        }
        result = _format_annot(highlight)
        assert r"\&" in result

    def test_escapes_special_characters_in_comments(self) -> None:
        """Special characters in comments should be escaped."""
        highlight = {
            "tag": "tag",
            "author": "User",
            "text": "some text",
            "comments": [{"author": "Bob", "text": "100% agree & more"}],
        }
        result = _format_annot(highlight)
        assert r"\%" in result
        assert r"\&" in result


class TestInsertMarkersIntoHtml:
    """Tests for _insert_markers_into_html function."""

    def test_empty_highlights(self) -> None:
        """Empty highlights should return unchanged HTML."""
        html = "<p>Hello world</p>"
        result, markers = _insert_markers_into_html(html, [])
        assert result == html
        assert markers == []

    def test_single_highlight(self) -> None:
        """Single highlight should insert marker at word position."""
        html = "<p>Hello world test</p>"
        highlights = [{"start_word": 1, "tag": "test"}]
        result, markers = _insert_markers_into_html(html, highlights)
        assert "ANNMARKER0ENDMARKER" in result
        assert "world" in result
        assert len(markers) == 1

    def test_multiple_highlights(self) -> None:
        """Multiple highlights should insert multiple markers."""
        html = "<p>One two three four five</p>"
        highlights = [
            {"start_word": 1, "tag": "a"},
            {"start_word": 3, "tag": "b"},
        ]
        result, markers = _insert_markers_into_html(html, highlights)
        assert "ANNMARKER0ENDMARKER" in result
        assert "ANNMARKER1ENDMARKER" in result
        assert len(markers) == 2

    def test_preserves_html_tags(self) -> None:
        """HTML tags should be preserved."""
        html = "<p><strong>Bold</strong> text</p>"
        highlights = [{"start_word": 0, "tag": "test"}]
        result, _ = _insert_markers_into_html(html, highlights)
        assert "<strong>" in result
        assert "</strong>" in result


class TestReplaceMarkersWithAnnots:
    """Tests for _replace_markers_with_annots function."""

    def test_replaces_marker(self) -> None:
        """Marker should be replaced with annot command."""
        latex = "Some ANNMARKER0ENDMARKER text here"
        highlights = [
            {
                "start_word": 0,
                "end_word": 1,
                "tag": "jurisdiction",
                "author": "Alice",
                "text": "test",
                "comments": [],
            }
        ]
        result = _replace_markers_with_annots(latex, highlights)
        assert "ANNMARKER" not in result
        assert r"\annot{tag-jurisdiction}" in result

    def test_with_word_to_legal_para(self) -> None:
        """Should include paragraph reference when mapping provided."""
        latex = "Some ANNMARKER0ENDMARKER text"
        highlights = [
            {
                "start_word": 5,
                "end_word": 8,
                "tag": "reasons",
                "author": "Bob",
                "text": "test",
                "comments": [],
            }
        ]
        word_to_para = {5: 10, 6: 10, 7: 10}
        result = _replace_markers_with_annots(latex, highlights, word_to_para)
        assert "[10]" in result

    def test_multiple_markers(self) -> None:
        """Multiple markers should all be replaced."""
        latex = "ANNMARKER0ENDMARKER and ANNMARKER1ENDMARKER"
        highlights = [
            {
                "start_word": 0,
                "end_word": 1,
                "tag": "a",
                "author": "X",
                "text": "t",
                "comments": [],
            },
            {
                "start_word": 2,
                "end_word": 3,
                "tag": "b",
                "author": "Y",
                "text": "u",
                "comments": [],
            },
        ]
        result = _replace_markers_with_annots(latex, highlights)
        assert "ANNMARKER" not in result
        assert r"\annot{tag-a}" in result
        assert r"\annot{tag-b}" in result
