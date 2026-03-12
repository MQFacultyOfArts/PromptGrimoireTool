"""Unit tests for the bulk enrolment upload handler in courses.py.

Tests _handle_enrol_upload in isolation with mocked NiceGUI and DB.

Traceability:
- Issue: #320 (Bulk Student Enrolment)
- AC: AC7.1 (success notification), AC7.2 (parse error), AC7.3 (conflict error)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

_COURSES = "promptgrimoire.pages.courses"


def _make_course() -> MagicMock:
    """Build a mock Course-like object."""
    course = MagicMock()
    course.id = uuid4()
    course.code = "LAWS1100"
    course.name = "Torts"
    return course


def _make_upload_event(data: bytes = b"fake xlsx") -> MagicMock:
    """Build a mock UploadEventArguments with async file.read()."""
    event = MagicMock()
    event.file.read = AsyncMock(return_value=data)
    event.file.name = "grades.xlsx"
    return event


def _make_enrolment_report(
    entries_processed: int = 2,
    users_created: int = 1,
    users_existing: int = 1,
    enrolments_created: int = 2,
    enrolments_skipped: int = 0,
    groups_created: int = 0,
    group_memberships_created: int = 0,
    student_ids_overwritten: int = 0,
    student_id_warnings: tuple = (),
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


class TestHandleEnrolUploadSuccess:
    """AC7.1: Successful parse + enrol shows positive notification."""

    @pytest.mark.anyio
    async def test_success_notifies_positive(self) -> None:
        from promptgrimoire.pages.courses import _handle_enrol_upload

        course = _make_course()
        event = _make_upload_event()
        report = _make_enrolment_report()

        with (
            patch(f"{_COURSES}.parse_xlsx") as mock_parse,
            patch(f"{_COURSES}.bulk_enrol", new_callable=AsyncMock) as mock_enrol,
            patch(f"{_COURSES}.ui") as mock_ui,
        ):
            mock_parse.return_value = [MagicMock()]
            mock_enrol.return_value = report

            await _handle_enrol_upload(event, course, force=False)

        mock_ui.notify.assert_called_once()
        call_kwargs = mock_ui.notify.call_args
        assert call_kwargs.kwargs.get("type") == "positive" or (
            len(call_kwargs.args) >= 1 and call_kwargs[1].get("type") == "positive"
        )

    @pytest.mark.anyio
    async def test_success_message_includes_summary(self) -> None:
        from promptgrimoire.pages.courses import _handle_enrol_upload

        course = _make_course()
        event = _make_upload_event()
        report = _make_enrolment_report(
            entries_processed=3, enrolments_created=2, enrolments_skipped=1
        )

        with (
            patch(f"{_COURSES}.parse_xlsx") as mock_parse,
            patch(f"{_COURSES}.bulk_enrol", new_callable=AsyncMock) as mock_enrol,
            patch(f"{_COURSES}.ui") as mock_ui,
        ):
            mock_parse.return_value = [MagicMock()]
            mock_enrol.return_value = report

            await _handle_enrol_upload(event, course, force=False)

        msg = mock_ui.notify.call_args.args[0]
        assert "3" in msg  # entries_processed
        assert "2" in msg  # enrolments_created

    @pytest.mark.anyio
    async def test_all_duplicates_shows_info_not_positive(self) -> None:
        """Re-upload with all existing students shows info notification."""
        from promptgrimoire.pages.courses import _handle_enrol_upload

        course = _make_course()
        event = _make_upload_event()
        report = _make_enrolment_report(
            entries_processed=50,
            enrolments_created=0,
            enrolments_skipped=50,
            users_created=0,
            users_existing=50,
        )

        with (
            patch(f"{_COURSES}.parse_xlsx") as mock_parse,
            patch(f"{_COURSES}.bulk_enrol", new_callable=AsyncMock) as mock_enrol,
            patch(f"{_COURSES}.ui") as mock_ui,
        ):
            mock_parse.return_value = [MagicMock()]
            mock_enrol.return_value = report

            await _handle_enrol_upload(event, course, force=False)

        call_kwargs = mock_ui.notify.call_args
        assert call_kwargs.kwargs.get("type") == "info"
        msg = call_kwargs.args[0]
        assert "0" in msg
        assert "50 already enrolled" in msg


class TestHandleEnrolUploadParseError:
    """AC7.2: EnrolmentParseError shows warning notification."""

    @pytest.mark.anyio
    async def test_parse_error_notifies_warning(self) -> None:
        from promptgrimoire.enrol.xlsx_parser import EnrolmentParseError
        from promptgrimoire.pages.courses import _handle_enrol_upload

        course = _make_course()
        event = _make_upload_event()

        with (
            patch(f"{_COURSES}.parse_xlsx") as mock_parse,
            patch(f"{_COURSES}.ui") as mock_ui,
        ):
            mock_parse.side_effect = EnrolmentParseError(["Row 2: invalid email 'bad'"])

            await _handle_enrol_upload(event, course, force=False)

        mock_ui.notify.assert_called_once()
        call_kwargs = mock_ui.notify.call_args
        assert call_kwargs.kwargs.get("type") == "warning"
        msg = call_kwargs.args[0]
        assert "Row 2" in msg


class TestHandleEnrolUploadConflict:
    """AC7.3: StudentIdConflictError shows negative notification."""

    @pytest.mark.anyio
    async def test_conflict_error_notifies_negative(self) -> None:
        from promptgrimoire.db.enrolment import StudentIdConflictError
        from promptgrimoire.pages.courses import _handle_enrol_upload

        course = _make_course()
        event = _make_upload_event()
        conflicts = [("alice@uni.edu", "OLD123", "NEW456")]

        with (
            patch(f"{_COURSES}.parse_xlsx") as mock_parse,
            patch(f"{_COURSES}.bulk_enrol", new_callable=AsyncMock) as mock_enrol,
            patch(f"{_COURSES}.ui") as mock_ui,
        ):
            mock_parse.return_value = [MagicMock()]
            mock_enrol.side_effect = StudentIdConflictError(conflicts)

            await _handle_enrol_upload(event, course, force=False)

        mock_ui.notify.assert_called_once()
        call_kwargs = mock_ui.notify.call_args
        assert call_kwargs.kwargs.get("type") == "negative"
        msg = call_kwargs.args[0]
        assert "alice@uni.edu" in msg

    @pytest.mark.anyio
    async def test_conflict_message_includes_ids(self) -> None:
        from promptgrimoire.db.enrolment import StudentIdConflictError
        from promptgrimoire.pages.courses import _handle_enrol_upload

        course = _make_course()
        event = _make_upload_event()
        conflicts = [("bob@uni.edu", "SID001", "SID999")]

        with (
            patch(f"{_COURSES}.parse_xlsx") as mock_parse,
            patch(f"{_COURSES}.bulk_enrol", new_callable=AsyncMock) as mock_enrol,
            patch(f"{_COURSES}.ui") as mock_ui,
        ):
            mock_parse.return_value = [MagicMock()]
            mock_enrol.side_effect = StudentIdConflictError(conflicts)

            await _handle_enrol_upload(event, course, force=False)

        msg = mock_ui.notify.call_args.args[0]
        assert "SID001" in msg or "SID999" in msg
