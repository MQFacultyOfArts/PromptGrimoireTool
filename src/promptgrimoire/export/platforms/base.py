"""Shared utilities for platform handlers.

This module provides common functions used across multiple platform handlers
and the entry point.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from selectolax.lexbor import LexborHTMLParser

logger = structlog.get_logger()

# Common chrome patterns - apply to all platforms
_CHROME_CLASS_PATTERNS = [
    "avatar",
    "profile-pic",
    "profile-picture",
    "tabler-icon",
    "icon-copy",
    "icon-share",
    "copy-button",
    "share-button",
    "logo",
    "brand",
    "closing",
    "side-element",
    "year-options",
    "text-xs",
]

_CHROME_ID_PATTERNS = [
    "page-header",
    "page-search",
    "page-logo",
    "page-side",
    "page-tertiary",
    "panels",
    "panel-",
    "ribbon",
]

# Pattern for thinking time indicators
_THINKING_TIME_PATTERN = re.compile(r"^\d+s$")


def _remove_chrome_by_patterns(tree: LexborHTMLParser) -> None:
    """Remove elements matching chrome class and ID patterns."""
    for pattern in _CHROME_CLASS_PATTERNS:
        for node in tree.css(f'[class*="{pattern}"]'):
            node.decompose()

    for pattern in _CHROME_ID_PATTERNS:
        for node in tree.css(f'[id^="{pattern}"]'):
            node.decompose()


def _remove_chrome_images(tree: LexborHTMLParser) -> None:
    """Remove small icons and remote images."""
    for img in tree.css("img"):
        attrs = img.attributes
        width = attrs.get("width", "")
        height = attrs.get("height", "")
        try:
            if (width and int(width) < 32) or (height and int(height) < 32):
                img.decompose()
                continue
        except ValueError:
            logger.warning(
                "img_dimension_parse_failed",
                operation="remove_icons_and_remote_images",
                width=width,
                height=height,
            )

        # Remove remote images (including blob: URLs which can't be resolved)
        src = attrs.get("src") or ""
        if src.startswith(("http://", "https://", "blob:")):
            img.decompose()


def _strip_event_attributes(tree: LexborHTMLParser) -> None:
    """Strip ``on*`` event handler attributes from all elements (#117)."""
    for node in tree.css("*"):
        attrs = node.attributes
        for attr in list(attrs):
            if attr and attr.startswith("on"):
                del node.attrs[attr]


def _remove_chrome_elements(tree: LexborHTMLParser) -> None:
    """Remove SVGs, hidden elements, action buttons, and KaTeX visual rendering."""
    # Remove SVG elements
    for svg in tree.css("svg"):
        svg.decompose()

    # Remove hidden elements
    for node in tree.css('[style*="display: none"], [style*="display:none"]'):
        node.decompose()
    for node in tree.css('[style*="visibility: hidden"], [style*="visibility:hidden"]'):
        node.decompose()

    # Remove all buttons (#117 — interactive elements block text selection)
    for button in tree.css("button"):
        button.decompose()

    # Unwrap links — keep visible text, drop href (#117)
    for a in tree.css("a"):
        a.unwrap()

    _strip_event_attributes(tree)

    # Remove KaTeX visual rendering (keep MathML for Pandoc)
    for node in tree.css(".katex-html"):
        node.decompose()

    # Remove thinking time indicators (e.g., "18s", "21s" from Claude)
    for node in tree.css(".text-xs, .text-sm"):
        text = (node.text() or "").strip()
        if _THINKING_TIME_PATTERN.match(text):
            node.decompose()


def remove_common_chrome(tree: LexborHTMLParser) -> None:
    """Remove UI chrome elements common to all platforms.

    Removes:
    - Elements with chrome-related CSS classes
    - Elements with chrome-related IDs
    - Small images (< 32px, likely icons)
    - Remote images (http/https URLs)
    - SVG elements
    - Hidden elements (display: none, visibility: hidden)
    - Action buttons (copy, share, download)

    Args:
        tree: Parsed HTML tree to modify in-place.
    """
    _remove_chrome_by_patterns(tree)
    _remove_chrome_images(tree)
    _remove_chrome_elements(tree)


def collapse_wrapper_divs(tree: LexborHTMLParser) -> None:
    """Unwrap bare ``<div>`` elements that serve only as nesting wrappers.

    Paste handlers (especially ChatCraft) preserve the original DOM
    structure, producing deeply nested ``<div>`` chains with no semantic
    value.  This collapses them so Pandoc sees a flat structure.

    A div is unwrapped when it has **no** ``id``, ``class``, or ``data-*``
    attributes.  Divs with ``style`` only are also unwrapped — inline
    styles are irrelevant to the LaTeX pipeline.

    Must run **before** Pandoc conversion; safe to call multiple times.
    """
    for node in tree.css("div"):
        attrs = node.attributes
        has_id = "id" in attrs
        has_class = "class" in attrs
        has_data = any(k.startswith("data-") for k in attrs)
        if has_id or has_class or has_data:
            continue
        node.unwrap()


def remove_empty_containers(tree: LexborHTMLParser) -> None:
    """Remove empty container elements left after chrome removal.

    Makes multiple passes until no more empty containers are found.
    Note: Elements with data-* attributes are NOT considered empty
    (handled by selectolax's text() which returns None for such elements).

    Args:
        tree: Parsed HTML tree to modify in-place.
    """
    # Tags that should be removed when empty
    # Expanded from original {div, span} to include semantic containers
    # that may be left empty after chrome removal
    container_tags = {"div", "span", "p", "section", "article", "aside"}

    while True:
        removed = False
        for tag in container_tags:
            for node in tree.css(tag):
                # Check if truly empty (no text, no children with content)
                text = (node.text() or "").strip()
                if not text and not node.css("img, svg, video, audio, iframe"):
                    node.decompose()
                    removed = True
        if not removed:
            break
