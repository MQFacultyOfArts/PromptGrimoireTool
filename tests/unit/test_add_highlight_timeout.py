"""Tests for _add_highlight behaviour when ui.run_javascript times out.

H2a hypothesis: the `await ui.run_javascript("removeAllRanges")` at
highlights.py:288 is fire-and-forget (void return, no ordering dependency).
When the browser is busy, it times out at 1.0s. The TimeoutError skips
selection cleanup (lines 290-294), leaving stale selection_start/selection_end
and a visible ghost highlight_menu.

These tests verify:
1. TimeoutError from removeAllRanges must NOT propagate
2. Selection state must be cleaned up regardless of JS timeout
3. Highlight menu must be hidden regardless of JS timeout
"""

from __future__ import annotations

import contextlib
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
    the ui.run_javascript("removeAllRanges") call at line 288.
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


@pytest.mark.asyncio
async def test_timeout_does_not_propagate() -> None:
    """TimeoutError from removeAllRanges must not propagate to caller.

    Current code awaits ui.run_javascript("removeAllRanges") with 1.0s
    timeout. When the browser is busy, this raises TimeoutError which
    bubbles up to the NiceGUI event handler. After fix, the call should
    be fire-and-forget and no exception should escape.
    """
    state = _make_state()

    mock_pm = MagicMock()
    mock_pm.force_persist_workspace = AsyncMock()

    with (
        patch(
            "promptgrimoire.pages.annotation.highlights.get_persistence_manager",
            return_value=mock_pm,
        ),
        patch(
            "promptgrimoire.pages.annotation.highlights.ui.run_javascript",
            new_callable=AsyncMock,
            side_effect=TimeoutError("JavaScript did not respond within 1.0 s"),
        ),
        patch(
            "promptgrimoire.pages.annotation.highlights._push_highlights_to_client",
        ),
        patch(
            "promptgrimoire.pages.annotation.highlights.lookup_para_ref",
            return_value="",
        ),
    ):
        from promptgrimoire.pages.annotation.highlights import _add_highlight

        # This must NOT raise TimeoutError
        await _add_highlight(state, "test-tag")


@pytest.mark.asyncio
async def test_selection_cleared_on_timeout() -> None:
    """Selection state must be cleaned up even when removeAllRanges times out.

    Current code: lines 290-294 are skipped when line 288 raises TimeoutError.
    This leaves selection_start/selection_end set, causing ghost highlights.
    """
    state = _make_state(selection_start=10, selection_end=50)

    mock_pm = MagicMock()
    mock_pm.force_persist_workspace = AsyncMock()

    with (
        patch(
            "promptgrimoire.pages.annotation.highlights.get_persistence_manager",
            return_value=mock_pm,
        ),
        patch(
            "promptgrimoire.pages.annotation.highlights.ui.run_javascript",
            new_callable=AsyncMock,
            side_effect=TimeoutError("JavaScript did not respond within 1.0 s"),
        ),
        patch(
            "promptgrimoire.pages.annotation.highlights._push_highlights_to_client",
        ),
        patch(
            "promptgrimoire.pages.annotation.highlights.lookup_para_ref",
            return_value="",
        ),
    ):
        from promptgrimoire.pages.annotation.highlights import _add_highlight

        # Suppress the expected TimeoutError — testing state cleanup, not propagation
        with contextlib.suppress(TimeoutError):
            await _add_highlight(state, "test-tag")

    # Selection state MUST be cleared
    assert state.selection_start is None, (
        f"selection_start should be None, got {state.selection_start}"
    )
    assert state.selection_end is None, (
        f"selection_end should be None, got {state.selection_end}"
    )


@pytest.mark.asyncio
async def test_highlight_menu_hidden_on_timeout() -> None:
    """Highlight menu must be hidden even when removeAllRanges times out.

    Current code: highlight_menu.set_visibility(False) at line 294 is
    skipped when line 288 raises TimeoutError, leaving a ghost menu.
    """
    state = _make_state()

    mock_pm = MagicMock()
    mock_pm.force_persist_workspace = AsyncMock()

    with (
        patch(
            "promptgrimoire.pages.annotation.highlights.get_persistence_manager",
            return_value=mock_pm,
        ),
        patch(
            "promptgrimoire.pages.annotation.highlights.ui.run_javascript",
            new_callable=AsyncMock,
            side_effect=TimeoutError("JavaScript did not respond within 1.0 s"),
        ),
        patch(
            "promptgrimoire.pages.annotation.highlights._push_highlights_to_client",
        ),
        patch(
            "promptgrimoire.pages.annotation.highlights.lookup_para_ref",
            return_value="",
        ),
    ):
        from promptgrimoire.pages.annotation.highlights import _add_highlight

        with contextlib.suppress(TimeoutError):
            await _add_highlight(state, "test-tag")

    # Highlight menu MUST have been hidden
    mock_menu = cast("MagicMock", state.highlight_menu)
    mock_menu.set_visibility.assert_called_with(False)


@pytest.mark.asyncio
async def test_processing_highlight_released_on_timeout() -> None:
    """processing_highlight must be False after timeout (existing behaviour).

    This tests the existing finally block — should pass on current code.
    Included as a safety net to ensure the fix doesn't break this.
    """
    state = _make_state()

    mock_pm = MagicMock()
    mock_pm.force_persist_workspace = AsyncMock()

    with (
        patch(
            "promptgrimoire.pages.annotation.highlights.get_persistence_manager",
            return_value=mock_pm,
        ),
        patch(
            "promptgrimoire.pages.annotation.highlights.ui.run_javascript",
            new_callable=AsyncMock,
            side_effect=TimeoutError("JavaScript did not respond within 1.0 s"),
        ),
        patch(
            "promptgrimoire.pages.annotation.highlights._push_highlights_to_client",
        ),
        patch(
            "promptgrimoire.pages.annotation.highlights.lookup_para_ref",
            return_value="",
        ),
    ):
        from promptgrimoire.pages.annotation.highlights import _add_highlight

        with contextlib.suppress(TimeoutError):
            await _add_highlight(state, "test-tag")

    assert state.processing_highlight is False
