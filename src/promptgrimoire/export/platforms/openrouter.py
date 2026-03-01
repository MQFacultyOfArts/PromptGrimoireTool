"""OpenRouter platform handler for HTML preprocessing.

Handles OpenRouter Playground exports, which have:
- data-testid="playground-container" for platform detection
- data-testid="user-message" / "assistant-message" for turn boundaries
- data-testid="playground-composer" for the input area (removed)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selectolax.lexbor import LexborHTMLParser

# Platform detection pattern
_DETECTION_PATTERN = re.compile(r'data-testid="playground-container"', re.IGNORECASE)


class OpenRouterHandler:
    """Handler for OpenRouter Playground HTML exports."""

    name: str = "openrouter"

    def matches(self, html: str) -> bool:
        """Return True if HTML is from OpenRouter Playground.

        Detection is based on the presence of data-testid="playground-container",
        which is unique to OpenRouter Playground exports.
        """
        return bool(_DETECTION_PATTERN.search(html))

    def preprocess(self, tree: LexborHTMLParser) -> None:
        """Remove chrome and metadata from OpenRouter HTML.

        Removes:
        - playground-composer element (the input/composer area)
        - Metadata rows in assistant messages (timestamp, model name,
          reasoning badge) — model name is folded into data-speaker-name

        Args:
            tree: Parsed HTML tree to modify in-place.
        """
        for node in tree.css('[data-testid="playground-composer"]'):
            node.decompose()

        # Extract model name into data-speaker-name, then strip
        # the metadata row (timestamp, model name, reasoning badge)
        for msg in tree.css('[data-testid="assistant-message"]'):
            # Metadata row has classes: text-xs text-gray-500
            for meta in msg.css(".text-xs.text-gray-500"):
                model_span = meta.css_first(".font-medium")
                if model_span:
                    model_name = model_span.text(strip=True)
                    if model_name:
                        msg.attrs["data-speaker-name"] = model_name
                meta.decompose()

    def get_turn_markers(self) -> dict[str, str]:
        """Return regex patterns for OpenRouter turn boundaries.

        OpenRouter uses data-testid attributes to identify
        user vs assistant turns.

        Returns:
            Dict with 'user' and 'assistant' regex patterns.
        """
        return {
            "user": r'(<[^>]*data-testid="user-message"[^>]*>)',
            "assistant": r'(<[^>]*data-testid="assistant-message"[^>]*>)',
        }


# Module-level handler instance for autodiscovery
handler = OpenRouterHandler()
