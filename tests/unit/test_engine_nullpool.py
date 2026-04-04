"""Tests for NullPool toggle in init_db().

Verifies:
- infra-split.AC2.1: DATABASE__USE_NULL_POOL=true causes NullPool
- infra-split.AC2.2: Default (false) uses QueuePool kwargs
- infra-split.AC2.3: _pool_status() handles NullPool without errors
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from sqlalchemy.pool import NullPool

from promptgrimoire.db.engine import _pool_status

if TYPE_CHECKING:
    import pytest


class TestPoolStatusWithNullPool:
    """infra-split.AC2.3: _pool_status() does not error with NullPool."""

    def test_pool_status_nullpool_returns_question_marks(self) -> None:
        """NullPool lacks size/checkedin/etc — _pool_status returns '?' values."""
        pool = NullPool(creator=lambda: None)
        result = _pool_status(pool)
        assert "size=?" in result
        assert "checked_in=?" in result
        assert "checked_out=?" in result


class TestInitDbPoolSelection:
    """infra-split.AC2.1 and AC2.2: pool selection based on config flag."""

    async def _run_init_db_with_captured_kwargs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> dict[str, object]:
        """Reset engine state and capture create_async_engine kwargs."""
        from promptgrimoire.db import engine as engine_mod

        # Reset module state so init_db() actually runs
        monkeypatch.setattr(engine_mod, "_state", engine_mod._DatabaseState())

        captured_kwargs: dict[str, object] = {}

        mock_engine = AsyncMock()
        mock_engine.sync_engine.pool = NullPool(creator=lambda: None)

        def fake_create_async_engine(_url: str, **kwargs: object) -> AsyncMock:
            captured_kwargs.update(kwargs)
            return mock_engine

        monkeypatch.setattr(engine_mod, "create_async_engine", fake_create_async_engine)

        # Need a database URL
        monkeypatch.setenv("DATABASE__URL", "postgresql+asyncpg://test@localhost/test")

        await engine_mod.init_db()
        return captured_kwargs

    async def test_nullpool_when_config_flag_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """infra-split.AC2.1: DATABASE__USE_NULL_POOL=true -> NullPool."""
        monkeypatch.delenv("_PROMPTGRIMOIRE_USE_NULL_POOL", raising=False)
        monkeypatch.setenv("DATABASE__USE_NULL_POOL", "true")

        from promptgrimoire.config import Settings

        # Force settings reload
        monkeypatch.setattr(
            "promptgrimoire.db.engine.get_settings",
            lambda: Settings(_env_file=None),  # type: ignore[call-arg]
        )

        kwargs = await self._run_init_db_with_captured_kwargs(monkeypatch)
        assert kwargs.get("poolclass") is NullPool
        # QueuePool kwargs must NOT be present
        assert "pool_size" not in kwargs
        assert "max_overflow" not in kwargs
        assert "pool_pre_ping" not in kwargs
        assert "pool_recycle" not in kwargs

    async def test_queuepool_when_config_flag_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """infra-split.AC2.2: Default (use_null_pool=False) -> QueuePool kwargs."""
        monkeypatch.delenv("_PROMPTGRIMOIRE_USE_NULL_POOL", raising=False)
        monkeypatch.delenv("DATABASE__USE_NULL_POOL", raising=False)

        from promptgrimoire.config import Settings

        monkeypatch.setattr(
            "promptgrimoire.db.engine.get_settings",
            lambda: Settings(_env_file=None),  # type: ignore[call-arg]
        )

        kwargs = await self._run_init_db_with_captured_kwargs(monkeypatch)
        assert "poolclass" not in kwargs
        assert "pool_size" in kwargs
        assert "max_overflow" in kwargs

    async def test_nullpool_when_test_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test environment flag also triggers NullPool (existing behavior)."""
        monkeypatch.setenv("_PROMPTGRIMOIRE_USE_NULL_POOL", "1")
        monkeypatch.delenv("DATABASE__USE_NULL_POOL", raising=False)
        monkeypatch.delenv("_PROMPTGRIMOIRE_WORKER_NULLPOOL", raising=False)

        from promptgrimoire.config import Settings

        monkeypatch.setattr(
            "promptgrimoire.db.engine.get_settings",
            lambda: Settings(_env_file=None),  # type: ignore[call-arg]
        )

        kwargs = await self._run_init_db_with_captured_kwargs(monkeypatch)
        assert kwargs.get("poolclass") is NullPool

    async def test_nullpool_when_worker_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Worker override env var triggers NullPool independently of config."""
        monkeypatch.delenv("_PROMPTGRIMOIRE_USE_NULL_POOL", raising=False)
        monkeypatch.delenv("DATABASE__USE_NULL_POOL", raising=False)
        monkeypatch.setenv("_PROMPTGRIMOIRE_WORKER_NULLPOOL", "1")

        from promptgrimoire.config import Settings

        monkeypatch.setattr(
            "promptgrimoire.db.engine.get_settings",
            lambda: Settings(_env_file=None),  # type: ignore[call-arg]
        )

        kwargs = await self._run_init_db_with_captured_kwargs(monkeypatch)
        assert kwargs.get("poolclass") is NullPool
