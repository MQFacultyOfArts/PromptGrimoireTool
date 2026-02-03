"""AI Studio platform handler for HTML preprocessing.

Handles Google AI Studio exports, which have:
- <ms-chat-turn> custom elements
- data-turn-role attribute for turn identification ("User" or "Model")
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selectolax.lexbor import LexborHTMLParser

# Platform detection pattern
_DETECTION_PATTERN = re.compile(r"<ms-chat-turn\b", re.IGNORECASE)


class AIStudioHandler:
    """Handler for Google AI Studio HTML exports."""

    name: str = "aistudio"

    def matches(self, html: str) -> bool:
        """Return True if HTML is from Google AI Studio.

        Detection is based on the presence of <ms-chat-turn> custom element,
        which is unique to AI Studio exports.
        """
        return bool(_DETECTION_PATTERN.search(html))

    def preprocess(self, tree: LexborHTMLParser) -> None:
        """Preprocess AI Studio HTML.

        Removes:
        - .author-label elements (native speaker labels like "User", "Model")

        Args:
            tree: Parsed HTML tree to modify in-place.
        """
        # Remove native author labels
        for node in tree.css(".author-label"):
            node.decompose()

    def get_turn_markers(self) -> dict[str, str]:
        """Return regex patterns for AI Studio turn boundaries.

        AI Studio uses data-turn-role attribute with values "User" and "Model".

        Returns:
            Dict with 'user' and 'assistant' regex patterns.
        """
        return {
            "user": r'(<[^>]*data-turn-role="User"[^>]*>)',
            "assistant": r'(<[^>]*data-turn-role="Model"[^>]*>)',
        }


# Module-level handler instance for autodiscovery
handler = AIStudioHandler()
