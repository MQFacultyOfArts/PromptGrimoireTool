"""E2E tests for the workspace navigator page.

Verifies the navigator page at ``/`` renders workspace sections correctly,
handles authentication, and provides workspace navigation.

Acceptance Criteria:
- workspace-navigator-196.AC2.5: Unauthenticated redirect to login
- workspace-navigator-196.AC1.1: My Work section renders with workspace entries
- workspace-navigator-196.AC1.2: Unstarted Work section visible with activity entries
- workspace-navigator-196.AC1.7: Empty sections not rendered in DOM
- workspace-navigator-196.AC2.1: Title click navigates to annotation page
- workspace-navigator-196.AC2.3: Start button clones and navigates

Traceability:
- Issue: #196 (Workspace Navigator)
- Design: docs/implementation-plans/2026-02-24-workspace-navigator-196/phase_04.md
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import (
    _create_workspace_via_db,
    wait_for_text_walker,
)
from tests.e2e.conftest import _authenticate_page
from tests.e2e.course_helpers import (
    add_activity,
    add_week,
    configure_course_setting,
    create_course,
    enrol_student,
    publish_week,
)

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page
    from pytest_subtests import SubTests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fill_template_workspace(page: Page) -> None:
    """Click Create Template, add content for cloning.

    Expects the page to be on a course detail page with an activity
    showing a "Create Template" button.
    """
    page.get_by_role(
        "button",
        name=re.compile(r"Create Template|Edit Template"),
    ).click()
    page.wait_for_url(re.compile(r"/annotation\?workspace_id="), timeout=10000)

    content_input = page.get_by_placeholder(
        "Paste HTML content or type plain text here..."
    )
    content_input.wait_for(state="visible", timeout=5000)
    content_input.fill("Navigator test content for template workspace.")

    page.get_by_role("button", name=re.compile(r"add document", re.IGNORECASE)).click()

    confirm = page.get_by_role("button", name=re.compile(r"confirm", re.IGNORECASE))
    confirm.wait_for(state="visible", timeout=5000)
    confirm.click()

    wait_for_text_walker(page, timeout=15000)


def _get_section_header_texts(page: Page) -> list[str]:
    """Read all navigator section header texts from the page."""
    section_headers = page.locator(".navigator-section-header")
    return [section_headers.nth(i).inner_text() for i in range(section_headers.count())]


def _assert_activity_not_in_unstarted(page: Page, activity_title: str) -> None:
    """Assert no Start-button card contains the given activity title."""
    start_btns = page.locator(".navigator-start-btn")
    for i in range(start_btns.count()):
        parent_card = start_btns.nth(i).locator(
            "xpath=ancestor::div[contains(@class, 'q-card')]"
        )
        card_text = parent_card.inner_text()
        assert activity_title not in card_text, (
            f"Activity '{activity_title}' should not be in "
            f"Unstarted after cloning. Card text: {card_text}"
        )


def _student_start_and_verify(
    browser: Browser,
    app_server: str,
    *,
    student_email: str,
    activity_title: str,
    subtests: SubTests,
) -> None:
    """Student clicks Start, verifies clone navigation, and section move.

    Extracted to keep test method under PLR0915 statement limit.
    """
    student_ctx = browser.new_context()
    student_page = student_ctx.new_page()

    try:
        _authenticate_page(student_page, app_server, email=student_email)

        with subtests.test(msg="unstarted_shows_activity"):
            student_page.goto(f"{app_server}/")
            student_page.wait_for_timeout(2000)

            header_texts = _get_section_header_texts(student_page)
            assert "Unstarted Work" in header_texts, (
                f"Expected 'Unstarted Work', got: {header_texts}"
            )

            activity_label = student_page.get_by_text(activity_title, exact=False)
            expect(activity_label.first).to_be_visible(timeout=5000)

        with subtests.test(msg="start_navigates_to_annotation"):
            start_btn = student_page.locator(".navigator-start-btn").first
            expect(start_btn).to_be_visible(timeout=5000)
            start_btn.click()

            student_page.wait_for_url(
                re.compile(r"/annotation\?workspace_id="),
                timeout=15000,
            )
            assert "/annotation" in student_page.url, (
                f"Expected /annotation URL, got: {student_page.url}"
            )

        with subtests.test(msg="activity_moves_to_my_work"):
            student_page.goto(f"{app_server}/")
            student_page.wait_for_timeout(2000)

            header_texts = _get_section_header_texts(student_page)
            assert "My Work" in header_texts, (
                f"Expected 'My Work' after cloning, got: {header_texts}"
            )

            action_btns = student_page.locator(".navigator-action-btn")
            expect(action_btns.first).to_be_visible(timeout=5000)

            _assert_activity_not_in_unstarted(student_page, activity_title)

    finally:
        student_page.goto("about:blank")
        student_page.close()
        student_ctx.close()


def _setup_course_with_activity(
    page: Page,
    app_server: str,
    *,
    course_code: str,
    course_name: str,
    activity_title: str,
    student_email: str,
) -> str:
    """Create course, week, activity with template; publish and enrol student.

    Returns the course_id extracted from the URL.
    """
    create_course(
        page,
        app_server,
        code=course_code,
        name=course_name,
        semester="2026-S1",
    )

    match = re.search(r"/courses/([0-9a-f-]+)", page.url)
    assert match, f"Expected course UUID in URL, got: {page.url}"
    course_id = match.group(1)

    # Enable sharing so shared_in_unit works if needed later
    configure_course_setting(page, toggle_label="Default allow sharing", enabled=True)

    add_week(page, title="Navigator Week")
    add_activity(page, title=activity_title)

    _fill_template_workspace(page)

    # Navigate back to course detail page
    page.go_back()
    page.wait_for_url(re.compile(r"/courses/[0-9a-f-]+"), timeout=10000)

    publish_week(page, "Navigator Week")
    enrol_student(page, email=student_email)

    return course_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestNavigator:
    """E2E tests for the workspace navigator page."""

    def test_unauthenticated_redirect(self, fresh_page: Page, app_server: str) -> None:
        """AC2.5: Unauthenticated access to / redirects to /login."""
        fresh_page.goto(f"{app_server}/")
        expect(fresh_page).to_have_url(re.compile(r"/login"), timeout=10000)

    def test_navigator_renders_my_work(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC1.1, AC1.7, AC2.1: My Work section with owned workspace.

        Steps:
        1. Authenticate as student.
        2. Create a workspace owned by the student via DB.
        3. Navigate to /.
        4. Verify "My Work" section header appears.
        5. Verify workspace entry is visible.
        6. Verify empty sections (Unstarted, Shared With Me) are absent.
        7. Click workspace title, verify navigation to annotation page.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            uid = uuid4().hex[:8]
            email = f"nav-mywork-{uid}@test.example.edu.au"
            _authenticate_page(page, app_server, email=email)

            # Create a workspace owned by this student
            workspace_id = _create_workspace_via_db(
                user_email=email,
                html_content="<p>My navigator test workspace content</p>",
                seed_tags=False,
            )

            with subtests.test(msg="my_work_section_renders"):
                page.goto(f"{app_server}/")
                page.wait_for_timeout(2000)

                # "My Work" section header should be visible
                section_headers = page.locator(".navigator-section-header")
                header_texts = [
                    section_headers.nth(i).inner_text()
                    for i in range(section_headers.count())
                ]
                assert "My Work" in header_texts, (
                    f"Expected 'My Work' in section headers, got: {header_texts}"
                )

            with subtests.test(msg="workspace_entry_visible"):
                # The workspace link should be present with data-workspace-id
                ws_link = page.locator(f'[data-workspace-id="{workspace_id}"]')
                expect(ws_link).to_be_visible(timeout=5000)

            with subtests.test(msg="empty_sections_absent"):
                # "Unstarted Work" should NOT appear (student not enrolled)
                header_texts = [
                    section_headers.nth(i).inner_text()
                    for i in range(section_headers.count())
                ]
                assert "Unstarted Work" not in header_texts, (
                    "Unstarted Work should not appear for unenrolled student"
                )
                assert "Shared With Me" not in header_texts, (
                    "Shared With Me should not appear when no shared workspaces"
                )

            with subtests.test(msg="title_click_navigates"):
                ws_link = page.locator(f'[data-workspace-id="{workspace_id}"]')
                ws_link.click()
                page.wait_for_url(
                    re.compile(rf"workspace_id={workspace_id}"),
                    timeout=10000,
                )
                assert "/annotation" in page.url, (
                    f"Expected /annotation in URL, got: {page.url}"
                )

        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_navigator_renders_unstarted_work(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC1.2: Student sees Unstarted Work for published activities.

        Steps:
        1. Instructor creates course with published activity.
        2. Student is enrolled.
        3. Student navigates to /.
        4. Verify "Unstarted Work" section appears with activity title.
        """
        uid = uuid4().hex[:8]
        student_email = f"nav-unstarted-{uid}@test.example.edu.au"
        activity_title = f"Nav Activity {uid}"

        # --- Instructor sets up course ---
        instructor_ctx = browser.new_context()
        instructor_page = instructor_ctx.new_page()

        try:
            with subtests.test(msg="instructor_creates_course"):
                _authenticate_page(
                    instructor_page, app_server, email="instructor@uni.edu"
                )
                _setup_course_with_activity(
                    instructor_page,
                    app_server,
                    course_code=f"NAV-{uid}",
                    course_name=f"Navigator Test {uid}",
                    activity_title=activity_title,
                    student_email=student_email,
                )
        finally:
            instructor_page.goto("about:blank")
            instructor_page.close()
            instructor_ctx.close()

        # --- Student checks navigator ---
        student_ctx = browser.new_context()
        student_page = student_ctx.new_page()

        try:
            _authenticate_page(student_page, app_server, email=student_email)

            with subtests.test(msg="unstarted_section_renders"):
                student_page.goto(f"{app_server}/")
                student_page.wait_for_timeout(2000)

                section_headers = student_page.locator(".navigator-section-header")
                header_texts = [
                    section_headers.nth(i).inner_text()
                    for i in range(section_headers.count())
                ]
                assert "Unstarted Work" in header_texts, (
                    f"Expected 'Unstarted Work' in section headers, got: {header_texts}"
                )

            with subtests.test(msg="activity_title_visible"):
                activity_label = student_page.get_by_text(activity_title, exact=False)
                expect(activity_label.first).to_be_visible(timeout=5000)

            with subtests.test(msg="start_button_visible"):
                start_btn = student_page.locator(".navigator-start-btn")
                expect(start_btn.first).to_be_visible(timeout=5000)

        finally:
            student_page.goto("about:blank")
            student_page.close()
            student_ctx.close()

    def test_start_activity_clones_and_navigates(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC2.3: Start button clones activity template and navigates.

        Steps:
        1. Instructor creates course with published activity + template.
        2. Student is enrolled.
        3. Student navigates to /.
        4. Verify "Unstarted Work" shows the activity.
        5. Click Start.
        6. Verify navigation to /annotation?workspace_id=...
        7. Navigate back to /.
        8. Verify activity now appears under "My Work", not "Unstarted Work".
        """
        uid = uuid4().hex[:8]
        student_email = f"nav-start-{uid}@test.example.edu.au"
        activity_title = f"Start Activity {uid}"

        # --- Instructor sets up course ---
        instructor_ctx = browser.new_context()
        instructor_page = instructor_ctx.new_page()

        try:
            with subtests.test(msg="instructor_creates_course"):
                _authenticate_page(
                    instructor_page, app_server, email="instructor@uni.edu"
                )
                _setup_course_with_activity(
                    instructor_page,
                    app_server,
                    course_code=f"START-{uid}",
                    course_name=f"Start Test {uid}",
                    activity_title=activity_title,
                    student_email=student_email,
                )
        finally:
            instructor_page.goto("about:blank")
            instructor_page.close()
            instructor_ctx.close()

        # --- Student: clone via Start button ---
        _student_start_and_verify(
            browser,
            app_server,
            student_email=student_email,
            activity_title=activity_title,
            subtests=subtests,
        )
