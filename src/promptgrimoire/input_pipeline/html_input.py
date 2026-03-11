"""HTML input pipeline: detection, conversion, and orchestration.

This module provides the unified input pipeline for the annotation page.
All input types (HTML, RTF, DOCX, PDF, plain text) go through the same
HTML-based pipeline for character-level annotation support.

Text extraction and marker insertion live in ``text_extraction``.
HTML sanitisation lives in ``sanitisation``.  This module re-exports
their public API for backward compatibility.
"""

# Pattern: Functional Core (pure functions for content detection and transformation)

from __future__ import annotations

import asyncio
import html as html_module
import logging
import re
from typing import Literal

from selectolax.lexbor import LexborHTMLParser

from promptgrimoire.input_pipeline.converters import (
    convert_docx_to_html,
    convert_pdf_to_html,
)
from promptgrimoire.input_pipeline.marker_insertion import (
    collapsed_to_html_offset,
    find_text_node_offsets,
    insert_markers_into_dom,
)
from promptgrimoire.input_pipeline.sanitisation import (
    remove_empty_elements,
    strip_heavy_attributes,
)
from promptgrimoire.input_pipeline.text_extraction import (
    TextNodeInfo,
    extract_text_from_html,
    walk_and_map,
)

logger = logging.getLogger(__name__)

# Content types supported by the pipeline
CONTENT_TYPES = ("html", "rtf", "docx", "pdf", "text")
ContentType = Literal["html", "rtf", "docx", "pdf", "text"]


# ---------------------------------------------------------------------------
# Re-exports for backward compatibility
# ---------------------------------------------------------------------------
# External code imports these from html_input; keep them importable here.
__all__ = [
    "CONTENT_TYPES",
    "ContentType",
    "TextNodeInfo",
    "collapsed_to_html_offset",
    "detect_content_type",
    "extract_text_from_html",
    "find_text_node_offsets",
    "insert_markers_into_dom",
    "process_input",
    "walk_and_map",
]


# ---------------------------------------------------------------------------
# Content type detection
# ---------------------------------------------------------------------------


def _detect_from_bytes(content: bytes) -> ContentType | None:
    """Detect content type from binary magic bytes.

    Returns None if detection should continue with string-based analysis.
    """
    if content.startswith(b"%PDF"):
        return "pdf"
    if content.startswith(b"PK") and (
        b"word/document" in content[:2000] or b"[Content_Types].xml" in content[:2000]
    ):
        return "docx"
    if content.startswith(b"{\\rtf"):
        return "rtf"
    return None


# CSS selector for block-level elements per the HTML spec.
# Used by _is_fake_html() to distinguish real structured HTML from plain text
# wrapped in an HTML shell (e.g. PDF viewer paste).
_BLOCK_LEVEL_CSS = (
    "p, div, h1, h2, h3, h4, h5, h6, ul, ol, li, table, blockquote, pre,"
    " section, article, aside, nav, header, footer, main, figure, figcaption,"
    " details, summary, hr, dl, dt, dd, address, fieldset, form"
)


def _is_fake_html(content: str) -> bool:
    """Check whether *content* is plain text wrapped in an HTML shell.

    PDF viewers (Chrome, Evince) paste plain text as
    ``<html><body>text\\n...``</body></html>`` -- structurally HTML but
    semantically plain text.  If the body contains no block-level
    elements the content should be treated as ``"text"`` so that
    ``_text_to_html()`` can convert newlines to ``<br/>`` tags.

    Uses selectolax (lexbor) to parse the HTML and query the ``<body>``
    for block-level elements via CSS selectors, avoiding the classic
    "parsing HTML with regex" anti-pattern.
    """
    tree = LexborHTMLParser(content)
    body = tree.body
    if body is None:
        # No <body> element -- treat as fake HTML (plain text)
        return True
    return body.css_first(_BLOCK_LEVEL_CSS) is None


def _detect_from_string(content: str) -> ContentType:
    """Detect content type from string content."""
    stripped = content.lstrip()

    # RTF detection (text form)
    if stripped.startswith("{\\rtf"):
        return "rtf"

    # HTML detection
    lower = stripped.lower()
    if lower.startswith("<!doctype"):
        # NOTE: DOCTYPE path skips fake-HTML guard -- observed PDF pastes
        # never include DOCTYPE.
        return "html"
    if lower.startswith("<html"):
        # Guard: HTML-wrapped plain text (e.g. PDF paste) -> reclassify.
        # PDF viewers paste <html><body>text\n...</body></html> without
        # DOCTYPE -- no block-level elements means it's plain text.
        if _is_fake_html(stripped):
            return "text"
        return "html"

    # Check for HTML-like structure (tags)
    if re.search(
        r"<(div|p|span|h[1-6]|ul|ol|li|table|body)\b", stripped, re.IGNORECASE
    ):
        return "html"

    # Default to plain text
    return "text"


def _decode_bytes(content: bytes) -> str:
    """Decode bytes to string for content type detection."""
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        # Fall back to latin-1 which accepts all byte values
        return content.decode("latin-1")


def detect_content_type(content: str | bytes) -> ContentType:
    """Detect content type from magic bytes or structure.

    Args:
        content: Raw content to analyze (string or bytes).

    Returns:
        Detected content type: "html", "rtf", "docx", "pdf", or "text".

    Detection heuristics:
        - RTF: Starts with {\\rtf
        - PDF: Starts with %PDF
        - DOCX: PK magic bytes (ZIP archive with specific structure)
        - HTML: Starts with <!DOCTYPE, <html, or contains HTML-like tags
        - Text: Default fallback
    """
    if isinstance(content, bytes):
        # Check binary signatures first
        binary_result = _detect_from_bytes(content)
        if binary_result is not None:
            return binary_result

        # Decode for string-based detection
        content = _decode_bytes(content)

    return _detect_from_string(content)


# ---------------------------------------------------------------------------
# Text / HTML conversion helpers
# ---------------------------------------------------------------------------


def _strip_html_to_text(html_content: str) -> str:
    """Strip HTML tags to get plain text content.

    Used when QEditor provides HTML but user selected 'text' type.
    Preserves text content, converts <br> to newlines, removes other tags.
    """
    if not html_content:
        return ""

    tree = LexborHTMLParser(html_content)

    # Get text content - selectolax extracts text from all nodes
    # Replace <br> and block elements with newlines first
    for br in tree.css("br"):
        br.replace_with("\n")
    for block in tree.css("div, p"):
        # Add newline after block elements
        block.insert_after("\n")

    return tree.text() or ""


def _text_to_html(text: str) -> str:
    """Convert plain text to HTML paragraphs.

    Args:
        text: Plain text content (may contain HTML from QEditor that needs stripping).

    Returns:
        HTML with text wrapped in <p> tags, double newlines as paragraph breaks.
    """
    # If text looks like HTML (from QEditor), strip tags first
    if "<" in text and ">" in text:
        text = _strip_html_to_text(text)

    # Escape HTML special characters
    escaped = html_module.escape(text)

    # Split on double newlines for paragraphs
    paragraphs = escaped.split("\n\n")

    # Wrap each paragraph, convert single newlines to <br>
    html_parts = []
    for para in paragraphs:
        if para.strip():
            # Convert single newlines to <br>
            para_html = para.replace("\n", "<br>")
            html_parts.append(f"<p>{para_html}</p>")

    return "\n".join(html_parts) if html_parts else "<p></p>"


# ---------------------------------------------------------------------------
# Main pipeline orchestration
# ---------------------------------------------------------------------------


async def process_input(
    content: str | bytes,
    source_type: ContentType,
    platform_hint: str | None = None,
) -> str:
    """Full input processing pipeline: convert -> preprocess -> clean.

    Args:
        content: Raw input content (string or bytes).
        source_type: Confirmed content type.
        platform_hint: Optional platform hint for chatbot exports.

    Returns:
        Clean processed HTML ready for annotation. Highlight rendering
        and text selection use the CSS Custom Highlight API and JS
        text walker on the client side.

    Pipeline steps:
        1. Convert to HTML (if not already HTML)
        2. Preprocess for export (remove chrome, inject speaker labels)
        3. Strip heavy attributes and empty elements

    Note:
        DOCX and PDF conversion supported via converters module.
        RTF conversion is not yet implemented.
    """
    # Binary formats (DOCX, PDF) must receive bytes -- intercept before
    # the generic bytes->str decode that text/HTML paths need.
    if source_type in ("docx", "pdf"):
        if not isinstance(content, bytes):
            msg = f"{source_type.upper()} content must be bytes, got str"
            raise TypeError(msg)

        input_size = len(content)
        logger.debug(
            "[PIPELINE] Input: type=%s, size=%d bytes (%.1f KB)",
            source_type,
            input_size,
            input_size / 1024,
        )

        if source_type == "docx":
            loop = asyncio.get_running_loop()
            html = await loop.run_in_executor(None, convert_docx_to_html, content)
        else:
            html = await convert_pdf_to_html(content)
    else:
        # Text/HTML paths: decode bytes to string if needed
        if isinstance(content, bytes):
            content = _decode_bytes(content)

        input_size = len(content)
        logger.debug(
            "[PIPELINE] Input: type=%s, size=%d bytes (%.1f KB)",
            source_type,
            input_size,
            input_size / 1024,
        )

        # Step 1: Convert to HTML based on source type
        if source_type == "text":
            html = _text_to_html(content)
        elif source_type == "html":
            html = content
        else:
            msg = f"Conversion from {source_type} not yet implemented"
            raise NotImplementedError(msg)

    html_size = len(html)
    logger.debug(
        "[PIPELINE] After conversion: size=%d bytes (%.1f KB), ratio=%.1fx",
        html_size,
        html_size / 1024,
        html_size / max(input_size, 1),
    )

    # Step 2: Preprocess (remove chrome, inject speaker labels)
    # Lazy import to break circular dependency:
    # input_pipeline -> export.platforms -> export -> highlight_spans -> input_pipeline
    from promptgrimoire.export.platforms import preprocess_for_export

    preprocessed = preprocess_for_export(html, platform_hint=platform_hint)
    preproc_size = len(preprocessed)
    logger.debug(
        "[PIPELINE] After preprocess: size=%d bytes (%.1f KB), ratio=%.1fx",
        preproc_size,
        preproc_size / 1024,
        preproc_size / max(input_size, 1),
    )

    # Step 3: Strip unnecessary attributes to reduce size
    # (pasted HTML often has huge inline styles, data attributes, etc.)
    stripped = strip_heavy_attributes(preprocessed)

    # Step 4: Remove empty paragraphs/divs that only contain <br> tags
    # (Office apps use these for spacing, creates excessive whitespace)
    cleaned = remove_empty_elements(stripped)
    final_size = len(cleaned)
    logger.debug(
        "[PIPELINE] Final output: size=%d bytes (%.1f KB), ratio=%.1fx from input",
        final_size,
        final_size / 1024,
        final_size / max(input_size, 1),
    )

    # Return clean HTML - char spans are injected client-side to avoid
    # websocket message size limits (span injection multiplies size ~55x)
    return cleaned
