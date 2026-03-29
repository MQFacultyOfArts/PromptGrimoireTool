"""Tests for _add_highlight cleanup behaviour.

Originally written for #377 when ``ui.run_javascript("removeAllRanges")``
was awaited and could time out, leaving stale selection state and a
ghost highlight menu.  The call is now fire-and-forget (#454), so
TimeoutError can no longer occur, but the cleanup invariants remain:

1. No exception escapes ``_add_highlight``
2. Selection state is always cleared
3. Highlight menu is always hidden
4. ``processing_highlight`` lock is always released
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from promptgrimoire.pages.annotation import PageState


def _make_state(
    *,
    selection_start: int = 10,
    selection_end: int = 50,
) -> PageState:
    """Build a minimal PageState for _add_highlight testing.

    Sets up the minimum fields needed for _add_highlight to reach
    the fire-and-forget ``ui.run_javascript("removeAllRanges")`` call.
    """
    state = PageState(workspace_id=uuid4())
    state.selection_start = selection_start
    state.selection_end = selection_end
    state.document_id = uuid4()
    state.user_name = "Test User"
    state.user_id = "test-user-id"
    state.processing_highlight = False

    # Mock CRDT doc — needs add_highlight method
    state.crdt_doc = MagicMock()
    state.crdt_doc.add_highlight = MagicMock()
    state.crdt_doc.doc_id = "test-doc"

    # Mock save_status
    state.save_status = MagicMock()

    # Document chars for text extraction
    state.document_chars = list("x" * 100)

    # Mock highlight_menu with visibility tracking
    mock_menu = MagicMock()
    state.highlight_menu = cast("Any", mock_menu)

    # Mock refresh_annotations (fire-and-forget, not async)
    state.refresh_annotations = MagicMock()

    # Mock broadcast_update (async)
    state.broadcast_update = AsyncMock()

    # Mock highlight_style for _update_highlight_css
    state.highlight_style = MagicMock()
    state.highlight_style._props = {}

    return state


# MagicMock (not AsyncMock) for ui.run_javascript — the call is
# fire-and-forget, so AsyncMock would produce an unawaited coroutine
# RuntimeWarning.
_JS_PATCH = "promptgrimoire.pages.annotation.highlights.ui.run_javascript"
_PUSH_PATCH = "promptgrimoire.pages.annotation.highlights._push_highlights_to_client"
_LOOKUP_PATCH = "promptgrimoire.pages.annotation.highlights.lookup_para_ref"
_PM_PATCH = "promptgrimoire.pages.annotation.highlights.get_persistence_manager"


@pytest.mark.asyncio
async def test_no_exception_escapes() -> None:
    """No exception escapes _add_highlight during normal operation."""
    state = _make_state()

    mock_pm = MagicMock()
    mock_pm.force_persist_workspace = AsyncMock()

    with (
        patch(_PM_PATCH, return_value=mock_pm),
        patch(_JS_PATCH),
        patch(_PUSH_PATCH),
        patch(_LOOKUP_PATCH, return_value=""),
    ):
        from promptgrimoire.pages.annotation.highlights import _add_highlight

        await _add_highlight(state, "test-tag")


@pytest.mark.asyncio
async def test_selection_cleared() -> None:
    """Selection state is always cleared after _add_highlight completes."""
    state = _make_state(selection_start=10, selection_end=50)

    mock_pm = MagicMock()
    mock_pm.force_persist_workspace = AsyncMock()

    with (
        patch(_PM_PATCH, return_value=mock_pm),
        patch(_JS_PATCH),
        patch(_PUSH_PATCH),
        patch(_LOOKUP_PATCH, return_value=""),
    ):
        from promptgrimoire.pages.annotation.highlights import _add_highlight

        await _add_highlight(state, "test-tag")

    assert state.selection_start is None, (
        f"selection_start should be None, got {state.selection_start}"
    )
    assert state.selection_end is None, (
        f"selection_end should be None, got {state.selection_end}"
    )


@pytest.mark.asyncio
async def test_highlight_menu_hidden() -> None:
    """Highlight menu is always hidden after _add_highlight completes."""
    state = _make_state()

    mock_pm = MagicMock()
    mock_pm.force_persist_workspace = AsyncMock()

    with (
        patch(_PM_PATCH, return_value=mock_pm),
        patch(_JS_PATCH),
        patch(_PUSH_PATCH),
        patch(_LOOKUP_PATCH, return_value=""),
    ):
        from promptgrimoire.pages.annotation.highlights import _add_highlight

        await _add_highlight(state, "test-tag")

    mock_menu = cast("MagicMock", state.highlight_menu)
    mock_menu.set_visibility.assert_called_with(False)


@pytest.mark.asyncio
async def test_processing_highlight_released() -> None:
    """processing_highlight lock is always released after _add_highlight."""
    state = _make_state()

    mock_pm = MagicMock()
    mock_pm.force_persist_workspace = AsyncMock()

    with (
        patch(_PM_PATCH, return_value=mock_pm),
        patch(_JS_PATCH),
        patch(_PUSH_PATCH),
        patch(_LOOKUP_PATCH, return_value=""),
    ):
        from promptgrimoire.pages.annotation.highlights import _add_highlight

        await _add_highlight(state, "test-tag")

    assert state.processing_highlight is False
