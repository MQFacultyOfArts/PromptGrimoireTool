"""Claude API client for roleplay sessions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import anthropic
import structlog

from promptgrimoire.llm.lorebook import activate_entries
from promptgrimoire.llm.prompt import build_messages, build_system_prompt

logger = structlog.get_logger()
logging.getLogger(__name__).setLevel(logging.INFO)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from promptgrimoire.models import Session


class ClaudeClient:
    """Client for interacting with Claude API.

    Uses the async Anthropic client for non-blocking API calls.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        thinking_budget: int = 0,
        lorebook_budget: int = 0,
    ) -> None:
        """Initialize the Claude client.

        Args:
            api_key: Anthropic API key (required).
            model: Model identifier to use.
            thinking_budget: Token budget for extended thinking. 0 disables thinking.
            lorebook_budget: Max tokens for lorebook entries. 0 = unlimited.

        Raises:
            ValueError: If api_key is empty.
        """
        if not api_key:
            msg = (
                "API key is required. "
                "Configure LLM__API_KEY in .env or pass api_key parameter."
            )
            raise ValueError(msg)

        self.api_key = api_key
        self.model = model
        self.thinking_budget = thinking_budget
        self.lorebook_budget = lorebook_budget
        self._client = anthropic.AsyncAnthropic(api_key=self.api_key)

    async def send_message(self, session: Session, user_message: str) -> str:
        """Send a message and get a response.

        Args:
            session: The current roleplay session.
            user_message: The user's message.

        Returns:
            The assistant's response text.

        Raises:
            ValueError: If Claude returns an empty or non-text response.
        """
        # Add user turn to session
        session.add_turn(user_message, is_user=True)

        # Activate lorebook entries based on conversation
        activated = activate_entries(session.character.lorebook_entries, session.turns)

        # Build system prompt with lorebook injection
        system_prompt = build_system_prompt(
            session.character,
            activated,
            user_name=session.user_name,
            lorebook_budget=self.lorebook_budget,
        )

        # Build messages array
        messages = build_messages(session.turns)

        # Call Claude API (async)
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )

        # Extract response text safely
        if not response.content:
            raise ValueError("Empty response from Claude API")

        first_block = response.content[0]
        if not hasattr(first_block, "text") or first_block.type != "text":
            raise ValueError(f"Unexpected response type: {first_block.type}")

        response_text = str(first_block.text)

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
            session.character,
            activated,
            user_name=session.user_name,
            lorebook_budget=self.lorebook_budget,
        )
        messages = build_messages(session.turns)

        # Stream response (async)
        full_response = ""
        async with self._client.messages.stream(
            model=self.model,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                full_response += text
                yield text

        # Add complete response as turn
        session.add_turn(
            full_response,
            is_user=False,
            metadata={"model": self.model, "api": "claude"},
        )

    def _build_api_params(
        self,
        system_prompt: str,
        messages: list[anthropic.types.MessageParam],
    ) -> dict:
        """Build API parameters for the Claude messages stream call."""
        params: dict = {
            "model": self.model,
            "max_tokens": 16000 if self.thinking_budget > 0 else 1024,
            "system": system_prompt,
            "messages": messages,
        }
        if self.thinking_budget > 0:
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.thinking_budget,
            }
        return params

    def _build_turn_metadata(
        self,
        activated_names: list[str],
        thinking_content: str,
        error: Exception | None,
    ) -> dict:
        """Build metadata dict for the response turn."""
        metadata: dict = {
            "model": self.model,
            "api": "claude",
            "activated_lorebook": activated_names,
        }
        if thinking_content:
            metadata["reasoning"] = thinking_content
        if error:
            metadata["partial"] = True
            metadata["error"] = str(error)
        return metadata

    async def stream_message_only(self, session: Session) -> AsyncIterator[str]:
        """Stream response without adding user turn to session.

        Use when the UI has already added the user turn before calling.
        Reasoning is captured in metadata but NOT yielded (hidden from students).

        Args:
            session: The current roleplay session (user turn already added).

        Yields:
            Text chunks as they arrive (response only, not thinking).
        """
        activated = activate_entries(session.character.lorebook_entries, session.turns)
        system_prompt = build_system_prompt(
            session.character,
            activated,
            user_name=session.user_name,
            lorebook_budget=self.lorebook_budget,
        )
        messages = build_messages(session.turns)
        activated_names = [e.comment or ", ".join(e.keys[:3]) for e in activated]
        api_params = self._build_api_params(system_prompt, messages)

        full_response = ""
        thinking_content = ""
        error_occurred: Exception | None = None

        try:
            async with self._client.messages.stream(**api_params) as stream:
                async for event in stream:
                    if event.type == "thinking":
                        thinking_content += getattr(event, "thinking", "")
                    elif event.type == "text":
                        text: str = getattr(event, "text", "")
                        full_response += text
                        yield text
        except Exception as e:
            error_occurred = e
            logger.error(
                "Stream error after %d chars: %s",
                len(full_response),
                e,
                exc_info=True,
            )
        finally:
            metadata = self._build_turn_metadata(
                activated_names,
                thinking_content,
                error_occurred,
            )
            session.add_turn(full_response, is_user=False, metadata=metadata)

        if error_occurred:
            raise error_occurred
