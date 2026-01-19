"""Tests for JSONL log output in SillyTavern format."""

from __future__ import annotations

import json
from datetime import datetime
from io import StringIO
from typing import TYPE_CHECKING

import pytest

from promptgrimoire.llm.log import JSONLLogger, write_session_log
from promptgrimoire.models import Character, Session, Turn

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def character() -> Character:
    """Sample character for testing."""
    return Character(
        name="Becky Bennett",
        description="A client seeking legal advice.",
        personality="Introverted and cautious.",
        scenario="Seeking advice about a workplace accident.",
        first_mes="Thanks for making time to see me.",
        system_prompt="You are Becky. Keep responses under 30 words.",
    )


@pytest.fixture
def session(character: Character) -> Session:
    """Sample session with some turns."""
    sess = Session(character=character, user_name="Jordan")
    sess.add_turn(character.first_mes, is_user=False)
    sess.add_turn("Hello, welcome. Please have a seat.", is_user=True)
    sess.add_turn(
        "Thank you. I'm a bit nervous.",
        is_user=False,
        metadata={"model": "claude-sonnet-4-20250514", "api": "claude"},
    )
    return sess


class TestTurnToJsonl:
    """Tests for Turn.to_jsonl_dict() method."""

    def test_user_turn_format(self) -> None:
        """User turn has correct JSONL structure."""
        turn = Turn(
            name="Jordan",
            content="Hello there.",
            is_user=True,
            timestamp=datetime(2025, 1, 15, 10, 30),
        )

        result = turn.to_jsonl_dict()

        assert result["name"] == "Jordan"
        assert result["is_user"] is True
        assert result["is_system"] is False
        assert result["mes"] == "Hello there."
        assert "send_date" in result

    def test_character_turn_format(self) -> None:
        """Character turn has correct JSONL structure."""
        turn = Turn(
            name="Becky Bennett",
            content="Nice to meet you.",
            is_user=False,
            metadata={"model": "claude-sonnet-4", "api": "claude"},
        )

        result = turn.to_jsonl_dict()

        assert result["name"] == "Becky Bennett"
        assert result["is_user"] is False
        assert result["extra"]["model"] == "claude-sonnet-4"
        assert result["extra"]["api"] == "claude"

    def test_date_format(self) -> None:
        """send_date matches SillyTavern format."""
        turn = Turn(
            name="Jordan",
            content="Test",
            is_user=True,
            timestamp=datetime(2025, 1, 15, 14, 30),
        )

        result = turn.to_jsonl_dict()

        # SillyTavern format: "January 15, 2025 02:30PM"
        assert "January 15, 2025" in result["send_date"]


class TestJSONLLogger:
    """Tests for JSONLLogger class."""

    def test_writes_header_line(self, session: Session) -> None:
        """First line contains session metadata."""
        output = StringIO()
        logger = JSONLLogger(output)

        logger.write_header(session)

        output.seek(0)
        header = json.loads(output.readline())

        assert header["user_name"] == "Jordan"
        assert header["character_name"] == "Becky Bennett"
        assert "create_date" in header

    def test_writes_turn(self, session: Session) -> None:
        """Turns are written as JSONL lines."""
        output = StringIO()
        logger = JSONLLogger(output)

        logger.write_turn(session.turns[0])

        output.seek(0)
        line = json.loads(output.readline())

        assert line["name"] == "Becky Bennett"
        assert line["mes"] == "Thanks for making time to see me."

    def test_multiple_turns(self, session: Session) -> None:
        """Multiple turns create multiple lines."""
        output = StringIO()
        logger = JSONLLogger(output)

        for turn in session.turns:
            logger.write_turn(turn)

        output.seek(0)
        lines = output.readlines()

        assert len(lines) == 3

    def test_each_line_is_valid_json(self, session: Session) -> None:
        """Each line is independently valid JSON."""
        output = StringIO()
        logger = JSONLLogger(output)

        logger.write_header(session)
        for turn in session.turns:
            logger.write_turn(turn)

        output.seek(0)
        for line in output:
            parsed = json.loads(line)
            assert isinstance(parsed, dict)


class TestWriteSessionLog:
    """Tests for write_session_log convenience function."""

    def test_writes_complete_session(self, session: Session, tmp_path: Path) -> None:
        """Writes header + all turns to file."""
        log_path = tmp_path / "session.jsonl"

        write_session_log(session, log_path)

        lines = log_path.read_text().strip().split("\n")
        # Header + 3 turns = 4 lines
        assert len(lines) == 4

        # First line is header
        header = json.loads(lines[0])
        assert header["character_name"] == "Becky Bennett"

        # Remaining lines are turns
        for i, line in enumerate(lines[1:]):
            turn_data = json.loads(line)
            assert turn_data["mes"] == session.turns[i].content

    def test_creates_parent_directories(self, session: Session, tmp_path: Path) -> None:
        """Creates parent directories if they don't exist."""
        log_path = tmp_path / "logs" / "sessions" / "test.jsonl"

        write_session_log(session, log_path)

        assert log_path.exists()

    def test_filename_from_session(self, session: Session) -> None:
        """Can generate filename from session metadata."""
        # This tests a helper that generates sensible filenames
        from promptgrimoire.llm.log import generate_log_filename

        filename = generate_log_filename(session)

        assert "Becky_Bennett" in filename or "becky" in filename.lower()
        assert filename.endswith(".jsonl")
