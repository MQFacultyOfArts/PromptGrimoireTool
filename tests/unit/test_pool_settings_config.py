"""Tests for configurable pool settings in DatabaseConfig and init_db.

Verifies that pool_size, max_overflow, pool_pre_ping, and pool_recycle
are read from DatabaseConfig (and therefore overridable via DATABASE__*
env vars) rather than hardcoded in engine.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from promptgrimoire.config import DatabaseConfig, DevConfig, Settings


def _settings_with_pool(
    url: str = "postgresql+asyncpg://test:test@localhost/testdb",
    pool_size: int = 80,
    max_overflow: int = 15,
    pool_pre_ping: bool = True,
    pool_recycle: int = 3600,
) -> Settings:
    """Create a Settings instance with specific pool settings."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        database=DatabaseConfig(
            url=url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=pool_pre_ping,
            pool_recycle=pool_recycle,
        ),
        dev=DevConfig(database_echo=False, branch_db_suffix=False),
    )


class TestDatabaseConfigDefaults:
    """DatabaseConfig pool settings have correct defaults."""

    def test_default_pool_size(self) -> None:
        config = DatabaseConfig()
        assert config.pool_size == 80

    def test_default_max_overflow(self) -> None:
        config = DatabaseConfig()
        assert config.max_overflow == 15

    def test_default_pool_pre_ping(self) -> None:
        config = DatabaseConfig()
        assert config.pool_pre_ping is True

    def test_default_pool_recycle(self) -> None:
        config = DatabaseConfig()
        assert config.pool_recycle == 3600

    def test_pool_size_overridable(self) -> None:
        config = DatabaseConfig(pool_size=30)
        assert config.pool_size == 30

    def test_max_overflow_overridable(self) -> None:
        config = DatabaseConfig(max_overflow=5)
        assert config.max_overflow == 5


class TestInitDbReadsPoolConfig:
    """init_db passes pool settings from DatabaseConfig to create_async_engine."""

    @pytest.fixture(autouse=True)
    def _force_non_test_env(self) -> object:
        """Prevent _is_test_environment from short-circuiting to NullPool."""
        with patch(
            "promptgrimoire.db.engine._is_test_environment",
            return_value=False,
        ):
            yield

    @pytest.mark.asyncio
    async def test_custom_pool_size_passed_to_engine(self) -> None:
        """Pool size from config is passed to create_async_engine."""
        from promptgrimoire.db.engine import _state

        original_engine = _state.engine
        original_factory = _state.session_factory
        _state.engine = None
        _state.session_factory = None

        custom_settings = _settings_with_pool(pool_size=25, max_overflow=5)

        try:
            with (
                patch(
                    "promptgrimoire.db.engine.get_settings",
                    return_value=custom_settings,
                ),
                patch(
                    "promptgrimoire.db.engine.create_async_engine",
                    return_value=MagicMock(sync_engine=MagicMock(pool=MagicMock())),
                ) as mock_create,
                patch("promptgrimoire.db.engine._install_pool_listeners"),
            ):
                from promptgrimoire.db.engine import init_db

                await init_db()

                call_kwargs = mock_create.call_args[1]
                assert call_kwargs["pool_size"] == 25
                assert call_kwargs["max_overflow"] == 5
        finally:
            _state.engine = None
            _state.session_factory = None
            _state.engine = original_engine
            _state.session_factory = original_factory

    @pytest.mark.asyncio
    async def test_pool_pre_ping_passed_to_engine(self) -> None:
        """pool_pre_ping from config is passed to create_async_engine."""
        from promptgrimoire.db.engine import _state

        original_engine = _state.engine
        original_factory = _state.session_factory
        _state.engine = None
        _state.session_factory = None

        custom_settings = _settings_with_pool(pool_pre_ping=False)

        try:
            with (
                patch(
                    "promptgrimoire.db.engine.get_settings",
                    return_value=custom_settings,
                ),
                patch(
                    "promptgrimoire.db.engine.create_async_engine",
                    return_value=MagicMock(sync_engine=MagicMock(pool=MagicMock())),
                ) as mock_create,
                patch("promptgrimoire.db.engine._install_pool_listeners"),
            ):
                from promptgrimoire.db.engine import init_db

                await init_db()

                call_kwargs = mock_create.call_args[1]
                assert call_kwargs["pool_pre_ping"] is False
        finally:
            _state.engine = None
            _state.session_factory = None
            _state.engine = original_engine
            _state.session_factory = original_factory

    @pytest.mark.asyncio
    async def test_pool_recycle_passed_to_engine(self) -> None:
        """pool_recycle from config is passed to create_async_engine."""
        from promptgrimoire.db.engine import _state

        original_engine = _state.engine
        original_factory = _state.session_factory
        _state.engine = None
        _state.session_factory = None

        custom_settings = _settings_with_pool(pool_recycle=1800)

        try:
            with (
                patch(
                    "promptgrimoire.db.engine.get_settings",
                    return_value=custom_settings,
                ),
                patch(
                    "promptgrimoire.db.engine.create_async_engine",
                    return_value=MagicMock(sync_engine=MagicMock(pool=MagicMock())),
                ) as mock_create,
                patch("promptgrimoire.db.engine._install_pool_listeners"),
            ):
                from promptgrimoire.db.engine import init_db

                await init_db()

                call_kwargs = mock_create.call_args[1]
                assert call_kwargs["pool_recycle"] == 1800
        finally:
            _state.engine = None
            _state.session_factory = None
            _state.engine = original_engine
            _state.session_factory = original_factory

    @pytest.mark.asyncio
    async def test_null_pool_ignores_config_pool_settings(self) -> None:
        """Test environment (NullPool) does not use pool settings from config."""
        from promptgrimoire.db.engine import _state

        original_engine = _state.engine
        original_factory = _state.session_factory
        _state.engine = None
        _state.session_factory = None

        custom_settings = _settings_with_pool(pool_size=999)

        try:
            with (
                patch(
                    "promptgrimoire.db.engine.get_settings",
                    return_value=custom_settings,
                ),
                patch(
                    "promptgrimoire.db.engine._is_test_environment",
                    return_value=True,
                ),
                patch(
                    "promptgrimoire.db.engine.create_async_engine",
                    return_value=MagicMock(sync_engine=MagicMock(pool=MagicMock())),
                ) as mock_create,
                patch("promptgrimoire.db.engine._install_pool_listeners"),
            ):
                from promptgrimoire.db.engine import init_db

                await init_db()

                call_kwargs = mock_create.call_args[1]
                assert "pool_size" not in call_kwargs
                assert "max_overflow" not in call_kwargs
        finally:
            _state.engine = None
            _state.session_factory = None
            _state.engine = original_engine
            _state.session_factory = original_factory

    @pytest.mark.asyncio
    async def test_init_db_logs_pool_config(self) -> None:
        """init_db logs pool_size and max_overflow on startup."""
        from promptgrimoire.db.engine import _state

        original_engine = _state.engine
        original_factory = _state.session_factory
        _state.engine = None
        _state.session_factory = None

        custom_settings = _settings_with_pool(pool_size=42, max_overflow=7)

        try:
            with (
                patch(
                    "promptgrimoire.db.engine.get_settings",
                    return_value=custom_settings,
                ),
                patch(
                    "promptgrimoire.db.engine.create_async_engine",
                    return_value=MagicMock(sync_engine=MagicMock(pool=MagicMock())),
                ),
                patch("promptgrimoire.db.engine._install_pool_listeners"),
                patch("promptgrimoire.db.engine.logger") as mock_logger,
            ):
                from promptgrimoire.db.engine import init_db

                await init_db()

                mock_logger.info.assert_any_call(
                    "pool_configured",
                    pool_size=42,
                    max_overflow=7,
                )
        finally:
            _state.engine = None
            _state.session_factory = None
            _state.engine = original_engine
            _state.session_factory = original_factory
