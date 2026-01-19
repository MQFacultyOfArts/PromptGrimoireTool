"""Tests for Claude API client."""

from unittest.mock import MagicMock, patch

import pytest

from promptgrimoire.llm.client import ClaudeClient
from promptgrimoire.models import Character, Session


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

    def test_init_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Client reads API key from environment."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
        client = ClaudeClient()
        assert client.api_key == "env-key"

    def test_init_no_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing API key raises ValueError."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(ValueError, match="API key"):
            ClaudeClient()


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
