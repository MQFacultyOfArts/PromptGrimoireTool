"""Unit tests for database engine module."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from pytest import LogCaptureFixture


class TestGetSession:
    """Tests for get_session() context manager."""

    @pytest.mark.asyncio
    async def test_session_logs_on_exception(self, caplog: LogCaptureFixture) -> None:
        """Session context manager logs exceptions before re-raising."""
        from promptgrimoire.db.engine import _state, get_session

        # Create mock session that raises on commit
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.commit = AsyncMock(side_effect=ValueError("Test DB error"))
        mock_session.rollback = AsyncMock()

        # Create mock session factory
        mock_factory = MagicMock(return_value=mock_session)

        # Temporarily replace session factory
        original_factory = _state.session_factory
        _state.session_factory = mock_factory

        try:
            with (
                caplog.at_level(logging.ERROR, logger="promptgrimoire.db.engine"),
                pytest.raises(ValueError, match="Test DB error"),
            ):
                async with get_session():
                    pass  # Just entering and exiting triggers commit

            # Verify logging occurred
            assert "rolling back" in caplog.text.lower()
            assert "database session error" in caplog.text.lower()

            # Verify rollback was called
            mock_session.rollback.assert_awaited_once()
        finally:
            _state.session_factory = original_factory

    @pytest.mark.asyncio
    async def test_session_lazy_initializes_when_factory_is_none(self) -> None:
        """Getting a session when factory is None lazily initializes the engine."""
        from promptgrimoire.db.engine import _state, close_db, get_session

        # Ensure factory is None (simulating first use)
        original_factory = _state.session_factory
        original_engine = _state.engine
        _state.session_factory = None
        _state.engine = None

        try:
            # get_session should lazily call init_db
            async with get_session() as session:
                # Should have initialized the engine and factory
                assert _state.engine is not None
                assert _state.session_factory is not None
                # Session should be usable
                assert session is not None
        finally:
            # Clean up the lazily-created engine
            await close_db()
            _state.session_factory = original_factory
            _state.engine = original_engine


class TestGetEngine:
    """Tests for get_engine() function."""

    def test_get_engine_returns_none_before_init(self) -> None:
        """engine returns None before initialization."""
        from promptgrimoire.db.engine import _state, get_engine

        # Ensure engine is None
        original_engine = _state.engine
        _state.engine = None

        try:
            assert get_engine() is None
        finally:
            _state.engine = original_engine

    def test_get_engine_returns_engine_after_init(self) -> None:
        """engine returns the engine after initialization."""
        from promptgrimoire.db.engine import _state, get_engine

        # Set a mock engine
        mock_engine = MagicMock()
        original_engine = _state.engine
        _state.engine = mock_engine

        try:
            assert get_engine() is mock_engine
        finally:
            _state.engine = original_engine
