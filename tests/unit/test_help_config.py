"""Tests for HelpConfig sub-model in pydantic-settings.

Verifies:
- AC4.1: Fields load with correct defaults and types via HELP__ prefix
- AC4.2: Default help_enabled is False
- AC4.3: Missing Algolia credentials raise validation error when backend is algolia
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from promptgrimoire.config import HelpConfig, Settings


class TestHelpConfigDefaults:
    """AC4.1, AC4.2: Default values and field types."""

    def test_default_help_enabled_is_false(self) -> None:
        """AC4.2: help_enabled defaults to False."""
        cfg = HelpConfig()
        assert cfg.help_enabled is False

    def test_default_help_backend_is_mkdocs(self) -> None:
        """Default backend is mkdocs."""
        cfg = HelpConfig()
        assert cfg.help_backend == "mkdocs"

    def test_default_algolia_fields_are_empty(self) -> None:
        """Algolia fields default to empty strings."""
        cfg = HelpConfig()
        assert cfg.algolia_app_id == ""
        assert cfg.algolia_search_api_key == ""
        assert cfg.algolia_index_name == ""

    def test_all_fields_accept_values(self) -> None:
        """AC4.1: All fields load with correct types."""
        cfg = HelpConfig(
            help_enabled=True,
            help_backend="algolia",
            algolia_app_id="APPID123",
            algolia_search_api_key="searchkey456",
            algolia_index_name="my_index",
        )
        assert cfg.help_enabled is True
        assert cfg.help_backend == "algolia"
        assert cfg.algolia_app_id == "APPID123"
        assert cfg.algolia_search_api_key == "searchkey456"
        assert cfg.algolia_index_name == "my_index"


class TestHelpConfigOnSettings:
    """AC4.1: HelpConfig is registered on Settings with HELP__ prefix."""

    def test_settings_has_help_field(self) -> None:
        """Settings includes help sub-model with defaults."""
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert hasattr(s, "help")
        assert isinstance(s.help, HelpConfig)
        assert s.help.help_enabled is False

    def test_settings_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """HELP__ env vars override defaults via Settings."""
        monkeypatch.setenv("HELP__HELP_ENABLED", "true")
        monkeypatch.setenv("HELP__HELP_BACKEND", "mkdocs")
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.help.help_enabled is True
        assert s.help.help_backend == "mkdocs"


class TestHelpConfigAlgoliaValidation:
    """AC4.3: Algolia credentials required when backend is algolia and enabled."""

    def test_algolia_enabled_missing_all_credentials(self) -> None:
        """All three Algolia fields missing raises ValidationError."""
        with pytest.raises(ValidationError, match="algolia_app_id"):
            HelpConfig(help_enabled=True, help_backend="algolia")

    def test_algolia_enabled_missing_app_id(self) -> None:
        """Missing algolia_app_id raises ValidationError."""
        with pytest.raises(ValidationError, match="algolia_app_id"):
            HelpConfig(
                help_enabled=True,
                help_backend="algolia",
                algolia_search_api_key="key",
                algolia_index_name="idx",
            )

    def test_algolia_enabled_missing_search_api_key(self) -> None:
        """Missing algolia_search_api_key raises ValidationError."""
        with pytest.raises(ValidationError, match="algolia_search_api_key"):
            HelpConfig(
                help_enabled=True,
                help_backend="algolia",
                algolia_app_id="app",
                algolia_index_name="idx",
            )

    def test_algolia_enabled_missing_index_name(self) -> None:
        """Missing algolia_index_name raises ValidationError."""
        with pytest.raises(ValidationError, match="algolia_index_name"):
            HelpConfig(
                help_enabled=True,
                help_backend="algolia",
                algolia_app_id="app",
                algolia_search_api_key="key",
            )

    def test_algolia_enabled_with_all_credentials_succeeds(self) -> None:
        """All Algolia fields provided passes validation."""
        cfg = HelpConfig(
            help_enabled=True,
            help_backend="algolia",
            algolia_app_id="app",
            algolia_search_api_key="key",
            algolia_index_name="idx",
        )
        assert cfg.algolia_app_id == "app"

    def test_mkdocs_backend_does_not_require_algolia(self) -> None:
        """help_enabled=True with mkdocs backend needs no Algolia credentials."""
        cfg = HelpConfig(help_enabled=True, help_backend="mkdocs")
        assert cfg.help_enabled is True
        assert cfg.algolia_app_id == ""

    def test_disabled_algolia_does_not_require_credentials(self) -> None:
        """help_enabled=False with algolia backend skips credential validation."""
        cfg = HelpConfig(help_enabled=False, help_backend="algolia")
        assert cfg.help_enabled is False
        assert cfg.algolia_app_id == ""

    def test_invalid_backend_raises_validation_error(self) -> None:
        """Invalid help_backend value raises ValidationError."""
        with pytest.raises(ValidationError, match="help_backend"):
            HelpConfig(help_backend="invalid")  # type: ignore[arg-type]
