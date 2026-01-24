"""Tests for PDF export functionality."""

from pathlib import Path

import pytest

from promptgrimoire.export.pdf import (
    Annotation,
    ExportOptions,
    _build_annotation_card,
    _build_document_html,
    _build_sidebar_html,
    export_brief_to_pdf,
)


class TestAnnotationCard:
    """Tests for annotation card HTML generation."""

    def test_builds_card_with_all_fields(self) -> None:
        """Card includes tag, paragraph ref, quoted text, and comment."""
        annotation = Annotation(
            id="1",
            quoted_text="The court held that...",
            tag="ratio",
            comment="Key finding",
            paragraph_ref="42",
        )

        html = _build_annotation_card(annotation, include_para_ref=True)

        assert 'class="annotation-card"' in html
        assert 'class="tag ratio"' in html
        assert "ratio" in html
        assert "¶ 42" in html
        assert "The court held that..." in html
        assert "Key finding" in html

    def test_omits_paragraph_ref_when_disabled(self) -> None:
        """Paragraph ref is omitted when include_para_ref=False."""
        annotation = Annotation(
            id="1",
            quoted_text="Text",
            tag="facts",
            paragraph_ref="10",
        )

        html = _build_annotation_card(annotation, include_para_ref=False)

        assert "¶ 10" not in html

    def test_omits_comment_when_none(self) -> None:
        """Comment section is omitted when comment is None."""
        annotation = Annotation(
            id="1",
            quoted_text="Text",
            tag="issue",
            comment=None,
        )

        html = _build_annotation_card(annotation, include_para_ref=True)

        assert 'class="comment"' not in html

    def test_truncates_long_quoted_text(self) -> None:
        """Quoted text over 150 chars is truncated with ellipsis."""
        long_text = "x" * 200
        annotation = Annotation(
            id="1",
            quoted_text=long_text,
            tag="holding",
        )

        html = _build_annotation_card(annotation, include_para_ref=True)

        assert "..." in html
        assert "x" * 147 in html
        assert "x" * 148 not in html


class TestSidebarHtml:
    """Tests for sidebar HTML generation."""

    def test_empty_annotations_shows_message(self) -> None:
        """Empty annotations list shows 'No annotations' message."""
        html = _build_sidebar_html([], include_para_refs=True)

        assert "No annotations" in html

    def test_includes_annotation_count(self) -> None:
        """Sidebar header shows annotation count."""
        annotations = [
            Annotation(id="1", quoted_text="Text 1", tag="ratio"),
            Annotation(id="2", quoted_text="Text 2", tag="facts"),
        ]

        html = _build_sidebar_html(annotations, include_para_refs=True)

        assert "Annotations (2)" in html

    def test_renders_all_cards(self) -> None:
        """All annotation cards are rendered."""
        annotations = [
            Annotation(id="1", quoted_text="First quote", tag="ratio"),
            Annotation(id="2", quoted_text="Second quote", tag="issue"),
        ]

        html = _build_sidebar_html(annotations, include_para_refs=True)

        assert "First quote" in html
        assert "Second quote" in html
        assert html.count("annotation-card") == 2


class TestDocumentHtml:
    """Tests for complete document HTML generation."""

    def test_includes_title(self) -> None:
        """Document includes the title in head and h1."""
        options = ExportOptions(title="Test Case v Crown")

        html = _build_document_html("<p>Content</p>", [], options)

        assert "<title>Test Case v Crown</title>" in html
        assert "<h1>Test Case v Crown</h1>" in html

    def test_includes_brief_content(self) -> None:
        """Document includes the brief HTML content."""
        brief = "<p>The defendant argued...</p>"

        html = _build_document_html(brief, [], ExportOptions())

        assert "The defendant argued..." in html

    def test_includes_sidebar(self) -> None:
        """Document includes the annotations sidebar."""
        annotations = [Annotation(id="1", quoted_text="Quote", tag="ratio")]

        html = _build_document_html("<p>Brief</p>", annotations, ExportOptions())

        assert "annotations-sidebar" in html
        assert "Quote" in html


class TestExportBriefToPdf:
    """Tests for PDF export function."""

    def test_creates_pdf_file(self, tmp_path: Path) -> None:
        """PDF file is created at the specified path."""
        output = tmp_path / "test.pdf"

        result = export_brief_to_pdf(
            "<p>Test content</p>",
            [],
            output,
        )

        assert result == output
        assert output.exists()
        assert output.stat().st_size > 0

    def test_pdf_starts_with_magic_bytes(self, tmp_path: Path) -> None:
        """Generated file is a valid PDF (starts with %PDF)."""
        output = tmp_path / "test.pdf"

        export_brief_to_pdf("<p>Content</p>", [], output)

        content = output.read_bytes()
        assert content.startswith(b"%PDF")

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        """Function accepts string path as well as Path object."""
        output = str(tmp_path / "test.pdf")

        result = export_brief_to_pdf("<p>Content</p>", [], output)

        assert Path(output).exists()
        assert result == Path(output)

    def test_uses_custom_options(self, tmp_path: Path) -> None:
        """Custom export options are applied."""
        output = tmp_path / "test.pdf"
        options = ExportOptions(
            title="Custom Title",
            page_size="Letter",
            margin="1in",
        )

        # Should not raise
        export_brief_to_pdf("<p>Content</p>", [], output, options)

        assert output.exists()

    def test_includes_annotations_in_pdf(self, tmp_path: Path) -> None:
        """Annotations are included in the generated PDF."""
        output = tmp_path / "test.pdf"
        annotations = [
            Annotation(
                id="1",
                quoted_text="Important quote",
                tag="ratio",
                comment="This is crucial",
            ),
        ]

        export_brief_to_pdf(
            "<p>Brief content with highlights</p>",
            annotations,
            output,
        )

        # PDF is generated (content verification would require PDF parsing)
        assert output.exists()
        assert output.stat().st_size > 1000  # Non-trivial size

    def test_handles_special_characters(self, tmp_path: Path) -> None:
        """Special characters in content don't break PDF generation."""
        output = tmp_path / "test.pdf"
        brief = '<p>Legal § symbols &amp; ampersands — em-dashes "quotes"</p>'
        annotations = [
            Annotation(
                id="1",
                quoted_text="§ 42 of the Act",
                tag="jurisdiction",
            ),
        ]

        # Should not raise
        export_brief_to_pdf(brief, annotations, output)

        assert output.exists()
