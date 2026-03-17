"""Unit tests for database engine module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from promptgrimoire.config import DatabaseConfig, DevConfig, Settings
from promptgrimoire.db.exceptions import BusinessLogicError


def _settings_with_db(
    url: str = "postgresql+asyncpg://test:test@localhost/testdb",
) -> Settings:
    """Create a Settings instance with a database URL for testing."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        database=DatabaseConfig(url=url),
        dev=DevConfig(database_echo=False, branch_db_suffix=False),
    )


class TestGetSession:
    """Tests for get_session() context manager."""

    @pytest.mark.asyncio
    async def test_session_logs_on_exception(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
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
            with pytest.raises(ValueError, match="Test DB error"):
                async with get_session():
                    pass  # Just entering and exiting triggers commit

            # Verify logging occurred — structlog emits to stdout/stderr
            captured = capsys.readouterr()
            combined = (captured.out + captured.err).lower()
            assert "rolling back" in combined
            assert "database session error" in combined

            # Verify rollback was called
            mock_session.rollback.assert_awaited_once()
        finally:
            _state.session_factory = original_factory

    @pytest.mark.asyncio
    async def test_business_logic_error_logs_warning_not_exception(self) -> None:
        """BusinessLogicError logs warning, not exception (AC2.1, AC2.5)."""
        from promptgrimoire.db.engine import _state, get_session

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_factory = MagicMock(return_value=mock_session)
        original_factory = _state.session_factory
        _state.session_factory = mock_factory

        try:
            with patch("promptgrimoire.db.engine.logger") as mock_logger:
                with pytest.raises(BusinessLogicError, match="not allowed"):
                    async with get_session():
                        raise BusinessLogicError("not allowed")

                mock_logger.warning.assert_called_once()
                mock_logger.exception.assert_not_called()
                mock_session.rollback.assert_awaited_once()
        finally:
            _state.session_factory = original_factory

    @pytest.mark.asyncio
    async def test_unexpected_exception_logs_exception_not_warning(self) -> None:
        """Unexpected Exception inside get_session() logs exception at ERROR (AC2.2)."""
        from promptgrimoire.db.engine import _state, get_session

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_factory = MagicMock(return_value=mock_session)
        original_factory = _state.session_factory
        _state.session_factory = mock_factory

        try:
            with patch("promptgrimoire.db.engine.logger") as mock_logger:
                with pytest.raises(RuntimeError, match="unexpected"):
                    async with get_session():
                        raise RuntimeError("unexpected")

                mock_logger.exception.assert_called_once()
                mock_logger.warning.assert_not_called()
                mock_session.rollback.assert_awaited_once()
        finally:
            _state.session_factory = original_factory

    @pytest.mark.asyncio
    async def test_business_logic_error_uses_distinct_event_name(self) -> None:
        """BusinessLogicError uses distinct event name (AC2.3)."""
        from promptgrimoire.db.engine import _state, get_session

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_factory = MagicMock(return_value=mock_session)
        original_factory = _state.session_factory
        _state.session_factory = mock_factory

        try:
            with patch("promptgrimoire.db.engine.logger") as mock_logger:
                with pytest.raises(BusinessLogicError):
                    async with get_session():
                        raise BusinessLogicError("test")

                event_name = mock_logger.warning.call_args[0][0]
                assert event_name == "Business logic error, rolling back transaction"
                assert event_name != "Database session error, rolling back transaction"
        finally:
            _state.session_factory = original_factory

    @pytest.mark.asyncio
    async def test_both_branches_include_exc_class(self) -> None:
        """Both exception branches include exc_class in structured log (AC2.4)."""
        from promptgrimoire.db.engine import _state, get_session

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_factory = MagicMock(return_value=mock_session)
        original_factory = _state.session_factory
        _state.session_factory = mock_factory

        try:
            # Test BusinessLogicError branch
            with patch("promptgrimoire.db.engine.logger") as mock_logger:
                with pytest.raises(BusinessLogicError):
                    async with get_session():
                        raise BusinessLogicError("test")

                kwargs = mock_logger.warning.call_args[1]
                assert kwargs["exc_class"] == "BusinessLogicError"

            # Test generic Exception branch
            with patch("promptgrimoire.db.engine.logger") as mock_logger:
                with pytest.raises(RuntimeError):
                    async with get_session():
                        raise RuntimeError("test")

                kwargs = mock_logger.exception.call_args[1]
                assert kwargs["exc_class"] == "RuntimeError"
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
            # Patch get_settings to provide a database URL
            with patch(
                "promptgrimoire.db.engine.get_settings",
                return_value=_settings_with_db(),
            ):
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
