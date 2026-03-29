"""E2E test: Happy path continuous workflow.

A lightweight glue test that exercises the full instructor-to-student
journey without database seeding, verifying state transitions between
administrative setup and canvas interaction.

Acceptance Criteria:
- e2e-instructor-workflow-split.AC2.1: Course, activity, tag created via UI
- e2e-instructor-workflow-split.AC2.2: Student enrols, starts, applies tag
- e2e-instructor-workflow-split.AC2.3: No state bleed between personas
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from promptgrimoire.docs.helpers import wait_for_text_walker
from tests.e2e.card_helpers import expand_card
from tests.e2e.conftest import _authenticate_page
from tests.e2e.course_helpers import (
    add_activity,
    add_week,
    create_course,
    enrol_student,
    publish_week,
)
from tests.e2e.highlight_tools import select_text_range

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page
    from pytest_subtests import SubTests

pytestmark = [pytest.mark.noci]


def _extract_course_id(page: Page) -> str:
    match = re.search(r"/courses/([0-9a-f-]+)", page.url)
    assert match, f"Expected course UUID in URL, got: {page.url}"
    return match.group(1)


def _fill_template_and_create_tag(page: Page) -> None:
    """Click template button, add content, create a quick tag."""
    # Only one activity on page — use testid prefix directly
    page.locator("[data-testid^='template-btn-']").first.click()
    page.wait_for_url(re.compile(r"/annotation\?workspace_id="), timeout=10000)

    content_input = page.get_by_test_id("content-editor").locator(".q-editor__content")
    content_input.wait_for(state="visible", timeout=5000)
    content_input.fill("Lions and tigers are mammals.")

    page.get_by_test_id("add-document-btn").click()
    confirm_btn = page.get_by_test_id("confirm-content-type-btn")
    confirm_btn.wait_for(state="visible", timeout=5000)
    confirm_btn.click()

    wait_for_text_walker(page, timeout=10000)

    # Quick-create a tag via the toolbar add button
    page.get_by_test_id("tag-create-btn").click()
    dialog = page.locator("[data-testid='tag-quick-create-dialog']")
    expect(dialog).to_be_visible(timeout=5000)
    dialog.get_by_test_id("tag-quick-create-name-input").fill("Mammals")
    dialog.get_by_test_id("quick-create-save-btn").click()
    expect(dialog).to_be_hidden(timeout=5000)

    toolbar = page.locator("[data-testid='tag-toolbar']")
    expect(toolbar).to_contain_text("Mammals", timeout=5000)


def _student_start_and_apply_tag(
    browser: Browser,
    app_server: str,
    *,
    student_email: str,
    course_id: str,
) -> None:
    """Authenticate as student, start activity, apply the Mammals tag."""
    student_ctx = browser.new_context()
    student_page = student_ctx.new_page()

    try:
        _authenticate_page(student_page, app_server, email=student_email)
        student_page.goto(f"{app_server}/courses/{course_id}")

        # Only one activity — use testid prefix directly
        start_btn = student_page.locator("[data-testid^='start-activity-btn-']").first
        start_btn.wait_for(state="visible", timeout=10000)
        start_btn.click()

        student_page.wait_for_url(
            re.compile(r"/annotation\?workspace_id="), timeout=15000
        )
        wait_for_text_walker(student_page, timeout=10000)

        # Select text and click the first (only) tag button
        select_text_range(student_page, "Lions")

        student_page.locator("[data-testid='tag-toolbar'] [data-tag-id]").first.click()

        first_card = student_page.locator("[data-testid='annotation-card']").first
        first_card.wait_for(state="visible", timeout=5000)
        expand_card(student_page, 0)
        expect(first_card.get_by_test_id("tag-select")).to_contain_text(
            "Mammals", timeout=3000
        )
    finally:
        student_page.close()
        student_ctx.close()


@pytest.mark.e2e
@pytest.mark.cards
class TestHappyPathWorkflow:
    def test_happy_path_workflow(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """Happy-path run-through without database seeding."""
        uid = uuid4().hex[:8]
        course_code = f"TEST-{uid}"
        course_name = f"Happy Path {uid}"
        semester = "2026-S1"
        student_email = f"student-{uid}@test.edu"

        course_id: str | None = None
        instructor_ctx = browser.new_context()
        page = instructor_ctx.new_page()

        try:
            with subtests.test(msg="authenticate_as_instructor"):
                _authenticate_page(page, app_server, email="instructor@uni.edu")

            with subtests.test(msg="create_course_and_activity"):
                create_course(
                    page,
                    app_server,
                    code=course_code,
                    name=course_name,
                    semester=semester,
                )
                add_week(page, title="Week 1")
                add_activity(page, title="Happy Path Activity")

            with subtests.test(msg="create_template_and_tag"):
                _fill_template_and_create_tag(page)

            with subtests.test(msg="publish_and_enrol"):
                page.go_back()
                page.wait_for_url(
                    re.compile(r"/courses/[0-9a-f-]+"),
                    timeout=10000,
                )
                publish_week(page, "Week 1")
                enrol_student(page, email=student_email)
                course_id = _extract_course_id(page)

        finally:
            page.close()
            instructor_ctx.close()

        if course_id is None:
            pytest.fail("Instructor setup failed — cannot proceed to student phase")

        with subtests.test(msg="student_applies_tag"):
            _student_start_and_apply_tag(
                browser,
                app_server,
                student_email=student_email,
                course_id=course_id,
            )
