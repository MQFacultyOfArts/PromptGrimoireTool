"""E2E: week and activity edit dialogs save captured values.

The edit dialogs are the only two courses.py forms whose value-capture
wiring (``on_submit_with_values``) no other test drives — the create
forms and enrolment are covered by the instructor-marking journey.  A
wrong capture key or unwired save button here would fail only in
production, so this test drives both dialogs through a real browser and
asserts the edited values land: on the card for the week, and in the
reopened dialog for the activity.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import _authenticate_page
from tests.e2e.course_helpers import add_activity, add_week, create_course

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from pytest_subtests import SubTests


@pytest.mark.e2e
class TestCourseEditDialogs:
    """Instructor edits a week and an activity via the dialogs."""

    def test_edit_dialogs_save_captured_values(
        self, page: Page, app_server: str, subtests: SubTests
    ) -> None:
        uid = uuid4().hex[:8]
        instructor_email = f"edit-dialogs-{uid}@test.example.edu.au"

        _authenticate_page(page, app_server, email=instructor_email)
        create_course(
            page,
            app_server,
            code=f"EDIT{uid[:4].upper()}",
            name="Edit Dialogs",
            semester="2026-S1",
        )
        match = re.search(r"/courses/([0-9a-f-]+)", page.url)
        assert match, "Expected course UUID in URL"
        course_id = match.group(1)

        add_week(page, title="Draft Week")
        add_activity(page, title="Draft Activity")

        with subtests.test(msg="edit_week_dialog"):
            page.locator('[data-testid^="edit-week-btn-"]').first.click()
            title_input = page.get_by_test_id("edit-week-title-input")
            title_input.wait_for(state="visible", timeout=5000)
            title_input.fill("Edited Week")
            page.get_by_test_id("edit-week-number-input").fill("7")
            page.get_by_test_id("save-edit-week-btn").click()

            card = page.locator('[data-testid^="week-card-"]').filter(
                has_text="Edited Week"
            )
            expect(card.first).to_be_visible(timeout=5000)
            expect(card.first).to_contain_text("7")

        with subtests.test(msg="edit_activity_dialog"):
            page.locator('[data-testid^="edit-activity-btn-"]').first.click()
            title_input = page.get_by_test_id("edit-activity-title-input")
            title_input.wait_for(state="visible", timeout=5000)
            title_input.fill("Edited Activity")
            page.get_by_test_id("edit-activity-description-input").fill(
                "Edited description text."
            )
            page.get_by_test_id("save-edit-activity-btn").click()

            expect(
                page.get_by_text("Edited Activity", exact=False).first
            ).to_be_visible(timeout=5000)

            # Reopen the dialog: both captured fields must have persisted.
            page.goto(f"{app_server}/courses/{course_id}")
            page.locator('[data-testid^="edit-activity-btn-"]').first.click()
            title_input = page.get_by_test_id("edit-activity-title-input")
            title_input.wait_for(state="visible", timeout=5000)
            expect(title_input).to_have_value("Edited Activity")
            expect(
                page.get_by_test_id("edit-activity-description-input")
            ).to_have_value("Edited description text.")
