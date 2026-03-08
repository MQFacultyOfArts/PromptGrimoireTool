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
    from selectolax.lexbor import LexborHTMLParser, LexborNode

# Platform detection: must have both chakra-card class AND chatcraft.org text
# ChatCraft exports browser-rendered HTML which always uses double-quoted attributes
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
    # Exact match: ChatCraft uses "System Prompt" (title-case) as of 2026-02
    if title == "System Prompt":
        return "system"
    if " " not in title and "-" in title:
        return "assistant"
    return "user"


def _extract_speaker_label(card: LexborNode) -> str | None:
    """Extract the speaker label from a ChatCraft card header.

    ChatCraft cards are not fully consistent:
    - some cards expose the speaker/model name on ``span[title]``
    - some user cards have no avatar ``title`` at all
    - system prompt cards can use avatar title ``ChatCraft`` while the
      visible header heading is ``System Prompt``

    Prefer the visible heading when available, then fall back to the
    avatar title.
    """
    header = card.css_first(".chakra-card__header")
    if header is not None:
        heading = header.css_first("h2")
        if heading is not None:
            text = (heading.text() or "").strip()
            if text:
                return text

        avatar = header.css_first("span[title]")
        if avatar is not None:
            title = (avatar.attributes.get("title") or "").strip()
            if title:
                return title

    avatar = card.css_first("span[title]")
    if avatar is not None:
        title = (avatar.attributes.get("title") or "").strip()
        if title:
            return title

    return None


def _same_node(left: LexborNode | None, right: LexborNode | None) -> bool:
    """Return True when two selectolax node wrappers point at the same node."""
    if left is None or right is None:
        return left is right
    return left.mem_id == right.mem_id


def _top_level_body_child(node: LexborNode, body: LexborNode) -> LexborNode | None:
    """Return the direct ``body`` child containing ``node``."""
    current: LexborNode | None = node
    while (
        current is not None
        and current.parent is not None
        and not _same_node(current.parent, body)
    ):
        current = current.parent
    return current


def _classify_chatcraft_cards(tree: LexborHTMLParser) -> None:
    """Tag ChatCraft cards with speaker metadata and strip card headers."""
    for card in tree.css(".chakra-card"):
        label = _extract_speaker_label(card)
        if not label:
            continue
        role = _classify_speaker(label)
        card.attrs["data-speaker"] = role
        card.attrs["data-speaker-name"] = label
        for header in card.css(".chakra-card__header"):
            header.decompose()


def _remove_pre_turn_chrome(tree: LexborHTMLParser) -> None:
    """Remove top-level page chrome that appears before the first conversation turn."""
    body = tree.body
    if body is None:
        return

    first_turn = next(
        (
            card
            for card in tree.css(".chakra-card")
            if card.attributes.get("data-speaker")
        ),
        None,
    )
    if first_turn is None:
        return

    first_turn_container = _top_level_body_child(first_turn, body)
    child = body.first_child
    while child is not None and not _same_node(child, first_turn_container):
        next_child = child.next
        child.decompose()
        child = next_child


def _remove_non_turn_cards(tree: LexborHTMLParser) -> None:
    """Remove non-conversation ChatCraft cards after classification."""
    for card in tree.css(".chakra-card"):
        if not card.attributes.get("data-speaker"):
            card.decompose()


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
        _classify_chatcraft_cards(tree)

        # 2. Remove chrome elements (accordion items, forms, menus)
        #    after cards have been classified.
        for selector in _CHROME_SELECTORS:
            for node in tree.css(selector):
                node.decompose()

        _remove_pre_turn_chrome(tree)
        _remove_non_turn_cards(tree)

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
