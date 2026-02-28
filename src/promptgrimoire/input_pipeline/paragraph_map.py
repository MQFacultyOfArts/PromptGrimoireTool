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


def _collapse_text_node(node: Any) -> str | None:
    """Return collapsed text for a text node, or ``None`` if it should be skipped.

    Applies the same whitespace rules as ``extract_text_from_html()``:
    skip empty text, skip whitespace-only text inside block elements,
    and collapse whitespace runs to a single space.
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
    collapsed = _collapse_text_node(node)
    if collapsed is None:
        return

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


@dataclass
class _InjectState:
    """Mutable state for the attribute-injection walk."""

    paragraph_map: dict[int, int]
    char_offset: int = 0
    consecutive_br: int = 0
    current_block_node: Any = None
    current_block_tag: str | None = None
    # br-br pseudo-paragraphs need string-level wrapping after
    # serialisation because selectolax escapes HTML in replace_with
    # on text nodes.  Collect (text_content, para_num) tuples here.
    br_br_wraps: list[tuple[str, int]] = field(default_factory=list)


def _inject_handle_text(node: Any, state: _InjectState) -> None:
    """Process a text node during injection, mirroring _handle_text_node."""
    collapsed = _collapse_text_node(node)
    if collapsed is None:
        return

    # br-br pseudo-paragraph: record for post-serialisation wrapping.
    # selectolax escapes HTML when replacing text nodes, so we must
    # do string-level insertion after the DOM is serialised.
    if state.consecutive_br >= 2 and state.char_offset in state.paragraph_map:
        para_num = state.paragraph_map[state.char_offset]
        raw_text = node.html or node.text_content
        state.br_br_wraps.append((raw_text, para_num))

    state.consecutive_br = 0
    state.char_offset += len(collapsed)


def _inject_handle_para(node: Any, tag: str, state: _InjectState) -> None:
    """Record the current block node for a _PARA_TAGS element during injection."""
    state.current_block_tag = tag
    state.current_block_node = node
    state.consecutive_br = 0

    # Set data-para on block elements whose char offset is in the map.
    if state.char_offset in state.paragraph_map:
        para_num = state.paragraph_map[state.char_offset]
        node.attrs["data-para"] = str(para_num)


def _inject_walk(node: Any, state: _InjectState) -> None:
    """Walk a DOM node for attribute injection.

    Follows the same traversal logic as ``_walk`` but mutates the DOM
    by setting ``data-para`` attributes via ``_inject_handle_para``.
    Child iteration pre-captures ``next_child`` before recursion because
    DOM mutation can invalidate sibling pointers in some selectolax builds.
    """
    tag = node.tag

    if tag == "-text":
        _inject_handle_text(node, state)
        return

    if tag in _STRIP_TAGS:
        return

    if tag == "br":
        state.consecutive_br += 1
        state.char_offset += 1
        return

    is_para_tag = tag in _PARA_TAGS
    prev_block_tag = state.current_block_tag
    prev_block_node = state.current_block_node

    if is_para_tag:
        _inject_handle_para(node, tag, state)

    # Pre-capture next_child before recursion because _inject_handle_para
    # mutates node attributes, which can invalidate child.next in some
    # selectolax builds.  _walk does not mutate the DOM so it reads
    # child.next after recursion instead.
    child = node.child
    while child is not None:
        next_child = child.next
        _inject_walk(child, state)
        child = next_child

    if is_para_tag:
        state.current_block_tag = prev_block_tag
        state.current_block_node = prev_block_node


def _apply_br_br_wraps(html: str, wraps: list[tuple[str, int]]) -> str:
    """Wrap br-br pseudo-paragraph text in ``<span data-para="N">`` tags.

    Searches for each text string in the serialised HTML and wraps it
    with a span.  Processes in reverse document order to preserve
    string offsets.
    """
    if not wraps:
        return html

    # Find positions (search sequentially to handle duplicates)
    insertions: list[tuple[int, int, int]] = []  # (start, end, para_num)
    search_from = 0
    for raw_text, para_num in wraps:
        idx = html.find(raw_text, search_from)
        if idx != -1:
            insertions.append((idx, idx + len(raw_text), para_num))
            search_from = idx + len(raw_text)

    # Apply in reverse order to preserve offsets
    for start, end, para_num in reversed(insertions):
        original = html[start:end]
        html = (
            html[:start]
            + f'<span data-para="{para_num}">{original}</span>'
            + html[end:]
        )

    return html


def inject_paragraph_attributes(html: str, paragraph_map: dict[str, int]) -> str:
    """Add ``data-para`` attributes to block elements for margin display.

    Walks the DOM with the same traversal as ``build_paragraph_map()``
    (identical char-offset accounting).  At each block element whose
    char offset is a key in *paragraph_map*, adds
    ``data-para="N"`` to that element.

    For ``<br><br>+`` pseudo-paragraphs (text following two or more
    ``<br>`` elements within a block), wraps the text in a
    ``<span data-para="N">`` since there is no enclosing block element.
    This uses string-level insertion after DOM serialisation because
    selectolax escapes HTML when replacing text nodes.

    If *paragraph_map* is empty, returns *html* unchanged without
    parsing overhead.

    Args:
        html: Document HTML (clean, no char-span wrappers).
        paragraph_map: Mapping from char offset (as string) to
            paragraph number, as returned by
            ``build_paragraph_map_for_json()``.

    Returns:
        Modified HTML with ``data-para`` attributes injected.
    """
    if not paragraph_map or not html:
        return html

    # Convert string keys to int for offset comparison.
    int_map: dict[int, int] = {int(k): v for k, v in paragraph_map.items()}

    tree = LexborHTMLParser(html)
    body = tree.body
    root = body if body else tree.root
    if root is None:
        return html

    state = _InjectState(paragraph_map=int_map)

    child = root.child
    while child is not None:
        next_child = child.next
        _inject_walk(child, state)
        child = next_child

    # selectolax serialises the full document including <html><head><body>.
    # Extract just the body inner content to match the input format.
    body_node = tree.body
    result = body_node.inner_html if body_node is not None else tree.html
    if result is None:
        return html

    # Apply br-br pseudo-paragraph wraps via string insertion.
    result = _apply_br_br_wraps(result, state.br_br_wraps)

    return result


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
