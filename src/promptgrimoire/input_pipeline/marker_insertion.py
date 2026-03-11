"""Annotation marker insertion into HTML.

Two-pass approach:
1. DOM walk (via ``text_extraction``) to build a position map of text nodes
2. String insertion of HLSTART/HLEND/ANNMARKER sentinels at byte offsets

The marker positions use the same character indices as
``extract_text_from_html`` so that highlights align correctly with the
client-side JS text walker (Issue #129).
"""

from __future__ import annotations

import html as html_module
from typing import Any

from promptgrimoire.input_pipeline.marker_constants import (
    HLEND_TEMPLATE,
    HLSTART_TEMPLATE,
    MARKER_TEMPLATE,
)
from promptgrimoire.input_pipeline.text_extraction import (
    _ENTITY_MAP,
    TextNodeInfo,
    walk_and_map,
)


def _try_entity_match(
    html: str, html_pos: int, decoded_text: str, decoded_pos: int
) -> tuple[int, int] | None:
    """Try to match an HTML entity at *html_pos* against decoded text.

    Returns ``(new_html_pos, new_decoded_pos)`` on success, or ``None``
    if the entity does not match.
    """
    semicolon = html.find(";", html_pos + 1)
    if semicolon == -1 or semicolon - html_pos >= 12:
        return None
    entity_text = html[html_pos : semicolon + 1]
    decoded_entity = html_module.unescape(entity_text)
    if decoded_text[decoded_pos : decoded_pos + len(decoded_entity)] == decoded_entity:
        return (semicolon + 1, decoded_pos + len(decoded_entity))
    return None


def _match_at_candidate(
    html: str, html_len: int, candidate_start: int, decoded_text: str
) -> int | None:
    """Try to match *decoded_text* starting at *candidate_start* in *html*.

    Returns the end position in *html* on full match, or ``None``.
    """
    html_pos = candidate_start
    decoded_pos = 0

    while decoded_pos < len(decoded_text) and html_pos < html_len:
        ch = html[html_pos]
        if ch == "<":
            return None  # Tag boundary -- text node can't span tags

        if ch == "&":
            entity_result = _try_entity_match(html, html_pos, decoded_text, decoded_pos)
            if entity_result is not None:
                html_pos, decoded_pos = entity_result
                continue
            # Not a matching entity -- try literal '&' match
            if decoded_text[decoded_pos] != "&":
                return None
            decoded_pos += 1
            html_pos += 1
            continue

        if ch != decoded_text[decoded_pos]:
            return None
        html_pos += 1
        decoded_pos += 1

    if decoded_pos == len(decoded_text):
        return html_pos
    return None


def _entity_aware_find(
    html: str, decoded_text: str, start: int
) -> tuple[int, int] | None:
    """Find *decoded_text* in *html* matching through HTML entities.

    Walks the source HTML character by character starting from *start*.
    Each decoded character can match either its literal form or any HTML
    entity that decodes to it (named like ``&quot;``, decimal like ``&#34;``,
    or hex like ``&#x22;``).

    Returns ``(match_start, match_end)`` byte offsets in *html*, or
    ``None`` if no match is found.
    """
    if not decoded_text:
        return (start, start)

    html_len = len(html)

    for candidate_start in range(start, html_len):
        if html[candidate_start] == "<":
            continue

        end = _match_at_candidate(html, html_len, candidate_start, decoded_text)
        if end is not None:
            return (candidate_start, end)

    return None


def find_text_node_offsets(html: str, text_nodes: list[TextNodeInfo]) -> list[int]:
    """Find the byte offset of each text node's html_text in the serialised HTML.

    Searches sequentially, advancing the search position so matches follow
    document order.

    Three fallback strategies for matching text nodes to source HTML:

    1. ``html_text`` (selectolax serialization) -- handles entities that
       selectolax preserves (``&amp;``, ``&lt;``, ``&gt;``, ``&nbsp;``).
    2. ``decoded_text`` -- handles cases where selectolax re-encodes
       (e.g. literal ``\\xa0`` becomes ``&nbsp;`` in ``node.html``).
    3. Entity-aware matching -- handles entities that selectolax decodes
       but the source retains (``&quot;``, ``&#x27;``, numeric refs).
       See #143.
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
                # #143: selectolax decoded entities (e.g. &quot; -> ") that
                # the source HTML retains.  Match character-by-character,
                # allowing entity forms in source to match decoded chars.
                result = _entity_aware_find(html, info.decoded_text, search_from)
                if result is not None:
                    idx, end = result
                    info.html_text = html[idx:end]
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


def collapsed_to_html_offset(
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
    text_nodes: list[TextNodeInfo],
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
            raw_offset = collapsed_to_html_offset(
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
            raw_offset = collapsed_to_html_offset(
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
        raw_offset = collapsed_to_html_offset(
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

    # Pass 1 -- DOM walk to build position map
    _chars, text_nodes = walk_and_map(html)

    # Pass 2a -- find byte offsets of each text node in serialised HTML
    byte_offsets = find_text_node_offsets(html, text_nodes)

    # Pass 2b -- build insertion list
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

    # Sort insertions by byte offset descending -- insert back-to-front
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
