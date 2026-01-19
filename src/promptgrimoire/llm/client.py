"""Claude API client for roleplay sessions."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import anthropic

from promptgrimoire.llm.lorebook import activate_entries
from promptgrimoire.llm.prompt import build_messages, build_system_prompt

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from promptgrimoire.models import Session


class ClaudeClient:
    """Client for interacting with Claude API."""

    def __init__(
        self, api_key: str | None = None, model: str = "claude-sonnet-4-20250514"
    ) -> None:
        """Initialize the Claude client.

        Args:
            api_key: Anthropic API key. If not provided, reads from ANTHROPIC_API_KEY.
            model: Model identifier to use.

        Raises:
            ValueError: If no API key is available.
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("API key required. Set ANTHROPIC_API_KEY or pass api_key.")

        self.model = model
        self._client = anthropic.Anthropic(api_key=self.api_key)

    async def send_message(self, session: Session, user_message: str) -> str:
        """Send a message and get a response.

        Args:
            session: The current roleplay session.
            user_message: The user's message.

        Returns:
            The assistant's response text.
        """
        # Add user turn to session
        session.add_turn(user_message, is_user=True)

        # Activate lorebook entries based on conversation
        activated = activate_entries(session.character.lorebook_entries, session.turns)

        # Build system prompt with lorebook injection
        system_prompt = build_system_prompt(
            session.character, activated, user_name=session.user_name
        )

        # Build messages array
        messages = build_messages(session.turns)

        # Call Claude API
        response = self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )

        # Extract response text
        response_text = response.content[0].text

        # Add assistant turn to session
        session.add_turn(
            response_text,
            is_user=False,
            metadata={"model": self.model, "api": "claude"},
        )

        return response_text

    async def stream_message(
        self, session: Session, user_message: str
    ) -> AsyncIterator[str]:
        """Send a message and stream the response.

        Args:
            session: The current roleplay session.
            user_message: The user's message.

        Yields:
            Text chunks as they arrive.
        """
        # Add user turn to session
        session.add_turn(user_message, is_user=True)

        # Activate lorebook entries
        activated = activate_entries(session.character.lorebook_entries, session.turns)

        # Build prompts
        system_prompt = build_system_prompt(
            session.character, activated, user_name=session.user_name
        )
        messages = build_messages(session.turns)

        # Stream response
        full_response = ""
        with self._client.messages.stream(
            model=self.model,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                full_response += text
                yield text

        # Add complete response as turn
        session.add_turn(
            full_response,
            is_user=False,
            metadata={"model": self.model, "api": "claude"},
        )

    async def stream_message_only(self, session: Session) -> AsyncIterator[str]:
        """Stream response without adding user turn to session.

        Use when the UI has already added the user turn before calling.

        Args:
            session: The current roleplay session (user turn already added).

        Yields:
            Text chunks as they arrive.
        """
        # Activate lorebook entries
        activated = activate_entries(session.character.lorebook_entries, session.turns)

        # Build prompts
        system_prompt = build_system_prompt(
            session.character, activated, user_name=session.user_name
        )
        messages = build_messages(session.turns)

        # Stream response
        full_response = ""
        with self._client.messages.stream(
            model=self.model,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                full_response += text
                yield text

        # Add complete response as turn
        session.add_turn(
            full_response,
            is_user=False,
            metadata={"model": self.model, "api": "claude"},
        )
