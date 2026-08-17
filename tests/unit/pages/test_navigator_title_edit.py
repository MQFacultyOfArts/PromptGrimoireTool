"""Tests for navigator workspace title editing (`_persist_title_change`).

NiceGUI 3.11 made ``ValueElement`` generic, so ``Input.value`` is correctly
typed ``str | None``. ``_persist_title_change`` called ``.strip()`` on it
directly, which raises ``AttributeError`` when the value is ``None`` -- and the
surrounding ``except Exception`` would have swallowed that into a "Failed to
save title" notification, silently discarding the user's edit rather than
surfacing a crash.

The verdict in each test comes from what was persisted to the database, not
from re-reading the code under test.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

if TYPE_CHECKING:
    from nicegui.elements.input import Input


async def test_none_value_persists_as_none() -> None:
    """A ``None`` input value must be persisted as ``None``, not raise.

    Guards the NiceGUI 3.11+ ``Input.value: str | None`` contract.
    """
    from promptgrimoire.pages.navigator._cards import _persist_title_change

    workspace_id = uuid4()
    title_input = SimpleNamespace(value=None)

    with patch(
        "promptgrimoire.pages.navigator._cards.update_workspace_title",
        new_callable=AsyncMock,
    ) as mock_update:
        await _persist_title_change(
            workspace_id=workspace_id,
            title_input=cast("Input", title_input),
            fallback_title="Untitled Workspace",
            original_title="Untitled Workspace",
            page_state=None,
        )

    mock_update.assert_awaited_once_with(workspace_id, None)
    assert title_input.value == "Untitled Workspace", (
        "A cleared title must fall back to the display title in the input box"
    )


async def test_whitespace_only_value_persists_as_none() -> None:
    """Whitespace-only titles collapse to ``None`` (pre-existing behaviour)."""
    from promptgrimoire.pages.navigator._cards import _persist_title_change

    workspace_id = uuid4()
    title_input = SimpleNamespace(value="   ")

    with patch(
        "promptgrimoire.pages.navigator._cards.update_workspace_title",
        new_callable=AsyncMock,
    ) as mock_update:
        await _persist_title_change(
            workspace_id=workspace_id,
            title_input=cast("Input", title_input),
            fallback_title="Untitled Workspace",
            original_title="Untitled Workspace",
            page_state=None,
        )

    mock_update.assert_awaited_once_with(workspace_id, None)


async def test_real_title_is_stripped_and_persisted() -> None:
    """Surrounding whitespace is trimmed before persisting.

    Positive control: proves these tests can observe a persisted value at all,
    so the ``None`` assertions above are not passing vacuously.
    """
    from promptgrimoire.pages.navigator._cards import _persist_title_change

    workspace_id = uuid4()
    title_input = SimpleNamespace(value="  Becky Bennett interview  ")

    with patch(
        "promptgrimoire.pages.navigator._cards.update_workspace_title",
        new_callable=AsyncMock,
    ) as mock_update:
        await _persist_title_change(
            workspace_id=workspace_id,
            title_input=cast("Input", title_input),
            fallback_title="Untitled Workspace",
            original_title="Untitled Workspace",
            page_state=None,
        )

    mock_update.assert_awaited_once_with(workspace_id, "Becky Bennett interview")
    assert title_input.value == "Becky Bennett interview"
