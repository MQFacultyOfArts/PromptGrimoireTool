"""Tests for configuration sub-models in pydantic-settings.

Verifies:
- AC7.2: unit_label is configurable via pydantic-settings, defaults to "Unit".
- infra-split.AC7.1: worker_in_process defaults to True.
- infra-split.AC7.2: FEATURES__WORKER_IN_PROCESS=false overrides to False.
- Export config: max_concurrent_compilations defaults to 2, configurable via env.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from promptgrimoire.config import (
    DatabaseConfig,
    ExportConfig,
    FeaturesConfig,
    I18nConfig,
    Settings,
)

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


class TestExportConfig:
    """ExportConfig sub-model tests for max_concurrent_compilations."""

    def test_max_concurrent_compilations_defaults_to_2(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default max_concurrent_compilations is 2."""
        for key in list(os.environ):
            if key.startswith("EXPORT__"):
                monkeypatch.delenv(key, raising=False)
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.export.max_concurrent_compilations == 2

    def test_max_concurrent_compilations_override_via_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """EXPORT__MAX_CONCURRENT_COMPILATIONS env var overrides the default."""
        monkeypatch.setenv("EXPORT__MAX_CONCURRENT_COMPILATIONS", "1")
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.export.max_concurrent_compilations == 1

    def test_export_config_direct(self) -> None:
        """ExportConfig accepts max_concurrent_compilations kwarg."""
        cfg = ExportConfig(max_concurrent_compilations=3)
        assert cfg.max_concurrent_compilations == 3


class TestDatabaseConfig:
    """DatabaseConfig sub-model tests for use_null_pool flag.

    Verifies:
    - infra-split.AC2.1: DATABASE__USE_NULL_POOL=true overrides to True
    - infra-split.AC2.2: use_null_pool defaults to False
    """

    def test_use_null_pool_defaults_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """infra-split.AC2.2: use_null_pool defaults to False."""
        for key in list(os.environ):
            if key.startswith("DATABASE__"):
                monkeypatch.delenv(key, raising=False)
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.database.use_null_pool is False

    def test_use_null_pool_true_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """infra-split.AC2.1: DATABASE__USE_NULL_POOL=true overrides to True."""
        monkeypatch.setenv("DATABASE__USE_NULL_POOL", "true")
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.database.use_null_pool is True

    def test_database_config_direct(self) -> None:
        """DatabaseConfig accepts use_null_pool kwarg."""
        cfg = DatabaseConfig(use_null_pool=True)
        assert cfg.use_null_pool is True
