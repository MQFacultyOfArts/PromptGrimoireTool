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
        - ms-file-chunk elements (file metadata, paste dates, token counts)
        - ms-thought-chunk elements (thought section accordion chrome)
        - ms-toolbar elements (title bar, global token count)
        - .token-count elements (per-attachment token counts)

        Args:
            tree: Parsed HTML tree to modify in-place.
        """
        # Remove virtual-scroll spacer divs (empty divs with fixed
        # pixel heights that create massive whitespace in paste HTML)
        for container in tree.css(".virtual-scroll-container"):
            child = container.child
            while child:
                nxt = child.next
                if child.tag != "-text" and not child.text(strip=True):
                    cls = child.attributes.get("class") or ""
                    if not cls:
                        child.decompose()
                child = nxt

        for selector in [
            "ms-chat-turn-options",
            ".author-label",
            "ms-file-chunk",
            "ms-thought-chunk",
            "ms-toolbar",
            ".token-count",
        ]:
            for node in tree.css(selector):
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
