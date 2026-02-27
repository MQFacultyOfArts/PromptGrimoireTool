"""Paragraph-number mapping builder for the annotation pipeline.

Walks document HTML using the same selectolax traversal as
``extract_text_from_html()`` in ``html_input.py``, but additionally
tracks paragraph boundaries.  Produces a ``dict[int, int]`` mapping
char-offset-of-block-start to paragraph number.

Two modes:
- **auto-number** (default): sequential numbering of block elements
- **source-number**: uses ``<li value="N">`` attributes from the HTML

A detection function (``detect_source_numbering``) inspects HTML to
recommend which mode to use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from selectolax.lexbor import LexborHTMLParser

from promptgrimoire.input_pipeline.html_input import (
    _BLOCK_TAGS,
    _STRIP_TAGS,
    _WHITESPACE_RUN,
)

# Block elements that receive paragraph numbers in auto-number mode.
# Headers (h1-h6) are explicitly excluded per AC1.5.
_PARA_TAGS = frozenset(("p", "li", "blockquote", "div"))


def _has_nonwhitespace_text(node: Any) -> bool:
    """Check whether *node* contains any non-whitespace text content."""
    text = node.text(deep=True)
    if not text:
        return False
    return not _WHITESPACE_RUN.fullmatch(text)


@dataclass
class _WalkState:
    """Mutable state threaded through the paragraph-map walk."""

    auto_number: bool
    result: dict[int, int] = field(default_factory=dict)
    char_offset: int = 0
    current_para: int = 0
    consecutive_br: int = 0
    block_recorded: bool = False
    current_block_tag: str | None = None


def _handle_text_node(node: Any, state: _WalkState) -> None:
    """Process a text node, updating char offset and br-split state."""
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

    # After 2+ consecutive <br>, this text starts a new
    # paragraph (br-br split within a block).
    if state.consecutive_br >= 2 and state.auto_number:
        state.current_para += 1
        state.result[state.char_offset] = state.current_para
        state.block_recorded = True

    state.consecutive_br = 0
    state.char_offset += len(collapsed)


def _handle_para_tag(node: Any, tag: str, state: _WalkState) -> None:
    """Record a paragraph entry for a _PARA_TAGS element."""
    state.current_block_tag = tag
    state.block_recorded = False
    state.consecutive_br = 0

    if state.auto_number:
        if _has_nonwhitespace_text(node):
            state.current_para += 1
            state.result[state.char_offset] = state.current_para
            state.block_recorded = True
    elif tag == "li":
        # Source-number mode: only <li> with value attr
        value_attr = node.attributes.get("value")
        if value_attr is not None:
            para_num = int(value_attr)
            state.result[state.char_offset] = para_num
            state.block_recorded = True


def _walk(node: Any, state: _WalkState) -> None:
    """Walk a DOM node, mirroring extract_text_from_html traversal."""
    tag = node.tag

    if tag == "-text":
        _handle_text_node(node, state)
        return

    if tag in _STRIP_TAGS:
        return

    if tag == "br":
        state.consecutive_br += 1
        state.char_offset += 1  # \n character
        return

    # Save/restore state around _PARA_TAGS elements.
    is_para_tag = tag in _PARA_TAGS
    prev_block_tag = state.current_block_tag
    prev_block_recorded = state.block_recorded

    if is_para_tag:
        _handle_para_tag(node, tag, state)

    # Recurse into children (including headers, for
    # char-offset tracking).
    child = node.child
    while child is not None:
        _walk(child, state)
        child = child.next

    if is_para_tag:
        state.current_block_tag = prev_block_tag
        state.block_recorded = prev_block_recorded


def build_paragraph_map(
    html: str,
    *,
    auto_number: bool = True,
) -> dict[int, int]:
    """Build a char-offset to paragraph-number mapping.

    Mirrors the selectolax traversal from
    ``extract_text_from_html()`` in ``html_input.py`` so that the
    returned char offsets are valid indices into that function's
    output.

    Args:
        html: Document HTML (clean, no char-span wrappers).
        auto_number: If ``True``, assign sequential paragraph
            numbers to block elements.  If ``False``, use
            ``<li value="N">`` attributes (source-number mode).

    Returns:
        Mapping from char offset (first text char of a paragraph)
        to paragraph number.  In source-number mode, only ``<li>``
        elements with ``value`` attributes appear in the map.
    """
    if not html:
        return {}

    tree = LexborHTMLParser(html)
    body = tree.body
    root = body if body else tree.root
    if root is None:
        return {}

    state = _WalkState(auto_number=auto_number)

    child = root.child
    while child is not None:
        _walk(child, state)
        child = child.next

    return state.result


def build_paragraph_map_for_json(
    html: str,
    *,
    auto_number: bool = True,
) -> dict[str, int]:
    """Build a paragraph map with string keys suitable for JSON storage.

    Thin wrapper around ``build_paragraph_map()`` that converts the
    ``int`` char-offset keys to ``str``, as required by PostgreSQL
    JSONB and JavaScript ``Object`` keys.

    Args:
        html: Document HTML (clean, no char-span wrappers).
        auto_number: If ``True``, assign sequential paragraph
            numbers.  If ``False``, use ``<li value="N">``
            attributes (source-number mode).

    Returns:
        Mapping from char offset (as string) to paragraph number.
    """
    raw = build_paragraph_map(html, auto_number=auto_number)
    return {str(k): v for k, v in raw.items()}


def detect_source_numbering(html: str) -> bool:
    """Detect whether *html* uses explicit source paragraph numbering.

    Returns ``True`` if 2 or more ``<li>`` elements have an explicit
    ``value`` attribute, indicating AustLII-style numbered paragraphs.

    Args:
        html: Document HTML to inspect.

    Returns:
        ``True`` if source-numbered, ``False`` otherwise.
    """
    if not html:
        return False
    tree = LexborHTMLParser(html)
    matches = tree.css("li[value]")
    return len(matches) >= 2
