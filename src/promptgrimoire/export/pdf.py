"""PDF export for Case Brief Tool.

Generates a PDF with the brief content and annotations in a sidebar layout.
Uses WeasyPrint for HTML-to-PDF conversion with CSS for layout.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from weasyprint import CSS, HTML

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass
class Annotation:
    """An annotation/highlight with its associated card content."""

    id: str
    quoted_text: str
    tag: str
    comment: str | None = None
    paragraph_ref: str | None = None


@dataclass
class ExportOptions:
    """Options for PDF export."""

    title: str = "Case Brief"
    author: str | None = None
    include_paragraph_refs: bool = True
    page_size: str = "A4"
    margin: str = "2cm"


# CSS for the two-column layout with sidebar
BRIEF_PDF_CSS = """
@page {
    size: %(page_size)s;
    margin: %(margin)s;

    @bottom-center {
        content: counter(page) " of " counter(pages);
        font-size: 10pt;
        color: #666;
    }
}

* {
    box-sizing: border-box;
}

body {
    font-family: "Times New Roman", Times, serif;
    font-size: 12pt;
    line-height: 1.5;
    color: #333;
}

.document-container {
    display: flex;
    gap: 1.5cm;
}

.brief-content {
    flex: 2;
    min-width: 0;
}

.annotations-sidebar {
    flex: 1;
    min-width: 6cm;
    max-width: 8cm;
    font-size: 10pt;
}

/* Brief content styling */
.brief-content h1 {
    font-size: 18pt;
    margin-bottom: 0.5cm;
    border-bottom: 2px solid #333;
    padding-bottom: 0.25cm;
}

.brief-content p {
    margin-bottom: 0.5em;
    text-align: justify;
}

/* Highlight styling */
.highlight {
    background-color: #fff3cd;
    padding: 1px 2px;
    border-radius: 2px;
}

.highlight[data-tag="ratio"] {
    background-color: #d4edda;
    border-left: 3px solid #28a745;
}

.highlight[data-tag="facts"] {
    background-color: #cce5ff;
    border-left: 3px solid #007bff;
}

.highlight[data-tag="issue"] {
    background-color: #f8d7da;
    border-left: 3px solid #dc3545;
}

.highlight[data-tag="holding"] {
    background-color: #e2d5f1;
    border-left: 3px solid #6f42c1;
}

.highlight[data-tag="jurisdiction"] {
    background-color: #d1ecf1;
    border-left: 3px solid #17a2b8;
}

/* Annotation card styling */
.annotation-card {
    background: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 4px;
    padding: 0.4cm;
    margin-bottom: 0.4cm;
    page-break-inside: avoid;
}

.annotation-card .tag {
    display: inline-block;
    font-size: 8pt;
    font-weight: bold;
    text-transform: uppercase;
    padding: 2px 6px;
    border-radius: 3px;
    margin-bottom: 0.2cm;
}

.annotation-card .tag.ratio { background: #d4edda; color: #155724; }
.annotation-card .tag.facts { background: #cce5ff; color: #004085; }
.annotation-card .tag.issue { background: #f8d7da; color: #721c24; }
.annotation-card .tag.holding { background: #e2d5f1; color: #432874; }
.annotation-card .tag.jurisdiction { background: #d1ecf1; color: #0c5460; }
.annotation-card .tag.reflection { background: #fff3cd; color: #856404; }

.annotation-card .para-ref {
    font-size: 8pt;
    color: #666;
    margin-bottom: 0.15cm;
}

.annotation-card .quoted-text {
    font-style: italic;
    font-size: 9pt;
    color: #555;
    border-left: 2px solid #ccc;
    padding-left: 0.3cm;
    margin-bottom: 0.2cm;
}

.annotation-card .comment {
    font-size: 10pt;
    color: #333;
}

/* Code block styling */
pre {
    background-color: #f4f4f4;
    border: 1px solid #ddd;
    border-radius: 4px;
    padding: 0.5cm;
    margin: 0.5em 0;
    font-family: "Courier New", Courier, monospace;
    font-size: 10pt;
    line-height: 1.4;
    overflow-x: auto;
    white-space: pre-wrap;
    word-wrap: break-word;
}

code {
    font-family: "Courier New", Courier, monospace;
    font-size: 10pt;
    background-color: #f4f4f4;
    padding: 1px 4px;
    border-radius: 3px;
}

pre code {
    background: none;
    padding: 0;
    border-radius: 0;
}

/* Sidebar header */
.sidebar-header {
    font-size: 14pt;
    font-weight: bold;
    margin-bottom: 0.5cm;
    padding-bottom: 0.25cm;
    border-bottom: 1px solid #ccc;
}
"""


def _build_annotation_card(annotation: Annotation, include_para_ref: bool) -> str:
    """Build HTML for a single annotation card."""
    parts = ['<div class="annotation-card">']
    parts.append(f'<span class="tag {annotation.tag}">{annotation.tag}</span>')

    if include_para_ref and annotation.paragraph_ref:
        parts.append(f'<div class="para-ref">¶ {annotation.paragraph_ref}</div>')

    # Truncate quoted text for sidebar display
    quoted = annotation.quoted_text
    if len(quoted) > 150:
        quoted = quoted[:147] + "..."
    parts.append(f'<div class="quoted-text">"{quoted}"</div>')

    if annotation.comment:
        parts.append(f'<div class="comment">{annotation.comment}</div>')

    parts.append("</div>")
    return "\n".join(parts)


def _build_sidebar_html(
    annotations: Sequence[Annotation], include_para_refs: bool
) -> str:
    """Build the annotations sidebar HTML."""
    if not annotations:
        return '<div class="annotations-sidebar"><p>No annotations</p></div>'

    cards = [_build_annotation_card(a, include_para_refs) for a in annotations]

    return f"""
    <div class="annotations-sidebar">
        <div class="sidebar-header">Annotations ({len(annotations)})</div>
        {"".join(cards)}
    </div>
    """


def _build_document_html(
    brief_html: str,
    annotations: Sequence[Annotation],
    options: ExportOptions,
) -> str:
    """Build the complete document HTML."""
    sidebar = _build_sidebar_html(annotations, options.include_paragraph_refs)

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{options.title}</title>
    </head>
    <body>
        <div class="document-container">
            <div class="brief-content">
                <h1>{options.title}</h1>
                {brief_html}
            </div>
            {sidebar}
        </div>
    </body>
    </html>
    """


def export_brief_to_pdf(
    brief_html: str,
    annotations: Sequence[Annotation],
    output_path: str | Path,
    options: ExportOptions | None = None,
) -> Path:
    """Export a brief with annotations to PDF.

    Args:
        brief_html: The HTML content of the brief (case text with highlights).
        annotations: List of annotations to display in the sidebar.
        output_path: Where to save the PDF file.
        options: Export options (title, page size, etc.).

    Returns:
        Path to the generated PDF file.

    Example:
        >>> annotations = [
        ...     Annotation(
        ...         id="1",
        ...         quoted_text="The defendant was negligent...",
        ...         tag="ratio",
        ...         comment="Key finding on negligence standard",
        ...         paragraph_ref="42",
        ...     ),
        ... ]
        >>> export_brief_to_pdf(
        ...     "<p>Case content here...</p>",
        ...     annotations,
        ...     "output.pdf",
        ... )
    """
    if options is None:
        options = ExportOptions()

    output_path = Path(output_path)

    # Build the complete HTML document
    html_content = _build_document_html(brief_html, annotations, options)

    # Build CSS with options
    css_content = BRIEF_PDF_CSS % {
        "page_size": options.page_size,
        "margin": options.margin,
    }

    # Generate PDF
    html_doc = HTML(string=html_content)
    css_doc = CSS(string=css_content)

    html_doc.write_pdf(output_path, stylesheets=[css_doc])

    return output_path
