"""HTML sanitisation: strip heavy attributes and remove empty elements.

Pure functions that clean up pasted/converted HTML for annotation storage.
Removes excessive inline styles, data-* attributes, class attributes, and
empty paragraphs/divs that create unwanted whitespace.
"""

from __future__ import annotations

import re
from typing import Any

from selectolax.lexbor import LexborHTMLParser

_KEEP_STYLE_PROPS = frozenset(
    {
        "margin-left",
        "margin-right",
        "text-indent",
        "padding-left",
        "padding-right",
    }
)


def _filter_style(style_val: str) -> str | None:
    """Return filtered style string keeping only structural properties.

    Returns ``None`` if no structural properties survive.
    """
    kept: list[str] = []
    for prop in _KEEP_STYLE_PROPS:
        pattern = rf"{re.escape(prop)}\s*:\s*([^;]+)"
        match = re.search(pattern, style_val, re.IGNORECASE)
        if match:
            kept.append(f"{prop}:{match.group(1).strip()}")
    return ";".join(kept) if kept else None


def _should_remove_attr(attr_name: str) -> bool:
    """Return whether an attribute should be stripped."""
    if attr_name == "class":
        return True
    return attr_name.startswith("data-") and attr_name != "data-speaker"


def _strip_node_attrs(node: Any) -> None:
    """Strip heavy attributes from a single DOM node."""
    attrs = node.attributes
    attrs_to_remove: list[str] = []

    for attr_name in attrs:
        if attr_name == "style":
            filtered = _filter_style(attrs.get("style") or "")
            if filtered:
                node.attrs["style"] = filtered
            else:
                attrs_to_remove.append("style")
        elif _should_remove_attr(attr_name):
            attrs_to_remove.append(attr_name)

    for attr_name in attrs_to_remove:
        del node.attrs[attr_name]


def strip_heavy_attributes(html: str) -> str:
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

    tree = LexborHTMLParser(html)

    for node in tree.css("*"):
        _strip_node_attrs(node)

    return tree.html or html


def _is_empty_element(node: Any) -> bool:
    """Return whether *node* is empty (whitespace-only, <br>-only, or no children).

    Speaker marker divs (``data-speaker``) are never considered empty.
    """
    if node.attributes.get("data-speaker"):
        return False
    raw = node.text() or ""
    # Use ASCII-only strip: Python's str.strip() treats U+00A0 (nbsp) as
    # whitespace, but nbsp is semantically significant — ChatGPT exports
    # use <span>&nbsp;</span> for inter-word spacing around bold/italic (#273).
    text = raw.strip(" \t\n\r\f\v")
    if text:
        return False
    return all(child.tag == "br" for child in node.iter())


def _is_sole_content_element(node: Any, tree: LexborHTMLParser) -> bool:
    """Return whether *node* is the only content element inside ``<body>``."""
    body = tree.css_first("body")
    if not body:
        return False
    return all(n == node for n in body.css("p, div, span"))


def remove_empty_elements(html: str) -> str:
    """Remove empty paragraphs and divs that only contain whitespace or <br> tags.

    These create excessive vertical whitespace in pasted content, especially
    from office applications that use empty paragraphs for spacing.

    Note: Preserves at least one content element to avoid returning empty body.
    """
    if not html:
        return html

    tree = LexborHTMLParser(html)

    changed = True
    while changed:
        changed = False
        for node in tree.css("p, div, span"):
            if not _is_empty_element(node):
                continue
            if _is_sole_content_element(node, tree):
                continue
            node.decompose()
            changed = True

    return tree.html or html
