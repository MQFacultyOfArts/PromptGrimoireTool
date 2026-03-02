"""Tests for admin CLI — Typer command wrappers and async command handlers.

Tests argument forwarding via CliRunner and command error paths.
DB functions are already tested in their own suites; these tests mock
the DB layer and verify CLI output behaviour.
"""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from rich.console import Console
from typer.testing import CliRunner

from promptgrimoire.cli import app

# Patch targets — functions are imported locally inside each _cmd_* function,
# so we patch at the source module.
_USERS = "promptgrimoire.db.users"
_COURSES = "promptgrimoire.db.courses"
_CLI = "promptgrimoire.cli.admin"

runner = CliRunner()


# ---------------------------------------------------------------------------
# Format helpers (pure)
# ---------------------------------------------------------------------------


class TestFormatLastLogin:
    """_format_last_login returns human-readable login status."""

    def test_none_returns_never(self) -> None:
        from promptgrimoire.cli.admin import _format_last_login

        assert _format_last_login(None) == "Never"

    def test_datetime_returns_formatted(self) -> None:
        from promptgrimoire.cli.admin import _format_last_login

        dt = datetime(2026, 2, 16, 10, 30, 0, tzinfo=UTC)
        result = _format_last_login(dt)
        assert "2026-02-16" in result


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_user(
    email: str = "test@example.com",
    display_name: str = "Test User",
    is_admin: bool = False,
    last_login: datetime | None = None,
) -> MagicMock:
    """Build a mock User-like object for testing CLI output."""
    user = MagicMock()
    user.id = uuid4()
    user.email = email
    user.display_name = display_name
    user.is_admin = is_admin
    user.last_login = last_login
    return user


def _make_course(
    code: str = "LAWS1100",
    name: str = "Torts",
    semester: str = "2026-S1",
) -> MagicMock:
    """Build a mock Course-like object."""
    course = MagicMock()
    course.id = uuid4()
    course.code = code
    course.name = name
    course.semester = semester
    return course


def _make_enrollment(course_id=None, user_id=None, role: str = "student") -> MagicMock:
    """Build a mock CourseEnrollment-like object."""
    enrollment = MagicMock()
    enrollment.id = uuid4()
    enrollment.course_id = course_id or uuid4()
    enrollment.user_id = user_id or uuid4()
    enrollment.role = role
    return enrollment


def _capture_console() -> tuple[Console, StringIO]:
    """Create a Rich Console that writes to a StringIO buffer."""
    buf = StringIO()
    return Console(file=buf, width=120, force_terminal=False), buf


# ---------------------------------------------------------------------------
# CliRunner argument forwarding tests (AC5.5 + AC5.7)
# ---------------------------------------------------------------------------


class TestAdminCliRunner:
    """Verify Typer argument semantics via CliRunner.

    Replaces argparse parser tests.
    """

    def test_admin_help_shows_all_subcommands(self) -> None:
        """AC5.5: CliRunner help test for grimoire admin."""
        result = runner.invoke(app, ["admin", "--help"])
        assert result.exit_code == 0
        for cmd in (
            "list",
            "show",
            "create",
            "admin",
            "instructor",
            "enroll",
            "unenroll",
            "role",
        ):
            assert cmd in result.output

    def test_admin_remove_flag_forwarded(self) -> None:
        """AC5.7: --remove flag is received by _cmd_admin."""
        with patch(f"{_CLI}._cmd_admin", new_callable=AsyncMock) as mock:
            result = runner.invoke(app, ["admin", "admin", "user@test.com", "--remove"])
            assert result.exit_code == 0
            mock.assert_called_once_with("user@test.com", remove=True)

    def test_admin_default_no_remove(self) -> None:
        """AC5.7: --remove defaults to False."""
        with patch(f"{_CLI}._cmd_admin", new_callable=AsyncMock) as mock:
            result = runner.invoke(app, ["admin", "admin", "user@test.com"])
            assert result.exit_code == 0
            mock.assert_called_once_with("user@test.com", remove=False)

    def test_show_positional_email(self) -> None:
        """AC5.7: positional email argument works for show."""
        with patch(f"{_CLI}._cmd_show", new_callable=AsyncMock) as mock:
            result = runner.invoke(app, ["admin", "show", "alice@example.com"])
            assert result.exit_code == 0
            mock.assert_called_once_with("alice@example.com")

    def test_enroll_positionals_and_role(self) -> None:
        """AC5.7: enroll forwards 3 positional args and --role option."""
        with patch(f"{_CLI}._cmd_enroll", new_callable=AsyncMock) as mock:
            result = runner.invoke(
                app,
                [
                    "admin",
                    "enroll",
                    "u@ex.com",
                    "LAWS1100",
                    "2026-S1",
                    "--role",
                    "tutor",
                ],
            )
            assert result.exit_code == 0
            mock.assert_called_once_with(
                "u@ex.com", "LAWS1100", "2026-S1", role="tutor"
            )

    def test_enroll_default_role_student(self) -> None:
        """AC5.7: enroll defaults --role to 'student'."""
        with patch(f"{_CLI}._cmd_enroll", new_callable=AsyncMock) as mock:
            result = runner.invoke(
                app, ["admin", "enroll", "u@ex.com", "LAWS1100", "2026-S1"]
            )
            assert result.exit_code == 0
            mock.assert_called_once_with(
                "u@ex.com", "LAWS1100", "2026-S1", role="student"
            )

    def test_unenroll_positionals(self) -> None:
        """AC5.7: unenroll forwards 3 positional args."""
        with patch(f"{_CLI}._cmd_unenroll", new_callable=AsyncMock) as mock:
            result = runner.invoke(
                app, ["admin", "unenroll", "u@ex.com", "LAWS1100", "2026-S1"]
            )
            assert result.exit_code == 0
            mock.assert_called_once_with("u@ex.com", "LAWS1100", "2026-S1")

    def test_role_positionals(self) -> None:
        """AC5.7: role forwards 4 positional args."""
        with patch(f"{_CLI}._cmd_role", new_callable=AsyncMock) as mock:
            result = runner.invoke(
                app, ["admin", "role", "u@ex.com", "LAWS1100", "2026-S1", "instructor"]
            )
            assert result.exit_code == 0
            mock.assert_called_once_with(
                "u@ex.com", "LAWS1100", "2026-S1", "instructor"
            )

    def test_list_all_flag(self) -> None:
        """AC5.7: list --all flag is forwarded."""
        with patch(f"{_CLI}._cmd_list", new_callable=AsyncMock) as mock:
            result = runner.invoke(app, ["admin", "list", "--all"])
            assert result.exit_code == 0
            mock.assert_called_once_with(include_all=True)

    def test_list_default_no_all(self) -> None:
        """AC5.7: list defaults --all to False."""
        with patch(f"{_CLI}._cmd_list", new_callable=AsyncMock) as mock:
            result = runner.invoke(app, ["admin", "list"])
            assert result.exit_code == 0
            mock.assert_called_once_with(include_all=False)

    def test_create_positional_and_name_option(self) -> None:
        """AC5.7: create forwards positional email and --name option."""
        with patch(f"{_CLI}._cmd_create", new_callable=AsyncMock) as mock:
            result = runner.invoke(
                app, ["admin", "create", "new@test.com", "--name", "New User"]
            )
            assert result.exit_code == 0
            mock.assert_called_once_with("new@test.com", name="New User")

    def test_instructor_remove_flag(self) -> None:
        """AC5.7: instructor --remove flag is forwarded."""
        with patch(f"{_CLI}._cmd_instructor", new_callable=AsyncMock) as mock:
            result = runner.invoke(
                app, ["admin", "instructor", "teach@uni.edu", "--remove"]
            )
            assert result.exit_code == 0
            mock.assert_called_once_with("teach@uni.edu", remove=True)


# ---------------------------------------------------------------------------
# Command handlers (mock DB layer, verify output)
# ---------------------------------------------------------------------------


class TestCmdList:
    """admin list — tabular user output."""

    @pytest.mark.anyio
    async def test_list_shows_user_emails(self) -> None:
        from promptgrimoire.cli.admin import _cmd_list

        con, buf = _capture_console()
        user = _make_user(email="alice@uni.edu", display_name="Alice", is_admin=True)

        with patch(f"{_USERS}.list_all_users", new_callable=AsyncMock) as mock:
            mock.return_value = [user]
            await _cmd_list(include_all=True, console=con)

        output = buf.getvalue()
        assert "alice@uni.edu" in output
        assert "Alice" in output

    @pytest.mark.anyio
    async def test_list_empty(self) -> None:
        from promptgrimoire.cli.admin import _cmd_list

        con, buf = _capture_console()

        with patch(f"{_USERS}.list_all_users", new_callable=AsyncMock) as mock:
            mock.return_value = []
            await _cmd_list(include_all=True, console=con)

        output = buf.getvalue()
        assert "No users" in output


class TestCmdShow:
    """manage-users show — user details and enrollments."""

    @pytest.mark.anyio
    async def test_show_user_not_found(self) -> None:
        from promptgrimoire.cli.admin import _cmd_show

        con, buf = _capture_console()

        with patch(f"{_USERS}.get_user_by_email", new_callable=AsyncMock) as mock:
            mock.return_value = None
            with pytest.raises(SystemExit):
                await _cmd_show("nobody@example.com", console=con)

        output = buf.getvalue()
        assert "nobody@example.com" in output

    @pytest.mark.anyio
    async def test_show_displays_enrollments(self) -> None:
        from promptgrimoire.cli.admin import _cmd_show

        con, buf = _capture_console()
        user = _make_user(email="bob@uni.edu", display_name="Bob")
        course = _make_course()
        enrollment = _make_enrollment(
            course_id=course.id, user_id=user.id, role="tutor"
        )

        with (
            patch(f"{_USERS}.get_user_by_email", new_callable=AsyncMock) as mock_user,
            patch(
                f"{_COURSES}.list_user_enrollments", new_callable=AsyncMock
            ) as mock_enroll,
            patch(
                f"{_COURSES}.get_course_by_id", new_callable=AsyncMock
            ) as mock_course,
        ):
            mock_user.return_value = user
            mock_enroll.return_value = [enrollment]
            mock_course.return_value = course
            await _cmd_show("bob@uni.edu", console=con)

        output = buf.getvalue()
        assert "bob@uni.edu" in output
        assert "LAWS1100" in output
        assert "tutor" in output


class TestCmdAdmin:
    """admin admin — set/remove admin status."""

    @pytest.mark.anyio
    async def test_admin_user_not_found(self) -> None:
        from promptgrimoire.cli.admin import _cmd_admin

        con, _buf = _capture_console()

        with patch(f"{_USERS}.get_user_by_email", new_callable=AsyncMock) as mock:
            mock.return_value = None
            with pytest.raises(SystemExit):
                await _cmd_admin("nobody@example.com", console=con)

    @pytest.mark.anyio
    async def test_admin_set(self) -> None:
        from promptgrimoire.cli.admin import _cmd_admin

        con, _buf = _capture_console()
        user = _make_user(is_admin=False)

        with (
            patch(f"{_USERS}.get_user_by_email", new_callable=AsyncMock) as mock_get,
            patch(f"{_USERS}.set_admin", new_callable=AsyncMock) as mock_set,
            patch(
                f"{_CLI}._update_stytch_metadata",
                new_callable=AsyncMock,
            ) as mock_stytch,
        ):
            mock_get.return_value = user
            mock_set.return_value = user
            mock_stytch.return_value = True
            await _cmd_admin(user.email, console=con)

        mock_set.assert_called_once_with(user.id, True)
        mock_stytch.assert_called_once_with(user, {"is_admin": True}, console=con)

    @pytest.mark.anyio
    async def test_admin_remove(self) -> None:
        from promptgrimoire.cli.admin import _cmd_admin

        con, _buf = _capture_console()
        user = _make_user(is_admin=True)

        with (
            patch(f"{_USERS}.get_user_by_email", new_callable=AsyncMock) as mock_get,
            patch(f"{_USERS}.set_admin", new_callable=AsyncMock) as mock_set,
            patch(
                f"{_CLI}._update_stytch_metadata",
                new_callable=AsyncMock,
            ) as mock_stytch,
        ):
            mock_get.return_value = user
            mock_set.return_value = user
            mock_stytch.return_value = True
            await _cmd_admin(user.email, remove=True, console=con)

        mock_set.assert_called_once_with(user.id, False)
        mock_stytch.assert_called_once_with(user, {"is_admin": False}, console=con)


class TestCmdEnroll:
    """manage-users enroll — enrol user in course."""

    @pytest.mark.anyio
    async def test_enroll_course_not_found(self) -> None:
        from promptgrimoire.cli.admin import _cmd_enroll

        con, _buf = _capture_console()
        user = _make_user()

        with (
            patch(f"{_USERS}.get_user_by_email", new_callable=AsyncMock) as mock_user,
            patch(f"{_CLI}._find_course", new_callable=AsyncMock) as mock_course,
        ):
            mock_user.return_value = user
            mock_course.return_value = None
            with pytest.raises(SystemExit):
                await _cmd_enroll(user.email, "NOPE999", "2026-S1", console=con)

    @pytest.mark.anyio
    async def test_enroll_success(self) -> None:
        from promptgrimoire.cli.admin import _cmd_enroll

        con, buf = _capture_console()
        user = _make_user()
        course = _make_course()

        with (
            patch(f"{_USERS}.get_user_by_email", new_callable=AsyncMock) as mock_user,
            patch(f"{_CLI}._find_course", new_callable=AsyncMock) as mock_find,
            patch(f"{_COURSES}.enroll_user", new_callable=AsyncMock) as mock_enroll,
        ):
            mock_user.return_value = user
            mock_find.return_value = course
            mock_enroll.return_value = _make_enrollment()
            await _cmd_enroll(
                user.email, "LAWS1100", "2026-S1", role="tutor", console=con
            )

        mock_enroll.assert_called_once_with(
            course_id=course.id, user_id=user.id, role="tutor"
        )
        output = buf.getvalue()
        assert "Enrolled" in output
