"""Unit tests for roleplay page visual integration.

Tests avatar parameter wiring in _create_chat_message().
Verifies AC1.2 (user avatar) and AC1.3 (AI avatar).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestAvatarParameter:
    """Tests for avatar parameter in _create_chat_message."""

    @patch("promptgrimoire.pages.roleplay.ui")
    def test_user_message_passes_user_avatar(self, mock_ui: MagicMock) -> None:
        """AC1.2: _create_chat_message(sent=True) passes user avatar URL."""
        mock_msg = MagicMock()
        mock_ui.chat_message.return_value = mock_msg
        mock_msg.__enter__ = MagicMock(return_value=mock_msg)
        mock_msg.__exit__ = MagicMock(return_value=False)
        mock_md = MagicMock()
        mock_ui.markdown.return_value = mock_md
        mock_md.classes.return_value = mock_md

        from promptgrimoire.pages.roleplay import _create_chat_message

        _create_chat_message(
            "Hello",
            "Jane",
            sent=True,
            avatar="/static/roleplay/user-default.png",
        )
        mock_ui.chat_message.assert_called_once_with(
            name="Jane", sent=True, avatar="/static/roleplay/user-default.png"
        )

    @patch("promptgrimoire.pages.roleplay.ui")
    def test_ai_message_passes_ai_avatar(self, mock_ui: MagicMock) -> None:
        """AC1.3: _create_chat_message(sent=False) passes AI avatar URL."""
        mock_msg = MagicMock()
        mock_ui.chat_message.return_value = mock_msg
        mock_msg.__enter__ = MagicMock(return_value=mock_msg)
        mock_msg.__exit__ = MagicMock(return_value=False)
        mock_md = MagicMock()
        mock_ui.markdown.return_value = mock_md
        mock_md.classes.return_value = mock_md

        from promptgrimoire.pages.roleplay import _create_chat_message

        _create_chat_message(
            "Hi there",
            "Becky Bennett",
            sent=False,
            avatar="/static/roleplay/becky-bennett.png",
        )
        mock_ui.chat_message.assert_called_once_with(
            name="Becky Bennett",
            sent=False,
            avatar="/static/roleplay/becky-bennett.png",
        )

    @patch("promptgrimoire.pages.roleplay.ui")
    def test_avatar_defaults_to_none(self, mock_ui: MagicMock) -> None:
        """Backward compat: omitting avatar passes avatar=None."""
        mock_msg = MagicMock()
        mock_ui.chat_message.return_value = mock_msg
        mock_msg.__enter__ = MagicMock(return_value=mock_msg)
        mock_msg.__exit__ = MagicMock(return_value=False)
        mock_md = MagicMock()
        mock_ui.markdown.return_value = mock_md
        mock_md.classes.return_value = mock_md

        from promptgrimoire.pages.roleplay import _create_chat_message

        _create_chat_message("Test", "User", sent=True)
        mock_ui.chat_message.assert_called_once_with(
            name="User", sent=True, avatar=None
        )
