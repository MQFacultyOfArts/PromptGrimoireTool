"""Claude API client for roleplay sessions."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, cast

import anthropic

from promptgrimoire.llm.lorebook import activate_entries
from promptgrimoire.llm.prompt import build_messages, build_system_prompt

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from promptgrimoire.models import Session


class ClaudeClient:
    """Client for interacting with Claude API.

    Uses the async Anthropic client for non-blocking API calls.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        thinking_budget: int = 0,
    ) -> None:
        """Initialize the Claude client.

        Args:
            api_key: Anthropic API key. If not provided, reads from ANTHROPIC_API_KEY.
            model: Model identifier to use.
            thinking_budget: Token budget for extended thinking. 0 disables thinking.

        Raises:
            ValueError: If no API key is available.
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("API key required. Set ANTHROPIC_API_KEY or pass api_key.")

        self.model = model
        self.thinking_budget = thinking_budget
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
            session.character, activated, user_name=session.user_name
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
        if not isinstance(first_block, anthropic.types.TextBlock):
            raise ValueError(f"Unexpected response type: {first_block.type}")

        # Type guard: we've verified it's a text block above
        response_text = cast("str", first_block.text)  # type: ignore[attr-defined]

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

    async def stream_message_only(self, session: Session) -> AsyncIterator[str]:
        """Stream response without adding user turn to session.

        Use when the UI has already added the user turn before calling.
        Reasoning is captured in metadata but NOT yielded (hidden from students).

        Args:
            session: The current roleplay session (user turn already added).

        Yields:
            Text chunks as they arrive (response only, not thinking).
        """
        # Activate lorebook entries
        activated = activate_entries(session.character.lorebook_entries, session.turns)

        # Build prompts
        system_prompt = build_system_prompt(
            session.character, activated, user_name=session.user_name
        )
        messages = build_messages(session.turns)

        # Build metadata including activated lorebook entries
        activated_names = [e.comment or ", ".join(e.keys[:3]) for e in activated]

        # Build API params
        api_params: dict = {
            "model": self.model,
            "max_tokens": 16000 if self.thinking_budget > 0 else 1024,
            "system": system_prompt,
            "messages": messages,
        }

        # Add thinking if budget > 0
        if self.thinking_budget > 0:
            api_params["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.thinking_budget,
            }

        # Stream response - collect thinking separately from response (async)
        # Uses high-level SDK events: "text" and "thinking" (not raw deltas)
        full_response = ""
        thinking_content = ""
        error_occurred: Exception | None = None

        # HIGH-4: Wrap in try/finally to capture partial responses on error
        try:
            async with self._client.messages.stream(**api_params) as stream:
                async for event in stream:
                    if event.type == "thinking":
                        # Capture thinking but don't yield it (hidden from students)
                        # getattr for type checker - ThinkingEvent always has .thinking
                        thinking_content += getattr(event, "thinking", "")
                    elif event.type == "text":
                        # Yield text response to UI
                        # getattr for type checker - TextEvent always has .text
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
            # Always add turn to session (even if partial) for audit trail
            metadata: dict = {
                "model": self.model,
                "api": "claude",
                "activated_lorebook": activated_names,
            }

            # Add thinking to metadata if present (for logging, not display)
            if thinking_content:
                metadata["reasoning"] = thinking_content

            # HIGH-4: Mark partial responses with error info
            if error_occurred:
                metadata["partial"] = True
                metadata["error"] = str(error_occurred)

            # Add response as turn (complete or partial)
            session.add_turn(
                full_response,
                is_user=False,
                metadata=metadata,
            )

        # Re-raise the error after logging the partial turn
        if error_occurred:
            raise error_occurred
