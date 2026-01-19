"""Prompt assembly for roleplay sessions."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal, TypedDict

if TYPE_CHECKING:
    from anthropic.types import MessageParam

    from promptgrimoire.models import Character, LorebookEntry, Turn


class MessageDict(TypedDict):
    """Message format compatible with Claude API."""

    role: Literal["user", "assistant"]
    content: str


def substitute_placeholders(text: str, *, char_name: str, user_name: str) -> str:
    """Substitute {{char}} and {{user}} placeholders in text.

    Args:
        text: Text containing placeholders.
        char_name: Character name to substitute.
        user_name: User name to substitute.

    Returns:
        Text with placeholders replaced.
    """
    # Case-insensitive replacement
    result = re.sub(r"\{\{char\}\}", char_name, text, flags=re.IGNORECASE)
    result = re.sub(r"\{\{user\}\}", user_name, result, flags=re.IGNORECASE)
    return result


def build_system_prompt(
    character: Character,
    activated_entries: list[LorebookEntry],
    *,
    user_name: str,
) -> str:
    """Build the system prompt with lorebook injection.

    Order:
    1. Activated lorebook entries (sorted by insertion_order descending)
    2. Character description
    3. Character personality
    4. Character scenario
    5. System prompt instructions

    All {{char}}/{{user}} placeholders are substituted.

    Args:
        character: The character being roleplayed.
        activated_entries: Lorebook entries to inject.
        user_name: The user's persona name.

    Returns:
        Complete system prompt string.
    """
    parts: list[str] = []

    # 1. Lorebook entries (already sorted by caller, but ensure order)
    sorted_entries = sorted(
        activated_entries, key=lambda e: e.insertion_order, reverse=True
    )
    for entry in sorted_entries:
        if entry.content.strip():
            parts.append(entry.content.strip())

    # 2-4. Character definition
    if character.description.strip():
        parts.append(character.description.strip())
    if character.personality.strip():
        parts.append(character.personality.strip())
    if character.scenario.strip():
        parts.append(character.scenario.strip())

    # 5. System prompt instructions
    if character.system_prompt.strip():
        parts.append(character.system_prompt.strip())

    # Join and substitute placeholders
    full_prompt = "\n\n".join(parts)
    return substitute_placeholders(
        full_prompt, char_name=character.name, user_name=user_name
    )


def build_messages(turns: list[Turn]) -> list[MessageParam]:
    """Build the messages array from conversation turns.

    Args:
        turns: Conversation history.

    Returns:
        List of message dicts with 'role' and 'content' keys.
    """
    messages: list[MessageDict] = []

    for turn in turns:
        role: Literal["user", "assistant"] = "user" if turn.is_user else "assistant"
        messages.append({"role": role, "content": turn.content})

    # Cast to MessageParam for type compatibility with Anthropic SDK
    return messages  # type: ignore[return-value]
