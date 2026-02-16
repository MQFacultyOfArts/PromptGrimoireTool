"""E2E test: instructor course setup workflow.

Narrative persona test covering the full instructor journey:
authenticate -> create course -> add week -> create activity ->
configure copy protection -> edit template workspace -> publish week.

Each step is a discrete subtest checkpoint using pytest-subtests.

Acceptance Criteria:
- 156-e2e-test-migration.AC3.1: Persona test covering course setup flow
- 156-e2e-test-migration.AC3.6: Uses pytest-subtests for checkpoints
- 156-e2e-test-migration.AC4.1: No CSS.highlights assertions
- 156-e2e-test-migration.AC4.2: No page.evaluate() for internal DOM state
- 156-e2e-test-migration.AC5.1: Creates own workspace (no shared state)
- 156-e2e-test-migration.AC5.2: UUID-suffixed course code for isolation

Traceability:
- Issue: #156 (E2E test migration)
- Design: docs/design-plans/2026-02-14-156-e2e-test-migration.md Phase 3
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from tests.e2e.conftest import _authenticate_page
from tests.e2e.course_helpers import (
    add_activity,
    add_week,
    configure_course_copy_protection,
    create_course,
    enrol_student,
    publish_week,
)

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page
    from pytest_subtests import SubTests


def _fill_template_workspace(page: Page) -> None:
    """Click Create Template, add content, and verify rendering.

    Extracted to keep test method statement count under the limit.
    Expects the page to be on a course detail page with a freshly
    created activity showing a "Create Template" button.
    """
    # Click "Create Template" to open the template workspace
    page.get_by_role(
        "button",
        name=re.compile(r"Create Template|Edit Template"),
    ).click()

    # Wait for the annotation page to load
    page.wait_for_url(
        re.compile(r"/annotation\?workspace_id="),
        timeout=10000,
    )

    # Fill content in the editor (QEditor with placeholder)
    content_input = page.get_by_placeholder(re.compile(r"paste|content", re.IGNORECASE))
    content_input.wait_for(state="visible", timeout=5000)
    content_input.fill("Becky Bennett suffered a workplace injury.")

    # Click "Add Document" button
    page.get_by_role(
        "button",
        name=re.compile(r"add document", re.IGNORECASE),
    ).click()

    # Confirm content type dialog
    confirm_btn = page.get_by_role(
        "button",
        name=re.compile(r"confirm", re.IGNORECASE),
    )
    confirm_btn.wait_for(state="visible", timeout=5000)
    confirm_btn.click()

    # Wait for text walker to initialise (content rendered)
    page.wait_for_function(
        "() => window._textNodes && window._textNodes.length > 0",
        timeout=10000,
    )

    # Verify document content is visible
    doc_container = page.locator("#doc-container")
    doc_container.wait_for(state="visible", timeout=5000)
    assert doc_container.inner_text().strip(), (
        "Document container should have visible text"
    )


def _extract_course_id(page: Page) -> str:
    """Extract the course UUID from the current page URL.

    Expects the page URL to contain ``/courses/{uuid}``.
    """
    match = re.search(r"/courses/([0-9a-f-]+)", page.url)
    assert match, f"Expected course UUID in URL, got: {page.url}"
    return match.group(1)


def _student_clones_and_sees_content(
    browser: Browser,
    app_server: str,
    *,
    student_email: str,
    course_id: str,
    activity_title: str,
    expected_text: str,
) -> None:
    """Log in as student, navigate to course, clone workspace, verify content.

    Creates a separate browser context for the student. Verifies the
    cloned workspace contains the template content.
    """
    student_ctx = browser.new_context()
    student_page = student_ctx.new_page()
    try:
        _authenticate_page(student_page, app_server, email=student_email)

        # Navigate to the course detail page
        student_page.goto(f"{app_server}/courses/{course_id}")

        # Find and click "Start Activity" for the activity
        activity_label = student_page.get_by_text(activity_title)
        activity_label.wait_for(state="visible", timeout=10000)
        card = activity_label.locator("xpath=ancestor::div[contains(@class, 'q-card')]")
        card.get_by_role("button", name="Start Activity").click()

        # Wait for redirect to annotation page with cloned workspace
        student_page.wait_for_url(
            re.compile(r"/annotation\?workspace_id="),
            timeout=15000,
        )

        # Wait for text walker to initialise (content rendered)
        student_page.wait_for_function(
            "() => window._textNodes && window._textNodes.length > 0",
            timeout=10000,
        )

        # Verify cloned content is visible
        doc_container = student_page.locator("#doc-container")
        doc_container.wait_for(state="visible", timeout=5000)
        visible_text = doc_container.inner_text().strip()
        assert expected_text in visible_text, (
            f"Expected '{expected_text}' in cloned workspace, got: {visible_text!r}"
        )
    finally:
        student_page.close()
        student_ctx.close()


def _verify_copy_protection_enabled(page: Page) -> None:
    """Re-open course settings and verify copy protection is on.

    Opens the settings dialog, checks the switch state, then
    closes the dialog via Cancel.
    """
    page.locator("button").filter(
        has=page.locator("i.q-icon", has_text="settings")
    ).click()
    dialog_title = page.get_by_text("Course Settings", exact=True)
    dialog_title.wait_for(state="visible", timeout=5000)

    toggle = page.locator(".q-toggle").filter(has_text="Default copy protection")
    assert toggle.get_attribute("aria-checked") == "true", (
        "Copy protection switch should be ON after enabling"
    )

    # Close the dialog without saving
    page.get_by_role("button", name="Cancel").click()
    dialog_title.wait_for(state="hidden", timeout=5000)


@pytest.mark.e2e
class TestInstructorWorkflow:
    """Instructor persona: course setup from scratch."""

    def test_full_course_setup(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """Walk through complete course setup as an instructor.

        Creates a course, adds a week and activity, configures copy
        protection, edits the template workspace, and publishes.
        """
        # Unique suffix for xdist isolation
        uid = uuid4().hex[:8]
        course_code = f"TEST-{uid}"
        course_name = f"E2E Workflow {uid}"
        semester = "2026-S1"

        context = browser.new_context()
        page = context.new_page()

        try:
            with subtests.test(msg="authenticate_as_instructor"):
                _authenticate_page(page, app_server, email="instructor@uni.edu")
                # Verify auth succeeded — not redirected to login
                assert "/login" not in page.url, "Auth should succeed"

            with subtests.test(msg="create_course"):
                create_course(
                    page,
                    app_server,
                    code=course_code,
                    name=course_name,
                    semester=semester,
                )
                page.get_by_text(f"{course_code} - {course_name}").wait_for(
                    state="visible", timeout=5000
                )

            with subtests.test(msg="add_week"):
                add_week(page, title="Introduction")
                page.get_by_text(re.compile(r"Week \d+:\s*Introduction")).wait_for(
                    state="visible", timeout=5000
                )

            with subtests.test(msg="create_activity"):
                add_activity(page, title="Annotate Becky")
                page.get_by_text("Annotate Becky").wait_for(
                    state="visible", timeout=5000
                )

            with subtests.test(msg="configure_copy_protection"):
                configure_course_copy_protection(page, enabled=True)
                _verify_copy_protection_enabled(page)

            with subtests.test(msg="edit_template_workspace"):
                _fill_template_workspace(page)

            with subtests.test(msg="publish_week"):
                # Navigate back to the course detail page
                page.go_back()
                page.wait_for_url(
                    re.compile(r"/courses/[0-9a-f-]+"),
                    timeout=10000,
                )
                publish_week(page, "Introduction")
                unpub_btn = page.get_by_role("button", name="Unpublish")
                assert unpub_btn.is_visible(), "Unpublish button should be visible"

            # --- Bridge: instructor-to-student handoff ---
            student_email = f"student-{uid}@test.edu"
            course_id = _extract_course_id(page)

            with subtests.test(msg="enrol_student"):
                enrol_student(page, email=student_email)

            with subtests.test(msg="student_clones_and_sees_content"):
                _student_clones_and_sees_content(
                    browser,
                    app_server,
                    student_email=student_email,
                    course_id=course_id,
                    activity_title="Annotate Becky",
                    expected_text="Becky Bennett",
                )

        finally:
            page.close()
            context.close()
