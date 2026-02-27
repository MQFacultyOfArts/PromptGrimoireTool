"""Unit tests for process_dirty_workspaces() in search_worker.py.

Tests the async batch processing loop: dirty workspace fetch, tag batch
fetch, CRDT extraction, and CAS-guarded update.  All database I/O is
mocked via unittest.mock.AsyncMock; no real DB connection is required.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from promptgrimoire.search_worker import process_dirty_workspaces

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_row(*values: Any) -> tuple[Any, ...]:
    """Build a plain tuple row matching the workspace SELECT columns.

    Columns: (id, crdt_state, ws_title, activity_title)
    """
    return tuple(values)


def _make_mock_session(
    *,
    fetchall_results: list[list[tuple[Any, ...]]] | None = None,
) -> AsyncMock:
    """Create a mock AsyncSession that returns successive fetchall() results.

    fetchall_results is a list of return values, consumed in order for each
    session.execute(...).fetchall() call.  A single shared queue is used so
    the same mock session can serve multiple execute() calls correctly.
    """
    session = AsyncMock()
    results_queue = list(fetchall_results or [[]])

    async def _execute(*_args: Any, **_kwargs: Any) -> MagicMock:
        result = MagicMock()
        rows = results_queue.pop(0) if results_queue else []
        result.fetchall.return_value = rows
        return result

    session.execute = _execute
    return session


@asynccontextmanager
async def _session_context_factory(
    sessions: list[AsyncMock],
) -> AsyncIterator[AsyncMock]:
    """Yield sessions from a pre-built list, one per context-manager entry."""
    session = sessions.pop(0)
    yield session


def _make_get_session_patch(sessions: list[AsyncMock]):
    """Return a callable suitable for patching get_session.

    get_session is an asynccontextmanager used as ``async with get_session()``.
    Returning an async context manager that pops from the list matches that
    usage pattern.
    """

    def _factory():
        return _session_context_factory(sessions)

    return _factory


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProcessDirtyWorkspacesEmptyBatch:
    """No dirty workspaces: returns 0 without any update calls."""

    @pytest.mark.asyncio
    async def test_empty_batch_returns_zero(self) -> None:
        # First session: dirty-workspace fetch returns empty list.
        # Tag fetch session is never opened (ws_ids is empty).
        dirty_session = _make_mock_session(fetchall_results=[[]])
        sessions = [dirty_session]

        with patch(
            "promptgrimoire.search_worker.get_session",
            side_effect=_make_get_session_patch(sessions),
        ):
            result = await process_dirty_workspaces()

        assert result == 0


class TestProcessDirtyWorkspacesNullCrdtState:
    """Workspace with crdt_state=None should still write a title-only search_text."""

    @pytest.mark.asyncio
    async def test_null_crdt_state_produces_title_only(self) -> None:
        ws_id = uuid.uuid4()
        ws_title = "My Workspace"
        activity_title = "Week 3 Activity"

        dirty_rows = [_make_row(ws_id, None, ws_title, activity_title)]
        tag_rows: list[tuple[Any, ...]] = []  # no tags

        # Session 1: dirty workspace fetch
        dirty_session = _make_mock_session(fetchall_results=[dirty_rows])
        # Session 2: tag batch fetch
        tag_session = _make_mock_session(fetchall_results=[tag_rows])
        # Session 3: CAS update for the workspace
        update_session = _make_mock_session(fetchall_results=[[]])

        sessions = [dirty_session, tag_session, update_session]
        written_texts: list[str] = []

        @asynccontextmanager
        async def _capturing_get_session() -> AsyncIterator[AsyncMock]:
            session = sessions.pop(0)
            original_execute = session.execute

            async def _execute_capture(*args: Any, **kwargs: Any) -> Any:
                # Capture search_text from the positional params dict
                if (
                    len(args) >= 2
                    and isinstance(args[1], dict)
                    and "search_text" in args[1]
                ):
                    written_texts.append(args[1]["search_text"])
                return await original_execute(*args, **kwargs)

            session.execute = _execute_capture
            yield session

        with patch(
            "promptgrimoire.search_worker.get_session",
            side_effect=_capturing_get_session,
        ):
            result = await process_dirty_workspaces()

        assert result == 1
        # The written text must contain both title components
        assert len(written_texts) == 1
        assert ws_title in written_texts[0]
        assert activity_title in written_texts[0]


class TestProcessDirtyWorkspacesExtractionError:
    """extract_searchable_text raising must skip that workspace but process others."""

    @pytest.mark.asyncio
    async def test_extraction_error_logged_and_skipped(self) -> None:
        ws_id_bad = uuid.uuid4()
        ws_id_good = uuid.uuid4()

        dirty_rows = [
            _make_row(ws_id_bad, b"bad-crdt", "Bad WS", ""),
            _make_row(ws_id_good, b"good-crdt", "Good WS", ""),
        ]
        tag_rows: list[tuple[Any, ...]] = []

        dirty_session = _make_mock_session(fetchall_results=[dirty_rows])
        tag_session = _make_mock_session(fetchall_results=[tag_rows])
        # Only one update session because ws_id_bad is skipped
        update_session = _make_mock_session(fetchall_results=[[]])

        sessions = [dirty_session, tag_session, update_session]
        call_count = 0

        def _extract_side_effect(
            crdt_bytes: bytes | None, _tag_names: dict[str, str]
        ) -> str:
            nonlocal call_count
            call_count += 1
            if crdt_bytes == b"bad-crdt":
                raise ValueError("corrupt CRDT state")
            return "extracted text"

        with (
            patch(
                "promptgrimoire.search_worker.get_session",
                side_effect=_make_get_session_patch(sessions),
            ),
            patch(
                "promptgrimoire.search_worker.extract_searchable_text",
                side_effect=_extract_side_effect,
            ),
        ):
            result = await process_dirty_workspaces()

        # Only the good workspace counted
        assert result == 1
        # Both workspaces were attempted
        assert call_count == 2


class TestProcessDirtyWorkspacesTitlePrepend:
    """Workspace and activity titles are prepended to extracted CRDT text."""

    @pytest.mark.asyncio
    async def test_titles_prepended_to_search_text(self) -> None:
        ws_id = uuid.uuid4()
        ws_title = "Tort Law Analysis"
        activity_title = "Week 5: Negligence"
        crdt_content = "defendant breached duty of care"

        dirty_rows = [_make_row(ws_id, b"some-crdt", ws_title, activity_title)]
        tag_rows: list[tuple[Any, ...]] = []

        dirty_session = _make_mock_session(fetchall_results=[dirty_rows])
        tag_session = _make_mock_session(fetchall_results=[tag_rows])
        update_session = _make_mock_session(fetchall_results=[[]])

        sessions = [dirty_session, tag_session, update_session]
        written_texts: list[str] = []

        @asynccontextmanager
        async def _capturing_get_session() -> AsyncIterator[AsyncMock]:
            session = sessions.pop(0)
            original_execute = session.execute

            async def _execute_capture(*args: Any, **kwargs: Any) -> Any:
                if (
                    len(args) >= 2
                    and isinstance(args[1], dict)
                    and "search_text" in args[1]
                ):
                    written_texts.append(args[1]["search_text"])
                return await original_execute(*args, **kwargs)

            session.execute = _execute_capture
            yield session

        with (
            patch(
                "promptgrimoire.search_worker.get_session",
                side_effect=_capturing_get_session,
            ),
            patch(
                "promptgrimoire.search_worker.extract_searchable_text",
                return_value=crdt_content,
            ),
        ):
            result = await process_dirty_workspaces()

        assert result == 1
        assert len(written_texts) == 1
        text = written_texts[0]

        assert ws_title in text
        assert activity_title in text
        assert crdt_content in text

        # Titles come before CRDT body
        title_end = max(
            text.index(ws_title) + len(ws_title),
            text.index(activity_title) + len(activity_title),
        )
        crdt_start = text.index(crdt_content)
        assert title_end < crdt_start, (
            f"Expected titles before CRDT content but got: {text!r}"
        )

    @pytest.mark.asyncio
    async def test_ws_title_only_when_no_activity_title(self) -> None:
        """When activity_title is empty, only ws_title appears in prefix."""
        ws_id = uuid.uuid4()
        ws_title = "Standalone Workspace"
        crdt_content = "some extracted text"

        dirty_rows = [_make_row(ws_id, b"crdt", ws_title, "")]
        tag_rows: list[tuple[Any, ...]] = []

        dirty_session = _make_mock_session(fetchall_results=[dirty_rows])
        tag_session = _make_mock_session(fetchall_results=[tag_rows])
        update_session = _make_mock_session(fetchall_results=[[]])

        sessions = [dirty_session, tag_session, update_session]
        written_texts: list[str] = []

        @asynccontextmanager
        async def _capturing_get_session() -> AsyncIterator[AsyncMock]:
            session = sessions.pop(0)
            original_execute = session.execute

            async def _execute_capture(*args: Any, **kwargs: Any) -> Any:
                if (
                    len(args) >= 2
                    and isinstance(args[1], dict)
                    and "search_text" in args[1]
                ):
                    written_texts.append(args[1]["search_text"])
                return await original_execute(*args, **kwargs)

            session.execute = _execute_capture
            yield session

        with (
            patch(
                "promptgrimoire.search_worker.get_session",
                side_effect=_capturing_get_session,
            ),
            patch(
                "promptgrimoire.search_worker.extract_searchable_text",
                return_value=crdt_content,
            ),
        ):
            result = await process_dirty_workspaces()

        assert result == 1
        assert len(written_texts) == 1
        text = written_texts[0]
        assert ws_title in text
        assert crdt_content in text
        # No trailing space from empty activity title in the prefix
        assert not text.startswith(" ")
