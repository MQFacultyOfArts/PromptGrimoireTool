"""Block and inline boundary detection for highlight span splitting.

Provides constants and functions that identify character positions where
highlight ``<span>`` elements must be split to produce well-formed HTML
that Pandoc can process without silently destroying spans.

Separated from ``highlight_spans.py`` (region computation + DOM insertion)
for single-responsibility clarity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from promptgrimoire.input_pipeline.html_input import TextNodeInfo

# Block-level elements that Pandoc treats as block-level.
# Spans crossing these boundaries are silently destroyed by Pandoc.
# Separate from ``_BLOCK_TAGS`` in ``html_input.py`` which serves whitespace
# collapsing.
PANDOC_BLOCK_ELEMENTS: frozenset[str] = frozenset(
    (
        "p",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "blockquote",
        "div",
        "li",
        "ul",
        "ol",
        "table",
        "tr",
        "td",
        "th",
        "section",
        "article",
        "aside",
        "header",
        "footer",
        "figure",
        "figcaption",
        "pre",
        "dl",
        "dt",
        "dd",
    )
)

# Inline formatting elements whose boundaries require span splitting.
# A highlight span opening inside <b> and closing outside </b> produces
# malformed HTML that parsers and Pandoc silently destroy.
INLINE_FORMATTING_ELEMENTS: frozenset[str] = frozenset(
    (
        "b",
        "strong",
        "em",
        "i",
        "u",
        "s",
        "del",
        "ins",
        "mark",
        "small",
        "sub",
        "sup",
        "code",
        "abbr",
        "cite",
        "dfn",
        "kbd",
        "q",
        "samp",
        "var",
    )
)


# ---------------------------------------------------------------------------
# Block-boundary detection
# ---------------------------------------------------------------------------


def _detect_block_boundaries(
    html: str,
    text_nodes: list[TextNodeInfo],
    byte_offsets: list[int],
) -> set[int]:
    """Identify character positions where a block boundary occurs.

    A block boundary is the ``char_start`` of a text node whose nearest
    block-level ancestor differs from that of the preceding text node.

    Scans backwards through the serialized HTML to find the nearest
    block-level ancestor tag for each text node, then compares consecutive
    text nodes to detect boundary transitions.

    Args:
        html: Serialized HTML string.
        text_nodes: List of text node info from walk_and_map.
        byte_offsets: Byte offsets of each text node in the HTML string.
    """
    if len(text_nodes) <= 1:
        return set()

    def _find_block_ancestor_at(byte_pos: int) -> str:
        """Find the innermost block-level ancestor tag at a byte position.

        Scans backwards through the HTML to find the nearest open tag that
        is a block element. Uses a simple tag-stack approach.
        """
        # Walk backwards from byte_pos looking for the nearest block tag
        # We look for the most recent unclosed block-level opening tag.
        depth = 0
        i = byte_pos - 1
        while i >= 0:
            if html[i] == ">":
                # Found a tag end, scan backwards to find tag start
                tag_end = i
                tag_start = html.rfind("<", 0, i)
                if tag_start == -1:
                    i -= 1
                    continue
                tag_content = html[tag_start + 1 : tag_end]
                if tag_content.startswith("/"):
                    # Closing tag
                    tag_name = tag_content[1:].split()[0].strip("/").lower()
                    if tag_name in PANDOC_BLOCK_ELEMENTS:
                        depth += 1
                elif not tag_content.startswith("!"):
                    # Opening tag
                    tag_name = tag_content.split()[0].strip("/").lower()
                    if tag_name in PANDOC_BLOCK_ELEMENTS:
                        if depth == 0:
                            return f"{tag_name}@{tag_start}"
                        depth -= 1
                i = tag_start - 1
            else:
                i -= 1
        return "root@0"

    # Build block ancestor identity for each text node
    prev_block: str | None = None
    boundaries: set[int] = set()

    for i, tn in enumerate(text_nodes):
        block_id = _find_block_ancestor_at(byte_offsets[i])
        if prev_block is not None and block_id != prev_block:
            boundaries.add(tn.char_start)
        prev_block = block_id

    return boundaries


# ---------------------------------------------------------------------------
# Inline-formatting boundary detection
# ---------------------------------------------------------------------------


def _inline_context_at(
    html: str,
    byte_pos: int,
) -> tuple[str, ...]:
    """Compute the inline formatting ancestor context at a byte position.

    Scans backwards from *byte_pos* through the serialised HTML, collecting
    unclosed inline formatting tags until a block-level element is reached.
    Returns a sorted tuple of inline tag names that are open at this position.
    """
    # Track nesting: when we see a closing tag we need to skip its matching
    # open tag (it's a completed element, not an ancestor).
    depth: dict[str, int] = {}
    ancestors: list[str] = []
    i = byte_pos - 1

    while i >= 0:
        if html[i] == ">":
            tag_end = i
            tag_start = html.rfind("<", 0, i)
            if tag_start == -1:
                i -= 1
                continue
            tag_content = html[tag_start + 1 : tag_end]
            if tag_content.startswith("/"):
                # Closing tag -- the element is completed, skip its opener
                tag_name = tag_content[1:].split()[0].strip("/").lower()
                if tag_name in PANDOC_BLOCK_ELEMENTS:
                    break  # Stop at block boundary
                if tag_name in INLINE_FORMATTING_ELEMENTS:
                    depth[tag_name] = depth.get(tag_name, 0) + 1
            elif not tag_content.startswith("!"):
                # Opening tag
                tag_name = tag_content.split()[0].strip("/").lower()
                if tag_name in PANDOC_BLOCK_ELEMENTS:
                    break  # Stop at block boundary
                if tag_name in INLINE_FORMATTING_ELEMENTS:
                    d = depth.get(tag_name, 0)
                    if d > 0:
                        depth[tag_name] = d - 1
                    else:
                        ancestors.append(tag_name)
            i = tag_start - 1
        else:
            i -= 1

    return tuple(sorted(ancestors))


def _detect_inline_boundaries(
    html: str,
    text_nodes: list[TextNodeInfo],
    byte_offsets: list[int],
) -> set[int]:
    """Identify character positions where inline formatting context changes.

    For each pair of consecutive text nodes within the same block, computes
    the set of inline formatting ancestors.  When the inline context differs,
    a boundary is recorded at the ``char_start`` of the second text node.

    This ensures that highlight ``<span>`` elements are split at inline
    formatting boundaries (e.g. ``</b>``, ``</em>``) so the resulting HTML
    is well-formed.
    """
    if len(text_nodes) <= 1:
        return set()

    boundaries: set[int] = set()
    prev_ctx: tuple[str, ...] | None = None

    for i, tn in enumerate(text_nodes):
        ctx = _inline_context_at(html, byte_offsets[i])
        if prev_ctx is not None and ctx != prev_ctx:
            boundaries.add(tn.char_start)
        prev_ctx = ctx

    return boundaries
