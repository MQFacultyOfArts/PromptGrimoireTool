"""Tests for help button rendering logic in layout.py.

Verifies:
- AC5.1: Help button renders when help_enabled=True
- AC5.2 (routing): Algolia path called when help_backend="algolia"
- AC5.4: No UI calls when help_enabled=False
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from promptgrimoire.config import HelpConfig
from promptgrimoire.pages.layout import _render_help_button


class TestHelpButtonDisabled:
    """AC5.4: When help_enabled=False, no help button is rendered."""

    @patch("promptgrimoire.pages.layout._render_algolia_help")
    @patch("promptgrimoire.pages.layout._render_mkdocs_help")
    @patch("promptgrimoire.pages.layout.get_settings")
    def test_disabled_returns_early_no_ui_calls(
        self,
        mock_settings: MagicMock,
        mock_mkdocs: MagicMock,
        mock_algolia: MagicMock,
    ) -> None:
        """help_enabled=False causes early return with no rendering calls."""
        mock_settings.return_value.help = HelpConfig(help_enabled=False)
        _render_help_button()
        mock_algolia.assert_not_called()
        mock_mkdocs.assert_not_called()


class TestHelpButtonAlgolia:
    """AC5.2 (routing): Algolia path is called when configured."""

    @patch("promptgrimoire.pages.layout._render_algolia_help")
    @patch("promptgrimoire.pages.layout._render_mkdocs_help")
    @patch("promptgrimoire.pages.layout.get_settings")
    def test_algolia_backend_calls_algolia_renderer(
        self,
        mock_settings: MagicMock,
        mock_mkdocs: MagicMock,
        mock_algolia: MagicMock,
    ) -> None:
        """help_backend='algolia' routes to _render_algolia_help."""
        help_config = HelpConfig(
            help_enabled=True,
            help_backend="algolia",
            algolia_app_id="test-app",
            algolia_search_api_key="test-key",
            algolia_index_name="test-index",
        )
        mock_settings.return_value.help = help_config
        _render_help_button()
        mock_algolia.assert_called_once_with(help_config)
        mock_mkdocs.assert_not_called()


class TestHelpButtonMkdocs:
    """AC5.1/AC5.3: MkDocs path is called when configured."""

    @patch("promptgrimoire.pages.layout._render_algolia_help")
    @patch("promptgrimoire.pages.layout._render_mkdocs_help")
    @patch("promptgrimoire.pages.layout.get_settings")
    def test_mkdocs_backend_calls_mkdocs_renderer(
        self,
        mock_settings: MagicMock,
        mock_mkdocs: MagicMock,
        mock_algolia: MagicMock,
    ) -> None:
        """help_backend='mkdocs' routes to _render_mkdocs_help."""
        mock_settings.return_value.help = HelpConfig(
            help_enabled=True,
            help_backend="mkdocs",
        )
        _render_help_button()
        mock_mkdocs.assert_called_once()
        mock_algolia.assert_not_called()
