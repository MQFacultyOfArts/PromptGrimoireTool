"""JSONL log output in SillyTavern-compatible format."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from pathlib import Path

    from promptgrimoire.models import Session, Turn


class JSONLLogger:
    """Writes session data to JSONL format compatible with SillyTavern."""

    def __init__(self, output: TextIO) -> None:
        """Initialize logger with output stream.

        Args:
            output: A text stream to write JSONL lines to.
        """
        self._output = output

    def write_header(self, session: Session) -> None:
        """Write session metadata as the first JSONL line.

        Args:
            session: The session to write metadata for.
        """
        header = {
            "user_name": session.user_name,
            "character_name": session.character.name,
            "create_date": session.created_at.strftime("%B %d, %Y %I:%M%p"),
            "chat_metadata": {
                "session_id": str(session.id),
            },
        }
        self._output.write(json.dumps(header) + "\n")

    def write_turn(self, turn: Turn) -> None:
        """Write a single turn as a JSONL line.

        Args:
            turn: The turn to write.
        """
        self._output.write(json.dumps(turn.to_jsonl_dict()) + "\n")


def write_session_log(session: Session, path: Path) -> None:
    """Write a complete session to a JSONL file.

    Creates parent directories if they don't exist.

    Args:
        session: The session to write.
        path: Path to the output file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w") as f:
        logger = JSONLLogger(f)
        logger.write_header(session)
        for turn in session.turns:
            logger.write_turn(turn)


def generate_log_filename(session: Session) -> str:
    """Generate a sensible filename for a session log.

    Format: {character_name}_{timestamp}.jsonl

    Args:
        session: The session to generate a filename for.

    Returns:
        A filename string.
    """
    # Sanitize character name for filename
    char_name = session.character.name.replace(" ", "_")
    char_name = "".join(c for c in char_name if c.isalnum() or c == "_")

    timestamp = session.created_at.strftime("%Y%m%d_%H%M%S")

    return f"{char_name}_{timestamp}.jsonl"
