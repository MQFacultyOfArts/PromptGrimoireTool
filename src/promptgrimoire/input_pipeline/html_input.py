"""HTML input pipeline: detection, conversion, and char span injection.

This module provides the unified input pipeline for the annotation page.
All input types (HTML, RTF, DOCX, PDF, plain text) go through the same
HTML-based pipeline for character-level annotation support.
"""

# Pattern: Functional Core (pure functions for content detection and transformation)

from __future__ import annotations

import html as html_module
import logging
import re
from typing import Any, Literal

from selectolax.lexbor import LexborHTMLParser

from promptgrimoire.export.platforms import preprocess_for_export

logger = logging.getLogger(__name__)

# Content types supported by the pipeline
CONTENT_TYPES = ("html", "rtf", "docx", "pdf", "text")
ContentType = Literal["html", "rtf", "docx", "pdf", "text"]

# Tags to strip entirely (security: NiceGUI rejects script tags)
_STRIP_TAGS = frozenset(("script", "style", "noscript", "template"))

# Self-closing (void) tags to strip (e.g., base64 images from clipboard paste)
_STRIP_VOID_TAGS = frozenset(("img",))

# Map of characters that need HTML entity escaping
# Note: Spaces are NOT converted to &nbsp; - we use CSS white-space: pre-wrap
# to preserve them. This allows proper word wrapping at word boundaries.
_CHAR_ESCAPE_MAP: dict[str, str] = {
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
}


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


def _detect_from_string(content: str) -> ContentType:
    """Detect content type from string content."""
    stripped = content.lstrip()

    # RTF detection (text form)
    if stripped.startswith("{\\rtf"):
        return "rtf"

    # HTML detection
    lower = stripped.lower()
    if lower.startswith("<!doctype") or lower.startswith("<html"):
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


def inject_char_spans(html: str) -> str:
    """Wrap each text character in a data-char-index span.

    Args:
        html: HTML content (after preprocessing).

    Returns:
        HTML with each text character wrapped in
        <span class="char" data-char-index="N">c</span>

    Implementation notes:
        Uses a state-machine approach because selectolax doesn't support
        direct text node manipulation. We parse to validate structure,
        then iterate through HTML to wrap text characters in spans.

        Special handling:
        - Whitespace is preserved as HTML entities (&nbsp; etc.)
        - <br> tags become newline characters with indices
        - Script, style, and other non-content tags are ignored
    """
    if not html:
        return html

    # Parse to validate and normalize HTML
    tree = LexborHTMLParser(html)

    # Get body content (or full html if no body)
    body = tree.body
    if body is None:
        # Not a full document, parse as fragment
        return _inject_spans_to_html(html)

    body_html = body.inner_html
    if not body_html:
        return html

    injected = _inject_spans_to_html(body_html)

    # Reconstruct full document if we had one
    head = tree.head
    head_html = head.html if head else ""
    return f"<!DOCTYPE html><html>{head_html}<body>{injected}</body></html>"


def _make_char_span(char_index: int, content: str) -> str:
    """Create a span element wrapping a single character."""
    return f'<span class="char" data-char-index="{char_index}">{content}</span>'


def _escape_char(char: str) -> str:
    """Escape a character to its HTML entity if needed."""
    return _CHAR_ESCAPE_MAP.get(char, char)


def _get_tag_name(tag_content: str) -> str:
    """Extract tag name from tag content (without < and >).

    Examples:
        "div class='foo'" -> "div"
        "/div" -> "div"
        "br/" -> "br"
    """
    # Remove leading / for closing tags
    content = tag_content.lstrip("/").strip()
    # Get first word (tag name)
    name = content.split()[0] if content.split() else ""
    # Remove trailing / for self-closing
    return name.rstrip("/").lower()


def _process_skip_tag(html: str, tag_name: str, tag_end: int) -> int | None:
    """Handle tags to strip entirely (script, style, etc.).

    Security: NiceGUI rejects HTML with script tags. Strip them during processing.

    Returns new position after closing tag, or None if not a strip tag.
    """
    if tag_name not in _STRIP_TAGS:
        return None

    close_tag = f"</{tag_name}>"
    close_pos = html.lower().find(close_tag.lower(), tag_end + 1)
    if close_pos != -1:
        return close_pos + len(close_tag)
    return None


def _process_tag(
    html: str, i: int, result: list[str], char_index: int
) -> tuple[int, int]:
    """Process an HTML tag at position i.

    Returns (new_position, new_char_index). Returns (-1, char_index) on malformed HTML.
    """
    tag_end = html.find(">", i)
    if tag_end == -1:
        return -1, char_index  # Malformed HTML

    tag_content = html[i + 1 : tag_end]
    full_tag = html[i : tag_end + 1]
    tag_name = _get_tag_name(tag_content)

    # Strip script, style, etc. tags entirely (security: NiceGUI rejects script tags)
    skip_pos = _process_skip_tag(html, tag_name, tag_end)
    if skip_pos is not None:
        # Don't append - strip the tag entirely
        return skip_pos, char_index

    # Strip void/self-closing tags like img (removes base64 images from clipboard)
    if tag_name in _STRIP_VOID_TAGS:
        # Skip this tag entirely - no content to process
        return tag_end + 1, char_index

    # Handle <br> as newline character
    if tag_name == "br":
        result.append(_make_char_span(char_index, "\n"))
        return tag_end + 1, char_index + 1

    # Pass through other tags unchanged
    result.append(full_tag)
    return tag_end + 1, char_index


def _process_entity(
    html: str, i: int, result: list[str], char_index: int
) -> tuple[int, int]:
    """Process an HTML entity at position i.

    Returns (new_position, new_char_index).
    """
    entity_end = html.find(";", i)
    if entity_end != -1 and entity_end - i < 10:
        entity = html[i : entity_end + 1]
        result.append(_make_char_span(char_index, entity))
        return entity_end + 1, char_index + 1

    # Not a valid entity, treat & as character
    result.append(_make_char_span(char_index, "&amp;"))
    return i + 1, char_index + 1


def _inject_spans_to_html(html: str) -> str:
    """Inject char spans into HTML fragment.

    Internal function that processes HTML text content character by character,
    wrapping each in a span with data-char-index attribute.
    """
    result: list[str] = []
    char_index = 0
    i = 0
    n = len(html)

    while i < n:
        char = html[i]
        if char == "<":
            i, char_index = _process_tag(html, i, result, char_index)
            if i == -1:
                break  # Malformed HTML
        elif char == "&":
            i, char_index = _process_entity(html, i, result, char_index)
        else:
            escaped = _escape_char(char)
            result.append(_make_char_span(char_index, escaped))
            char_index += 1
            i += 1

    return "".join(result)


def strip_char_spans(html_with_spans: str) -> str:
    """Remove char span wrappers, preserving content.

    Args:
        html_with_spans: HTML with <span class="char" data-char-index="N"> wrappers.

    Returns:
        Clean HTML with char spans unwrapped (content preserved).
    """
    tree = LexborHTMLParser(html_with_spans)

    # Find all char spans and unwrap them
    for span in tree.css("span.char[data-char-index]"):
        span.unwrap()

    return tree.html or html_with_spans


def extract_chars_from_spans(html_with_spans: str) -> list[str]:
    """Extract characters from char-span HTML, ordered by index.

    Args:
        html_with_spans: HTML with <span class="char" data-char-index="N"> wrappers.

    Returns:
        List of characters where index matches data-char-index.
    """
    tree = LexborHTMLParser(html_with_spans)
    chars: dict[int, str] = {}

    for span in tree.css("span.char[data-char-index]"):
        index_attr = span.attributes.get("data-char-index")
        if index_attr is not None:
            try:
                idx = int(index_attr)
                # Get text content, decode HTML entities
                text = span.text() or ""
                # Handle &nbsp; which appears as \xa0
                if text == "\xa0":
                    text = " "
                chars[idx] = text
            except ValueError:
                pass

    if not chars:
        return []

    # Build ordered list
    max_idx = max(chars.keys())
    return [chars.get(i, "") for i in range(max_idx + 1)]


def extract_text_from_html(html: str) -> list[str]:
    """Extract text characters from clean HTML (no char spans).

    Used for building document_chars list server-side when char spans
    are injected client-side.

    Args:
        html: Clean HTML without char span wrappers.

    Returns:
        List of characters in document order.
    """
    if not html:
        return []

    tree = LexborHTMLParser(html)

    # Get body or full content
    body = tree.body
    root = body if body else tree.root

    if root is None:
        return []

    chars: list[str] = []

    def walk_node(node: Any) -> None:
        """Recursively walk nodes and extract text."""
        # Skip script, style, etc.
        if hasattr(node, "tag") and node.tag in _STRIP_TAGS:
            return

        # Handle <br> as newline
        if hasattr(node, "tag") and node.tag == "br":
            chars.append("\n")
            return

        # Get text content of this node (not children)
        if hasattr(node, "text_content"):
            text = node.text_content
            if text:
                for char in text:
                    chars.append(char)

        # Walk children
        if hasattr(node, "iter"):
            for child in node.iter():
                if child != node:  # Don't re-process self
                    walk_node(child)

    # Use text() which extracts all text content
    text = root.text() or ""
    return list(text)


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


def _strip_heavy_attributes(html: str) -> str:
    """Strip heavy attributes to reduce HTML size for websocket transmission.

    Removes:
    - Most style properties (inline styles can be huge)
    - data-* attributes (except data-speaker which we use)
    - class attributes (keep semantic structure, lose styling)

    Preserves:
    - margin-left, margin-right, text-indent (structural indentation)
    - padding-left, padding-right (structural spacing)

    This is aggressive but necessary for large pasted content where the
    HTML can be 10-50x larger than the text content.
    """
    if not html:
        return html

    # Properties to preserve from inline styles
    keep_props = {
        "margin-left",
        "margin-right",
        "text-indent",
        "padding-left",
        "padding-right",
    }

    tree = LexborHTMLParser(html)

    # Process all elements
    for node in tree.css("*"):
        attrs = node.attributes
        attrs_to_remove = []

        for attr_name in attrs:
            if attr_name == "style":
                # Parse and filter style, keeping only structural properties
                style_val = attrs.get("style") or ""
                kept_styles: list[str] = []
                for prop in keep_props:
                    # Match property: value; pattern
                    pattern = rf"{re.escape(prop)}\s*:\s*([^;]+)"
                    match = re.search(pattern, style_val, re.IGNORECASE)
                    if match:
                        kept_styles.append(f"{prop}:{match.group(1).strip()}")
                if kept_styles:
                    node.attrs["style"] = ";".join(kept_styles)
                else:
                    attrs_to_remove.append("style")
            elif attr_name == "class":
                attrs_to_remove.append("class")
            elif attr_name.startswith("data-") and attr_name != "data-speaker":
                attrs_to_remove.append(attr_name)

        for attr_name in attrs_to_remove:
            del node.attrs[attr_name]

    return tree.html or html


def _remove_empty_elements(html: str) -> str:
    """Remove empty paragraphs and divs that only contain whitespace or <br> tags.

    These create excessive vertical whitespace in pasted content, especially
    from office applications that use empty paragraphs for spacing.

    Note: Preserves at least one content element to avoid returning empty body.
    """
    if not html:
        return html

    tree = LexborHTMLParser(html)

    # Keep removing until no more empty elements found
    changed = True
    while changed:
        changed = False
        for node in tree.css("p, div, span"):
            # Get text content (strips HTML)
            text = (node.text() or "").strip()
            if text:
                continue  # Has real text, keep it

            # Check if all children are just <br> tags
            children = list(node.iter())
            all_br = all(child.tag == "br" for child in children) if children else True

            if all_br:
                # Don't remove if it's the only content element in body
                body = tree.css_first("body")
                if body:
                    content_els = [n for n in body.css("p, div, span") if n != node]
                    if not content_els:
                        continue  # Keep this one - it's the only content

                # Only <br> tags or empty - remove this element
                node.decompose()
                changed = True

    return tree.html or html


async def process_input(
    content: str | bytes,
    source_type: ContentType,
    platform_hint: str | None = None,
) -> str:
    """Full input processing pipeline: convert -> preprocess -> inject spans.

    Args:
        content: Raw input content (string or bytes).
        source_type: Confirmed content type.
        platform_hint: Optional platform hint for chatbot exports.

    Returns:
        Processed HTML with char spans ready for annotation.

    Pipeline steps:
        1. Convert to HTML (if not already HTML)
        2. Preprocess for export (remove chrome, inject speaker labels)
        3. Inject character spans for selection

    Note:
        Step 1 (conversion) is implemented in Phase 7.
        For now, only HTML and text inputs are fully supported.
    """
    # Async marker for Phase 7 compatibility (file conversion will add await points).
    # Convert bytes to string if needed
    if isinstance(content, bytes):
        content = _decode_bytes(content)

    input_size = len(content)
    logger.info(
        "[PIPELINE] Input: type=%s, size=%d bytes (%.1f KB)",
        source_type,
        input_size,
        input_size / 1024,
    )

    # Step 1: Convert to HTML based on source type
    if source_type == "text":
        # Wrap plain text in paragraph tags
        html = _text_to_html(content)
    elif source_type == "html":
        html = content
    else:
        # RTF, DOCX, PDF conversion - Phase 7
        # For now, raise NotImplementedError
        msg = f"Conversion from {source_type} not yet implemented (Phase 7)"
        raise NotImplementedError(msg)

    html_size = len(html)
    logger.info(
        "[PIPELINE] After conversion: size=%d bytes (%.1f KB), ratio=%.1fx",
        html_size,
        html_size / 1024,
        html_size / max(input_size, 1),
    )

    # Step 2: Preprocess (remove chrome, inject speaker labels)
    preprocessed = preprocess_for_export(html, platform_hint=platform_hint)
    preproc_size = len(preprocessed)
    logger.info(
        "[PIPELINE] After preprocess: size=%d bytes (%.1f KB), ratio=%.1fx",
        preproc_size,
        preproc_size / 1024,
        preproc_size / max(input_size, 1),
    )

    # Step 3: Strip unnecessary attributes to reduce size
    # (pasted HTML often has huge inline styles, data attributes, etc.)
    stripped = _strip_heavy_attributes(preprocessed)

    # Step 4: Remove empty paragraphs/divs that only contain <br> tags
    # (Office apps use these for spacing, creates excessive whitespace)
    cleaned = _remove_empty_elements(stripped)
    final_size = len(cleaned)
    logger.info(
        "[PIPELINE] Final output: size=%d bytes (%.1f KB), ratio=%.1fx from input",
        final_size,
        final_size / 1024,
        final_size / max(input_size, 1),
    )

    # Return clean HTML - char spans are injected client-side to avoid
    # websocket message size limits (span injection multiplies size ~55x)
    return cleaned
