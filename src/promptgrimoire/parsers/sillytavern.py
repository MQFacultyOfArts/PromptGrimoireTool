"""Parser for SillyTavern chara_card_v3 format."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from promptgrimoire.models import Character, LorebookEntry, SelectiveLogic

if TYPE_CHECKING:
    from pathlib import Path


def parse_character_card(path: Path) -> tuple[Character, list[LorebookEntry]]:
    """Parse a SillyTavern chara_card_v3 JSON file.

    Args:
        path: Path to the character card JSON file.

    Returns:
        Tuple of (Character, list of LorebookEntry).

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the JSON is invalid or missing required fields.
    """
    if not path.exists():
        raise FileNotFoundError(f"Character card not found: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {path}: {e}") from e

    # Validate required fields
    if "name" not in raw:
        raise ValueError("Character card missing required field: name")

    # Extract character fields - prefer 'data' block if present (v3 format)
    data = raw.get("data", {})

    character = Character(
        name=raw["name"],
        description=_clean_text(raw.get("description", "")),
        personality=_clean_text(raw.get("personality", "")),
        scenario=_clean_text(raw.get("scenario", "")),
        first_mes=_clean_text(raw.get("first_mes", "")),
        system_prompt=_clean_text(data.get("system_prompt", "")),
        user_persona_name=_extract_user_persona(),
    )

    # Parse embedded lorebook
    entries = _parse_lorebook_entries(data.get("character_book", {}))

    return character, entries


def _clean_text(text: str) -> str:
    """Normalize line endings and whitespace."""
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _extract_user_persona() -> str:
    """Extract user persona name from extensions or default."""
    # Could be in extensions or inferred from scenario
    return "User"


def _parse_lorebook_entries(book: dict[str, Any]) -> list[LorebookEntry]:
    """Parse lorebook/character_book entries."""
    if not book:
        return []

    raw_entries = book.get("entries", [])
    entries = []

    for raw_entry in raw_entries:
        entry = LorebookEntry(
            id=raw_entry.get("id", 0),
            keys=raw_entry.get("keys", []),
            secondary_keys=raw_entry.get("secondary_keys", []),
            content=_clean_text(raw_entry.get("content", "")),
            comment=raw_entry.get("comment", ""),
            insertion_order=raw_entry.get("insertion_order", 100),
            scan_depth=_get_scan_depth(raw_entry),
            selective=raw_entry.get("selective", True),
            selective_logic=SelectiveLogic(
                raw_entry.get("extensions", {}).get("selectiveLogic", 0)
            ),
            enabled=raw_entry.get("enabled", True),
            case_sensitive=raw_entry.get("extensions", {}).get("case_sensitive")
            or False,
            match_whole_words=raw_entry.get("extensions", {}).get("match_whole_words")
            or False,
        )
        entries.append(entry)

    return entries


def _get_scan_depth(entry: dict[str, Any]) -> int:
    """Extract scan depth from entry, checking extensions."""
    # Check extensions first, then top-level
    extensions = entry.get("extensions", {})
    depth = extensions.get("depth") or entry.get("depth")
    return depth if depth is not None else 4
