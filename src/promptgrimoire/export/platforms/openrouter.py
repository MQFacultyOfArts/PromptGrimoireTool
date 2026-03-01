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
        - Thinking/reasoning content blocks

        Structural approach: actual content lives in a ``.prose`` div
        inside the chat bubble.  Everything else (metadata row, thinking
        section) is a sibling and gets removed.

        Args:
            tree: Parsed HTML tree to modify in-place.
        """
        for node in tree.css('[data-testid="playground-composer"]'):
            node.decompose()

        for msg in tree.css('[data-testid="assistant-message"]'):
            # Extract model name before stripping
            model_span = msg.css_first(".font-medium")
            if model_span:
                model_name = model_span.text(strip=True)
                if model_name:
                    msg.attrs["data-speaker-name"] = model_name

            # Find prose content div; strip all siblings
            prose = msg.css_first(".prose")
            if not prose or not prose.parent:
                continue
            bubble = prose.parent
            child = bubble.child
            while child:
                next_sib = child.next
                if child != prose and child.tag != "-text":
                    child.decompose()
                child = next_sib

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
