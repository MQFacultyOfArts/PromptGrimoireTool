"""Wikimedia platform handler for HTML preprocessing.

Handles content copied from Wikipedia, Wikisource, and other Wikimedia sites.
These use the MediaWiki Vector skin with:
- mw-parser-output class for article body content
- vector-* classes for navigation chrome
- mw-editsection spans for [edit] links
- #toc / .toc for table of contents
- #catlinks for category links
- #footer / .mw-footer for footer chrome
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selectolax.lexbor import LexborHTMLParser

# Detection patterns — any one match is sufficient
_MW_PARSER_OUTPUT = re.compile(r'class="[^"]*mw-parser-output[^"]*"', re.IGNORECASE)
_MW_BODY_CONTENT = re.compile(r'class="[^"]*mw-body-content[^"]*"', re.IGNORECASE)
_VECTOR_HEADER = re.compile(r'class="[^"]*vector-header[^"]*"', re.IGNORECASE)

# CSS selectors for chrome elements to remove
_CHROME_SELECTORS = [
    # Navigation
    "nav",
    ".vector-main-menu-landmark",
    ".vector-main-menu",
    ".vector-main-menu-container",
    "#mw-navigation",
    ".mw-jump-link",
    # Sidebar
    ".vector-sidebar",
    "#mw-panel",
    ".mw-portlet",
    ".vector-pinnable-element",
    # Header
    ".vector-header-container",
    ".vector-header",
    ".mw-header",
    "#mw-head",
    ".vector-sticky-header",
    # Footer
    "#footer",
    ".mw-footer",
    # Edit links
    ".mw-editsection",
    # Table of contents
    "#toc",
    ".toc",
    ".vector-toc",
    # Categories
    "#catlinks",
    # Search
    "#p-search",
    "#searchInput",
    ".vector-search-box",
    # User links and tools
    ".vector-user-links",
    "#p-personal",
    ".vector-page-tools",
    "#p-cactions",
    # Language links
    "#p-lang",
    ".vector-dropdown",
    # Site notice
    "#siteNotice",
    # Aria/accessibility helpers that are chrome
    "#mw-aria-live-region",
    # Column layout wrappers
    ".vector-column-start",
    ".vector-column-end",
    # Site notice
    ".vector-sitenotice-container",
    # Page toolbar
    ".vector-page-toolbar",
    ".vector-page-toolbar-container",
    # Page title bar (redundant with article heading)
    ".vector-page-titlebar",
]


class WikimediaHandler:
    """Handler for Wikimedia/Wikipedia HTML content."""

    name: str = "wikimedia"

    def matches(self, html: str) -> bool:
        """Return True if HTML is from a Wikimedia site.

        Detection is based on MediaWiki-specific class patterns:
        - mw-parser-output (article body wrapper)
        - mw-body-content (content area)
        - vector-header (Vector skin header)
        """
        return bool(
            _MW_PARSER_OUTPUT.search(html)
            or _MW_BODY_CONTENT.search(html)
            or _VECTOR_HEADER.search(html)
        )

    def preprocess(self, tree: LexborHTMLParser) -> None:
        """Remove Wikimedia chrome, preserving article content.

        Strips navigation, sidebar, header, footer, edit links,
        table of contents, categories, and other UI chrome.

        Args:
            tree: Parsed HTML tree to modify in-place.
        """
        for selector in _CHROME_SELECTORS:
            for node in tree.css(selector):
                node.decompose()

    def get_turn_markers(self) -> dict[str, str]:
        """Return empty markers — Wikimedia content has no speaker turns.

        Unlike chatbot platforms, Wikimedia content is article text
        without user/assistant turn structure.
        """
        return {}


# Module-level handler instance for autodiscovery
handler = WikimediaHandler()
