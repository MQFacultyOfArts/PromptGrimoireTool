"""Tests for IdleConfig sub-model in pydantic-settings.

Verifies:
- AC5.1: IDLE__TIMEOUT_SECONDS=900 sets idle timeout to 15 min
- AC5.2: IDLE__WARNING_SECONDS=120 sets warning to 2 min
- AC5.3: IDLE__ENABLED=false disables idle eviction entirely
- AC5.4: Defaults are 1800s timeout, 60s warning, enabled=true
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from promptgrimoire.config import IdleConfig, Settings

if TYPE_CHECKING:
    import pytest


class TestIdleConfig:
    """IdleConfig sub-model tests."""

    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """idle-tab-eviction-471.AC5.4: correct defaults."""
        for key in list(os.environ):
            if key.startswith("IDLE__"):
                monkeypatch.delenv(key, raising=False)
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert isinstance(s.idle, IdleConfig)
        assert s.idle.timeout_seconds == 1800
        assert s.idle.warning_seconds == 60
        assert s.idle.enabled is True

    def test_timeout_override_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """idle-tab-eviction-471.AC5.1: IDLE__TIMEOUT_SECONDS=900 overrides."""
        monkeypatch.setenv("IDLE__TIMEOUT_SECONDS", "900")
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.idle.timeout_seconds == 900

    def test_warning_override_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """idle-tab-eviction-471.AC5.2: IDLE__WARNING_SECONDS=120 overrides."""
        monkeypatch.setenv("IDLE__WARNING_SECONDS", "120")
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.idle.warning_seconds == 120

    def test_enabled_false_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """idle-tab-eviction-471.AC5.3: IDLE__ENABLED=false disables."""
        monkeypatch.setenv("IDLE__ENABLED", "false")
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.idle.enabled is False

    def test_idle_config_direct(self) -> None:
        """IdleConfig accepts keyword arguments."""
        cfg = IdleConfig(timeout_seconds=900, warning_seconds=120, enabled=False)
        assert cfg.timeout_seconds == 900
        assert cfg.warning_seconds == 120
        assert cfg.enabled is False
