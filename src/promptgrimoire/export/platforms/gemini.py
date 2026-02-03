"""Gemini platform handler for HTML preprocessing.

Handles Google Gemini web exports, which have:
- <user-query> custom elements for user turns
- <model-response> custom elements for assistant turns
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selectolax.lexbor import LexborHTMLParser

# Platform detection pattern
_DETECTION_PATTERN = re.compile(r"<user-query\b", re.IGNORECASE)


class GeminiHandler:
    """Handler for Google Gemini HTML exports."""

    name: str = "gemini"

    def matches(self, html: str) -> bool:
        """Return True if HTML is from Google Gemini.

        Detection is based on the presence of <user-query> custom element,
        which is unique to Gemini web exports.
        """
        return bool(_DETECTION_PATTERN.search(html))

    def preprocess(self, tree: LexborHTMLParser) -> None:
        """Preprocess Gemini HTML.

        Gemini uses semantic custom elements, so minimal preprocessing needed.
        Chrome removal handled by common patterns.

        Args:
            tree: Parsed HTML tree to modify in-place.
        """
        # Gemini's custom elements are clean - no native labels to strip
        pass

    def get_turn_markers(self) -> dict[str, str]:
        """Return regex patterns for Gemini turn boundaries.

        Gemini uses custom HTML elements for turn boundaries.

        Returns:
            Dict with 'user' and 'assistant' regex patterns.
        """
        return {
            "user": r"(<user-query\b[^>]*>)",
            "assistant": r"(<model-response\b[^>]*>)",
        }


# Module-level handler instance for autodiscovery
handler = GeminiHandler()
