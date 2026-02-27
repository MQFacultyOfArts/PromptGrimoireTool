"""Tests for I18nConfig sub-model in pydantic-settings.

Verifies AC7.2: unit_label is configurable via pydantic-settings, defaults to "Unit".
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from promptgrimoire.config import I18nConfig, Settings

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
