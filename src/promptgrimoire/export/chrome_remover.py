"""UI chrome removal for chatbot HTML exports.

Removes non-content elements (avatars, icons, buttons, branding) that
don't belong in PDF exports.

This is a pre-processor that runs before Pandoc conversion.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

# Pattern for thinking time indicators (e.g., "18s", "21s")
_THINKING_TIME_PATTERN = re.compile(r"^\d+s$")

# Class patterns that indicate UI chrome (case-insensitive substring match)
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
    "closing",  # AustLII footer
    "side-element",  # AustLII sidebar elements
    "year-options",  # AustLII year filter dropdown
    "text-xs",  # Small metadata text (timestamps, etc.)
]

# ID patterns that indicate navigation/header chrome (case-insensitive prefix match)
# These catch AustLII-style legal database navigation
_CHROME_ID_PATTERNS = [
    "page-header",
    "page-search",
    "page-logo",
    "page-side",  # AustLII sidebar (Print, Download, Cited By, etc.)
    "page-tertiary",  # AustLII footer navigation
    "panels",
    "panel-",  # panel-type, panel-jurisdiction, panel-year, etc.
    "ribbon",  # AustLII breadcrumb navigation
]

# Maximum dimension (px) for images to be considered icons and removed
_ICON_MAX_SIZE = 32


def _has_chrome_class(element: Tag) -> bool:
    """Check if element has a class indicating UI chrome."""
    classes = element.get("class")
    if classes is None:
        return False
    if isinstance(classes, str):
        classes = [classes]

    class_str = " ".join(str(c) for c in classes).lower()
    return any(pattern in class_str for pattern in _CHROME_CLASS_PATTERNS)


def _has_chrome_id(element: Tag) -> bool:
    """Check if element has an ID indicating navigation/header chrome."""
    elem_id = element.get("id")
    if not elem_id:
        return False

    id_lower = str(elem_id).lower()
    return any(id_lower.startswith(pattern) for pattern in _CHROME_ID_PATTERNS)


def _is_small_image(element: Tag) -> bool:
    """Check if image element is small enough to be an icon."""
    if element.name != "img":
        return False

    width = element.get("width")
    height = element.get("height")

    # Also check inline style for dimensions
    style = str(element.get("style") or "")

    # Try to parse dimensions from attributes
    try:
        if width is not None:
            w = int(re.sub(r"[^\d]", "", str(width)) or "0")
            if 0 < w < _ICON_MAX_SIZE:
                return True
        if height is not None:
            h = int(re.sub(r"[^\d]", "", str(height)) or "0")
            if 0 < h < _ICON_MAX_SIZE:
                return True
    except (ValueError, TypeError):
        pass

    # Check inline style for small dimensions (e.g., "width: 16px")
    style_width = re.search(r"width:\s*(\d+)px", style)
    style_height = re.search(r"height:\s*(\d+)px", style)
    if style_width and int(style_width.group(1)) < _ICON_MAX_SIZE:
        return True

    return bool(style_height and int(style_height.group(1)) < _ICON_MAX_SIZE)


def _is_remote_image(element: Tag) -> bool:
    """Check if image has a remote URL that can't be included in LaTeX."""
    if element.name not in ("img", "image"):
        return False

    src = element.get("src") or element.get("href")
    return bool(src and str(src).startswith(("http://", "https://")))


def _is_svg_image(element: Tag) -> bool:
    """Check if element is an SVG that would cause LaTeX issues."""
    # SVG elements
    if element.name == "svg":
        return True

    # Images with .svg extension
    if element.name == "img":
        src = str(element.get("src") or "")
        if src.endswith(".svg"):
            return True

    return False


def _is_hidden(element: Tag) -> bool:
    """Check if element has display:none or visibility:hidden."""
    style = element.get("style")
    if not style:
        return False

    style_str = str(style).lower()
    return "display: none" in style_str or "display:none" in style_str


def _is_thinking_time(element: Tag) -> bool:
    """Check if element is a thinking time indicator (e.g., "18s")."""
    if element.name not in ("span", "p"):
        return False

    text = element.get_text(strip=True)
    return bool(_THINKING_TIME_PATTERN.match(text))


def _should_remove(element: Tag) -> bool:
    """Determine if an element should be removed as UI chrome."""
    # Check for various chrome patterns
    if (
        _has_chrome_class(element)
        or _has_chrome_id(element)
        or _is_small_image(element)
        or _is_remote_image(element)
        or _is_svg_image(element)
        or _is_hidden(element)
        or _is_thinking_time(element)
    ):
        return True

    # Check for button elements with chrome-related text
    if element.name == "button":
        text = element.get_text().lower()
        if any(word in text for word in ["copy", "share", "download"]):
            return True

    return False


def _is_empty_container(element: Tag) -> bool:
    """Check if element is an empty container (no text content).

    Preserves elements with data-* attributes used for styling/markers.
    """
    # Only check div and span containers
    if element.name not in ("div", "span"):
        return False

    # Preserve elements with data attributes (used for speaker/thinking markers)
    attrs = element.attrs or {}
    if any(k.startswith("data-") for k in attrs):
        return False

    # Get text content (strip whitespace)
    text = element.get_text(strip=True)
    return not text


def remove_ui_chrome(html: str) -> str:
    """Remove UI chrome elements from HTML.

    Removes:
    - Avatar images (class contains 'avatar', 'profile-pic')
    - Icon elements (tabler-icon-*, icon-*)
    - Action buttons (copy-button, share-button)
    - Small images (< 32px in either dimension)
    - Hidden elements (display: none)
    - Empty containers left after removal

    Args:
        html: Raw HTML content.

    Returns:
        HTML with UI chrome elements removed.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Find and remove chrome elements
    # We need to collect them first, then remove (can't modify during iteration)
    elements_to_remove = []

    for element in soup.find_all(True):  # Find all tags
        if _should_remove(element):
            elements_to_remove.append(element)

    for element in elements_to_remove:
        element.decompose()

    # Second pass: remove empty containers left behind
    # Repeat until no more empty containers found (handles nested empties)
    while True:
        empty_elements = [el for el in soup.find_all(True) if _is_empty_container(el)]
        if not empty_elements:
            break
        for element in empty_elements:
            element.decompose()

    return str(soup)
