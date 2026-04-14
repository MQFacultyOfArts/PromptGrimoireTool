"""High-level PDF export orchestration for annotated documents.

Coordinates the full pipeline from HTML + annotations to PDF:
1. Convert HTML to LaTeX with annotation markers
2. Build complete LaTeX document with preamble
3. Append general notes section
4. Compile to PDF via latexmk
"""

from __future__ import annotations

import asyncio
import html
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from promptgrimoire.export.pandoc import convert_html_with_annotations
from promptgrimoire.export.pdf import compile_latex
from promptgrimoire.export.platforms import preprocess_for_export
from promptgrimoire.export.preamble import build_annotation_preamble
from promptgrimoire.export.unicode_latex import detect_scripts, escape_unicode_latex
from promptgrimoire.word_count_enforcement import check_word_count_violation

logger = structlog.get_logger()
# Path to the .sty file that contains all static LaTeX preamble content
STY_SOURCE = Path(__file__).parent / "promptgrimoire-export.sty"


def ensure_sty_in_dir(output_dir: Path) -> None:
    """Copy promptgrimoire-export.sty to the output directory for latexmk.

    Always overwrites to ensure the .sty matches the current package version.
    """
    shutil.copy2(STY_SOURCE, output_dir / "promptgrimoire-export.sty")


# LaTeX document template
_DOCUMENT_TEMPLATE = r"""
\documentclass[a4paper,12pt]{{article}}
{preamble}

\begin{{document}}

{body}

{general_notes_section}

\flushannotendnotes

\end{{document}}
"""

# General notes section template
_GENERAL_NOTES_TEMPLATE = r"""
\section*{{Response}}
{content}
"""


def _plain_text_to_html(text: str | None, escape: bool = True) -> str:
    """Convert plain text to HTML with paragraph structure.

    Preserves line breaks as <p> tags for proper Pandoc conversion.
    Plain text newlines are collapsed by Pandoc when passed as HTML,
    so we need to wrap lines in paragraph tags.

    IMPORTANT: Must match the input pipeline's extract_text_from_html() behavior
    for character indexing alignment (Issue #111). Both use `if line:` to detect
    empty lines, NOT `if line.strip():`. Whitespace-only lines (including '\r'
    from CRLF) must be preserved so PDF marker indices match UI indices.

    Args:
        text: Plain text content, possibly with newlines.
        escape: Whether to HTML-escape the content. Set to False when markers
            have already been inserted and escaping will be done later.
            When False, adds data-structural attribute to tags so they can
            be distinguished from user content during escaping.

    Returns:
        HTML with each line wrapped in <p> tags.
    """
    if not text:
        return ""

    lines = text.split("\n")
    html_parts = []

    # When not escaping, add a marker so we can identify structural tags later
    p_open = "<p>" if escape else '<p data-structural="1">'
    p_close = "</p>"

    for line in lines:
        if line:
            # Non-empty line (including whitespace-only like '\r' from CRLF)
            # Must preserve whitespace content for character index alignment
            escaped_line = html.escape(line) if escape else line
            html_parts.append(f"{p_open}{escaped_line}{p_close}")
        else:
            # Truly empty line - preserve as empty paragraph for spacing
            html_parts.append(f"{p_open}{p_close}")

    return "\n".join(html_parts)


def html_to_latex_notes(html_content: str) -> str:
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


async def markdown_to_latex_notes(markdown_content: str | None) -> str:
    """Convert markdown content to LaTeX using Pandoc.

    Uses the same Pandoc installation as the main export pipeline for
    consistency. This is the conversion path for Milkdown editor output
    (response draft), which produces markdown rather than HTML.

    Args:
        markdown_content: Markdown text from the Milkdown editor.

    Returns:
        LaTeX-formatted content, or empty string if input is empty.

    Raises:
        subprocess.CalledProcessError: If Pandoc fails.
    """
    if not markdown_content or not markdown_content.strip():
        return ""

    # Strip markdown image syntax — we don't support images in export.
    # Inline: ![alt](url)  Reference: ![alt][id] and [id]: url
    markdown_content = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", markdown_content)
    markdown_content = re.sub(r"!\[[^\]]*\]\[[^\]]*\]", "", markdown_content)
    markdown_content = re.sub(
        r"^\[[^\]]*\]:\s+\S+.*$", "", markdown_content, flags=re.MULTILINE
    )

    # Escape lone backslashes before letters.  Pandoc's markdown parser
    # treats \word as a RawInline "tex" command, passing it straight
    # through to the LaTeX writer.  Student text containing accidental
    # backslashes (e.g. "\before") would produce undefined control
    # sequences.  Doubling the backslash makes Pandoc emit
    # \textbackslash{} instead.  Backslash before ASCII punctuation is
    # already a valid markdown escape and must not be changed.
    markdown_content = re.sub(
        r"\\([A-Za-z])", lambda m: "\\\\" + m.group(1), markdown_content
    )

    proc = await asyncio.create_subprocess_exec(
        "pandoc",
        "-f",
        "markdown",
        "-t",
        "latex",
        "--no-highlight",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(input=markdown_content.encode("utf-8")), timeout=30
        )
    except TimeoutError:
        logger.warning("pandoc_timeout", operation="markdown_to_latex")
        proc.kill()
        raise subprocess.CalledProcessError(
            1, ["pandoc"], "Pandoc timed out after 30s"
        ) from None
    if proc.returncode is None or proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode or 1,
            ["pandoc", "-f", "markdown", "-t", "latex"],
            stderr_bytes.decode(),
        )
    return stdout_bytes.decode().strip()


def _build_general_notes_section(
    general_notes: str,
    latex_content: str | None = None,
) -> str:
    """Build the LaTeX general notes section.

    Supports two input paths:
    - **HTML path** (existing): ``general_notes`` contains HTML from the
      WYSIWYG editor, converted via ``html_to_latex_notes()``.
    - **LaTeX path** (Phase 7): ``latex_content`` contains pre-converted
      LaTeX (e.g., from Pandoc markdown conversion). When provided, this
      takes precedence over the HTML path.

    Args:
        general_notes: HTML content from the notes editor.
        latex_content: Pre-converted LaTeX content (takes precedence).

    Returns:
        LaTeX section string, empty if no notes.
    """
    # LaTeX path: pre-converted content takes precedence
    if latex_content and latex_content.strip():
        return _GENERAL_NOTES_TEMPLATE.format(content=latex_content)

    # HTML path: convert HTML to LaTeX
    if not general_notes or not general_notes.strip():
        return ""

    converted = html_to_latex_notes(general_notes)
    if not converted:
        return ""

    return _GENERAL_NOTES_TEMPLATE.format(content=converted)


# Path to Lua filter for LibreOffice HTML handling (tables, margins, etc.)
_LIBREOFFICE_FILTER = Path(__file__).parent / "filters" / "libreoffice.lua"


async def _convert_single_document(
    html_content: str,
    highlights: list[dict[str, Any]],
    tag_colours: dict[str, str],
    word_to_legal_para: dict[int, int | None] | None = None,
) -> str:
    """Convert one document's HTML + highlights to a LaTeX body fragment."""
    processed_html = preprocess_for_export(html_content) if html_content else ""
    return await convert_html_with_annotations(
        html=processed_html,
        highlights=highlights,
        tag_colours=tag_colours,
        filter_paths=[_LIBREOFFICE_FILTER],
        word_to_legal_para=word_to_legal_para,
    )


async def _build_multi_doc_body(
    documents: list[dict[str, Any]],
    tag_colours: dict[str, str],
) -> str:
    """Process multiple documents into a combined LaTeX body.

    Each document is converted independently (so highlight char offsets
    remain relative to their own HTML), then joined with section headings.
    Single-document workspaces omit the heading for backwards compatibility.
    """
    parts: list[str] = []
    for i, doc in enumerate(documents):
        latex = await _convert_single_document(
            doc["html_content"],
            doc.get("highlights", []),
            tag_colours,
            word_to_legal_para=doc.get("word_to_legal_para"),
        )
        if len(documents) > 1:
            title = doc.get("title", f"Source {i + 1}")
            escaped = escape_unicode_latex(title)
            parts.append(f"\\section*{{{escaped}}}")
        parts.append(latex)
    return "\n\n".join(parts)


def _resolve_output_dir(user_id: str | None, workspace_id: str | None) -> Path:
    """Resolve or create the output directory for an export."""
    if user_id:
        return _get_export_dir(user_id)
    prefix = "promptgrimoire_export_"
    if workspace_id:
        prefix = f"promptgrimoire_export_{workspace_id[:8]}_"
    return Path(tempfile.mkdtemp(prefix=prefix))


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


def _red_badge(label: str) -> str:
    """Return a red ``\\fcolorbox`` LaTeX snippet with *label* in bold."""
    return (
        r"\noindent\fcolorbox{red}{red!10}{%"
        "\n"
        r"\parbox{\dimexpr\textwidth-2\fboxsep-2\fboxrule}{%"
        "\n"
        rf"\textcolor{{red}}{{\textbf{{{label}}}}}"
        "%\n"
        r"}}"
        "\n"
        r"\vspace{1em}"
        "\n"
    )


def _build_word_count_badge(
    count: int,
    word_minimum: int | None,
    word_limit: int | None,
) -> str:
    """Build a LaTeX word count badge for the PDF export.

    Returns a LaTeX snippet to prepend before the document body:
    - Red ``\\fcolorbox`` for violations (over limit or below minimum).
    - Neutral italic line when within limits.
    - Empty string when no limits are configured.

    Delegates violation detection to
    :func:`~promptgrimoire.word_count_enforcement.check_word_count_violation`
    so the rules are defined in exactly one place.

    Args:
        count: Current word count.
        word_minimum: Minimum word count threshold, or None.
        word_limit: Maximum word count threshold, or None.

    Returns:
        LaTeX snippet (may be empty).
    """
    if word_limit is None and word_minimum is None:
        return ""

    violation = check_word_count_violation(count, word_minimum, word_limit)

    # Determine the denominator for the "X / Y" display
    denominator = word_limit if word_limit is not None else word_minimum

    if violation.over_limit:
        return _red_badge(f"Word Count: {count:,} / {denominator:,} (Exceeded)")

    if violation.under_minimum:
        return _red_badge(f"Word Count: {count:,} / {denominator:,} (Below Minimum)")

    # Within limits -- neutral italic line
    label = f"Word Count: {count:,} / {denominator:,}"
    return r"\noindent\textit{" + label + "}\n" + r"\vspace{1em}" + "\n"


async def generate_tex_only(
    html_content: str,
    highlights: list[dict[str, Any]],
    tag_colours: dict[str, str],
    output_dir: Path,
    general_notes: str = "",
    notes_latex: str = "",
    word_to_legal_para: dict[int, int | None] | None = None,
    filename: str = "annotated_document",
    *,
    word_count: int | None = None,
    word_minimum: int | None = None,
    word_limit: int | None = None,
    documents: list[dict[str, Any]] | None = None,
) -> Path:
    """Generate a .tex file from HTML + annotations without compiling to PDF.

    Runs the full export pipeline (preprocess, convert, assemble) up to
    writing the .tex file but does NOT invoke ``compile_latex()``. This
    enables fast assertions on LaTeX content in tests without paying
    the 5-10s compilation cost.

    When *documents* is provided (multi-doc workspaces), each document
    is processed independently and joined with ``\\section*{}`` headings.
    The legacy *html_content* / *highlights* parameters are used as a
    single-document fallback.

    Returns:
        Path to the generated .tex file.

    Raises:
        ValueError: If highlights are provided but content is empty.
    """
    # Ensure .sty is in the output directory before writing .tex
    ensure_sty_in_dir(output_dir)

    # Build LaTeX body from documents list or legacy single-doc params
    if documents:
        latex_body = await _build_multi_doc_body(documents, tag_colours)
    else:
        if highlights and (not html_content or not html_content.strip()):
            raise ValueError(
                "Cannot insert annotation markers into empty content. "
                "Provide document content or remove highlights."
            )
        latex_body = await _convert_single_document(
            html_content, highlights, tag_colours, word_to_legal_para
        )

    # Prepend word count badge if word count info is provided
    if word_count is not None:
        badge = _build_word_count_badge(word_count, word_minimum, word_limit)
        if badge:
            latex_body = badge + latex_body

    # Build general notes section
    notes_section = _build_general_notes_section(
        general_notes, latex_content=notes_latex
    )

    # Build preamble with tag colours and dynamic font loading
    full_text = f"{latex_body}\n{notes_section}" if notes_section else latex_body
    preamble = build_annotation_preamble(tag_colours, body_text=full_text)

    # Assemble complete document
    document = _DOCUMENT_TEMPLATE.format(
        preamble=preamble,
        body=latex_body,
        general_notes_section=notes_section,
    )

    tex_path = output_dir / f"{filename}.tex"
    tex_path.write_text(document)

    return tex_path


async def export_annotation_pdf(
    html_content: str,
    highlights: list[dict[str, Any]],
    tag_colours: dict[str, str],
    general_notes: str = "",
    notes_latex: str = "",
    word_to_legal_para: dict[int, int | None] | None = None,
    output_dir: Path | None = None,
    user_id: str | None = None,
    filename: str = "annotated_document",
    *,
    workspace_id: str | None = None,
    word_count: int | None = None,
    word_minimum: int | None = None,
    word_limit: int | None = None,
    documents: list[dict[str, Any]] | None = None,
) -> Path:
    """Generate PDF with annotations from live annotation data.

    This is the main entry point for PDF export. It orchestrates:
    1. HTML -> LaTeX conversion with annotation markers
    2. PDF compilation via latexmk

    When *documents* is provided (multi-doc workspaces), each document
    is processed independently and joined with ``\\section*{}`` headings.
    The legacy *html_content* / *highlights* parameters are used as a
    single-document fallback.

    Returns:
        Path to the generated PDF file.
    """
    t_export_start = time.monotonic()
    export_id = str(uuid4())
    log = logger.bind(export_id=export_id)

    # Resolve output directory
    if output_dir is None:
        output_dir = _resolve_output_dir(user_id, workspace_id)

    log.info(
        "PDF export workspace=%s output_dir=%s",
        workspace_id or "unknown",
        output_dir,
    )

    # --- Stage: pandoc_convert ---
    t0 = time.monotonic()
    if documents:
        latex_body = await _build_multi_doc_body(documents, tag_colours)
    else:
        if highlights and (not html_content or not html_content.strip()):
            raise ValueError(
                "Cannot insert annotation markers into empty content. "
                "Provide document content or remove highlights."
            )
        latex_body = await _convert_single_document(
            html_content, highlights, tag_colours, word_to_legal_para
        )
    log.info(
        "export_stage_complete",
        export_stage="pandoc_convert",
        stage_duration_ms=round((time.monotonic() - t0) * 1000),
    )

    # --- Stage: tex_generate ---
    t0 = time.monotonic()
    # Prepend word count badge if word count info is provided
    if word_count is not None:
        badge = _build_word_count_badge(word_count, word_minimum, word_limit)
        if badge:
            latex_body = badge + latex_body

    notes_section = _build_general_notes_section(
        general_notes, latex_content=notes_latex
    )
    full_text = f"{latex_body}\n{notes_section}" if notes_section else latex_body
    scripts = detect_scripts(full_text)
    preamble = build_annotation_preamble(
        tag_colours, body_text=full_text, scripts=scripts
    )

    ensure_sty_in_dir(output_dir)
    document = _DOCUMENT_TEMPLATE.format(
        preamble=preamble,
        body=latex_body,
        general_notes_section=notes_section,
    )
    tex_path = output_dir / f"{filename}.tex"
    tex_path.write_text(document)
    log.info(
        "export_stage_complete",
        export_stage="tex_generate",
        stage_duration_ms=round((time.monotonic() - t0) * 1000),
    )

    # --- Stage: latex_compile ---
    t0 = time.monotonic()
    pdf_path = await compile_latex(tex_path, output_dir)
    log.info(
        "export_stage_complete",
        export_stage="latex_compile",
        stage_duration_ms=round((time.monotonic() - t0) * 1000),
    )

    # --- Export complete ---
    log.info(
        "export_complete",
        font_fallbacks=sorted(scripts),
        total_duration_ms=round((time.monotonic() - t_export_start) * 1000),
    )

    return pdf_path
