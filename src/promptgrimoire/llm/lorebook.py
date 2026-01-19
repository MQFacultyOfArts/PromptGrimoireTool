"""Lorebook activation engine for keyword-triggered context injection."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from promptgrimoire.models import LorebookEntry, SelectiveLogic, Turn


def match_keyword(
    keyword: str,
    text: str,
    *,
    case_sensitive: bool = False,
    match_whole_words: bool = False,
) -> bool:
    """Check if a keyword matches within text.

    Args:
        keyword: The keyword to search for. Supports * wildcard.
        text: The text to search in.
        case_sensitive: Whether matching is case-sensitive.
        match_whole_words: Whether to match only whole words.

    Returns:
        True if keyword matches, False otherwise.
    """
    if not keyword or not text:
        return False

    # Handle wildcard patterns (e.g., "drink*")
    if "*" in keyword:
        # Convert wildcard to regex pattern
        pattern = re.escape(keyword).replace(r"\*", r"\w*")
        flags = 0 if case_sensitive else re.IGNORECASE
        return bool(re.search(pattern, text, flags))

    # Normalize case if not case-sensitive
    search_text = text if case_sensitive else text.lower()
    search_keyword = keyword if case_sensitive else keyword.lower()

    if match_whole_words:
        # Use word boundary matching
        pattern = rf"\b{re.escape(search_keyword)}\b"
        flags = 0 if case_sensitive else re.IGNORECASE
        return bool(re.search(pattern, text, flags))

    return search_keyword in search_text


def build_haystack(turns: list[Turn], depth: int) -> str:
    """Build searchable text from recent conversation turns.

    Args:
        turns: List of conversation turns.
        depth: Number of recent turns to include.

    Returns:
        Joined text from recent turns.
    """
    if depth <= 0 or not turns:
        return ""

    recent = turns[-depth:]
    return " ".join(turn.content for turn in recent)


def activate_entries(
    entries: list[LorebookEntry],
    turns: list[Turn],
) -> list[LorebookEntry]:
    """Activate lorebook entries based on conversation keywords.

    Args:
        entries: All available lorebook entries.
        turns: Conversation history.

    Returns:
        List of activated entries, sorted by insertion_order descending.
    """
    # Import here to avoid circular imports at module level
    from promptgrimoire.models import SelectiveLogic

    activated: list[LorebookEntry] = []

    for entry in entries:
        if not entry.enabled:
            continue

        # Build haystack for this entry's scan depth
        haystack = build_haystack(turns, entry.scan_depth)

        if _entry_matches(entry, haystack, SelectiveLogic):
            activated.append(entry)

    # Sort by insertion_order descending (higher priority first)
    activated.sort(key=lambda e: e.insertion_order, reverse=True)

    return activated


def _entry_matches(
    entry: LorebookEntry, haystack: str, SelectiveLogic: type[SelectiveLogic]
) -> bool:
    """Check if an entry's keywords match the haystack.

    Args:
        entry: The lorebook entry to check.
        haystack: The text to search in.
        SelectiveLogic: The SelectiveLogic enum type.

    Returns:
        True if the entry should activate.
    """
    # Check primary keywords - any must match
    primary_match = any(
        match_keyword(
            key,
            haystack,
            case_sensitive=entry.case_sensitive,
            match_whole_words=entry.match_whole_words,
        )
        for key in entry.keys
    )

    if not primary_match:
        return False

    # If no secondary keys or selective is disabled, primary match is enough
    if not entry.selective or not entry.secondary_keys:
        return True

    # Check secondary keywords
    secondary_matches = [
        match_keyword(
            key,
            haystack,
            case_sensitive=entry.case_sensitive,
            match_whole_words=entry.match_whole_words,
        )
        for key in entry.secondary_keys
    ]

    any_secondary = any(secondary_matches)
    all_secondary = all(secondary_matches)

    if entry.selective_logic == SelectiveLogic.AND_ANY:
        # Primary matches AND at least one secondary matches
        return any_secondary
    if entry.selective_logic == SelectiveLogic.NOT_ALL:
        # Primary matches AND at least one secondary does NOT match
        return not all_secondary
    if entry.selective_logic == SelectiveLogic.NOT_ANY:
        # Primary matches AND NO secondary matches
        return not any_secondary
    if entry.selective_logic == SelectiveLogic.AND_ALL:
        # Primary matches AND ALL secondary match
        return all_secondary

    return False
