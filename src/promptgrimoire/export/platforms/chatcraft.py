"""ChatCraft platform handler for HTML preprocessing.

Handles ChatCraft exports (chatcraft.org), which have:
- chakra-card class elements for conversation cards
- chatcraft.org text for platform detection
- Avatar spans with title attributes indicating speaker identity
- Speaker classification via heuristic (model names vs human names)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selectolax.lexbor import LexborHTMLParser

# Platform detection: must have both chakra-card class AND chatcraft.org text
_CARD_PATTERN = re.compile(r'class="[^"]*chakra-card[^"]*"', re.IGNORECASE)

# CSS selectors for ChatCraft chrome elements to remove
_CHROME_SELECTORS = [
    ".chakra-accordion__item",
    "form",
    ".chakra-menu__menuitem",
]


def _classify_speaker(title: str) -> str:
    """Classify a ChatCraft avatar title into a speaker role.

    Heuristic: model identifiers contain hyphens but no spaces
    (e.g. claude-sonnet-4, gpt-4). Human names have spaces.
    """
    if title == "System Prompt":
        return "system"
    if " " not in title and "-" in title:
        return "assistant"
    return "user"


class ChatCraftHandler:
    """Handler for ChatCraft HTML exports."""

    name: str = "chatcraft"

    def matches(self, html: str) -> bool:
        """Return True if HTML is from ChatCraft.

        Detection requires both a chakra-card class element and
        chatcraft.org text, to avoid false positives from other
        Chakra UI applications.
        """
        return bool(_CARD_PATTERN.search(html)) and "chatcraft.org" in html

    def preprocess(self, tree: LexborHTMLParser) -> None:
        """Remove chrome and inject data-speaker attributes on ChatCraft cards.

        Removes:
        - Accordion items (settings/config sections)
        - Forms (input areas)
        - Menu items (context menus)

        Then walks each .chakra-card, finds the avatar span[title],
        classifies the speaker, and sets data-speaker on the card.

        Args:
            tree: Parsed HTML tree to modify in-place.
        """
        # Remove chrome elements
        for selector in _CHROME_SELECTORS:
            for node in tree.css(selector):
                node.decompose()

        # Walk cards and inject speaker attributes
        for card in tree.css(".chakra-card"):
            spans = card.css("span[title]")
            if not spans:
                continue
            title = spans[0].attributes.get("title")
            if not title:
                continue
            role = _classify_speaker(title)
            card.attrs["data-speaker"] = role

    def get_turn_markers(self) -> dict[str, str]:
        """Return regex patterns for ChatCraft turn boundaries.

        ChatCraft uses data-speaker attributes injected during preprocessing
        to identify user, assistant, and system turns.

        Returns:
            Dict with 'user', 'assistant', and 'system' regex patterns.
        """
        return {
            "user": r'(<[^>]*data-speaker="user"[^>]*>)',
            "assistant": r'(<[^>]*data-speaker="assistant"[^>]*>)',
            "system": r'(<[^>]*data-speaker="system"[^>]*>)',
        }


# Module-level handler instance for autodiscovery
handler = ChatCraftHandler()
