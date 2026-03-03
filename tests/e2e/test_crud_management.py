"""E2E tests for CRUD management delete guards.

Verifies the delete confirmation dialog UI and role-based visibility
of the Delete Unit button.

Acceptance Criteria:
- crud-management-229.AC2.5: Delete confirmation dialog workflow
- crud-management-229.AC6.5: Delete Unit button hidden for non-coordinators

Traceability:
- Issue: #229 (CRUD management)
- Design: docs/implementation-plans/2026-03-02-crud-management-229/phase_05.md
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import _authenticate_page
from tests.e2e.course_helpers import (
    add_week,
    create_course,
)

if TYPE_CHECKING:
    from playwright.sync_api import Browser


def _unique_course_params() -> tuple[str, str, str]:
    """Generate unique course code, name, and semester for test isolation."""
    uid = uuid4().hex[:8]
    return f"DEL-{uid}", f"Delete Test {uid}", "2026-S1"


@pytest.mark.e2e
class TestDeleteWeekConfirmationDialog:
    """Verify the delete confirmation dialog appears and cancel preserves state."""

    def test_delete_week_cancel_preserves_week(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Click delete on a week, cancel, and verify the week survives.

        Steps:
        1. Authenticate and create a course with one week.
        2. Click the delete button on the week card.
        3. Verify the confirmation dialog appears with confirm/cancel buttons.
        4. Click cancel.
        5. Verify the week is still visible on the page.
        """
        context = browser.new_context()
        page = context.new_page()
        try:
            _authenticate_page(page, app_server, email="instructor@uni.edu")

            code, name, semester = _unique_course_params()
            create_course(page, app_server, code=code, name=name, semester=semester)

            week_title = "Week to Not Delete"
            add_week(page, title=week_title)

            # Verify the week is visible
            week_label = page.get_by_text(
                re.compile(rf"Week \d+:\s*{re.escape(week_title)}")
            )
            week_label.wait_for(state="visible", timeout=5000)

            # Find the delete-week button (there should be exactly one week)
            delete_btns = page.locator("[data-testid^='delete-week-btn-']")
            expect(delete_btns).to_have_count(1, timeout=5000)
            delete_btns.first.click()

            # Confirmation dialog should appear
            confirm_btn = page.get_by_test_id("confirm-delete-btn")
            cancel_btn = page.get_by_test_id("cancel-delete-btn")
            expect(confirm_btn).to_be_visible(timeout=5000)
            expect(cancel_btn).to_be_visible(timeout=5000)

            # Click cancel
            cancel_btn.click()

            # Dialog should close — confirm button no longer visible
            expect(confirm_btn).to_be_hidden(timeout=5000)

            # Week should still exist
            expect(week_label).to_be_visible(timeout=5000)
        finally:
            page.close()
            context.close()


@pytest.mark.e2e
class TestDeleteWeekSuccess:
    """Verify that confirming delete actually removes the week."""

    def test_delete_week_removes_it(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Create a week with no student workspaces, delete it, verify removal.

        Steps:
        1. Authenticate and create a course with one week.
        2. Click the delete button, then confirm.
        3. Verify the week text disappears from the page.
        """
        context = browser.new_context()
        page = context.new_page()
        try:
            _authenticate_page(page, app_server, email="instructor@uni.edu")

            code, name, semester = _unique_course_params()
            create_course(page, app_server, code=code, name=name, semester=semester)

            week_title = "Week to Delete"
            add_week(page, title=week_title)

            # Verify the week is visible
            week_label = page.get_by_text(
                re.compile(rf"Week \d+:\s*{re.escape(week_title)}")
            )
            week_label.wait_for(state="visible", timeout=5000)

            # Click the delete button
            delete_btns = page.locator("[data-testid^='delete-week-btn-']")
            expect(delete_btns).to_have_count(1, timeout=5000)
            delete_btns.first.click()

            # Confirm deletion
            confirm_btn = page.get_by_test_id("confirm-delete-btn")
            expect(confirm_btn).to_be_visible(timeout=5000)
            confirm_btn.click()

            # Week should disappear from the page
            expect(week_label).to_be_hidden(timeout=10000)

            # The delete button should also be gone
            expect(delete_btns).to_have_count(0, timeout=5000)
        finally:
            page.close()
            context.close()


@pytest.mark.e2e
class TestDeleteUnitButtonVisibility:
    """Verify Delete Unit button visibility based on enrollment role."""

    def test_delete_unit_visible_for_coordinator(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Coordinator (course creator) should see the Delete Unit button.

        Creating a course auto-enrolls the creator as coordinator.
        """
        context = browser.new_context()
        page = context.new_page()
        try:
            _authenticate_page(page, app_server, email="instructor@uni.edu")

            code, name, semester = _unique_course_params()
            create_course(page, app_server, code=code, name=name, semester=semester)

            # Coordinator should see the delete button
            delete_unit_btn = page.get_by_test_id("delete-unit-btn")
            expect(delete_unit_btn).to_be_visible(timeout=5000)
        finally:
            page.close()
            context.close()

    def test_delete_unit_hidden_for_instructor_role(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Non-coordinator instructor should NOT see the Delete Unit button (AC6.5).

        Steps:
        1. Coordinator creates a course.
        2. Coordinator enrolls a second user as "instructor" role.
        3. Second user authenticates and navigates to the course.
        4. Verify Delete Unit button is not visible.
        """
        # --- Coordinator creates the course and enrolls an instructor ---
        coord_ctx = browser.new_context()
        coord_page = coord_ctx.new_page()

        uid = uuid4().hex[:8]
        instructor_email = f"instr-{uid}@test.example.edu.au"

        try:
            _authenticate_page(coord_page, app_server, email="instructor@uni.edu")

            code, name, semester = _unique_course_params()
            create_course(
                coord_page, app_server, code=code, name=name, semester=semester
            )

            # Extract course URL for the second user
            course_url = coord_page.url

            # Navigate to enrollment management and add the instructor
            coord_page.get_by_test_id("manage-enrollments-btn").click()
            coord_page.wait_for_url(
                re.compile(r"/courses/[0-9a-f-]+/enrollments"), timeout=10000
            )

            coord_page.get_by_test_id("enrollment-email-input").fill(instructor_email)

            # Select "instructor" role from the role select dropdown
            role_select = coord_page.get_by_test_id("enrollment-role-select")
            role_select.click()
            coord_page.wait_for_timeout(300)
            coord_page.locator(".q-item").filter(has_text="instructor").click()
            coord_page.wait_for_timeout(300)

            coord_page.get_by_test_id("add-enrollment-btn").click()

            # Wait for success notification
            coord_page.get_by_text(re.compile(r"Enrollment added")).wait_for(
                state="visible", timeout=5000
            )
        finally:
            coord_page.close()
            coord_ctx.close()

        # --- Instructor logs in and checks the course ---
        instr_ctx = browser.new_context()
        instr_page = instr_ctx.new_page()
        try:
            _authenticate_page(instr_page, app_server, email=instructor_email)

            instr_page.goto(course_url)

            # Wait for the page to render — look for the course code
            instr_page.get_by_text(code).wait_for(state="visible", timeout=10000)

            # The Delete Unit button should NOT be present for an instructor
            delete_unit_btn = instr_page.get_by_test_id("delete-unit-btn")
            expect(delete_unit_btn).to_have_count(0, timeout=5000)
        finally:
            instr_page.close()
            instr_ctx.close()
