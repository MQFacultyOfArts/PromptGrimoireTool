"""Unit tests for the deadline polling worker (mocked DB)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _make_mock_session(result_rows=None, scalar_value=None):
    """Create a mock async session with a sync Result object."""
    mock_session = AsyncMock()
    mock_result = MagicMock()  # Result.fetchall() / scalar_one_or_none() are sync
    if result_rows is not None:
        mock_result.fetchall.return_value = result_rows
    if scalar_value is not None:
        mock_result.scalar_one_or_none.return_value = scalar_value
    else:
        mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result
    return mock_session


def _mock_get_session(mock_session):
    """Wrap a mock session in the get_session async context manager."""

    @asynccontextmanager
    async def _get_session():
        yield mock_session

    return _get_session


@pytest.mark.asyncio
async def test_check_expired_deadlines_fires_for_expired() -> None:
    """check_expired_deadlines calls on_deadline_fired for expired activities."""
    activity_id = uuid4()
    mock_session = _make_mock_session(result_rows=[(activity_id,)])
    mock_on_deadline = AsyncMock()

    with (
        patch(
            "promptgrimoire.deadline_worker.get_session",
            _mock_get_session(mock_session),
        ),
        patch(
            "promptgrimoire.db.wargames.on_deadline_fired",
            mock_on_deadline,
        ),
    ):
        from promptgrimoire.deadline_worker import check_expired_deadlines

        result = await check_expired_deadlines()

    assert result == 1
    mock_on_deadline.assert_awaited_once_with(activity_id)


@pytest.mark.asyncio
async def test_check_expired_deadlines_skips_future() -> None:
    """check_expired_deadlines does NOT fire for future deadlines."""
    mock_session = _make_mock_session(result_rows=[])

    with patch(
        "promptgrimoire.deadline_worker.get_session",
        _mock_get_session(mock_session),
    ):
        from promptgrimoire.deadline_worker import check_expired_deadlines

        result = await check_expired_deadlines()

    assert result == 0


@pytest.mark.asyncio
async def test_check_expired_deadlines_exception_doesnt_prevent_others() -> None:
    """Exception in one activity doesn't prevent processing others."""
    id1 = uuid4()
    id2 = uuid4()
    mock_session = _make_mock_session(result_rows=[(id1,), (id2,)])

    call_log: list = []

    async def mock_on_deadline(activity_id):
        call_log.append(activity_id)
        if activity_id == id1:
            raise RuntimeError("boom")

    with (
        patch(
            "promptgrimoire.deadline_worker.get_session",
            _mock_get_session(mock_session),
        ),
        patch(
            "promptgrimoire.db.wargames.on_deadline_fired",
            mock_on_deadline,
        ),
    ):
        from promptgrimoire.deadline_worker import check_expired_deadlines

        result = await check_expired_deadlines()

    # Only id2 succeeded
    assert result == 1
    # But both were attempted
    assert len(call_log) == 2


@pytest.mark.asyncio
async def test_next_deadline_seconds_returns_none_when_no_deadlines() -> None:
    """_next_deadline_seconds returns None when no deadlines exist."""
    mock_session = _make_mock_session(scalar_value=None)

    with patch(
        "promptgrimoire.deadline_worker.get_session",
        _mock_get_session(mock_session),
    ):
        from promptgrimoire.deadline_worker import _next_deadline_seconds

        result = await _next_deadline_seconds()

    assert result is None
