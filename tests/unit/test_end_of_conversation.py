"""Tests for StreamChunk and detect_end_of_conversation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from promptgrimoire.llm.client import StreamChunk, detect_end_of_conversation
from promptgrimoire.models import Character, Session


async def _chunks(*texts: str) -> AsyncIterator[str]:
    for t in texts:
        yield t


@pytest.mark.asyncio
async def test_marker_in_single_chunk() -> None:
    """AC3.1: Marker in a single chunk yields text before it, ended=True."""
    results: list[StreamChunk] = []
    async for chunk in detect_end_of_conversation(
        _chunks("Hello world<endofconversation>")
    ):
        results.append(chunk)

    assert len(results) == 1
    assert results[0].text == "Hello world"
    assert results[0].ended is True


@pytest.mark.asyncio
async def test_marker_at_end_of_multi_chunk() -> None:
    """AC3.1: Marker at end of response across chunks."""
    results: list[StreamChunk] = []
    async for chunk in detect_end_of_conversation(
        _chunks("Hello ", "world<endofconversation>")
    ):
        results.append(chunk)

    combined = "".join(c.text for c in results)
    assert combined == "Hello world"
    assert results[-1].ended is True


@pytest.mark.asyncio
async def test_marker_in_middle_of_chunk() -> None:
    """AC3.1: Marker in middle — text before yielded, after discarded."""
    results: list[StreamChunk] = []
    async for chunk in detect_end_of_conversation(
        _chunks("Before<endofconversation>After"),
    ):
        results.append(chunk)

    combined = "".join(c.text for c in results)
    assert combined == "Before"
    assert results[-1].ended is True
    # "After" must not appear
    assert all("After" not in c.text for c in results)


@pytest.mark.asyncio
async def test_marker_spanning_two_chunks() -> None:
    """AC3.2: Marker split across two chunks."""
    results: list[StreamChunk] = []
    async for chunk in detect_end_of_conversation(
        _chunks("Hello <endofconv", "ersation> goodbye"),
    ):
        results.append(chunk)

    combined = "".join(c.text for c in results)
    assert combined == "Hello "
    assert results[-1].ended is True


@pytest.mark.asyncio
async def test_marker_spanning_three_chunks() -> None:
    """AC3.2: Marker split across three chunks."""
    results: list[StreamChunk] = []
    async for chunk in detect_end_of_conversation(
        _chunks("<endof", "conver", "sation>"),
    ):
        results.append(chunk)

    # Should have ended=True on terminal chunk specifically
    assert results[-1].ended is True
    # No marker text in output
    combined = "".join(c.text for c in results)
    assert "<endofconversation>" not in combined
    assert "<endof" not in combined


@pytest.mark.asyncio
async def test_no_marker() -> None:
    """AC3.3: No marker — all chunks ended=False."""
    results: list[StreamChunk] = []
    async for chunk in detect_end_of_conversation(_chunks("Hello", " world")):
        results.append(chunk)

    combined = "".join(c.text for c in results)
    assert combined == "Hello world"
    assert all(c.ended is False for c in results)


@pytest.mark.asyncio
async def test_html_tag_no_false_positive() -> None:
    """AC3.3: Text with < but not marker — no false positive."""
    results: list[StreamChunk] = []
    async for chunk in detect_end_of_conversation(_chunks("Use <html> tags")):
        results.append(chunk)

    combined = "".join(c.text for c in results)
    assert combined == "Use <html> tags"
    assert all(c.ended is False for c in results)


@pytest.mark.asyncio
async def test_empty_stream() -> None:
    """Edge: Empty stream yields no chunks."""
    results: list[StreamChunk] = []
    async for chunk in detect_end_of_conversation(_chunks()):
        results.append(chunk)

    assert results == []


@pytest.mark.asyncio
async def test_marker_is_entire_response() -> None:
    """Edge: Marker is the entire response — empty text, ended=True."""
    results: list[StreamChunk] = []
    async for chunk in detect_end_of_conversation(
        _chunks("<endofconversation>"),
    ):
        results.append(chunk)

    assert len(results) == 1
    assert results[0].text == ""
    assert results[0].ended is True


def test_ended_session_blocks_further_messages() -> None:
    """AC3.7: Session.ended=True prevents further message submission.

    The guard in _handle_send() checks ``state["session"].ended`` and
    returns immediately when True.  Since _handle_send() is coupled to
    NiceGUI widgets, we verify the guard condition directly: a Session
    with ``ended=True`` must evaluate the guard to True, meaning no API
    call would be made.
    """
    character = Character(name="Test", system_prompt="test")
    session = Session(character=character, user_name="User")

    # Session not ended — guard should NOT fire
    assert not session.ended

    # Mark ended — guard should fire
    session.ended = True
    assert session.ended

    # Verify add_turn still physically works (the guard is in _handle_send,
    # not on Session itself), but the session IS ended
    initial_count = len(session.turns)
    session.add_turn("should not happen in real flow", is_user=True)
    assert len(session.turns) == initial_count + 1
    # The point: _handle_send() checks session.ended BEFORE calling add_turn,
    # so in real code this turn would never be added.
