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


def estimate_tokens(text: str) -> int:
    """Estimate token count for text.

    Uses a simple heuristic: ~4 characters per token on average.
    This is conservative and works reasonably well for English text.

    Args:
        text: Text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


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


def _collect_lorebook_entries(
    entries: list[LorebookEntry],
    *,
    budget: int,
    tokens_used: int,
) -> tuple[list[str], int]:
    """Collect lorebook entry contents respecting a shared token budget.

    Entries are sorted by ``insertion_order`` descending. Empty entries are
    skipped. When *budget* is positive, entries that would exceed the remaining
    budget are dropped (and iteration stops).

    Args:
        entries: Lorebook entries for one position slot.
        budget: Overall lorebook token budget (0 = unlimited).
        tokens_used: Tokens already consumed by a prior slot.

    Returns:
        A tuple of (collected content strings, updated tokens_used).
    """
    parts: list[str] = []
    for entry in sorted(entries, key=lambda e: e.insertion_order, reverse=True):
        content = entry.content.strip()
        if not content:
            continue
        if budget > 0:
            entry_tokens = estimate_tokens(content)
            if tokens_used + entry_tokens > budget:
                break
            tokens_used += entry_tokens
        parts.append(content)
    return parts, tokens_used


def build_system_prompt(
    character: Character,
    activated_entries: list[LorebookEntry],
    *,
    user_name: str,
    lorebook_budget: int = 0,
) -> str:
    """Build the system prompt with lorebook injection.

    Follows SillyTavern's slot ordering for prompt assembly:

    1. Main prompt — ``character.system_prompt``
    2. World Info Before — lorebook entries with ``position == "before_char"``,
       sorted by ``insertion_order`` descending, budget-enforced
    3. Character Description — ``character.description``
    4. Character Personality — ``character.personality``
    5. Scenario — ``character.scenario``
    6. World Info After — lorebook entries with ``position == "after_char"``,
       sorted by ``insertion_order`` descending, budget-enforced
    7. Dialogue Examples — ``character.mes_example``

    Token budget is shared across both World Info slots: before_char entries
    consume budget first, after_char entries use the remainder.

    Empty slots (empty string after strip) produce no gap.

    All ``{{char}}``/``{{user}}`` placeholders are substituted.

    Args:
        character: The character being roleplayed.
        activated_entries: Lorebook entries to inject.
        user_name: The user's persona name.
        lorebook_budget: Max tokens for lorebook entries (0 = unlimited).

    Returns:
        Complete system prompt string.
    """
    parts: list[str] = []

    # Split lorebook entries by position
    before_entries = [e for e in activated_entries if e.position == "before_char"]
    after_entries = [e for e in activated_entries if e.position == "after_char"]

    # 1. Main prompt (system_prompt)
    if character.system_prompt.strip():
        parts.append(character.system_prompt.strip())

    # 2. World Info Before — before_char lorebook entries
    before_parts, tokens_used = _collect_lorebook_entries(
        before_entries, budget=lorebook_budget, tokens_used=0
    )
    parts.extend(before_parts)

    # 3. Character Description
    if character.description.strip():
        parts.append(character.description.strip())

    # 4. Character Personality
    if character.personality.strip():
        parts.append(character.personality.strip())

    # 5. Scenario
    if character.scenario.strip():
        parts.append(character.scenario.strip())

    # 6. World Info After — after_char lorebook entries (shared budget)
    after_parts, _ = _collect_lorebook_entries(
        after_entries, budget=lorebook_budget, tokens_used=tokens_used
    )
    parts.extend(after_parts)

    # 7. Dialogue Examples
    if character.mes_example.strip():
        parts.append(character.mes_example.strip())

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
