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
from dataclasses import dataclass
from typing import Any, Literal

from selectolax.lexbor import LexborHTMLParser

from promptgrimoire.export.marker_constants import (
    HLEND_TEMPLATE,
    HLSTART_TEMPLATE,
    MARKER_TEMPLATE,
)
from promptgrimoire.export.platforms import preprocess_for_export

logger = logging.getLogger(__name__)

# Content types supported by the pipeline
CONTENT_TYPES = ("html", "rtf", "docx", "pdf", "text")
ContentType = Literal["html", "rtf", "docx", "pdf", "text"]

# Tags to strip entirely (security: NiceGUI rejects script tags)
_STRIP_TAGS = frozenset(("script", "style", "noscript", "template"))

# Self-closing (void) tags to strip (e.g., base64 images from clipboard paste)
_STRIP_VOID_TAGS = frozenset(("img",))

# Block-level elements where whitespace-only text nodes are formatting artefacts
# (indentation between tags) and should be skipped.  Must match the JS blockTags
# set in _injectCharSpans (annotation.py) for char-index parity.
_BLOCK_TAGS = frozenset(
    (
        "table",
        "tbody",
        "thead",
        "tfoot",
        "tr",
        "td",
        "th",
        "ul",
        "ol",
        "li",
        "dl",
        "dt",
        "dd",
        "div",
        "section",
        "article",
        "aside",
        "header",
        "footer",
        "nav",
        "main",
        "figure",
        "figcaption",
        "blockquote",
    )
)

# Whitespace pattern matching JS /[\s]+/g — includes \u00a0 (nbsp)
_WHITESPACE_RUN = re.compile(r"[\s\u00a0]+")

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
    """Extract text characters from clean HTML, matching JS _injectCharSpans.

    Walks the DOM via selectolax child/next iteration (which exposes text
    nodes) so that the resulting character list has the same indices as the
    client-side char-span injection.  The two must agree for highlight
    coordinates to be correct (Issue #129).

    Matching rules (mirroring the JS):
    - ``<br>`` → ``\\n``
    - script / style / noscript / template → skipped entirely
    - Whitespace-only text nodes inside block containers → skipped
    - Whitespace runs (including ``\\u00a0``) → collapsed to single space

    Args:
        html: Clean HTML without char span wrappers.

    Returns:
        List of characters in document order.
    """
    if not html:
        return []

    tree = LexborHTMLParser(html)

    body = tree.body
    root = body if body else tree.root

    if root is None:
        return []

    chars: list[str] = []

    def _walk(node: Any) -> None:
        tag = node.tag

        # Text node — selectolax uses "-text" as the tag
        if tag == "-text":
            text = node.text_content
            if not text:
                return
            # Skip whitespace-only text nodes inside block containers
            # (these are formatting indentation between tags, not content)
            parent = node.parent
            if (
                parent is not None
                and parent.tag in _BLOCK_TAGS
                and _WHITESPACE_RUN.fullmatch(text)
            ):
                return
            # Collapse whitespace runs (including nbsp) to single space
            text = _WHITESPACE_RUN.sub(" ", text)
            chars.extend(text)
            return

        # Skip stripped tags entirely
        if tag in _STRIP_TAGS:
            return

        # <br> → newline
        if tag == "br":
            chars.append("\n")
            return

        # Recurse into children
        child = node.child
        while child is not None:
            _walk(child)
            child = child.next

    # Start from root's children (skip the root element itself)
    child = root.child
    while child is not None:
        _walk(child)
        child = child.next

    return chars


# ---------------------------------------------------------------------------
# Marker insertion (two-pass DOM walk + string insertion)
# ---------------------------------------------------------------------------

# Common HTML entities and their decoded forms
_ENTITY_MAP: dict[str, str] = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&apos;": "'",
    "&nbsp;": "\u00a0",
}


@dataclass
class _TextNodeInfo:
    """Info about a text node's contribution to the character stream."""

    html_text: str  # HTML-encoded text (for finding in serialised HTML)
    decoded_text: str  # Decoded text (from text_content)
    collapsed_text: str  # After whitespace collapsing
    char_start: int  # Starting char index in the stream
    char_end: int  # Ending char index (exclusive)


def _walk_and_map(html: str) -> tuple[list[str], list[_TextNodeInfo]]:
    """Walk DOM exactly like extract_text_from_html, returning chars + node map.

    Pass 1 of the two-pass marker insertion approach. Builds a position map
    that records where each text node's characters fall in the collapsed
    character stream, along with the HTML-encoded text for byte-offset
    matching in pass 2.
    """
    if not html:
        return [], []

    tree = LexborHTMLParser(html)
    body = tree.body
    root = body if body else tree.root
    if root is None:
        return [], []

    chars: list[str] = []
    text_nodes: list[_TextNodeInfo] = []

    def _walk(node: Any) -> None:
        tag = node.tag

        if tag == "-text":
            text = node.text_content
            if not text:
                return
            parent = node.parent
            if (
                parent is not None
                and parent.tag in _BLOCK_TAGS
                and _WHITESPACE_RUN.fullmatch(text)
            ):
                return
            collapsed = _WHITESPACE_RUN.sub(" ", text)
            start = len(chars)
            chars.extend(collapsed)
            text_nodes.append(
                _TextNodeInfo(
                    html_text=node.html,  # HTML-encoded (e.g. "&amp;")
                    decoded_text=text,  # Decoded (e.g. "&")
                    collapsed_text=collapsed,
                    char_start=start,
                    char_end=len(chars),
                )
            )
            return

        if tag in _STRIP_TAGS:
            return

        if tag == "br":
            chars.append("\n")
            return

        child = node.child
        while child is not None:
            _walk(child)
            child = child.next

    child = root.child
    while child is not None:
        _walk(child)
        child = child.next

    return chars, text_nodes


def _find_text_node_offsets(html: str, text_nodes: list[_TextNodeInfo]) -> list[int]:
    """Find the byte offset of each text node's html_text in the serialised HTML.

    Searches sequentially, advancing the search position so matches follow
    document order.

    When selectolax re-encodes characters (e.g. literal ``\\xa0`` becomes
    ``&nbsp;`` in ``node.html``), the entity form will not match the source
    HTML.  In that case we fall back to ``decoded_text`` and update the
    node's ``html_text`` so downstream offset calculations stay consistent.
    """
    offsets: list[int] = []
    search_from = 0

    for info in text_nodes:
        idx = html.find(info.html_text, search_from)
        if idx == -1:
            # selectolax may re-encode chars (e.g. \xa0 -> &nbsp;).
            # Fall back to decoded_text which matches the source.
            idx = html.find(info.decoded_text, search_from)
            if idx != -1:
                info.html_text = info.decoded_text
            else:
                msg = (
                    f"Could not find text node "
                    f"{info.html_text!r} "
                    f"in HTML starting from offset "
                    f"{search_from}"
                )
                raise ValueError(msg)
        offsets.append(idx)
        search_from = idx + len(info.html_text)

    return offsets


def _html_char_length(html_text: str, html_pos: int, decoded_char: str) -> int:
    """Determine how many bytes in *html_text* correspond to one decoded char.

    If ``html_text[html_pos]`` starts an entity (e.g. ``&amp;``), return the
    entity length.  Otherwise return 1.
    """
    if html_pos >= len(html_text):
        return 1

    if html_text[html_pos] == "&":
        # Try to match a known entity
        for entity, decoded in _ENTITY_MAP.items():
            if html_text[html_pos:].startswith(entity) and decoded == decoded_char:
                return len(entity)
        # Try numeric entity &#NNN; or &#xHHH;
        semicolon = html_text.find(";", html_pos + 1)
        if semicolon != -1 and semicolon - html_pos < 12:
            return semicolon - html_pos + 1
    return 1


def _collapsed_to_html_offset(
    html_text: str, decoded_text: str, collapsed_offset: int
) -> int:
    """Map an offset in collapsed-decoded text to an offset in HTML-encoded text.

    Walks the decoded text (which has entities resolved, e.g. ``&`` not
    ``&amp;``) applying whitespace collapsing.  Simultaneously advances
    through the HTML text to track the corresponding byte position.
    """
    if collapsed_offset == 0:
        return 0

    collapsed_pos = 0
    decoded_pos = 0
    html_pos = 0
    in_whitespace = False

    while decoded_pos < len(decoded_text) and collapsed_pos < collapsed_offset:
        ch = decoded_text[decoded_pos]
        is_ws = ch in (" ", "\t", "\n", "\r", "\u00a0") or ch.isspace()

        html_char_len = _html_char_length(html_text, html_pos, ch)

        if is_ws:
            if not in_whitespace:
                collapsed_pos += 1
                in_whitespace = True
            html_pos += html_char_len
            decoded_pos += 1
        else:
            collapsed_pos += 1
            html_pos += html_char_len
            decoded_pos += 1
            in_whitespace = False

    return html_pos


def _add_marker_insertions(
    text_nodes: list[_TextNodeInfo],
    byte_offsets: list[int],
    start_char: int,
    end_char: int,
    marker_idx: int,
    insertions: list[tuple[int, str]],
) -> None:
    """Add HLSTART and HLEND markers for a single highlight to insertions list.

    Handles boundary cases where markers fall outside all text nodes.
    """
    # Find start position
    start_node_found = False
    for i, node_info in enumerate(text_nodes):
        if node_info.char_start <= start_char < node_info.char_end:
            offset_in_collapsed = start_char - node_info.char_start
            raw_offset = _collapsed_to_html_offset(
                node_info.html_text, node_info.decoded_text, offset_in_collapsed
            )
            byte_pos = byte_offsets[i] + raw_offset
            insertions.append((byte_pos, HLSTART_TEMPLATE.format(marker_idx)))
            start_node_found = True
            break

    # Fallback: if start_char=0 but first text node has char_start>0
    if not start_node_found and text_nodes and start_char == 0:
        byte_pos = byte_offsets[0]
        insertions.append((byte_pos, HLSTART_TEMPLATE.format(marker_idx)))

    # Find end position
    end_node_found = False
    for i, node_info in enumerate(text_nodes):
        if node_info.char_start < end_char <= node_info.char_end:
            offset_in_collapsed = end_char - node_info.char_start
            raw_offset = _collapsed_to_html_offset(
                node_info.html_text, node_info.decoded_text, offset_in_collapsed
            )
            byte_pos = byte_offsets[i] + raw_offset
            insertions.append(
                (
                    byte_pos,
                    HLEND_TEMPLATE.format(marker_idx)
                    + MARKER_TEMPLATE.format(marker_idx),
                )
            )
            end_node_found = True
            break

    # Fallback: if end_char equals document length or exceeds all nodes
    if not end_node_found and text_nodes:
        node_info = text_nodes[-1]
        offset_in_collapsed = len(node_info.collapsed_text)
        raw_offset = _collapsed_to_html_offset(
            node_info.html_text, node_info.decoded_text, offset_in_collapsed
        )
        byte_pos = byte_offsets[-1] + raw_offset
        insertions.append(
            (
                byte_pos,
                HLEND_TEMPLATE.format(marker_idx) + MARKER_TEMPLATE.format(marker_idx),
            )
        )


def insert_markers_into_dom(
    html: str,
    highlights: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Insert annotation markers into HTML at correct character positions.

    Walks the DOM using the same logic as ``extract_text_from_html``
    (same whitespace rules, same block/strip tags, same collapse).
    Inserts ``HLSTART``/``HLEND``/``ANNMARKER`` text into the serialised
    HTML at positions matching the char indices from
    ``extract_text_from_html``.

    Args:
        html: Clean HTML (from doc.content, no char spans).
        highlights: List of highlight dicts with ``start_char``, ``end_char``,
            ``tag``, etc.  Supports both ``start_char``/``end_char`` and
            legacy ``start_word``/``end_word`` fields.

    Returns:
        ``(marked_html, ordered_highlights)`` -- marked HTML with markers
        inserted, and highlights in marker order (same contract as
        ``_insert_markers_into_html``).

    Raises:
        ValueError: If *html* is empty/None and *highlights* are non-empty.
    """
    if not highlights:
        return html, []

    if not html:
        msg = "Cannot insert markers into empty HTML when highlights are non-empty"
        raise ValueError(msg)

    # Sort by start_char, then by tag (matching _insert_markers_into_html)
    sorted_highlights = sorted(
        highlights,
        key=lambda h: (
            h.get("start_char", h.get("start_word", 0)),
            h.get("tag", ""),
        ),
    )

    # Pass 1 — DOM walk to build position map
    _chars, text_nodes = _walk_and_map(html)

    # Pass 2a — find byte offsets of each text node in serialised HTML
    byte_offsets = _find_text_node_offsets(html, text_nodes)

    # Pass 2b — build insertion list
    insertions: list[tuple[int, str]] = []
    marker_to_highlight: list[dict[str, Any]] = []

    for hl in sorted_highlights:
        start_char = int(hl.get("start_char", hl.get("start_word", 0)))
        end_char = int(hl.get("end_char", hl.get("end_word", start_char + 1)))

        marker_idx = len(marker_to_highlight)
        marker_to_highlight.append(hl)

        _add_marker_insertions(
            text_nodes, byte_offsets, start_char, end_char, marker_idx, insertions
        )

    # Sort insertions by byte offset descending — insert back-to-front
    insertions.sort(key=lambda x: x[0], reverse=True)

    # Reverse items at the same byte position so they insert in correct order.
    # When multiple markers are at the same position, the insertion loop processes
    # them in order, each pushing earlier markers forward. By reversing items at
    # each position level, we ensure later-appended markers are processed first.
    i = 0
    while i < len(insertions):
        j = i + 1
        while j < len(insertions) and insertions[j][0] == insertions[i][0]:
            j += 1
        insertions[i:j] = list(reversed(insertions[i:j]))
        i = j

    result = html
    for byte_pos, marker in insertions:
        result = result[:byte_pos] + marker + result[byte_pos:]

    return result, marker_to_highlight


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
            # Preserve speaker marker divs (intentionally empty, styled via ::before)
            if node.attributes.get("data-speaker"):
                continue

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
