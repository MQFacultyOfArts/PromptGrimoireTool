"""Tests for admin ban and unban CLI commands."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import typer
from rich.console import Console

from promptgrimoire.auth.models import SessionResult


def _make_user(
    *,
    email: str = "target@test.com",
    is_admin: bool = False,
    stytch_member_id: str | None = "mock-member-abc",
) -> MagicMock:
    """Create a mock User object."""
    user = MagicMock()
    user.id = uuid4()
    user.email = email
    user.display_name = email.split("@", maxsplit=1)[0]
    user.is_admin = is_admin
    user.stytch_member_id = stytch_member_id
    user.is_banned = False
    user.banned_at = None
    return user


class TestCmdBan:
    """Tests for _cmd_ban handler."""

    @patch("promptgrimoire.config.get_settings")
    @patch("promptgrimoire.auth.get_auth_client")
    @patch("promptgrimoire.cli.admin._update_stytch_metadata", new_callable=AsyncMock)
    @patch("promptgrimoire.db.users.set_banned", new_callable=AsyncMock)
    @patch("promptgrimoire.cli.admin._require_user", new_callable=AsyncMock)
    async def test_ban_sets_db_state_and_stytch(
        self,
        mock_require_user: AsyncMock,
        mock_set_banned: AsyncMock,
        mock_update_stytch: AsyncMock,
        mock_get_auth: MagicMock,
        mock_get_settings: MagicMock,
    ) -> None:
        """AC1.3: ban calls set_banned(True) and updates Stytch metadata."""
        from promptgrimoire.cli.admin import _cmd_ban

        user = _make_user()
        mock_require_user.return_value = user
        mock_update_stytch.return_value = True

        auth_client = AsyncMock()
        auth_client.revoke_member_sessions.return_value = SessionResult(valid=True)
        mock_get_auth.return_value = auth_client

        settings = MagicMock()
        settings.admin.admin_api_secret.get_secret_value.return_value = ""
        mock_get_settings.return_value = settings

        con = Console(file=MagicMock())
        await _cmd_ban("target@test.com", console=con)

        mock_set_banned.assert_awaited_once_with(user.id, True)
        mock_update_stytch.assert_awaited_once_with(
            user, {"banned": "true"}, console=con
        )

    @patch("promptgrimoire.config.get_settings")
    @patch("promptgrimoire.auth.get_auth_client")
    @patch("promptgrimoire.cli.admin._update_stytch_metadata", new_callable=AsyncMock)
    @patch("promptgrimoire.db.users.set_banned", new_callable=AsyncMock)
    @patch("promptgrimoire.cli.admin._require_user", new_callable=AsyncMock)
    async def test_ban_revokes_sessions(
        self,
        mock_require_user: AsyncMock,
        _mock_set_banned: AsyncMock,
        mock_update_stytch: AsyncMock,
        mock_get_auth: MagicMock,
        mock_get_settings: MagicMock,
    ) -> None:
        """AC4.1: ban calls revoke_member_sessions for the member."""
        from promptgrimoire.cli.admin import _cmd_ban

        user = _make_user(stytch_member_id="member-xyz")
        mock_require_user.return_value = user
        mock_update_stytch.return_value = True

        auth_client = AsyncMock()
        auth_client.revoke_member_sessions.return_value = SessionResult(valid=True)
        mock_get_auth.return_value = auth_client

        settings = MagicMock()
        settings.admin.admin_api_secret.get_secret_value.return_value = ""
        mock_get_settings.return_value = settings

        con = Console(file=MagicMock())
        await _cmd_ban("target@test.com", console=con)

        auth_client.revoke_member_sessions.assert_awaited_once_with(
            member_id="member-xyz"
        )

    @patch("promptgrimoire.config.get_settings")
    @patch("promptgrimoire.auth.get_auth_client")
    @patch("promptgrimoire.cli.admin._update_stytch_metadata", new_callable=AsyncMock)
    @patch("promptgrimoire.db.users.set_banned", new_callable=AsyncMock)
    @patch("promptgrimoire.cli.admin._require_user", new_callable=AsyncMock)
    async def test_ban_without_stytch_member_id_warns(
        self,
        mock_require_user: AsyncMock,
        mock_set_banned: AsyncMock,
        mock_update_stytch: AsyncMock,
        mock_get_auth: MagicMock,
        mock_get_settings: MagicMock,
    ) -> None:
        """AC4.2: ban with missing stytch_member_id warns but continues."""
        from io import StringIO

        from promptgrimoire.cli.admin import _cmd_ban

        user = _make_user(stytch_member_id=None)
        mock_require_user.return_value = user
        mock_update_stytch.return_value = True

        auth_client = AsyncMock()
        mock_get_auth.return_value = auth_client

        settings = MagicMock()
        settings.admin.admin_api_secret.get_secret_value.return_value = ""
        mock_get_settings.return_value = settings

        output = StringIO()
        con = Console(file=output, force_terminal=False)
        await _cmd_ban("target@test.com", console=con)

        # Ban DB call still happens
        mock_set_banned.assert_awaited_once_with(user.id, True)
        # Session revocation NOT called
        auth_client.revoke_member_sessions.assert_not_awaited()
        # Warning in output
        text = output.getvalue()
        assert "skipping session revocation" in text.lower()

    @patch("promptgrimoire.config.get_settings")
    @patch("promptgrimoire.auth.get_auth_client")
    @patch("promptgrimoire.cli.admin._update_stytch_metadata", new_callable=AsyncMock)
    @patch("promptgrimoire.db.users.set_banned", new_callable=AsyncMock)
    @patch("promptgrimoire.cli.admin._require_user", new_callable=AsyncMock)
    async def test_ban_admin_user_warns(
        self,
        mock_require_user: AsyncMock,
        mock_set_banned: AsyncMock,
        mock_update_stytch: AsyncMock,
        mock_get_auth: MagicMock,
        mock_get_settings: MagicMock,
    ) -> None:
        """Ban of admin user prints warning but proceeds."""
        from io import StringIO

        from promptgrimoire.cli.admin import _cmd_ban

        user = _make_user(is_admin=True)
        mock_require_user.return_value = user
        mock_update_stytch.return_value = True

        auth_client = AsyncMock()
        auth_client.revoke_member_sessions.return_value = SessionResult(valid=True)
        mock_get_auth.return_value = auth_client

        settings = MagicMock()
        settings.admin.admin_api_secret.get_secret_value.return_value = ""
        mock_get_settings.return_value = settings

        output = StringIO()
        con = Console(file=output, force_terminal=False)
        await _cmd_ban("target@test.com", console=con)

        # Warning printed
        text = output.getvalue()
        assert "admin" in text.lower()
        # Ban still applied
        mock_set_banned.assert_awaited_once()

    @patch("promptgrimoire.config.get_settings")
    @patch("promptgrimoire.auth.get_auth_client")
    @patch("promptgrimoire.cli.admin._update_stytch_metadata", new_callable=AsyncMock)
    @patch("promptgrimoire.db.users.set_banned", new_callable=AsyncMock)
    @patch("promptgrimoire.cli.admin._require_user", new_callable=AsyncMock)
    async def test_ban_with_kick_endpoint(
        self,
        mock_require_user: AsyncMock,
        _mock_set_banned: AsyncMock,
        mock_update_stytch: AsyncMock,
        mock_get_auth: MagicMock,
        mock_get_settings: MagicMock,
    ) -> None:
        """Ban calls kick endpoint when ADMIN_API_SECRET is set."""
        from io import StringIO

        from promptgrimoire.cli.admin import _cmd_ban

        user = _make_user()
        mock_require_user.return_value = user
        mock_update_stytch.return_value = True

        auth_client = AsyncMock()
        auth_client.revoke_member_sessions.return_value = SessionResult(valid=True)
        mock_get_auth.return_value = auth_client

        settings = MagicMock()
        settings.admin.admin_api_secret.get_secret_value.return_value = "test-secret"
        settings.app.base_url = "http://localhost:8080"
        mock_get_settings.return_value = settings

        # Mock httpx
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"kicked": 2}

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        output = StringIO()
        con = Console(file=output, force_terminal=False)

        with patch(
            "httpx.AsyncClient",
            return_value=mock_http_client,
        ):
            await _cmd_ban("target@test.com", console=con)

        mock_http_client.post.assert_awaited_once()
        call_args = mock_http_client.post.call_args
        assert "/api/admin/kick" in call_args.args[0]
        text = output.getvalue()
        assert "2" in text  # kicked count
        assert "banned" in text.lower()


class TestCmdUnban:
    """Tests for _cmd_unban handler."""

    @patch("promptgrimoire.cli.admin._update_stytch_metadata", new_callable=AsyncMock)
    @patch("promptgrimoire.db.users.set_banned", new_callable=AsyncMock)
    @patch("promptgrimoire.cli.admin._require_user", new_callable=AsyncMock)
    async def test_unban_clears_db_state_and_stytch(
        self,
        mock_require_user: AsyncMock,
        mock_set_banned: AsyncMock,
        mock_update_stytch: AsyncMock,
    ) -> None:
        """AC1.4: unban calls set_banned(False) and clears Stytch metadata."""
        from promptgrimoire.cli.admin import _cmd_unban

        user = _make_user()
        user.is_banned = True
        user.banned_at = datetime.now(UTC)
        mock_require_user.return_value = user
        mock_update_stytch.return_value = True

        con = Console(file=MagicMock())
        await _cmd_unban("target@test.com", console=con)

        mock_set_banned.assert_awaited_once_with(user.id, False)
        mock_update_stytch.assert_awaited_once_with(user, {"banned": ""}, console=con)

    @patch("promptgrimoire.cli.admin._update_stytch_metadata", new_callable=AsyncMock)
    @patch("promptgrimoire.db.users.set_banned", new_callable=AsyncMock)
    @patch("promptgrimoire.cli.admin._require_user", new_callable=AsyncMock)
    async def test_unban_prints_success(
        self,
        mock_require_user: AsyncMock,
        _mock_set_banned: AsyncMock,
        mock_update_stytch: AsyncMock,
    ) -> None:
        """Unban prints success message."""
        from io import StringIO

        from promptgrimoire.cli.admin import _cmd_unban

        user = _make_user()
        mock_require_user.return_value = user
        mock_update_stytch.return_value = True

        output = StringIO()
        con = Console(file=output, force_terminal=False)
        await _cmd_unban("target@test.com", console=con)

        text = output.getvalue()
        assert "unbanned" in text.lower()
        assert "target@test.com" in text


class TestBanTyperCommands:
    """Tests for Typer command dispatch."""

    @patch("promptgrimoire.cli.admin._cmd_ban", new_callable=AsyncMock)
    def test_ban_command_dispatches(self, mock_cmd_ban: AsyncMock) -> None:  # noqa: ARG002
        """ban <email> dispatches to _cmd_ban."""
        from typer.testing import CliRunner

        from promptgrimoire.cli.admin import admin_app

        runner = CliRunner()
        app = typer.Typer()
        app.add_typer(admin_app, name="admin")
        result = runner.invoke(app, ["admin", "ban", "test@example.com"])
        assert result.exit_code == 0

    @patch("promptgrimoire.cli.admin._cmd_unban", new_callable=AsyncMock)
    def test_unban_command_dispatches(self, mock_cmd_unban: AsyncMock) -> None:  # noqa: ARG002
        """unban <email> dispatches to _cmd_unban."""
        from typer.testing import CliRunner

        from promptgrimoire.cli.admin import admin_app

        runner = CliRunner()
        app = typer.Typer()
        app.add_typer(admin_app, name="admin")
        result = runner.invoke(app, ["admin", "unban", "test@example.com"])
        assert result.exit_code == 0
