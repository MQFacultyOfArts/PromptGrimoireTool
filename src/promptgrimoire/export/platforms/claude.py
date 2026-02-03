"""Claude platform handler for HTML preprocessing.

Handles Claude exports, which have:
- font-user-message class for platform detection
- data-testid="user-message" for user turns
- font-claude-response class for assistant turns
- Thinking sections that need data-thinking attributes
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selectolax.lexbor import LexborHTMLParser

# Platform detection pattern
_DETECTION_PATTERN = re.compile(r'class="[^"]*font-user-message[^"]*"', re.IGNORECASE)

# Thinking section patterns
_THINKING_HEADER_TEXT = "Thought process"


class ClaudeHandler:
    """Handler for Claude HTML exports."""

    name: str = "claude"

    def matches(self, html: str) -> bool:
        """Return True if HTML is from Claude.

        Detection is based on the presence of 'font-user-message' class,
        which is unique to Claude exports.
        """
        return bool(_DETECTION_PATTERN.search(html))

    def preprocess(self, tree: LexborHTMLParser) -> None:
        """Remove chrome and mark thinking sections in Claude HTML.

        Marks thinking sections with data-thinking attributes for special
        styling in PDF export.

        Args:
            tree: Parsed HTML tree to modify in-place.
        """
        # Mark thinking headers
        for node in tree.css(".text-sm.font-semibold"):
            if node.text() and _THINKING_HEADER_TEXT in node.text():
                node.attrs["data-thinking"] = "header"

        # Mark thinking summaries (text-sm divs inside thinking sections)
        for node in tree.css(".thinking-summary .text-sm"):
            if "font-semibold" not in (node.attributes.get("class") or ""):
                node.attrs["data-thinking"] = "summary"

    def get_turn_markers(self) -> dict[str, str]:
        """Return regex patterns for Claude turn boundaries.

        Claude uses data-testid for user messages and specific CSS classes
        for assistant responses.

        Returns:
            Dict with 'user' and 'assistant' regex patterns.
        """
        return {
            "user": r'(<[^>]*data-testid="user-message"[^>]*>)',
            "assistant": (
                r'(<[^>]*class="font-claude-response relative '
                r'leading-\[1\.65rem\][^"]*"[^>]*>)'
            ),
        }


# Module-level handler instance for autodiscovery
handler = ClaudeHandler()
