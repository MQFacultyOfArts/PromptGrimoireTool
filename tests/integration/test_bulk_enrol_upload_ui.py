"""NiceGUI User-harness tests for the bulk enrolment upload widget.

Exercises the upload widget rendering and handler wiring on the
manage enrollments page using NiceGUI's simulated User — no browser
required.

Acceptance Criteria:
- AC7.1: Upload widget visible for instructors on manage enrollments page
- AC7.4: Upload widget not visible for students

Traceability:
- Issue: #320 (Bulk Student Enrolment)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from promptgrimoire.config import get_settings
from tests.conftest import make_xlsx_bytes
from tests.integration.conftest import _authenticate
from tests.integration.nicegui_helpers import (
    _find_by_testid,
    _should_not_see_testid,
    _should_see_testid,
)

if TYPE_CHECKING:
    from nicegui.testing.user import User

pytestmark = [
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
    pytest.mark.nicegui_ui,
]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _create_course() -> tuple[UUID, str]:
    """Create a course with a unique code. Returns (course_id, code)."""
    from promptgrimoire.db.courses import create_course

    uid = uuid4().hex[:8]
    code = f"ENRL{uid.upper()}"
    course = await create_course(
        code=code, name=f"Enrol Upload Test {uid}", semester="2026-S1"
    )
    return course.id, code


async def _enroll(course_id: UUID, email: str, role: str) -> UUID:
    """Ensure user exists and enroll them. Returns user_id."""
    from promptgrimoire.db.courses import enroll_user
    from promptgrimoire.db.users import find_or_create_user

    user_record, _ = await find_or_create_user(
        email=email, display_name=email.split("@", maxsplit=1)[0]
    )
    await enroll_user(course_id=course_id, user_id=user_record.id, role=role)
    return user_record.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBulkEnrolUploadWidget:
    """Verify upload widget rendering on the manage enrollments page."""

    @pytest.mark.asyncio
    async def test_instructor_sees_upload_widget(self, nicegui_user: User) -> None:
        """AC7.1: Instructor sees the upload widget on manage enrollments."""
        email = "instructor@uni.edu"
        await _authenticate(nicegui_user, email=email)

        course_id, _code = await _create_course()
        await _enroll(course_id, email, "instructor")

        await nicegui_user.open(f"/courses/{course_id}/enrollments")

        await _should_see_testid(nicegui_user, "enrol-upload")
        await _should_see_testid(nicegui_user, "enrol-force-checkbox")

    @pytest.mark.asyncio
    async def test_enrollment_table_visible(self, nicegui_user: User) -> None:
        """AC2.1: Enrollment table is visible after page load."""
        email = "instructor@uni.edu"
        await _authenticate(nicegui_user, email=email)

        course_id, _code = await _create_course()
        await _enroll(course_id, email, "instructor")

        await nicegui_user.open(f"/courses/{course_id}/enrollments")

        await _should_see_testid(nicegui_user, "enrollment-table")

    @pytest.mark.asyncio
    async def test_student_does_not_see_upload_widget(self, nicegui_user: User) -> None:
        """AC7.4: Students cannot see the upload widget."""
        instructor_email = "instructor@uni.edu"
        student_email = f"student-{uuid4().hex[:6]}@test.example.edu.au"

        await _authenticate(nicegui_user, email=student_email)

        course_id, _code = await _create_course()
        # Need an instructor to create the course enrollment context
        await _enroll(course_id, instructor_email, "instructor")
        await _enroll(course_id, student_email, "student")

        await nicegui_user.open(f"/courses/{course_id}/enrollments")

        await _should_not_see_testid(nicegui_user, "enrol-upload")

    @pytest.mark.asyncio
    async def test_upload_handler_fires_on_valid_xlsx(self, nicegui_user: User) -> None:
        """Upload a valid XLSX via handle_uploads and verify success notification."""
        from nicegui.elements.upload import Upload

        email = "instructor@uni.edu"
        await _authenticate(nicegui_user, email=email)

        course_id, _code = await _create_course()
        await _enroll(course_id, email, "instructor")

        await nicegui_user.open(f"/courses/{course_id}/enrollments")
        await _should_see_testid(nicegui_user, "enrol-upload")

        # Build valid XLSX bytes
        xlsx_bytes = make_xlsx_bytes(
            ["First name", "Last name", "ID number", "Email address"],
            [
                [
                    "Alice",
                    "Test",
                    "99999",
                    f"alice-{uuid4().hex[:6]}@test.example.edu.au",
                ]
            ],
        )

        # Find the upload element and simulate a file upload
        upload_el = _find_by_testid(nicegui_user, "enrol-upload")
        assert upload_el is not None
        assert isinstance(upload_el, Upload)

        file_upload = Upload.SmallFileUpload(
            name="test_students.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            _data=xlsx_bytes,
        )
        await upload_el.handle_uploads([file_upload])

        # Verify success notification appeared (should_see polls)
        await nicegui_user.should_see("Enrolled")

    @pytest.mark.asyncio
    async def test_second_upload_also_fires_handler(self, nicegui_user: User) -> None:
        """Verify that a second upload also triggers the handler (re-upload works)."""
        from nicegui.elements.upload import Upload

        email = "instructor@uni.edu"
        await _authenticate(nicegui_user, email=email)

        course_id, _code = await _create_course()
        await _enroll(course_id, email, "instructor")

        await nicegui_user.open(f"/courses/{course_id}/enrollments")
        await _should_see_testid(nicegui_user, "enrol-upload")

        unique = uuid4().hex[:6]
        xlsx_bytes = make_xlsx_bytes(
            ["First name", "Last name", "ID number", "Email address"],
            [["Bob", "Test", "88888", f"bob-{unique}@test.example.edu.au"]],
        )

        upload_el = _find_by_testid(nicegui_user, "enrol-upload")
        assert upload_el is not None
        assert isinstance(upload_el, Upload)

        file_upload = Upload.SmallFileUpload(
            name="students.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            _data=xlsx_bytes,
        )

        # First upload
        await upload_el.handle_uploads([file_upload])
        await nicegui_user.should_see("Enrolled 1 of 1")

        # Second upload of same data — should show info (all duplicates)
        await upload_el.handle_uploads([file_upload])
        await nicegui_user.should_see("already enrolled")
