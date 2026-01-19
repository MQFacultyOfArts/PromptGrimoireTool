"""Data models for SillyTavern scenario import and roleplay sessions.

These are plain dataclasses for in-memory use. PostgreSQL/SQLModel
persistence deferred to a future spike.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Any
from uuid import UUID, uuid4


class SelectiveLogic(IntEnum):
    """Logic for secondary keyword matching in lorebook entries.

    Based on SillyTavern's world-info.js selectiveLogic values.
    """

    AND_ANY = 0  # Primary matches AND any secondary matches
    NOT_ALL = 1  # Primary matches AND any secondary does NOT match
    NOT_ANY = 2  # Primary matches AND NO secondary matches
    AND_ALL = 3  # Primary matches AND ALL secondary match


@dataclass
class LorebookEntry:
    """A single lorebook/world-info entry with keyword triggers.

    Attributes:
        id: Unique identifier for this entry.
        keys: Primary keywords that trigger this entry.
        secondary_keys: Secondary keywords for selective logic.
        content: The context text to inject (may contain {{char}}/{{user}}).
        comment: Human-readable name/description for the entry.
        insertion_order: Priority for sorting (higher = earlier in prompt).
        scan_depth: How many recent messages to scan for keywords.
        selective: Whether secondary keyword logic is enabled.
        selective_logic: How to combine primary and secondary matches.
        enabled: Whether this entry is active.
        case_sensitive: Whether keyword matching is case-sensitive.
        match_whole_words: Whether to use word boundaries for matching.
    """

    keys: list[str]
    content: str
    id: int = 0
    secondary_keys: list[str] = field(default_factory=list)
    comment: str = ""
    insertion_order: int = 100
    scan_depth: int = 4
    selective: bool = True
    selective_logic: SelectiveLogic = SelectiveLogic.AND_ANY
    enabled: bool = True
    case_sensitive: bool = False
    match_whole_words: bool = False


@dataclass
class Character:
    """A SillyTavern character with system prompt and metadata.

    Attributes:
        name: Character display name.
        description: Character appearance and background.
        personality: Character traits and values.
        scenario: The roleplay situation/context.
        first_mes: Opening message when session starts.
        system_prompt: Full system instructions for the AI.
        lorebook_entries: Embedded world-info entries.
        user_persona_name: Default name for the user in this scenario.
    """

    name: str
    description: str = ""
    personality: str = ""
    scenario: str = ""
    first_mes: str = ""
    system_prompt: str = ""
    lorebook_entries: list[LorebookEntry] = field(default_factory=list)
    user_persona_name: str = "User"


@dataclass
class Turn:
    """A single message in a roleplay session.

    Attributes:
        id: Unique identifier for this turn.
        name: Speaker name (character name or user name).
        content: The message text.
        is_user: True if this is a user message, False for AI.
        is_system: True if this is a system message.
        timestamp: When this turn was created.
        metadata: Additional data (model info, reasoning, etc.).
    """

    name: str
    content: str
    is_user: bool = False
    is_system: bool = False
    id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_jsonl_dict(self) -> dict[str, Any]:
        """Convert to SillyTavern-compatible JSONL format."""
        return {
            "name": self.name,
            "is_user": self.is_user,
            "is_system": self.is_system,
            "send_date": self.timestamp.strftime("%B %d, %Y %I:%M%p"),
            "mes": self.content,
            "extra": self.metadata,
        }


@dataclass
class Session:
    """An active roleplay session with a character.

    Attributes:
        id: Unique session identifier.
        character: The character being roleplayed.
        user_name: The user's persona name for this session.
        turns: List of conversation turns.
        created_at: When the session started.
    """

    character: Character
    user_name: str = "User"
    id: UUID = field(default_factory=uuid4)
    turns: list[Turn] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def add_turn(
        self,
        content: str,
        is_user: bool,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Turn:
        """Add a new turn to the session.

        Args:
            content: The message text.
            is_user: True if user message, False if AI.
            name: Speaker name (defaults to user_name or character.name).
            metadata: Optional metadata dict.

        Returns:
            The created Turn object.
        """
        if name is None:
            name = self.user_name if is_user else self.character.name
        turn = Turn(
            name=name,
            content=content,
            is_user=is_user,
            metadata=metadata or {},
        )
        self.turns.append(turn)
        return turn

    def get_recent_messages(self, depth: int) -> list[Turn]:
        """Get the most recent N turns for lorebook scanning.

        Args:
            depth: Number of recent turns to return.

        Returns:
            List of turns, most recent last.
        """
        return self.turns[-depth:] if depth > 0 else []
