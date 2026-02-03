"""High-level PDF export orchestration for annotated documents.

Coordinates the full pipeline from HTML + annotations to PDF:
1. Convert HTML to LaTeX with annotation markers
2. Build complete LaTeX document with preamble
3. Append general notes section
4. Compile to PDF via latexmk
"""

from __future__ import annotations

import html
import logging
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from promptgrimoire.export.latex import (
    build_annotation_preamble,
    convert_html_with_annotations,
)
from promptgrimoire.export.pdf import compile_latex

logger = logging.getLogger(__name__)

# LaTeX document template
_DOCUMENT_TEMPLATE = r"""
\documentclass[a4paper,12pt]{{article}}
{preamble}

\begin{{document}}

{body}

{general_notes_section}

\end{{document}}
"""

# General notes section template
_GENERAL_NOTES_TEMPLATE = r"""
\section*{{General Notes}}
{content}
"""


def _plain_text_to_html(text: str | None) -> str:
    """Convert plain text to HTML with paragraph structure.

    Preserves line breaks as <p> tags for proper Pandoc conversion.
    Plain text newlines are collapsed by Pandoc when passed as HTML,
    so we need to wrap lines in paragraph tags.

    IMPORTANT: Must match UI's _process_text_to_char_spans() behavior exactly
    for character indexing alignment (Issue #111). Both use `if line:` to detect
    empty lines, NOT `if line.strip():`. Whitespace-only lines (including '\r'
    from CRLF) must be preserved so PDF marker indices match UI indices.

    Args:
        text: Plain text content, possibly with newlines.

    Returns:
        HTML with each line wrapped in <p> tags.
    """
    if not text:
        return ""

    lines = text.split("\n")
    html_parts = []

    for line in lines:
        if line:
            # Non-empty line (including whitespace-only like '\r' from CRLF)
            # Must preserve whitespace content for character index alignment
            html_parts.append(f"<p>{html.escape(line)}</p>")
        else:
            # Truly empty line - preserve as empty paragraph for spacing
            html_parts.append("<p></p>")

    return "\n".join(html_parts)


def _html_to_latex_notes(html_content: str) -> str:
    """Convert HTML notes content to LaTeX.

    Simple conversion for WYSIWYG editor output.
    Handles basic formatting tags.

    Args:
        html_content: HTML content from the notes editor.

    Returns:
        LaTeX-formatted content.
    """
    if not html_content or not html_content.strip():
        return ""

    # Strip outer tags and convert basic formatting
    content = html_content

    # Convert common HTML to LaTeX
    replacements = [
        (r"<br\s*/?>", r"\\\\\n"),
        (r"<p>", ""),
        (r"</p>", "\n\n"),
        (r"<strong>([^<]*)</strong>", r"\\textbf{\1}"),
        (r"<b>([^<]*)</b>", r"\\textbf{\1}"),
        (r"<em>([^<]*)</em>", r"\\textit{\1}"),
        (r"<i>([^<]*)</i>", r"\\textit{\1}"),
        (r"<u>([^<]*)</u>", r"\\underline{\1}"),
        (r"<ul>", r"\\begin{itemize}"),
        (r"</ul>", r"\\end{itemize}"),
        (r"<ol>", r"\\begin{enumerate}"),
        (r"</ol>", r"\\end{enumerate}"),
        (r"<li>([^<]*)</li>", r"\\item \1"),
        (r"<[^>]+>", ""),  # Strip remaining HTML tags
    ]

    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)

    # Escape special characters that weren't part of formatting
    # Note: Do this carefully to not double-escape
    special_chars = [
        ("&amp;", "&"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&nbsp;", " "),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
    ]

    for char, escaped in special_chars:
        content = content.replace(char, escaped)

    return content.strip()


def _build_general_notes_section(general_notes: str) -> str:
    """Build the LaTeX general notes section.

    Args:
        general_notes: HTML content from the notes editor.

    Returns:
        LaTeX section string, empty if no notes.
    """
    if not general_notes or not general_notes.strip():
        return ""

    latex_content = _html_to_latex_notes(general_notes)
    if not latex_content:
        return ""

    return _GENERAL_NOTES_TEMPLATE.format(content=latex_content)


# Path to Lua filter for LibreOffice HTML handling (tables, margins, etc.)
_LIBREOFFICE_FILTER = Path(__file__).parent / "filters" / "libreoffice.lua"


def _get_export_dir(user_id: str) -> Path:
    """Get or create user's export directory, cleaning up previous exports.

    Each user gets a single export directory that is cleaned on new export,
    preventing accumulation of stale temp directories.

    Args:
        user_id: User identifier (e.g., hashed email).

    Returns:
        Path to the export directory.
    """
    export_dir = Path(tempfile.gettempdir()) / f"promptgrimoire_export_{user_id}"
    if export_dir.exists():
        shutil.rmtree(export_dir)  # Clean previous export
    export_dir.mkdir(parents=True)
    return export_dir


async def export_annotation_pdf(
    html_content: str,
    highlights: list[dict[str, Any]],
    tag_colours: dict[str, str],
    general_notes: str = "",
    word_to_legal_para: dict[int, int | None] | None = None,
    output_dir: Path | None = None,
    user_id: str | None = None,
    filename: str = "annotated_document",
) -> Path:
    """Generate PDF with annotations from live annotation data.

    This is the main entry point for PDF export. It orchestrates:
    1. HTML → LaTeX conversion with annotation markers
    2. Complete document assembly with preamble
    3. General notes section
    4. PDF compilation via latexmk

    Args:
        html_content: Content to export. Can be plain text or HTML.
            Plain text (no HTML tags) is auto-converted to HTML paragraphs.
        highlights: List of highlight dicts from CRDT doc.
        tag_colours: Mapping of tag names to hex colours.
        general_notes: HTML content from general notes editor.
        word_to_legal_para: Optional mapping for paragraph references.
        output_dir: Optional output directory for PDF. Defaults to temp dir.
        user_id: Optional user identifier for scoped temp directory.
            If provided, creates a per-user export dir that is cleaned on reuse.

    Returns:
        Path to the generated PDF file.

    Raises:
        subprocess.CalledProcessError: If LaTeX compilation fails.
    """
    # Detect if content is ALREADY structured HTML (starts with HTML tags).
    # Plain text newlines are collapsed by Pandoc, so we wrap in <p> tags.
    # We check the START of content - not anywhere - because content like BLNS
    # contains HTML strings (XSS payloads) that shouldn't trigger HTML detection.
    is_structured_html = html_content and re.match(
        r"\s*<(?:!DOCTYPE|html|body|p|div|table|ul|ol|h[1-6])\b",
        html_content,
        re.IGNORECASE,
    )
    logger.info(
        "[PDF DEBUG] is_structured_html=%s, will call _plain_text_to_html=%s",
        bool(is_structured_html),
        not is_structured_html,
    )
    if not is_structured_html:
        html_content = _plain_text_to_html(html_content)
        logger.info(
            "[PDF DEBUG] after _plain_text_to_html, <p> count=%d",
            html_content.count("<p>"),
        )

    # Convert HTML to LaTeX body with annotations
    # Use libreoffice.lua filter for proper table handling
    latex_body = convert_html_with_annotations(
        html=html_content,
        highlights=highlights,
        tag_colours=tag_colours,
        filter_path=_LIBREOFFICE_FILTER,
        word_to_legal_para=word_to_legal_para,
    )

    # Build preamble with tag colours
    preamble = build_annotation_preamble(tag_colours)

    # Build general notes section
    notes_section = _build_general_notes_section(general_notes)

    # Assemble complete document
    document = _DOCUMENT_TEMPLATE.format(
        preamble=preamble,
        body=latex_body,
        general_notes_section=notes_section,
    )

    # Write to temp file and compile
    if output_dir is None:
        if user_id:
            output_dir = _get_export_dir(user_id)
        else:
            output_dir = Path(tempfile.mkdtemp(prefix="promptgrimoire_export_"))

    tex_path = output_dir / f"{filename}.tex"
    tex_path.write_text(document)

    # Compile to PDF
    pdf_path = compile_latex(tex_path, output_dir)

    return pdf_path
