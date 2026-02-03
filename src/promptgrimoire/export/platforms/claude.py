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

        Claude uses data-testid for user messages and a flexible pattern for
        assistant responses based on the font-claude-response class.

        Design note on assistant pattern:
        We use a flexible class pattern `class="[^"]*font-claude-response[^"]*"`
        rather than the specific `leading-[1.65rem]` value. This is because:
        1. The leading (line height) value may change across Claude UI updates
        2. The font-claude-response class is Claude's stable semantic marker
        3. A flexible pattern is more resilient to CSS refactoring

        Returns:
            Dict with 'user' and 'assistant' regex patterns.
        """
        return {
            "user": r'(<[^>]*data-testid="user-message"[^>]*>)',
            "assistant": r'(<[^>]*class="[^"]*font-claude-response[^"]*"[^>]*>)',
        }


# Module-level handler instance for autodiscovery
handler = ClaudeHandler()
