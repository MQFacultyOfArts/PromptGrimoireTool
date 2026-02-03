"""OpenAI platform handler for HTML preprocessing.

Handles ChatGPT exports, which have:
- agent-turn class for platform detection
- data-message-author-role attribute for turn boundaries
- sr-only elements containing native labels ("You said:", "ChatGPT")
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selectolax.lexbor import LexborHTMLParser

# Platform detection pattern
_DETECTION_PATTERN = re.compile(r'class="[^"]*agent-turn[^"]*"', re.IGNORECASE)

# CSS selectors for elements to remove
_CHROME_SELECTORS = [
    ".sr-only",  # Screen-reader-only labels ("You said:", "ChatGPT")
]


class OpenAIHandler:
    """Handler for OpenAI/ChatGPT HTML exports."""

    name: str = "openai"

    def matches(self, html: str) -> bool:
        """Return True if HTML is from OpenAI/ChatGPT.

        Detection is based on the presence of 'agent-turn' class,
        which is unique to ChatGPT exports.
        """
        return bool(_DETECTION_PATTERN.search(html))

    def preprocess(self, tree: LexborHTMLParser) -> None:
        """Remove chrome and native labels from OpenAI HTML.

        Removes:
        - sr-only elements (contain "You said:" and "ChatGPT" labels)

        Args:
            tree: Parsed HTML tree to modify in-place.
        """
        for selector in _CHROME_SELECTORS:
            for node in tree.css(selector):
                node.decompose()

    def get_turn_markers(self) -> dict[str, str]:
        """Return regex patterns for OpenAI turn boundaries.

        OpenAI uses data-message-author-role attribute to identify
        user vs assistant turns.

        Returns:
            Dict with 'user' and 'assistant' regex patterns.
        """
        return {
            "user": r'(<[^>]*data-message-author-role="user"[^>]*>)',
            "assistant": r'(<[^>]*data-message-author-role="assistant"[^>]*>)',
        }


# Module-level handler instance for autodiscovery
handler = OpenAIHandler()
