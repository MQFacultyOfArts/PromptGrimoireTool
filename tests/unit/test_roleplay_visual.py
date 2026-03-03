"""Unit tests for roleplay page visual integration.

Tests avatar parameter wiring in _create_chat_message().
Verifies AC1.2 (user avatar) and AC1.3 (AI avatar).

Also tests that _render_messages() passes the correct avatar constants
to _create_chat_message() for each turn type (AC1.2/AC1.3 call-site wiring).

Tests export button initial disabled state (AC3.4).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from promptgrimoire.models import Character, Session


def _make_mock_container() -> MagicMock:
    """Return a MagicMock that works as a `with` context manager."""
    container = MagicMock()
    container.__enter__ = MagicMock(return_value=container)
    container.__exit__ = MagicMock(return_value=False)
    return container


def _make_mock_scroll_area() -> MagicMock:
    """Return a MagicMock with a scroll_to method."""
    scroll_area = MagicMock()
    scroll_area.scroll_to = MagicMock()
    return scroll_area


class TestRenderMessagesAvatarWiring:
    """Tests that _render_messages passes correct avatar constants.

    Verifies the call-site wiring — that _USER_AVATAR is used for user
    turns and _AI_AVATAR for AI turns — not just that the constants
    exist on _create_chat_message's signature.
    """

    @patch("promptgrimoire.pages.roleplay._create_chat_message")
    def test_user_turn_gets_user_avatar(self, mock_create: MagicMock) -> None:
        """AC1.2: _render_messages passes _USER_AVATAR for user turns."""
        from promptgrimoire.pages.roleplay import _USER_AVATAR, _render_messages

        character = Character(name="Becky Bennett")
        session = Session(character=character, user_name="Jane")
        session.add_turn("Hello there", is_user=True)

        container = _make_mock_container()
        scroll_area = _make_mock_scroll_area()

        _render_messages(session, container, scroll_area)

        # Exactly one turn — should be called once
        mock_create.assert_called_once()
        _, _, kwargs = mock_create.mock_calls[0]
        assert kwargs.get("avatar") == _USER_AVATAR

    @patch("promptgrimoire.pages.roleplay._create_chat_message")
    def test_ai_turn_gets_ai_avatar(self, mock_create: MagicMock) -> None:
        """AC1.3: _render_messages passes _AI_AVATAR for AI turns."""
        from promptgrimoire.pages.roleplay import _AI_AVATAR, _render_messages

        character = Character(name="Becky Bennett")
        session = Session(character=character, user_name="Jane")
        session.add_turn("Hi, I'm Becky.", is_user=False)

        container = _make_mock_container()
        scroll_area = _make_mock_scroll_area()

        _render_messages(session, container, scroll_area)

        mock_create.assert_called_once()
        _, _, kwargs = mock_create.mock_calls[0]
        assert kwargs.get("avatar") == _AI_AVATAR

    @patch("promptgrimoire.pages.roleplay._create_chat_message")
    def test_mixed_turns_get_correct_avatars(self, mock_create: MagicMock) -> None:
        """Both avatar constants used when session has user and AI turns."""
        from promptgrimoire.pages.roleplay import (
            _AI_AVATAR,
            _USER_AVATAR,
            _render_messages,
        )

        character = Character(name="Becky Bennett")
        session = Session(character=character, user_name="Jane")
        session.add_turn("Hello there", is_user=True)
        session.add_turn("Hi, I'm Becky.", is_user=False)

        container = _make_mock_container()
        scroll_area = _make_mock_scroll_area()

        _render_messages(session, container, scroll_area)

        assert mock_create.call_count == 2
        calls = mock_create.mock_calls
        # First call: user turn
        _, _, kwargs0 = calls[0]
        assert kwargs0.get("avatar") == _USER_AVATAR
        # Second call: AI turn
        _, _, kwargs1 = calls[1]
        assert kwargs1.get("avatar") == _AI_AVATAR


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


class TestExportButtonState:
    """Tests for export button disabled state.

    The button's initial state is controlled by
    ``_EXPORT_BTN_INITIAL_DISABLED`` (consumed at roleplay.py:430
    via ``if _EXPORT_BTN_INITIAL_DISABLED: ...disable()``).
    NiceGUI button construction requires a running client context,
    so we verify both the constant and its consumption site.
    """

    def test_export_button_disabled_without_session(self) -> None:
        """AC3.4: Export button starts disabled when no session is active."""
        from promptgrimoire.pages.roleplay import _EXPORT_BTN_INITIAL_DISABLED

        assert _EXPORT_BTN_INITIAL_DISABLED is True

    def test_constant_is_consumed_in_page_function(self) -> None:
        """Verify _EXPORT_BTN_INITIAL_DISABLED is referenced in roleplay_page source."""
        import inspect

        from promptgrimoire.pages.roleplay import roleplay_page

        source = inspect.getsource(roleplay_page)
        assert "_EXPORT_BTN_INITIAL_DISABLED" in source
