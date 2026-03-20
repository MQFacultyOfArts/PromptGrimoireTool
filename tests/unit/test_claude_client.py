"""Tests for Claude API client."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from promptgrimoire.llm.client import ClaudeClient
from promptgrimoire.models import Character, Session

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
    """Sample session for testing."""
    sess = Session(character=character, user_name="Jordan")
    sess.add_turn(character.first_mes, is_user=False)
    return sess


class TestClaudeClient:
    """Tests for ClaudeClient class."""

    def test_init_with_api_key(self) -> None:
        """Client initializes with API key."""
        client = ClaudeClient(api_key="test-key")
        assert client.api_key == "test-key"

    def test_init_with_all_params(self) -> None:
        """Client stores all constructor parameters."""
        client = ClaudeClient(
            api_key="test-key",
            model="test-model",
            thinking_budget=2048,
            lorebook_budget=500,
        )
        assert client.model == "test-model"
        assert client.thinking_budget == 2048
        assert client.lorebook_budget == 500

    def test_init_empty_key_raises(self) -> None:
        """Empty API key raises ValueError."""
        with pytest.raises(ValueError, match="API key is required"):
            ClaudeClient(api_key="")

    def test_default_lorebook_budget_is_zero(self) -> None:
        """Default lorebook_budget is 0 (unlimited)."""
        client = ClaudeClient(api_key="test-key")
        assert client.lorebook_budget == 0


class TestSendMessage:
    """Tests for sending messages and receiving responses."""

    @pytest.fixture
    def mock_anthropic(self):
        """Mock anthropic async client."""
        with patch("promptgrimoire.llm.client.anthropic") as mock:
            # Create async mock for messages.create
            from unittest.mock import AsyncMock

            mock.AsyncAnthropic.return_value.messages.create = AsyncMock()
            yield mock

    @pytest.mark.asyncio
    async def test_send_message_returns_response(
        self, session: Session, mock_anthropic: MagicMock
    ) -> None:
        """send_message returns character response."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text="I understand. Please, go on.", type="text")
        ]
        mock_anthropic.AsyncAnthropic.return_value.messages.create.return_value = (
            mock_response
        )

        client = ClaudeClient(api_key="test-key")
        response = await client.send_message(session, "Hello, I need help.")

        assert response == "I understand. Please, go on."

    @pytest.mark.asyncio
    async def test_send_message_adds_user_turn(
        self, session: Session, mock_anthropic: MagicMock
    ) -> None:
        """User message is added to session turns."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Response", type="text")]
        mock_anthropic.AsyncAnthropic.return_value.messages.create.return_value = (
            mock_response
        )

        client = ClaudeClient(api_key="test-key")
        initial_turns = len(session.turns)

        await client.send_message(session, "My message")

        # Should have user turn + assistant turn
        assert len(session.turns) == initial_turns + 2
        assert session.turns[-2].is_user is True
        assert session.turns[-2].content == "My message"

    @pytest.mark.asyncio
    async def test_send_message_adds_assistant_turn(
        self, session: Session, mock_anthropic: MagicMock
    ) -> None:
        """Assistant response is added to session turns."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="My response", type="text")]
        mock_anthropic.AsyncAnthropic.return_value.messages.create.return_value = (
            mock_response
        )

        client = ClaudeClient(api_key="test-key")
        await client.send_message(session, "Hello")

        assert session.turns[-1].is_user is False
        assert session.turns[-1].content == "My response"


class TestStreamingResponse:
    """Tests for streaming response handling."""

    @pytest.fixture
    def mock_anthropic(self):
        """Mock anthropic client."""
        with patch("promptgrimoire.llm.client.anthropic") as mock:
            yield mock

    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self, mock_anthropic: MagicMock) -> None:
        """Streaming yields text chunks."""
        # This would test actual streaming behavior
        # For now, placeholder test
        pass


def _make_stream_mock() -> MagicMock:
    """Create a mock for client.messages.stream that yields text events."""
    text_event = MagicMock()
    text_event.type = "text"
    text_event.text = "Hello there"

    stream_obj = MagicMock()
    stream_obj.__aiter__ = lambda _self: _self
    _events = iter([text_event])

    async def _anext(_self):
        try:
            return next(_events)
        except StopIteration:
            raise StopAsyncIteration from None

    stream_obj.__anext__ = _anext

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=stream_obj)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.usefixtures("_mock_streaming_anthropic")
class TestAuditLog:
    """Tests for audit log writing (AC2.7)."""

    @pytest.fixture
    def _mock_streaming_anthropic(self):
        """Mock anthropic client with streaming support."""
        with patch("promptgrimoire.llm.client.anthropic") as mock:
            mock.AsyncAnthropic.return_value.messages.stream = MagicMock(
                return_value=_make_stream_mock()
            )
            yield mock

    @pytest.mark.asyncio
    async def test_audit_log_written_when_path_set(
        self, session: Session, tmp_path: Path
    ) -> None:
        """When audit_log_path is set, a JSON file is written with API params."""
        audit_path = tmp_path / "audit.json"
        client = ClaudeClient(api_key="test-key", audit_log_path=audit_path)

        chunks = []
        async for chunk in client.stream_message_only(session):
            chunks.append(chunk)

        assert audit_path.exists()
        data = json.loads(audit_path.read_text(encoding="utf-8"))
        assert "system" in data
        assert "messages" in data
        assert "model" in data
        assert "max_tokens" in data

    @pytest.mark.asyncio
    async def test_no_audit_log_when_path_none(
        self, session: Session, tmp_path: Path
    ) -> None:
        """When audit_log_path is None, no file is written."""
        client = ClaudeClient(api_key="test-key", audit_log_path=None)

        async for _chunk in client.stream_message_only(session):
            pass

        # No JSON files should exist in tmp_path
        assert list(tmp_path.glob("*.json")) == []

    @pytest.mark.asyncio
    async def test_audit_log_schema_validation(
        self, session: Session, tmp_path: Path
    ) -> None:
        """Audit log JSON has correct types for all fields."""
        audit_path = tmp_path / "sub" / "audit.json"
        client = ClaudeClient(api_key="test-key", audit_log_path=audit_path)

        async for _chunk in client.stream_message_only(session):
            pass

        data = json.loads(audit_path.read_text(encoding="utf-8"))
        assert isinstance(data["system"], str)
        assert isinstance(data["messages"], list)
        for msg in data["messages"]:
            assert isinstance(msg, dict)
            assert "role" in msg
            assert "content" in msg
        assert isinstance(data["model"], str)
        assert isinstance(data["max_tokens"], int)
