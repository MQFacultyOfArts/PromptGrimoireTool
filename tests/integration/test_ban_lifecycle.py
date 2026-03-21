"""Integration test for full ban/unban lifecycle via CLI handlers.

Uses real PostgreSQL but mocks Stytch auth calls.
Requires DEV__TEST_DATABASE_URL.
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from rich.console import Console

from promptgrimoire.auth.models import MemberUpdateResult, SessionResult
from promptgrimoire.config import get_settings

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


def _unique_email() -> str:
    return f"lifecycle-{uuid4().hex[:8]}@example.com"


def _mock_settings() -> MagicMock:
    """Create mock settings with empty admin secret (skip kick)."""
    settings = MagicMock()
    settings.admin.admin_api_secret.get_secret_value.return_value = ""
    settings.stytch.default_org_id = "mock-org"
    return settings


def _mock_auth_client() -> AsyncMock:
    """Create a mock auth client that succeeds for all operations."""
    client = AsyncMock()
    client.update_member_trusted_metadata.return_value = MemberUpdateResult(
        success=True
    )
    client.revoke_member_sessions.return_value = SessionResult(valid=True)
    return client


class TestBanLifecycle:
    """Full ban -> list -> unban -> list lifecycle with real DB."""

    @pytest.mark.asyncio
    @patch("promptgrimoire.config.get_settings")
    @patch("promptgrimoire.auth.get_auth_client")
    async def test_ban_list_unban_list(
        self,
        mock_get_auth: MagicMock,
        mock_get_settings: MagicMock,
    ) -> None:
        """AC4.3 + AC5.3: full lifecycle with real DB, mocked Stytch."""
        from promptgrimoire.cli.admin import _cmd_ban, _cmd_list_banned, _cmd_unban
        from promptgrimoire.db.users import create_user, get_user_by_email

        mock_get_settings.return_value = _mock_settings()
        mock_auth = _mock_auth_client()
        mock_get_auth.return_value = mock_auth

        email = _unique_email()

        # Create user with a stytch_member_id so session revocation path is hit
        await create_user(
            email=email,
            display_name="Lifecycle Test",
            stytch_member_id="member-lifecycle-test",
        )

        # --- Ban ---
        ban_output = StringIO()
        ban_con = Console(file=ban_output, force_terminal=False)
        await _cmd_ban(email, console=ban_con)

        ban_text = ban_output.getvalue()
        assert "banned" in ban_text.lower()

        # Verify DB state
        banned_user = await get_user_by_email(email)
        assert banned_user is not None
        assert banned_user.is_banned is True
        assert banned_user.banned_at is not None

        # Verify Stytch calls
        mock_auth.update_member_trusted_metadata.assert_awaited()
        mock_auth.revoke_member_sessions.assert_awaited_once_with(
            member_id="member-lifecycle-test"
        )

        # --- List banned ---
        list_output = StringIO()
        list_con = Console(file=list_output, force_terminal=False)
        await _cmd_list_banned(console=list_con)

        list_text = list_output.getvalue()
        assert email in list_text

        # --- Unban ---
        unban_output = StringIO()
        unban_con = Console(file=unban_output, force_terminal=False)
        await _cmd_unban(email, console=unban_con)

        unban_text = unban_output.getvalue()
        assert "unbanned" in unban_text.lower()

        # Verify DB state cleared
        unbanned_user = await get_user_by_email(email)
        assert unbanned_user is not None
        assert unbanned_user.is_banned is False
        assert unbanned_user.banned_at is None

        # --- List banned again (should not contain our user) ---
        list2_output = StringIO()
        list2_con = Console(file=list2_output, force_terminal=False)
        await _cmd_list_banned(console=list2_con)

        list2_text = list2_output.getvalue()
        assert email not in list2_text
