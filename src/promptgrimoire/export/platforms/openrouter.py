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
    from selectolax.lexbor import LexborHTMLParser, LexborNode

# Platform detection pattern
_DETECTION_PATTERN = re.compile(r'data-testid="playground-container"', re.IGNORECASE)


def _element_children(node: LexborNode) -> list[LexborNode]:
    """Collect direct element children, skipping text nodes."""
    result: list[LexborNode] = []
    child = node.child
    while child:
        if child.tag != "-text":
            result.append(child)
        child = child.next
    return result


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

        OpenRouter assistant-message structure (as of 2026-03)::

            [data-testid="assistant-message"]
              ├── child 0: timestamp (text-muted-foreground)
              ├── child 1: model link (<a href="/openrouter.ai/...">)
              ├── child 2: content wrapper
              │   ├── thinking div (border + rounded classes)
              │   └── response div (last child)
              └── child 3: actions (empty)

        We extract the model name from the link URL, strip everything
        except child 2's last child (the actual response).

        Args:
            tree: Parsed HTML tree to modify in-place.
        """
        for node in tree.css('[data-testid="playground-composer"]'):
            node.decompose()

        for msg in tree.css('[data-testid="assistant-message"]'):
            self._strip_assistant_chrome(msg)

    def _strip_assistant_chrome(self, msg: LexborNode) -> None:
        """Extract model name and strip metadata from one assistant message."""
        # Extract model name from link URL
        model_link = msg.css_first('a[href*="openrouter.ai"]')
        if model_link:
            href = model_link.attributes.get("href") or ""
            name = href.rstrip("/").rsplit("/", 1)[-1]
            if name:
                msg.attrs["data-speaker-name"] = name

        # Remove all direct children except child 2 (content wrapper)
        children = _element_children(msg)
        for i, ch in enumerate(children):
            if i != 2:
                ch.decompose()

        # Inside content wrapper, keep only the last child
        # (response), remove thinking (first child)
        wrapper = next((c for c in _element_children(msg)), None)
        if wrapper:
            w_children = _element_children(wrapper)
            for wch in w_children[:-1]:
                wch.decompose()

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
