"""Tests for configuration sub-models in pydantic-settings.

Verifies:
- AC7.2: unit_label is configurable via pydantic-settings, defaults to "Unit".
- infra-split.AC7.1: worker_in_process defaults to True.
- infra-split.AC7.2: FEATURES__WORKER_IN_PROCESS=false overrides to False.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from promptgrimoire.config import FeaturesConfig, I18nConfig, Settings

if TYPE_CHECKING:
    import pytest


class TestI18nConfig:
    """I18nConfig sub-model tests."""

    def test_default_unit_label_is_unit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default unit_label is 'Unit'."""
        # Clear any env vars that might interfere
        for key in list(os.environ):
            if key.startswith("I18N__"):
                monkeypatch.delenv(key, raising=False)
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.i18n.unit_label == "Unit"

    def test_override_unit_label(self) -> None:
        """I18nConfig accepts custom unit_label."""
        cfg = I18nConfig(unit_label="Course")
        assert cfg.unit_label == "Course"

    def test_override_via_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """I18N__UNIT_LABEL env var overrides the default."""
        monkeypatch.setenv("I18N__UNIT_LABEL", "Course")
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.i18n.unit_label == "Course"


class TestFeaturesConfig:
    """FeaturesConfig sub-model tests for worker_in_process flag."""

    def test_worker_in_process_defaults_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """infra-split.AC7.1: worker_in_process defaults to True."""
        for key in list(os.environ):
            if key.startswith("FEATURES__"):
                monkeypatch.delenv(key, raising=False)
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.features.worker_in_process is True

    def test_worker_in_process_false_via_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """infra-split.AC7.2: FEATURES__WORKER_IN_PROCESS=false overrides to False."""
        monkeypatch.setenv("FEATURES__WORKER_IN_PROCESS", "false")
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.features.worker_in_process is False

    def test_worker_in_process_direct(self) -> None:
        """FeaturesConfig accepts worker_in_process kwarg."""
        cfg = FeaturesConfig(worker_in_process=False)
        assert cfg.worker_in_process is False
