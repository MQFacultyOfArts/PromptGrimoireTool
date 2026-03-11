"""DOM text extraction: walking, collapsing, and position mapping.

Walks the DOM via selectolax child/next iteration (which exposes text nodes)
to extract characters and build position maps for annotation marker insertion.
The character indices must match the client-side JS text walker for highlight
coordinates to be correct (Issue #129).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from selectolax.lexbor import LexborHTMLParser

# Tags to strip entirely (security: NiceGUI rejects script tags)
_STRIP_TAGS = frozenset(("script", "style", "noscript", "template"))


# Block-level elements where whitespace-only text nodes are formatting artefacts
# (indentation between tags) and should be skipped.  Must match the JS blockTags
# set in walkTextNodes (annotation-highlight.js) for char-index parity.
_BLOCK_TAGS = frozenset(
    (
        "html",
        "body",
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

# Whitespace pattern matching JS /[\s]+/g -- includes \u00a0 (nbsp)
_WHITESPACE_RUN = re.compile(r"[\s\u00a0]+")

# Common HTML entities and their decoded forms.
# Shared with marker_insertion for entity-aware offset mapping.
ENTITY_MAP: dict[str, str] = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&apos;": "'",
    "&nbsp;": "\u00a0",
}


@dataclass
class TextNodeInfo:
    """Info about a text node's contribution to the character stream."""

    html_text: str  # HTML-encoded text (for finding in serialised HTML)
    decoded_text: str  # Decoded text (from text_content)
    collapsed_text: str  # After whitespace collapsing
    char_start: int  # Starting char index in the stream
    char_end: int  # Ending char index (exclusive)


def _collapse_text_node(node: Any) -> str | None:
    """Return collapsed text for a text node, or ``None`` if it should be skipped.

    Skips whitespace-only text nodes inside block containers (formatting
    artefacts).  Collapses whitespace runs (including nbsp) to single space.
    """
    text = node.text_content
    if not text:
        return None
    parent = node.parent
    if (
        parent is not None
        and parent.tag in _BLOCK_TAGS
        and _WHITESPACE_RUN.fullmatch(text)
    ):
        return None
    return _WHITESPACE_RUN.sub(" ", text)


def _get_dom_root(html: str) -> Any | None:
    """Parse *html* and return the root element for text walking."""
    tree = LexborHTMLParser(html)
    body = tree.body
    root = body if body else tree.root
    return root


def _walk_dom(
    node: Any,
    chars: list[str],
    text_nodes: list[TextNodeInfo] | None = None,
) -> None:
    """Recursively walk DOM collecting characters and optionally text-node info.

    Shared walker for ``extract_text_from_html`` and ``walk_and_map``.
    When *text_nodes* is not ``None``, appends ``TextNodeInfo`` entries
    for marker-insertion pass 2.
    """
    tag = node.tag

    if tag == "-text":
        collapsed = _collapse_text_node(node)
        if collapsed is None:
            return
        start = len(chars)
        chars.extend(collapsed)
        if text_nodes is not None:
            text_nodes.append(
                TextNodeInfo(
                    html_text=node.html,
                    decoded_text=node.text_content,
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
        _walk_dom(child, chars, text_nodes)
        child = child.next


def extract_text_from_html(html: str) -> list[str]:
    """Extract text characters from clean HTML, matching JS walkTextNodes.

    Walks the DOM via selectolax child/next iteration (which exposes text
    nodes) so that the resulting character list has the same indices as
    the client-side text walker.  The two must agree for highlight
    coordinates to be correct (Issue #129).

    Matching rules (mirroring the JS):
    - ``<br>`` -> ``\\n``
    - script / style / noscript / template -> skipped entirely
    - Whitespace-only text nodes inside block containers -> skipped
    - Whitespace runs (including ``\\u00a0``) -> collapsed to single space

    Args:
        html: Clean HTML without char span wrappers.

    Returns:
        List of characters in document order.
    """
    if not html:
        return []

    root = _get_dom_root(html)
    if root is None:
        return []

    chars: list[str] = []
    child = root.child
    while child is not None:
        _walk_dom(child, chars)
        child = child.next

    return chars


def walk_and_map(html: str) -> tuple[list[str], list[TextNodeInfo]]:
    """Walk DOM exactly like extract_text_from_html, returning chars + node map.

    Pass 1 of the two-pass marker insertion approach. Builds a position map
    that records where each text node's characters fall in the collapsed
    character stream, along with the HTML-encoded text for byte-offset
    matching in pass 2.
    """
    if not html:
        return [], []

    root = _get_dom_root(html)
    if root is None:
        return [], []

    chars: list[str] = []
    text_nodes: list[TextNodeInfo] = []

    child = root.child
    while child is not None:
        _walk_dom(child, chars, text_nodes)
        child = child.next

    return chars, text_nodes
