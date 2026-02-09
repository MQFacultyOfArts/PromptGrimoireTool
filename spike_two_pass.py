#!/usr/bin/env python3
"""Spike: Prove two-pass DOM walk + string insertion approach works.

This spike proves that we can:
1. Walk the DOM with the same logic as extract_text_from_html
2. Build a map of (char_index -> (text_node_content, offset_in_text_node))
3. Serialise the HTML
4. Find the text nodes in the serialised output
5. Insert marker strings at the correct byte positions
6. Verify the markers surround exactly the right characters

The key constraint: selectolax text nodes are read-only (.text_content is
read-only). So we CANNOT mutate the DOM directly. Instead we use the DOM
walk to build a position map, then operate on the serialised string.
"""

from __future__ import annotations

import html as html_module
import re
from dataclasses import dataclass
from typing import Any

from selectolax.lexbor import LexborHTMLParser

# Same constants as html_input.py
_STRIP_TAGS = frozenset(("script", "style", "noscript", "template"))
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
_WHITESPACE_RUN = re.compile(r"[\s\u00a0]+")


# --- Pass 1: Walk DOM, build position map ---


@dataclass
class TextNodeInfo:
    """Info about a text node's contribution to the char stream."""

    html_text: str  # HTML-encoded text (for finding in serialised HTML)
    decoded_text: str  # Decoded text (from text_content)
    collapsed_text: str  # After whitespace collapsing
    char_start: int  # Starting char index in the stream
    char_end: int  # Ending char index (exclusive)


def walk_and_map(html: str) -> tuple[list[str], list[TextNodeInfo]]:
    """Walk DOM exactly like extract_text_from_html, returning chars + node map."""
    if not html:
        return [], []

    tree = LexborHTMLParser(html)
    body = tree.body
    root = body if body else tree.root
    if root is None:
        return [], []

    chars: list[str] = []
    text_nodes: list[TextNodeInfo] = []

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
                TextNodeInfo(
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


# --- Pass 2: Find text nodes in serialised HTML, insert markers ---


def find_text_node_offsets(html: str, text_nodes: list[TextNodeInfo]) -> list[int]:
    """Find the byte offset of each text node's raw_text in the serialised HTML.

    We search for each text node's raw_text sequentially, advancing our search
    position so we match in document order.
    """
    offsets = []
    search_from = 0

    for info in text_nodes:
        idx = html.find(info.html_text, search_from)
        if idx == -1:
            raise ValueError(
                f"Could not find text node '{info.html_text!r}' "
                f"in HTML starting from offset {search_from}"
            )
        offsets.append(idx)
        search_from = idx + len(info.html_text)

    return offsets


def insert_markers(
    html: str,
    text_nodes: list[TextNodeInfo],
    byte_offsets: list[int],
    highlights: list[dict[str, int]],
) -> str:
    """Insert marker strings at correct positions in serialised HTML.

    For each highlight, finds which text node(s) contain the start/end
    char positions, computes the byte offset within the serialised HTML,
    and inserts markers.
    """
    # Build list of (byte_offset_in_html, marker_string) insertions
    insertions: list[tuple[int, str]] = []

    for hl_idx, hl in enumerate(highlights):
        start_char = hl["start_char"]
        end_char = hl["end_char"]

        # Find start position
        for i, node_info in enumerate(text_nodes):
            if node_info.char_start <= start_char < node_info.char_end:
                # Character offset within this text node's collapsed text
                offset_in_collapsed = start_char - node_info.char_start
                # Map from collapsed offset to HTML-encoded offset
                raw_offset = _collapsed_to_html_offset(
                    node_info.html_text, node_info.decoded_text, offset_in_collapsed
                )
                byte_pos = byte_offsets[i] + raw_offset
                insertions.append((byte_pos, f"HLSTART{hl_idx}ENDHL"))
                break

        # Find end position
        for i, node_info in enumerate(text_nodes):
            if node_info.char_start < end_char <= node_info.char_end:
                offset_in_collapsed = end_char - node_info.char_start
                raw_offset = _collapsed_to_html_offset(
                    node_info.html_text, node_info.decoded_text, offset_in_collapsed
                )
                byte_pos = byte_offsets[i] + raw_offset
                insertions.append((byte_pos, f"HLEND{hl_idx}ENDHL"))
                break

    # Sort insertions by byte offset descending — insert from back to front
    # so earlier insertions don't shift later positions
    insertions.sort(key=lambda x: x[0], reverse=True)

    result = html
    for byte_pos, marker in insertions:
        result = result[:byte_pos] + marker + result[byte_pos:]

    return result


def _collapsed_to_html_offset(
    html_text: str, decoded_text: str, collapsed_offset: int
) -> int:
    """Map an offset in collapsed-decoded text to an offset in HTML-encoded text.

    Walks the decoded text (which has entities resolved, e.g. "&" not "&amp;")
    applying whitespace collapsing. Simultaneously advances through the HTML
    text to track the corresponding byte position.

    The HTML text may contain entities like &amp; &lt; &gt; &nbsp; which are
    multi-byte in HTML but single-char in decoded text.
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

        # Figure out how many HTML bytes this decoded char takes
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


# Common HTML entities and their decoded forms
_ENTITY_MAP = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&apos;": "'",
    "&nbsp;": "\u00a0",
}


def _html_char_length(html_text: str, html_pos: int, decoded_char: str) -> int:
    """Determine how many bytes in html_text correspond to one decoded char.

    If html_text[html_pos] starts an entity (e.g. &amp;), return the entity
    length. Otherwise return 1.
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


# --- Verification ---


def verify_round_trip(html: str, highlights: list[dict[str, int]]) -> None:
    """Prove that markers appear at correct positions."""
    chars, text_nodes = walk_and_map(html)
    byte_offsets = find_text_node_offsets(html, text_nodes)
    marked = insert_markers(html, text_nodes, byte_offsets, highlights)

    print(f"\nInput HTML: {html!r}")
    print(f"Chars: {''.join(chars)!r}")
    print(f"Marked: {marked!r}")

    for hl_idx, hl in enumerate(highlights):
        start = hl["start_char"]
        end = hl["end_char"]
        expected_text = "".join(chars[start:end])

        # Extract text between markers in the marked output
        start_marker = f"HLSTART{hl_idx}ENDHL"
        end_marker = f"HLEND{hl_idx}ENDHL"
        sm_pos = marked.find(start_marker)
        em_pos = marked.find(end_marker)
        if sm_pos == -1 or em_pos == -1:
            print(f"  FAIL: Markers not found for highlight {hl_idx}")
            return

        between = marked[sm_pos + len(start_marker) : em_pos]
        # Strip any HTML tags from between to get just text
        between_text = re.sub(r"<[^>]+>", "", between)
        # Decode HTML entities (e.g. &amp; → &)
        between_text = html_module.unescape(between_text)
        # Collapse whitespace same way
        between_text = _WHITESPACE_RUN.sub(" ", between_text)

        match = expected_text == between_text
        status = "PASS" if match else "FAIL"
        print(f"  Highlight {hl_idx} [{start}:{end}]: {status}")
        print(f"    Expected: {expected_text!r}")
        print(f"    Got:      {between_text!r}")


# --- Test Cases ---

if __name__ == "__main__":
    print("=" * 60)
    print("Test 1: Simple paragraph")
    verify_round_trip(
        "<p>Hello world</p>",
        [{"start_char": 0, "end_char": 5}],  # "Hello"
    )

    print("\n" + "=" * 60)
    print("Test 2: Multi-paragraph")
    verify_round_trip(
        "<p>Hello</p><p>World</p>",
        [
            {"start_char": 0, "end_char": 5},  # "Hello"
            {"start_char": 5, "end_char": 10},
        ],  # "World"
    )

    print("\n" + "=" * 60)
    print("Test 3: Formatted spans (bold, italic)")
    verify_round_trip(
        "<p>Hello <strong>bold</strong> and <em>italic</em> text</p>",
        [{"start_char": 6, "end_char": 10}],  # "bold"
    )

    print("\n" + "=" * 60)
    print("Test 4: Highlight crossing tag boundary")
    verify_round_trip(
        "<p>Hello <strong>bold</strong> world</p>",
        [{"start_char": 4, "end_char": 14}],  # "o bold wor"
    )

    print("\n" + "=" * 60)
    print("Test 5: Whitespace collapsing")
    verify_round_trip(
        "<p>Hello   world</p>",
        [{"start_char": 0, "end_char": 11}],  # "Hello world" (collapsed)
    )

    print("\n" + "=" * 60)
    print("Test 6: CJK characters")
    verify_round_trip(
        "<p>你好世界</p>",
        [{"start_char": 0, "end_char": 2}],  # "你好"
    )

    print("\n" + "=" * 60)
    print("Test 7: br tag")
    verify_round_trip(
        "<p>Line one<br>Line two</p>",
        [{"start_char": 0, "end_char": 8}],  # "Line one"
    )

    print("\n" + "=" * 60)
    print("Test 8: Whitespace between block tags (should be skipped)")
    verify_round_trip(
        "<div>\n  <p>Hello</p>\n  <p>World</p>\n</div>",
        [
            {"start_char": 0, "end_char": 5},  # "Hello"
            {"start_char": 5, "end_char": 10},
        ],  # "World"
    )

    print("\n" + "=" * 60)
    print("Test 9: Table content")
    verify_round_trip(
        "<table><tr><td>Cell 1</td><td>Cell 2</td></tr></table>",
        [{"start_char": 0, "end_char": 6}],  # "Cell 1"
    )

    print("\n" + "=" * 60)
    print("Test 10: Heading + paragraph")
    verify_round_trip(
        "<h1>Title</h1><p>Body text here</p>",
        [
            {"start_char": 0, "end_char": 5},  # "Title"
            {"start_char": 5, "end_char": 19},
        ],  # "Body text here"
    )

    print("\n" + "=" * 60)
    print("Test 11: HTML entities (amp, lt, gt)")
    verify_round_trip(
        "<p>A &amp; B</p>",
        [{"start_char": 0, "end_char": 5}],  # "A & B"
    )

    print("\n" + "=" * 60)
    print("Test 12: Multiple entities in one text node")
    verify_round_trip(
        "<p>x &lt; y &amp; y &gt; z</p>",
        [{"start_char": 2, "end_char": 3}],  # "<"
    )

    print("\n" + "=" * 60)
    print("Test 13: Entity at highlight boundary")
    verify_round_trip(
        "<p>Hello &amp; world</p>",
        [{"start_char": 6, "end_char": 13}],  # "& world"
    )
