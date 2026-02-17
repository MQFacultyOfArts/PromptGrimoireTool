"""Tests for manage-users CLI — argument parsing and subcommand dispatch.

Tests parser correctness and command error paths. DB functions are
already tested in their own suites; these tests mock the DB layer
and verify CLI output behaviour.
"""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from rich.console import Console

# Patch targets — functions are imported locally inside each _cmd_* function,
# so we patch at the source module.
_USERS = "promptgrimoire.db.users"
_COURSES = "promptgrimoire.db.courses"
_CLI = "promptgrimoire.cli"


# ---------------------------------------------------------------------------
# Parser tests (pure — no mocking needed)
# ---------------------------------------------------------------------------


class TestUserParserSubcommands:
    """Parser recognises all subcommands and their arguments."""

    def _parser(self):
        from promptgrimoire.cli import _build_user_parser

        return _build_user_parser()

    def test_list_default(self) -> None:
        args = self._parser().parse_args(["list"])
        assert args.command == "list"
        assert args.all is False

    def test_list_with_all_flag(self) -> None:
        args = self._parser().parse_args(["list", "--all"])
        assert args.all is True

    def test_show_requires_email(self) -> None:
        with pytest.raises(SystemExit):
            self._parser().parse_args(["show"])

    def test_show_parses_email(self) -> None:
        args = self._parser().parse_args(["show", "user@example.com"])
        assert args.command == "show"
        assert args.email == "user@example.com"

    def test_admin_parses_email(self) -> None:
        args = self._parser().parse_args(["admin", "user@example.com"])
        assert args.command == "admin"
        assert args.email == "user@example.com"
        assert args.remove is False

    def test_admin_remove_flag(self) -> None:
        args = self._parser().parse_args(["admin", "--remove", "user@example.com"])
        assert args.remove is True

    def test_enroll_all_positionals(self) -> None:
        args = self._parser().parse_args(["enroll", "u@ex.com", "LAWS1100", "2026-S1"])
        assert args.command == "enroll"
        assert args.email == "u@ex.com"
        assert args.code == "LAWS1100"
        assert args.semester == "2026-S1"
        assert args.role == "student"

    def test_enroll_custom_role(self) -> None:
        args = self._parser().parse_args(
            ["enroll", "u@ex.com", "LAWS1100", "2026-S1", "--role", "tutor"]
        )
        assert args.role == "tutor"

    def test_unenroll_all_positionals(self) -> None:
        args = self._parser().parse_args(
            ["unenroll", "u@ex.com", "LAWS1100", "2026-S1"]
        )
        assert args.command == "unenroll"
        assert args.email == "u@ex.com"
        assert args.code == "LAWS1100"
        assert args.semester == "2026-S1"

    def test_role_all_positionals(self) -> None:
        args = self._parser().parse_args(
            ["role", "u@ex.com", "LAWS1100", "2026-S1", "instructor"]
        )
        assert args.command == "role"
        assert args.new_role == "instructor"

    def test_no_subcommand_fails(self) -> None:
        with pytest.raises(SystemExit):
            self._parser().parse_args([])


# ---------------------------------------------------------------------------
# Format helpers (pure)
# ---------------------------------------------------------------------------


class TestFormatLastLogin:
    """_format_last_login returns human-readable login status."""

    def test_none_returns_never(self) -> None:
        from promptgrimoire.cli import _format_last_login

        assert _format_last_login(None) == "Never"

    def test_datetime_returns_formatted(self) -> None:
        from promptgrimoire.cli import _format_last_login

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
# Command handlers (mock DB layer, verify output)
# ---------------------------------------------------------------------------


class TestCmdList:
    """manage-users list — tabular user output."""

    @pytest.mark.anyio
    async def test_list_shows_user_emails(self) -> None:
        from promptgrimoire.cli import _cmd_list

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
        from promptgrimoire.cli import _cmd_list

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
        from promptgrimoire.cli import _cmd_show

        con, buf = _capture_console()

        with patch(f"{_USERS}.get_user_by_email", new_callable=AsyncMock) as mock:
            mock.return_value = None
            with pytest.raises(SystemExit):
                await _cmd_show("nobody@example.com", console=con)

        output = buf.getvalue()
        assert "nobody@example.com" in output

    @pytest.mark.anyio
    async def test_show_displays_enrollments(self) -> None:
        from promptgrimoire.cli import _cmd_show

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
    """manage-users admin — set/remove admin status."""

    @pytest.mark.anyio
    async def test_admin_user_not_found(self) -> None:
        from promptgrimoire.cli import _cmd_admin

        con, _buf = _capture_console()

        with patch(f"{_USERS}.get_user_by_email", new_callable=AsyncMock) as mock:
            mock.return_value = None
            with pytest.raises(SystemExit):
                await _cmd_admin("nobody@example.com", console=con)

    @pytest.mark.anyio
    async def test_admin_set(self) -> None:
        from promptgrimoire.cli import _cmd_admin

        con, _buf = _capture_console()
        user = _make_user(is_admin=False)

        with (
            patch(f"{_USERS}.get_user_by_email", new_callable=AsyncMock) as mock_get,
            patch(f"{_USERS}.set_admin", new_callable=AsyncMock) as mock_set,
        ):
            mock_get.return_value = user
            mock_set.return_value = user
            await _cmd_admin(user.email, console=con)

        mock_set.assert_called_once_with(user.id, True)

    @pytest.mark.anyio
    async def test_admin_remove(self) -> None:
        from promptgrimoire.cli import _cmd_admin

        con, _buf = _capture_console()
        user = _make_user(is_admin=True)

        with (
            patch(f"{_USERS}.get_user_by_email", new_callable=AsyncMock) as mock_get,
            patch(f"{_USERS}.set_admin", new_callable=AsyncMock) as mock_set,
        ):
            mock_get.return_value = user
            mock_set.return_value = user
            await _cmd_admin(user.email, remove=True, console=con)

        mock_set.assert_called_once_with(user.id, False)


class TestCmdEnroll:
    """manage-users enroll — enrol user in course."""

    @pytest.mark.anyio
    async def test_enroll_course_not_found(self) -> None:
        from promptgrimoire.cli import _cmd_enroll

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
        from promptgrimoire.cli import _cmd_enroll

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
