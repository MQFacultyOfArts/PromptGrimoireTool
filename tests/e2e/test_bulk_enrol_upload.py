"""E2E tests for bulk enrolment upload widget on manage enrollments page.

Verifies that:
- Instructors can upload an XLSX and see a success notification (AC7.1)
- Invalid XLSX shows a warning notification (AC7.2)
- Students cannot access manage enrollments page (AC7.4)

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
def instructor_enrollments_page(
    browser: Browser, app_server: str
) -> Generator[tuple[Page, str]]:
    """Authenticated instructor page at the manage enrollments page.

    Yields (page, course_id).
    """
    context = browser.new_context()
    page = context.new_page()

    unique_id = uuid.uuid4().hex[:8]
    email = f"enrol-instr-{unique_id}@test.example.edu.au"
    _authenticate_page(page, app_server, email=email)

    course_id = _create_course_with_enrollment(email, role="instructor")
    page.goto(f"{app_server}/courses/{course_id}/enrollments")

    # Wait for the manage enrollments page to render
    page.get_by_test_id("enrol-upload").wait_for(state="visible", timeout=15000)

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
    page.goto(f"{app_server}/courses/{course_id}/enrollments")

    # Wait for the page to finish rendering
    page.wait_for_load_state("networkidle", timeout=15000)

    yield page, course_id

    page.goto("about:blank")
    page.close()
    context.close()


def _upload_xlsx(page: Page, xlsx_bytes: bytes) -> None:
    """Upload XLSX bytes via the enrol-upload widget.

    Two race conditions must be avoided:

    1. Quasar's ``<input type="file">`` may not be in the DOM yet — wait
       for ``state="attached"``.
    2. NiceGUI's ``upload.js`` computes the upload URL in a ``setTimeout``
       after Vue's ``mounted()`` hook.  If ``set_input_files`` triggers
       Quasar's auto-upload before the URL is resolved, the POST goes
       nowhere.  ``expect_response`` catches this: if no POST arrives
       within the timeout the test fails fast instead of hanging 15 s
       waiting for a notification that will never appear.
    """
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        f.write(xlsx_bytes)
        fixture_path = Path(f.name)

    upload_widget = page.get_by_test_id("enrol-upload")
    file_input = upload_widget.locator('input[type="file"]')
    file_input.wait_for(state="attached", timeout=10000)

    with page.expect_response(
        lambda r: r.request.method == "POST" and "/_nicegui" in r.url,
        timeout=10000,
    ):
        file_input.set_input_files(str(fixture_path))

    fixture_path.unlink()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestBulkEnrolUpload:
    """E2E tests for the bulk enrolment upload widget."""

    def test_enrollment_table_visible(
        self,
        instructor_enrollments_page: tuple[Page, str],
    ) -> None:
        """AC2.1: Enrollment table is visible after page load."""
        page, _course_id = instructor_enrollments_page

        table = page.get_by_test_id("enrollment-table")
        expect(table).to_be_visible(timeout=10000)

    def test_valid_xlsx_shows_success_notification(
        self,
        instructor_enrollments_page: tuple[Page, str],
    ) -> None:
        """AC7.1: Upload valid XLSX, verify success notification."""
        page, _course_id = instructor_enrollments_page

        # Verify enrollment table is present
        expect(page.get_by_test_id("enrollment-table")).to_be_visible()

        xlsx_bytes = make_xlsx_bytes(
            ["First name", "Last name", "ID number", "Email address"],
            [["Alice", "Smith", "12345", "alice-e2e@example.com"]],
        )
        _upload_xlsx(page, xlsx_bytes)

        # Quasar notifications use role="alert" natively. ui.notify() does not
        # support data-testid, so get_by_role("alert") is the accepted exception
        # to the project's data-testid locator convention.
        notification = page.get_by_role("alert")  # noqa: PG002
        expect(notification).to_be_visible(timeout=15000)
        expect(notification).to_contain_text("Enrolled")

        # AC3.1: table rows update to reflect new enrollment
        table = page.get_by_test_id("enrollment-table")
        expect(table.locator("tr", has_text="alice-e2e@example.com")).to_be_visible(
            timeout=5000
        )

    def test_invalid_xlsx_shows_warning_notification(
        self,
        instructor_enrollments_page: tuple[Page, str],
    ) -> None:
        """AC7.2: Upload XLSX with missing column, verify warning."""
        page, _course_id = instructor_enrollments_page

        # Missing "ID number" column
        xlsx_bytes = make_xlsx_bytes(
            ["First name", "Last name", "Email address"],
            [["Alice", "Smith", "alice@example.com"]],
        )
        _upload_xlsx(page, xlsx_bytes)

        notification = page.get_by_role("alert")  # noqa: PG002
        expect(notification).to_be_visible(timeout=15000)
        expect(notification).to_contain_text("Missing required column")

    def test_duplicate_upload_shows_already_enrolled(
        self,
        instructor_enrollments_page: tuple[Page, str],
    ) -> None:
        """#325: Re-upload same XLSX shows 'already enrolled' notification."""
        page, _course_id = instructor_enrollments_page

        unique = uuid.uuid4().hex[:6]
        xlsx_bytes = make_xlsx_bytes(
            ["First name", "Last name", "ID number", "Email address"],
            [
                [
                    "Dupe",
                    "Student",
                    "99999",
                    f"dupe-{unique}@test.example.edu.au",
                ]
            ],
        )

        # First upload — should succeed
        _upload_xlsx(page, xlsx_bytes)
        # Quasar notifications use role="alert" natively. ui.notify() does not
        # support data-testid, so get_by_role("alert") is the accepted exception
        # to the project's data-testid locator convention.
        first_notification = page.get_by_role("alert")  # noqa: PG002
        expect(first_notification).to_be_visible(timeout=15000)
        expect(first_notification).to_contain_text("Enrolled 1 of 1")

        # Dismiss the first notification (click OK or wait for auto-dismiss).
        # Quasar dialog buttons don't support data-testid, so
        # get_by_role("button", name="OK") is an accepted exception to the
        # project's data-testid locator convention.
        ok_button = first_notification.get_by_role("button", name="OK")  # noqa: PG002
        if ok_button.is_visible(timeout=2000):
            ok_button.click()
        # Wait for notification to disappear
        expect(first_notification).not_to_be_visible(timeout=10000)

        # Second upload of same data — should show already enrolled
        _upload_xlsx(page, xlsx_bytes)
        second_notification = page.get_by_role("alert")  # noqa: PG002
        expect(second_notification).to_be_visible(timeout=15000)
        expect(second_notification).to_contain_text("already enrolled")

    def test_preexisting_students_shows_already_enrolled(
        self,
        instructor_enrollments_page: tuple[Page, str],
    ) -> None:
        """#325: Upload XLSX when students already exist shows notification."""
        page, course_id = instructor_enrollments_page

        unique = uuid.uuid4().hex[:6]
        email = f"preseed-{unique}@test.example.edu.au"
        xlsx_bytes = make_xlsx_bytes(
            ["First name", "Last name", "ID number", "Email address"],
            [["Pre", "Seeded", "77777", email]],
        )

        # Pre-seed students via direct SQL so they already exist
        from sqlalchemy import create_engine, text

        from promptgrimoire.config import get_settings

        db_url = get_settings().database.url
        if not db_url:
            msg = "DATABASE__URL not configured"
            raise RuntimeError(msg)
        sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
        engine = create_engine(sync_url)

        with engine.begin() as conn:
            # Create user if not exists
            conn.execute(
                text(
                    'INSERT INTO "user"'
                    " (id, email, display_name, is_admin, created_at)"
                    " VALUES (gen_random_uuid(), :email, :name, false, now())"
                    " ON CONFLICT (email) DO NOTHING"
                ),
                {"email": email, "name": "Pre Seeded"},
            )
            # Get user id
            row = conn.execute(
                text('SELECT id FROM "user" WHERE email = :email'),
                {"email": email},
            ).first()
            assert row is not None
            user_id = row[0]
            # Enrol in course
            conn.execute(
                text(
                    "INSERT INTO course_enrollment"
                    " (id, course_id, user_id, role, created_at)"
                    " VALUES (gen_random_uuid(),"
                    "  CAST(:cid AS uuid), :uid, 'student', now())"
                    " ON CONFLICT DO NOTHING"
                ),
                {"cid": course_id, "uid": user_id},
            )
        engine.dispose()

        # Now upload via UI — all students already exist
        _upload_xlsx(page, xlsx_bytes)

        # Quasar notifications use role="alert" natively. ui.notify() does not
        # support data-testid, so get_by_role("alert") is the accepted exception
        # to the project's data-testid locator convention.
        notification = page.get_by_role("alert")  # noqa: PG002
        expect(notification).to_be_visible(timeout=15000)
        expect(notification).to_contain_text("already enrolled")

    def test_delete_enrollment_via_table(
        self,
        instructor_enrollments_page: tuple[Page, str],
    ) -> None:
        """AC3.3: Delete an enrollment via the table action button."""
        page, _course_id = instructor_enrollments_page

        # Upload a student first so we have a row to delete
        unique = uuid.uuid4().hex[:6]
        student_email = f"del-{unique}@test.example.edu.au"
        xlsx_bytes = make_xlsx_bytes(
            ["First name", "Last name", "ID number", "Email address"],
            [["Delete", "Me", "55555", student_email]],
        )
        _upload_xlsx(page, xlsx_bytes)

        # Quasar notifications use role="alert" natively. ui.notify() does not
        # support data-testid, so get_by_role("alert") is the accepted exception
        # to the project's data-testid locator convention.
        notification = page.get_by_role("alert")  # noqa: PG002
        expect(notification).to_be_visible(timeout=15000)
        expect(notification).to_contain_text("Enrolled")

        # Dismiss the notification
        # Quasar dialog buttons don't support data-testid, so
        # get_by_role("button", name="OK") is an accepted exception to the
        # project's data-testid locator convention.
        ok_button = notification.get_by_role("button", name="OK")  # noqa: PG002
        if ok_button.is_visible(timeout=2000):
            ok_button.click()
        expect(notification).not_to_be_visible(timeout=10000)

        # Find the row containing the student email and click its delete button
        table = page.get_by_test_id("enrollment-table")
        student_row = table.locator("tr", has_text=student_email)
        expect(student_row).to_be_visible(timeout=5000)

        delete_btn = student_row.get_by_test_id("delete-enrollment-btn")
        delete_btn.click()

        # Verify the row disappears after deletion
        expect(student_row).not_to_be_visible(timeout=10000)

        # Verify success notification
        delete_notification = page.get_by_role("alert")  # noqa: PG002
        expect(delete_notification).to_be_visible(timeout=10000)
        expect(delete_notification).to_contain_text("removed")

    def test_add_single_enrollment_updates_table(
        self,
        instructor_enrollments_page: tuple[Page, str],
    ) -> None:
        """AC3.2: After add-single enrollment, new student appears in table."""
        page, _course_id = instructor_enrollments_page

        unique = uuid.uuid4().hex[:6]
        email = f"single-{unique}@test.example.edu.au"

        email_input = page.get_by_test_id("enrollment-email-input")
        email_input.fill(email)
        page.get_by_test_id("add-enrollment-btn").click()

        # Quasar notifications use role="alert" natively. ui.notify() does not
        # support data-testid, so get_by_role("alert") is the accepted exception
        # to the project's data-testid locator convention.
        notification = page.get_by_role("alert")  # noqa: PG002
        expect(notification).to_be_visible(timeout=15000)
        expect(notification).to_contain_text("Enrollment added")

        # AC3.2: table rows update to reflect new enrollment
        table = page.get_by_test_id("enrollment-table")
        expect(table.locator("tr", has_text=email)).to_be_visible(timeout=5000)

    def test_student_cannot_see_upload_widget(
        self,
        student_course_page: tuple[Page, str],
    ) -> None:
        """AC7.4: Students should not see the upload widget."""
        page, _course_id = student_course_page

        # Students should see the access denial message, not the upload widget
        upload = page.get_by_test_id("enrol-upload")
        expect(upload).not_to_be_visible(timeout=5000)
