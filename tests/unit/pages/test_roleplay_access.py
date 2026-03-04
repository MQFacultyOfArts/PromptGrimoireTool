"""Unit tests for standalone roleplay page access guards."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from promptgrimoire.pages import logviewer, roleplay, roleplay_access


class TestRequireRoleplayPageAccess:
    """Verify the shared standalone roleplay access guard."""

    def test_redirects_unauthenticated_user_to_login(self) -> None:
        """Unauthenticated users are sent to login instead of seeing the page."""
        with (
            patch(
                "promptgrimoire.pages.roleplay_access._get_session_user",
                return_value=None,
            ),
            patch("promptgrimoire.pages.roleplay_access.ui") as mock_ui,
        ):
            assert roleplay_access.require_roleplay_page_access() is False

            mock_ui.navigate.to.assert_called_once_with("/login")
            mock_ui.notify.assert_not_called()

    def test_shows_negative_for_non_privileged_user(self) -> None:
        """Authenticated students get a negative notification and stay put."""
        with (
            patch(
                "promptgrimoire.pages.roleplay_access._get_session_user",
                return_value={
                    "email": "student@example.edu",
                    "is_admin": False,
                    "roles": [],
                },
            ),
            patch("promptgrimoire.pages.roleplay_access.ui") as mock_ui,
        ):
            assert roleplay_access.require_roleplay_page_access() is False

            mock_ui.notify.assert_called_once_with(
                "Roleplay is restricted",
                type="negative",
            )
            mock_ui.navigate.to.assert_not_called()

    def test_allows_privileged_user(self) -> None:
        """Privileged users retain standalone roleplay page access."""
        with (
            patch(
                "promptgrimoire.pages.roleplay_access._get_session_user",
                return_value={
                    "email": "staff@example.edu",
                    "is_admin": False,
                    "roles": ["instructor"],
                },
            ),
            patch("promptgrimoire.pages.roleplay_access.ui") as mock_ui,
        ):
            assert roleplay_access.require_roleplay_page_access() is True

            mock_ui.notify.assert_not_called()
            mock_ui.navigate.to.assert_not_called()


class TestRoleplayPagesUseSharedAccessGuard:
    """Verify standalone roleplay pages stop before rendering when denied."""

    async def test_roleplay_page_stops_when_access_guard_denies(self) -> None:
        """The roleplay UI does not render when standalone access is denied."""
        assert hasattr(roleplay, "require_roleplay_page_access")

        with (
            patch("promptgrimoire.pages.roleplay.ui") as mock_ui,
            patch(
                "promptgrimoire.pages.roleplay.require_roleplay_enabled",
                return_value=True,
            ),
            patch(
                "promptgrimoire.pages.roleplay.require_roleplay_page_access",
                return_value=False,
            ) as mock_access,
            patch("promptgrimoire.pages.roleplay.page_layout") as mock_layout,
        ):
            mock_ui.context.client.connected = AsyncMock()

            await roleplay.roleplay_page()

            mock_access.assert_called_once_with()
            mock_layout.assert_not_called()

    async def test_logs_page_stops_when_access_guard_denies(self) -> None:
        """The log viewer does not render when standalone access is denied."""
        assert hasattr(logviewer, "require_roleplay_page_access")

        with (
            patch("promptgrimoire.pages.logviewer.ui") as mock_ui,
            patch(
                "promptgrimoire.pages.logviewer.require_roleplay_enabled",
                return_value=True,
            ),
            patch(
                "promptgrimoire.pages.logviewer.require_roleplay_page_access",
                return_value=False,
            ) as mock_access,
        ):
            mock_ui.context.client.connected = AsyncMock()

            await logviewer.logs_page()

            mock_access.assert_called_once_with()
            mock_ui.label.assert_not_called()
