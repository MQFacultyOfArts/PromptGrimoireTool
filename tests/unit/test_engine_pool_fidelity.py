"""Tests for the production-fidelity pool override in init_db().

The E2E harness forces NullPool (``_PROMPTGRIMOIRE_USE_NULL_POOL=1``) so
xdist workers do not share asyncpg connection state.  A perf run needs the
opposite: QueuePool with the configured sizing, so the measured topology
matches production behind PgBouncer.  ``_PROMPTGRIMOIRE_POOL_FIDELITY=1``
is that opt-in.

Verified here:
- fidelity defeats the test-harness forcing (QueuePool, configured sizing);
- fidelity does not defeat the standalone-worker override;
- fidelity does not defeat explicit ``DATABASE__USE_NULL_POOL``;
- only the exact value ``"1"`` counts;
- the chosen mode is logged with a reason that names the deciding input.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import structlog
from sqlalchemy.pool import NullPool

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    import pytest


def _dummy_creator() -> Any:
    """Stand in for a DBAPI connection factory; never invoked."""
    return None


async def _init_db_capturing(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, object], list[MutableMapping[str, Any]]]:
    """Run init_db() with a fake engine factory and captured structlog events.

    Returns the kwargs handed to ``create_async_engine`` together with the
    structlog events emitted during the call.
    """
    from promptgrimoire.config import Settings
    from promptgrimoire.db import engine as engine_mod

    monkeypatch.setattr(engine_mod, "_state", engine_mod._DatabaseState())
    monkeypatch.setattr(
        "promptgrimoire.db.engine.get_settings",
        lambda: Settings(_env_file=None),  # type: ignore[call-arg]
    )
    monkeypatch.setenv("DATABASE__URL", "postgresql+asyncpg://test@localhost/test")

    captured_kwargs: dict[str, object] = {}
    mock_engine = AsyncMock()
    mock_engine.sync_engine.pool = NullPool(creator=_dummy_creator)

    def fake_create_async_engine(_url: str, **kwargs: object) -> AsyncMock:
        captured_kwargs.update(kwargs)
        return mock_engine

    monkeypatch.setattr(engine_mod, "create_async_engine", fake_create_async_engine)

    with structlog.testing.capture_logs() as events:
        await engine_mod.init_db()
    return captured_kwargs, events


def _pool_mode_event(
    events: list[MutableMapping[str, Any]],
) -> MutableMapping[str, Any]:
    """Return the single db_pool_mode event, failing loudly if it is absent."""
    matches = [e for e in events if e.get("event") == "db_pool_mode"]
    assert len(matches) == 1, f"expected one db_pool_mode event, got {matches}"
    return matches[0]


def _clear_pool_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start each case from no pool-selection input at all."""
    for name in (
        "_PROMPTGRIMOIRE_USE_NULL_POOL",
        "_PROMPTGRIMOIRE_WORKER_NULLPOOL",
        "_PROMPTGRIMOIRE_POOL_FIDELITY",
        "DATABASE__USE_NULL_POOL",
    ):
        monkeypatch.delenv(name, raising=False)


class TestPoolFidelityOverride:
    """_PROMPTGRIMOIRE_POOL_FIDELITY=1 crosses from forced NullPool to QueuePool."""

    async def test_fidelity_beats_test_environment_forcing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fidelity set under the test harness selects configured QueuePool."""
        _clear_pool_env(monkeypatch)
        monkeypatch.setenv("_PROMPTGRIMOIRE_USE_NULL_POOL", "1")
        monkeypatch.setenv("_PROMPTGRIMOIRE_POOL_FIDELITY", "1")
        monkeypatch.setenv("DATABASE__POOL_SIZE", "17")
        monkeypatch.setenv("DATABASE__MAX_OVERFLOW", "7")

        kwargs, events = await _init_db_capturing(monkeypatch)

        assert "poolclass" not in kwargs
        assert kwargs["pool_size"] == 17
        assert kwargs["max_overflow"] == 7
        event = _pool_mode_event(events)
        assert event["mode"] == "QueuePool"
        assert event["reason"] == "pool_fidelity"

    async def test_without_fidelity_test_environment_still_forces_nullpool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unset fidelity leaves today's forced-NullPool behaviour intact."""
        _clear_pool_env(monkeypatch)
        monkeypatch.setenv("_PROMPTGRIMOIRE_USE_NULL_POOL", "1")

        kwargs, events = await _init_db_capturing(monkeypatch)

        assert kwargs["poolclass"] is NullPool
        assert "pool_size" not in kwargs
        event = _pool_mode_event(events)
        assert event["mode"] == "NullPool"
        assert event["reason"] == "test"

    async def test_fidelity_requires_exact_value_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A non-"1" value is not an opt-in; the harness forcing still wins."""
        _clear_pool_env(monkeypatch)
        monkeypatch.setenv("_PROMPTGRIMOIRE_USE_NULL_POOL", "1")
        monkeypatch.setenv("_PROMPTGRIMOIRE_POOL_FIDELITY", "0")

        kwargs, events = await _init_db_capturing(monkeypatch)

        assert kwargs["poolclass"] is NullPool
        assert _pool_mode_event(events)["reason"] == "test"

    async def test_worker_override_outranks_fidelity(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The standalone export worker keeps NullPool even under fidelity."""
        _clear_pool_env(monkeypatch)
        monkeypatch.setenv("_PROMPTGRIMOIRE_WORKER_NULLPOOL", "1")
        monkeypatch.setenv("_PROMPTGRIMOIRE_POOL_FIDELITY", "1")

        kwargs, events = await _init_db_capturing(monkeypatch)

        assert kwargs["poolclass"] is NullPool
        assert _pool_mode_event(events)["reason"] == "worker_override"

    async def test_explicit_config_outranks_fidelity(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DATABASE__USE_NULL_POOL is an operator decision, not harness forcing."""
        _clear_pool_env(monkeypatch)
        monkeypatch.setenv("DATABASE__USE_NULL_POOL", "true")
        monkeypatch.setenv("_PROMPTGRIMOIRE_POOL_FIDELITY", "1")

        kwargs, events = await _init_db_capturing(monkeypatch)

        assert kwargs["poolclass"] is NullPool
        assert _pool_mode_event(events)["reason"] == "config"

    async def test_plain_run_reports_default_queuepool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no pool env input at all the reason distinguishes from fidelity."""
        _clear_pool_env(monkeypatch)

        kwargs, events = await _init_db_capturing(monkeypatch)

        assert "poolclass" not in kwargs
        event = _pool_mode_event(events)
        assert event["mode"] == "QueuePool"
        assert event["reason"] == "default"
