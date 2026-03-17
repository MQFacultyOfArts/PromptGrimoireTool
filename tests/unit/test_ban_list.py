"""Tests for admin ban --list command."""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

from rich.console import Console


def _make_banned_user(
    *,
    email: str = "banned@test.com",
    display_name: str = "Banned User",
    banned_at: datetime | None = None,
) -> MagicMock:
    """Create a mock banned User object."""
    user = MagicMock()
    user.email = email
    user.display_name = display_name
    user.banned_at = banned_at or datetime(2026, 3, 17, 12, 0, tzinfo=UTC)
    return user


class TestCmdListBanned:
    """Tests for _cmd_list_banned handler."""

    @patch("promptgrimoire.db.users.get_banned_users", new_callable=AsyncMock)
    async def test_list_banned_shows_table(
        self,
        mock_get_banned: AsyncMock,
    ) -> None:
        """AC5.1: list banned shows table with email, name, timestamp."""
        from promptgrimoire.cli.admin import _cmd_list_banned

        mock_get_banned.return_value = [
            _make_banned_user(
                email="bad@test.com",
                display_name="Bad Actor",
                banned_at=datetime(2026, 3, 17, 14, 30, tzinfo=UTC),
            ),
        ]

        output = StringIO()
        con = Console(file=output, force_terminal=False)
        await _cmd_list_banned(console=con)

        text = output.getvalue()
        assert "bad@test.com" in text
        assert "Bad Actor" in text
        assert "2026-03-17" in text

    @patch("promptgrimoire.db.users.get_banned_users", new_callable=AsyncMock)
    async def test_list_banned_empty(
        self,
        mock_get_banned: AsyncMock,
    ) -> None:
        """AC5.2: no banned users shows 'No banned users.' message."""
        from promptgrimoire.cli.admin import _cmd_list_banned

        mock_get_banned.return_value = []

        output = StringIO()
        con = Console(file=output, force_terminal=False)
        await _cmd_list_banned(console=con)

        text = output.getvalue()
        assert "no banned users" in text.lower()

    @patch("promptgrimoire.db.users.get_banned_users", new_callable=AsyncMock)
    async def test_list_banned_handles_null_banned_at(
        self,
        mock_get_banned: AsyncMock,
    ) -> None:
        """Users with NULL banned_at display a dash instead of crashing."""
        from promptgrimoire.cli.admin import _cmd_list_banned

        mock_get_banned.return_value = [
            _make_banned_user(email="old@test.com", banned_at=None),
        ]

        output = StringIO()
        con = Console(file=output, force_terminal=False)
        await _cmd_list_banned(console=con)

        text = output.getvalue()
        assert "old@test.com" in text
