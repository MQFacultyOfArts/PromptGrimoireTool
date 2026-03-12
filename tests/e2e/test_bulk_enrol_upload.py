"""E2E tests for bulk enrolment upload widget in unit settings.

Verifies that:
- Instructors can upload an XLSX and see a success notification (AC7.1)
- Invalid XLSX shows a warning notification (AC7.2)
- Students cannot see the upload widget (AC7.4)

Run with: uv run grimoire e2e run -k test_bulk_enrol

Traceability:
- Issue: #320 (Bulk Student Enrolment)
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.conftest import make_xlsx_bytes
from tests.e2e.conftest import _authenticate_page

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Browser, Page


# ---------------------------------------------------------------------------
# Direct-DB course creation helpers (sync, for E2E fixtures)
# ---------------------------------------------------------------------------


def _create_course_with_enrollment(
    user_email: str,
    *,
    role: str = "instructor",
) -> str:
    """Create a course and enrol the user via direct DB operations.

    Returns the course_id as a string.
    """
    from sqlalchemy import create_engine, text

    from promptgrimoire.config import get_settings

    db_url = get_settings().database.url
    if not db_url:
        msg = "DATABASE__URL not configured"
        raise RuntimeError(msg)
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    engine = create_engine(sync_url)

    course_id = str(uuid.uuid4())
    unique = uuid.uuid4().hex[:6]

    with engine.begin() as conn:
        # Look up user
        row = conn.execute(
            text('SELECT id FROM "user" WHERE email = :email'),
            {"email": user_email},
        ).first()
        if not row:
            msg = f"User not found in DB: {user_email}"
            raise RuntimeError(msg)
        user_id = row[0]

        # Create course
        conn.execute(
            text(
                "INSERT INTO course"
                " (id, code, name, semester, is_archived,"
                "  default_copy_protection, default_allow_sharing,"
                "  default_anonymous_sharing, default_allow_tag_creation,"
                "  default_word_limit_enforcement, created_at)"
                " VALUES (CAST(:id AS uuid), :code, :name, :semester,"
                "  false, false, false, false, false, false, now())"
            ),
            {
                "id": course_id,
                "code": f"ENRL-{unique}",
                "name": f"Bulk Enrol Test {unique}",
                "semester": "2026-S1",
            },
        )

        # Enrol user
        conn.execute(
            text(
                "INSERT INTO course_enrollment"
                " (id, course_id, user_id, role, created_at)"
                " VALUES (gen_random_uuid(),"
                "  CAST(:cid AS uuid), :uid, :role, now())"
                " ON CONFLICT DO NOTHING"
            ),
            {"cid": course_id, "uid": user_id, "role": role},
        )

    engine.dispose()
    return course_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def instructor_course_page(
    browser: Browser, app_server: str
) -> Generator[tuple[Page, str]]:
    """Authenticated instructor page at a course detail page.

    Yields (page, course_id).
    """
    context = browser.new_context()
    page = context.new_page()

    unique_id = uuid.uuid4().hex[:8]
    email = f"enrol-instr-{unique_id}@test.example.edu.au"
    _authenticate_page(page, app_server, email=email)

    course_id = _create_course_with_enrollment(email, role="instructor")
    page.goto(f"{app_server}/courses/{course_id}")

    # Wait for course detail to render
    page.wait_for_selector('[data-testid="course-settings-btn"]', timeout=15000)

    yield page, course_id

    page.goto("about:blank")
    page.close()
    context.close()


@pytest.fixture
def student_course_page(
    browser: Browser, app_server: str
) -> Generator[tuple[Page, str]]:
    """Authenticated student page at a course detail page.

    Yields (page, course_id).
    """
    context = browser.new_context()
    page = context.new_page()

    unique_id = uuid.uuid4().hex[:8]
    email = f"enrol-student-{unique_id}@test.example.edu.au"
    _authenticate_page(page, app_server, email=email)

    course_id = _create_course_with_enrollment(email, role="student")
    page.goto(f"{app_server}/courses/{course_id}")

    # Wait for the page to render (badge with role is always present)
    page.wait_for_selector("text=student", timeout=15000)

    yield page, course_id

    page.goto("about:blank")
    page.close()
    context.close()


def _open_settings_dialog(page: Page) -> None:
    """Click the Unit Settings button and wait for the dialog."""
    page.get_by_test_id("course-settings-btn").click()
    page.get_by_test_id("course-settings-title").wait_for(state="visible", timeout=5000)


def _upload_xlsx(page: Page, xlsx_bytes: bytes) -> None:
    """Upload XLSX bytes via the enrol-upload widget."""
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        f.write(xlsx_bytes)
        fixture_path = f.name

    upload_widget = page.get_by_test_id("enrol-upload")
    file_input = upload_widget.locator('input[type="file"]')
    file_input.set_input_files(fixture_path)

    Path(fixture_path).unlink()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestBulkEnrolUpload:
    """E2E tests for the bulk enrolment upload widget."""

    def test_valid_xlsx_shows_success_notification(
        self,
        instructor_course_page: tuple[Page, str],
    ) -> None:
        """AC7.1: Upload valid XLSX, verify success notification."""
        page, _course_id = instructor_course_page
        _open_settings_dialog(page)

        xlsx_bytes = make_xlsx_bytes(
            ["First name", "Last name", "ID number", "Email address"],
            [["Alice", "Smith", "12345", "alice-e2e@example.com"]],
        )
        _upload_xlsx(page, xlsx_bytes)

        # Wait for notification
        notification = page.get_by_role("alert")
        expect(notification).to_be_visible(timeout=15000)
        expect(notification).to_contain_text("Enrolled")

    def test_invalid_xlsx_shows_warning_notification(
        self,
        instructor_course_page: tuple[Page, str],
    ) -> None:
        """AC7.2: Upload XLSX with missing column, verify warning."""
        page, _course_id = instructor_course_page
        _open_settings_dialog(page)

        # Missing "ID number" column
        xlsx_bytes = make_xlsx_bytes(
            ["First name", "Last name", "Email address"],
            [["Alice", "Smith", "alice@example.com"]],
        )
        _upload_xlsx(page, xlsx_bytes)

        notification = page.get_by_role("alert")
        expect(notification).to_be_visible(timeout=15000)
        expect(notification).to_contain_text("Missing required column")

    def test_student_cannot_see_upload_widget(
        self,
        student_course_page: tuple[Page, str],
    ) -> None:
        """AC7.4: Students should not see the settings button or upload widget."""
        page, _course_id = student_course_page

        # Students should not see the settings button at all
        settings_btn = page.get_by_test_id("course-settings-btn")
        expect(settings_btn).not_to_be_visible(timeout=5000)
