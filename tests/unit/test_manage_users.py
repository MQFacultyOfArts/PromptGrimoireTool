"""Tests for admin CLI — Typer command wrappers and async command handlers.

Tests argument forwarding via CliRunner and command error paths.
DB functions are already tested in their own suites; these tests mock
the DB layer and verify CLI output behaviour.
"""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from rich.console import Console
from typer.testing import CliRunner

from promptgrimoire.cli import app
from promptgrimoire.cli.admin import (
    _cmd_admin,
    _cmd_enroll,
    _cmd_list,
    _cmd_show,
    _format_last_login,
)

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
        assert _format_last_login(None) == "Never"

    def test_datetime_returns_formatted(self) -> None:
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
        con, buf = _capture_console()

        with patch(f"{_USERS}.list_all_users", new_callable=AsyncMock) as mock:
            mock.return_value = []
            await _cmd_list(include_all=True, console=con)

        output = buf.getvalue()
        assert "No users" in output


class TestCmdShow:
    """admin show — user details and enrollments."""

    @pytest.mark.anyio
    async def test_show_user_not_found(self) -> None:
        con, buf = _capture_console()

        with patch(f"{_USERS}.get_user_by_email", new_callable=AsyncMock) as mock:
            mock.return_value = None
            with pytest.raises(SystemExit):
                await _cmd_show("nobody@example.com", console=con)

        output = buf.getvalue()
        assert "nobody@example.com" in output

    @pytest.mark.anyio
    async def test_show_displays_enrollments(self) -> None:
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
        con, _buf = _capture_console()

        with patch(f"{_USERS}.get_user_by_email", new_callable=AsyncMock) as mock:
            mock.return_value = None
            with pytest.raises(SystemExit):
                await _cmd_admin("nobody@example.com", console=con)

    @pytest.mark.anyio
    async def test_admin_set(self) -> None:
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
    """admin enroll — enrol user in course."""

    @pytest.mark.anyio
    async def test_enroll_course_not_found(self) -> None:
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


# ---------------------------------------------------------------------------
# enroll-bulk — CliRunner argument forwarding (Layer 1)
# ---------------------------------------------------------------------------


class TestEnrollBulkCliRunner:
    """Verify Typer argument forwarding for enroll-bulk command."""

    def test_enroll_bulk_positionals_and_defaults(self) -> None:
        """Positional args forwarded; defaults applied."""
        with patch(f"{_CLI}._cmd_enroll_bulk", new_callable=AsyncMock) as mock:
            result = runner.invoke(
                app,
                ["admin", "enroll-bulk", "/tmp/test.xlsx", "LAWS1100", "2026-S1"],
            )
            assert result.exit_code == 0
            from pathlib import Path

            mock.assert_called_once_with(
                Path("/tmp/test.xlsx"),
                "LAWS1100",
                "2026-S1",
                role="student",
                force=False,
            )

    def test_enroll_bulk_role_option(self) -> None:
        """--role option forwarded."""
        with patch(f"{_CLI}._cmd_enroll_bulk", new_callable=AsyncMock) as mock:
            result = runner.invoke(
                app,
                [
                    "admin",
                    "enroll-bulk",
                    "/tmp/test.xlsx",
                    "LAWS1100",
                    "2026-S1",
                    "--role",
                    "tutor",
                ],
            )
            assert result.exit_code == 0
            from pathlib import Path

            mock.assert_called_once_with(
                Path("/tmp/test.xlsx"),
                "LAWS1100",
                "2026-S1",
                role="tutor",
                force=False,
            )

    def test_enroll_bulk_force_flag(self) -> None:
        """--force flag forwarded."""
        with patch(f"{_CLI}._cmd_enroll_bulk", new_callable=AsyncMock) as mock:
            result = runner.invoke(
                app,
                [
                    "admin",
                    "enroll-bulk",
                    "/tmp/test.xlsx",
                    "LAWS1100",
                    "2026-S1",
                    "--force",
                ],
            )
            assert result.exit_code == 0
            from pathlib import Path

            mock.assert_called_once_with(
                Path("/tmp/test.xlsx"),
                "LAWS1100",
                "2026-S1",
                role="student",
                force=True,
            )

    def test_enroll_bulk_appears_in_help(self) -> None:
        """enroll-bulk listed in admin --help."""
        result = runner.invoke(app, ["admin", "--help"])
        assert result.exit_code == 0
        assert "enroll-bulk" in result.output


# ---------------------------------------------------------------------------
# enroll-bulk — handler logic (Layer 2)
# ---------------------------------------------------------------------------

_ENROL_XLSX = "promptgrimoire.enrol.xlsx_parser"
_ENROL_DB = "promptgrimoire.db.enrolment"


def _mock_xlsx_file() -> MagicMock:
    """Build a mock Path-like object whose read_bytes returns dummy data."""
    f = MagicMock(spec=Path)
    f.read_bytes.return_value = b"fake xlsx bytes"
    return f


def _make_enrolment_report(
    entries_processed: int = 3,
    users_created: int = 2,
    users_existing: int = 1,
    enrolments_created: int = 2,
    enrolments_skipped: int = 1,
    groups_created: int = 1,
    group_memberships_created: int = 2,
    student_ids_overwritten: int = 0,
    student_id_warnings: tuple[tuple[str, str, str], ...] = (),
) -> MagicMock:
    """Build a mock EnrolmentReport."""
    report = MagicMock()
    report.entries_processed = entries_processed
    report.users_created = users_created
    report.users_existing = users_existing
    report.enrolments_created = enrolments_created
    report.enrolments_skipped = enrolments_skipped
    report.groups_created = groups_created
    report.group_memberships_created = group_memberships_created
    report.student_ids_overwritten = student_ids_overwritten
    report.student_id_warnings = student_id_warnings
    return report


class TestCmdEnrollBulk:
    """admin enroll-bulk — handler logic with mocked DB."""

    @pytest.mark.anyio
    async def test_success_prints_summary_table(self) -> None:
        """AC6.1: Successful enrol prints Rich summary table."""
        from promptgrimoire.cli.admin import _cmd_enroll_bulk

        con, buf = _capture_console()
        course = _make_course()
        report = _make_enrolment_report()

        with (
            patch(f"{_CLI}._find_course", new_callable=AsyncMock) as mock_find,
            patch(f"{_ENROL_XLSX}.parse_xlsx") as mock_parse,
            patch(f"{_ENROL_DB}.bulk_enrol", new_callable=AsyncMock) as mock_enrol,
        ):
            mock_parse.return_value = [MagicMock()]
            mock_find.return_value = course
            mock_enrol.return_value = report

            await _cmd_enroll_bulk(
                _mock_xlsx_file(), "LAWS1100", "2026-S1", console=con
            )

        output = buf.getvalue()
        assert "Enrolment Summary" in output
        assert "2" in output  # users_created
        assert "1" in output  # users_existing

    @pytest.mark.anyio
    async def test_course_not_found_exits(self) -> None:
        """AC6.2: Non-existent course exits with code 1."""
        from promptgrimoire.cli.admin import _cmd_enroll_bulk

        con, buf = _capture_console()

        with (
            patch(f"{_CLI}._find_course", new_callable=AsyncMock) as mock_find,
            patch(f"{_ENROL_XLSX}.parse_xlsx") as mock_parse,
        ):
            mock_parse.return_value = [MagicMock()]
            mock_find.return_value = None

            with pytest.raises(SystemExit):
                await _cmd_enroll_bulk(
                    _mock_xlsx_file(), "NOPE999", "2026-S1", console=con
                )

        output = buf.getvalue()
        assert "Error" in output

    @pytest.mark.anyio
    async def test_parse_error_exits_with_line_numbers(self) -> None:
        """AC6.3: Parse errors printed with line numbers, exit code 1."""
        from promptgrimoire.cli.admin import _cmd_enroll_bulk
        from promptgrimoire.enrol.xlsx_parser import EnrolmentParseError

        con, buf = _capture_console()
        errors = ["Row 2: invalid email 'bad'", "Row 5: invalid email ''"]

        with patch(f"{_ENROL_XLSX}.parse_xlsx") as mock_parse:
            mock_parse.side_effect = EnrolmentParseError(errors)

            with pytest.raises(SystemExit):
                await _cmd_enroll_bulk(
                    _mock_xlsx_file(), "LAWS1100", "2026-S1", console=con
                )

        output = buf.getvalue()
        assert "Row 2" in output
        assert "Row 5" in output

    @pytest.mark.anyio
    async def test_student_id_conflict_exits_with_force_suggestion(self) -> None:
        """AC6.4: Student ID conflicts printed, suggests --force, exit code 1."""
        from promptgrimoire.cli.admin import _cmd_enroll_bulk
        from promptgrimoire.db.enrolment import StudentIdConflictError

        con, buf = _capture_console()
        course = _make_course()
        conflicts = [("alice@uni.edu", "OLD123", "NEW456")]

        with (
            patch(f"{_CLI}._find_course", new_callable=AsyncMock) as mock_find,
            patch(f"{_ENROL_XLSX}.parse_xlsx") as mock_parse,
            patch(f"{_ENROL_DB}.bulk_enrol", new_callable=AsyncMock) as mock_enrol,
        ):
            mock_parse.return_value = [MagicMock()]
            mock_find.return_value = course
            mock_enrol.side_effect = StudentIdConflictError(conflicts)

            with pytest.raises(SystemExit):
                await _cmd_enroll_bulk(
                    _mock_xlsx_file(), "LAWS1100", "2026-S1", console=con
                )

        output = buf.getvalue()
        assert "alice@uni.edu" in output
        assert "OLD123" in output
        assert "NEW456" in output
        assert "--force" in output

    @pytest.mark.anyio
    async def test_force_with_overwrites_prints_warnings(self) -> None:
        """AC6.5: --force with overwritten IDs prints warning lines."""
        from promptgrimoire.cli.admin import _cmd_enroll_bulk

        con, buf = _capture_console()
        course = _make_course()
        warnings = (("bob@uni.edu", "OLD999", "NEW111"),)
        report = _make_enrolment_report(
            student_ids_overwritten=1,
            student_id_warnings=warnings,
        )

        with (
            patch(f"{_CLI}._find_course", new_callable=AsyncMock) as mock_find,
            patch(f"{_ENROL_XLSX}.parse_xlsx") as mock_parse,
            patch(f"{_ENROL_DB}.bulk_enrol", new_callable=AsyncMock) as mock_enrol,
        ):
            mock_parse.return_value = [MagicMock()]
            mock_find.return_value = course
            mock_enrol.return_value = report

            await _cmd_enroll_bulk(
                _mock_xlsx_file(),
                "LAWS1100",
                "2026-S1",
                force=True,
                console=con,
            )

        output = buf.getvalue()
        assert "bob@uni.edu" in output
        assert "OLD999" in output
        assert "NEW111" in output
        assert "Student IDs overwritten" in output
