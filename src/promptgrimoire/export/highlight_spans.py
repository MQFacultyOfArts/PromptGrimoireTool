"""Pre-Pandoc highlight span insertion.

Transforms clean HTML + highlight list into HTML with
``<span data-hl="..." data-colors="..." data-annots="...">`` elements.
Spans are pre-split at block boundaries so that Pandoc does not silently
destroy cross-block spans (E5 experiment result).

Architecture:
    Reuses ``walk_and_map`` / ``extract_text_from_html`` from the input
    pipeline for character-position-to-DOM-node mapping.  Computes
    non-overlapping regions from overlapping highlights (event-sweep
    algorithm), then inserts flat ``<span>`` elements with comma-separated
    attribute lists.
"""

from __future__ import annotations

import logging
from typing import Any

from promptgrimoire.export.latex_render import NoEscape, latex_cmd
from promptgrimoire.export.preamble import _format_timestamp, _strip_test_uuid
from promptgrimoire.export.unicode_latex import escape_unicode_latex
from promptgrimoire.input_pipeline.html_input import (
    TextNodeInfo,
    collapsed_to_html_offset,
    find_text_node_offsets,
    walk_and_map,
)

logger = logging.getLogger(__name__)

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
# Annotation formatting (adapted from _format_annot in latex.py)
# ---------------------------------------------------------------------------


def format_annot_latex(
    highlight: dict[str, Any],
    para_ref: str = "",
) -> str:
    r"""Format a highlight as a LaTeX ``\annot`` command.

    Layout in margin note::

        **Tag** [para]
        name, date
        ---
        comment text...

    Adapts the logic from ``_format_annot()`` (formerly in ``latex.py``) for
    use by ``compute_highlight_spans()`` when populating the ``data-annots``
    attribute.

    Args:
        highlight: Highlight dict with ``tag``, ``author``, ``text``,
            ``comments``, ``created_at``.
        para_ref: Paragraph reference string (e.g. ``"[45]"`` or
            ``"[45]-[48]"``).

    Returns:
        LaTeX ``\annot{colour}{margin_content}`` command string.
    """
    tag = highlight.get("tag", "jurisdiction")
    author = _strip_test_uuid(highlight.get("author", "Unknown"))
    comments = highlight.get("comments", [])
    created_at = highlight.get("created_at", "")

    # Tag colour name (matches \definecolor name).
    # NoEscape: colour names may contain '#' (pre-existing bug, see AC4.4).
    colour_name = NoEscape(f"tag-{tag.replace('_', '-')}")

    # Build margin content
    tag_display = tag.replace("_", " ").title()
    timestamp = _format_timestamp(created_at)

    # escape_unicode_latex() already escapes LaTeX specials, so its output
    # is trusted LaTeX (NoEscape).  Do NOT layer escape_latex() on top.
    tag_esc = NoEscape(escape_unicode_latex(tag_display))

    # Line 1: **Tag** [para]
    tag_bold = latex_cmd("textbf", tag_esc)
    if para_ref:
        margin_parts: list[str] = [f"{tag_bold} {para_ref}"]
    else:
        margin_parts = [str(tag_bold)]

    # Line 2: name, date (scriptsize)
    author_esc = NoEscape(escape_unicode_latex(author))
    byline = f"{author_esc}, {timestamp}" if timestamp else str(author_esc)
    margin_parts.append(f"\\par{{\\scriptsize {byline}}}")

    # Separator and comments if present
    if comments:
        margin_parts.append("\\par\\hrulefill")
        for comment in comments:
            c_author = _strip_test_uuid(comment.get("author", "Unknown"))
            c_text = comment.get("text", "")
            c_timestamp = _format_timestamp(comment.get("created_at", ""))
            c_author_esc = NoEscape(escape_unicode_latex(c_author))
            c_text_esc = NoEscape(escape_unicode_latex(c_text))
            if c_timestamp:
                c_bold = latex_cmd("textbf", c_author_esc)
                attribution = f"{c_bold}, {c_timestamp}:"
            else:
                c_bold = latex_cmd("textbf", NoEscape(f"{c_author_esc}:"))
                attribution = str(c_bold)
            margin_parts.append(f"\\par{{\\scriptsize {attribution}}} {c_text_esc}")

    margin_content = NoEscape("".join(margin_parts))

    return str(latex_cmd("annot", colour_name, margin_content))


# ---------------------------------------------------------------------------
# Region data structure
# ---------------------------------------------------------------------------


class _HlRegion:
    """A contiguous character range with a constant set of active highlights.

    Attributes:
        start: Start character index (inclusive).
        end: End character index (exclusive).
        active: Frozenset of highlight indices active in this region.
        annots: Highlight indices whose annotation marker belongs here
                (the last span of that highlight).
    """

    __slots__ = ("active", "annots", "end", "start")

    def __init__(
        self,
        start: int,
        end: int,
        active: frozenset[int],
    ) -> None:
        self.start = start
        self.end = end
        self.active = active
        self.annots: list[int] = []


# ---------------------------------------------------------------------------
# Region computation (event-sweep)
# ---------------------------------------------------------------------------


def _compute_regions(
    highlights: list[dict[str, Any]],
) -> list[_HlRegion]:
    """Compute non-overlapping regions from overlapping highlights.

    Builds an event list of ``(char_position, highlight_index, "start"|"end")``
    tuples, sorts by position, then sweeps through creating regions where the
    active set is constant.

    Returns an empty list when *highlights* is empty.
    """
    if not highlights:
        return []

    # Build event list
    events: list[tuple[int, int, str]] = []
    for idx, hl in enumerate(highlights):
        start = int(hl.get("start_char", hl.get("start_word", 0)))
        end = int(hl.get("end_char", hl.get("end_word", start + 1)))
        events.append((start, idx, "start"))
        events.append((end, idx, "end"))

    # Sort: by position, then "start" before "end" at same position so that a
    # highlight starting exactly where another ends does not produce a gap.
    events.sort(key=lambda e: (e[0], 0 if e[2] == "start" else 1))

    # Sweep
    active: set[int] = set()
    regions: list[_HlRegion] = []
    prev_pos: int | None = None

    for pos, idx, kind in events:
        if prev_pos is not None and pos > prev_pos and active:
            regions.append(
                _HlRegion(
                    start=prev_pos,
                    end=pos,
                    active=frozenset(active),
                )
            )
        if kind == "start":
            active.add(idx)
        else:
            active.discard(idx)
        prev_pos = pos

    # Assign annotation markers to last region of each highlight.
    # The annotation margin note should appear at the end of the highlighted
    # range, matching where ANNMARKER would have been placed.
    for idx, hl in enumerate(highlights):
        end = int(hl.get("end_char", hl.get("end_word", 0)))
        # Walk backwards through regions to find the last one containing this
        # highlight index.
        for region in reversed(regions):
            if idx in region.active:
                region.annots.append(idx)
                break

    return regions


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
                # Closing tag — the element is completed, skip its opener
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


# ---------------------------------------------------------------------------
# Split regions at boundaries
# ---------------------------------------------------------------------------


def _split_regions_at_boundaries(
    regions: list[_HlRegion],
    boundaries: set[int],
) -> list[_HlRegion]:
    """Split regions that cross block or inline formatting boundaries.

    Each region that spans a boundary position is split into sub-regions
    with the same ``active`` set but different character ranges.
    ``annots`` are placed on the last sub-region.
    """
    if not boundaries:
        return regions

    result: list[_HlRegion] = []
    for region in regions:
        # Find boundaries within this region
        splits = sorted(b for b in boundaries if region.start < b < region.end)
        if not splits:
            result.append(region)
            continue

        # Split at each boundary
        positions = [region.start, *splits, region.end]
        sub_regions: list[_HlRegion] = []
        for j in range(len(positions) - 1):
            sub = _HlRegion(
                start=positions[j],
                end=positions[j + 1],
                active=region.active,
            )
            sub_regions.append(sub)

        # annots go on the last sub-region
        if sub_regions:
            sub_regions[-1].annots = region.annots

        result.extend(sub_regions)

    return result


# ---------------------------------------------------------------------------
# DOM insertion (back-to-front string insertion)
# ---------------------------------------------------------------------------


def _build_span_tag(
    region: _HlRegion,
    highlights: list[dict[str, Any]],
    tag_colours: dict[str, str],  # noqa: ARG001 — API placeholder; colours derived from tag slugs
    word_to_legal_para: dict[int, int | None] | None,
) -> tuple[str, str]:
    """Build opening and closing ``<span>`` tags for a region.

    Returns ``(open_tag, close_tag)``.
    """
    sorted_indices = sorted(region.active)
    hl_attr = ",".join(str(i) for i in sorted_indices)

    # Build colour names: tag-{slug}-light
    color_names: list[str] = []
    for i in sorted_indices:
        hl = highlights[i]
        tag = hl.get("tag", "unknown")
        safe_tag = tag.replace("_", "-")
        color_names.append(f"tag-{safe_tag}-light")
    colors_attr = ",".join(color_names)

    open_tag = f'<span data-hl="{hl_attr}" data-colors="{colors_attr}"'

    # Build data-annots attribute if this region has annotations.
    # The value is pre-formatted LaTeX (\annot{...}{...} commands) that the
    # Lua filter emits verbatim as RawInline.
    if region.annots:
        annot_parts: list[str] = []
        for annot_idx in region.annots:
            hl = highlights[annot_idx]
            # Resolve para_ref string
            para_ref = ""
            if word_to_legal_para is not None:
                start_char = int(hl.get("start_char", hl.get("start_word", 0)))
                para_num = word_to_legal_para.get(start_char)
                if para_num is not None:
                    para_ref = f"[{para_num}]"
            annot_parts.append(format_annot_latex(hl, para_ref=para_ref))
        annots_latex = "".join(annot_parts)
        # Use single quotes for the attribute since LaTeX uses braces/backslashes
        open_tag += f" data-annots='{annots_latex}'"

    open_tag += ">"
    close_tag = "</span>"
    return open_tag, close_tag


def _insert_spans_into_html(
    html: str,
    regions: list[_HlRegion],
    text_nodes: list[TextNodeInfo],
    byte_offsets: list[int],
    highlights: list[dict[str, Any]],
    tag_colours: dict[str, str],
    word_to_legal_para: dict[int, int | None] | None,
) -> str:
    """Insert ``<span>`` tags into HTML for each region.

    Uses back-to-front string insertion to preserve byte offsets.
    For each region, finds the text nodes it covers and inserts
    opening/closing span tags at the correct byte positions.
    """
    if not regions:
        return html

    # Build list of (byte_position, tag_string) insertions
    insertions: list[tuple[int, str]] = []

    for region in regions:
        open_tag, close_tag = _build_span_tag(
            region, highlights, tag_colours, word_to_legal_para
        )

        # Find the byte position for the start of this region
        start_byte = _char_to_byte_pos(
            region.start, text_nodes, byte_offsets, is_region_end=False
        )
        # Find the byte position for the end of this region
        end_byte = _char_to_byte_pos(
            region.end, text_nodes, byte_offsets, is_region_end=True
        )

        if start_byte is not None and end_byte is not None:
            insertions.append((end_byte, close_tag))
            insertions.append((start_byte, open_tag))

    # Sort by byte position descending (back-to-front insertion).
    # At the same position: closing tags before opening tags, so that when
    # inserted in order at the same byte position, we get: </old><new>
    # which is the correct order in the resulting HTML.
    def sort_key(item: tuple[int, str]) -> tuple[int, bool]:
        byte_pos, tag = item
        is_closing = tag.startswith("</")
        # Return (pos, is_closing): with reverse=True, (pos, True) > (pos, False)
        # so closing tags (True) come first in the sorted order
        return (byte_pos, is_closing)

    insertions.sort(key=sort_key, reverse=True)

    result = html
    prev_pos: int | None = None
    # Group insertions by position to handle same-position tags together.
    # When multiple insertions are at the same position, concatenate them
    # so they're inserted atomically, preserving the intended order.
    same_pos_buffer: list[str] = []

    for byte_pos, tag in insertions:
        if prev_pos is not None and byte_pos != prev_pos:
            # Different position: flush the buffer
            result = result[:prev_pos] + "".join(same_pos_buffer) + result[prev_pos:]
            same_pos_buffer = []
        same_pos_buffer.append(tag)
        prev_pos = byte_pos

    # Flush remaining buffer
    if same_pos_buffer and prev_pos is not None:
        result = result[:prev_pos] + "".join(same_pos_buffer) + result[prev_pos:]

    return result


def _char_to_byte_pos(
    char_idx: int,
    text_nodes: list[TextNodeInfo],
    byte_offsets: list[int],
    is_region_end: bool = False,
) -> int | None:
    """Map a character index to a byte position in the serialized HTML.

    Finds the text node containing ``char_idx`` and computes the
    byte offset within it using ``collapsed_to_html_offset``.

    At block boundaries where char_idx equals the char_end of one node AND
    the char_start of the next:
    - If ``is_region_end`` is False (default): uses the start of the next node
    - If ``is_region_end`` is True: uses the end of the previous node

    Args:
        char_idx: Character index to map.
        text_nodes: List of text node information.
        byte_offsets: Byte offsets of each text node.
        is_region_end: If True, map to position AFTER the last character
            (for region close tags). If False, map to position AT the character
            (for region open tags and positions within nodes).
    """
    # Match char_idx strictly within a text node's interior
    for i, tn in enumerate(text_nodes):
        if tn.char_start < char_idx < tn.char_end:
            offset_in_collapsed = char_idx - tn.char_start
            raw_offset = collapsed_to_html_offset(
                tn.html_text, tn.decoded_text, offset_in_collapsed
            )
            return byte_offsets[i] + raw_offset

    # At block boundaries: char_idx == prev_node.char_end == next_node.char_start.
    for i, tn in enumerate(text_nodes):
        if char_idx == tn.char_start:
            if is_region_end and i > 0:
                # For region ends at a boundary, use the END of the previous node
                prev = text_nodes[i - 1]
                prev_idx = i - 1
                raw_offset = collapsed_to_html_offset(
                    prev.html_text, prev.decoded_text, len(prev.collapsed_text)
                )
                return byte_offsets[prev_idx] + raw_offset
            else:
                # For region starts or positions within first node,
                # use the START of this node
                offset_in_collapsed = 0
                raw_offset = collapsed_to_html_offset(
                    tn.html_text, tn.decoded_text, offset_in_collapsed
                )
                return byte_offsets[i] + raw_offset

    # Match char_idx at the end of the last text node
    # (position after the final character)
    if text_nodes and char_idx == text_nodes[-1].char_end:
        last = text_nodes[-1]
        last_idx = len(text_nodes) - 1
        raw_offset = collapsed_to_html_offset(
            last.html_text, last.decoded_text, len(last.collapsed_text)
        )
        return byte_offsets[last_idx] + raw_offset

    # Fallback: char_idx beyond all text nodes -> end of last text node
    if text_nodes:
        last = text_nodes[-1]
        last_idx = len(text_nodes) - 1
        raw_offset = collapsed_to_html_offset(
            last.html_text, last.decoded_text, len(last.collapsed_text)
        )
        return byte_offsets[last_idx] + raw_offset

    return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compute_highlight_spans(
    html: str,
    highlights: list[dict[str, Any]],
    tag_colours: dict[str, str],
    word_to_legal_para: dict[int, int | None] | None = None,
) -> str:
    """Transform HTML + highlight list into HTML with highlight ``<span>`` elements.

    Computes non-overlapping regions from overlapping highlights, pre-splits
    at block boundaries (so Pandoc does not destroy cross-block spans), and
    inserts flat ``<span>`` elements with attribute lists.

    Args:
        html: Clean HTML (no char spans).
        highlights: List of highlight dicts with ``start_char``,
            ``end_char``, ``tag``, ``author``, ``para_ref``, ``text``,
            ``comments``.
        tag_colours: Mapping of tag slug to hex colour
            (e.g. ``{"jurisdiction": "#3366cc"}``).
        word_to_legal_para: Optional mapping of char index to legal
            paragraph number.

    Returns:
        HTML with ``<span>`` elements inserted.  If *highlights* is empty,
        returns *html* unchanged.
    """
    if not highlights:
        return html

    if not html:
        return html

    # Sort highlights by start_char for deterministic region computation
    sorted_highlights = sorted(
        highlights,
        key=lambda h: (
            int(h.get("start_char", h.get("start_word", 0))),
            h.get("tag", ""),
        ),
    )

    # Pass 1: DOM walk to build character position map
    _chars, text_nodes = walk_and_map(html)

    if not text_nodes:
        return html

    # Pass 2a: Find byte offsets of each text node in serialized HTML
    byte_offsets = find_text_node_offsets(html, text_nodes)

    # Compute non-overlapping regions
    regions = _compute_regions(sorted_highlights)

    if not regions:
        return html

    # Detect block and inline formatting boundaries
    boundaries = _detect_block_boundaries(html, text_nodes, byte_offsets)
    boundaries |= _detect_inline_boundaries(html, text_nodes, byte_offsets)

    # Split regions at boundaries
    regions = _split_regions_at_boundaries(regions, boundaries)

    # Insert spans into HTML
    return _insert_spans_into_html(
        html,
        regions,
        text_nodes,
        byte_offsets,
        sorted_highlights,
        tag_colours,
        word_to_legal_para,
    )
