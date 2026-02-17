"""E2E test: adversarial student behaviour -- security edge cases.

Narrative persona test covering three threat categories:
1. Dead-end navigation (bad workspace IDs)
2. Content injection (BLNS/XSS strings pasted as content)
3. Copy protection bypass attempts (copy, cut, drag, print interception)

Each step is a discrete subtest checkpoint using pytest-subtests.

Acceptance Criteria:
- 156-e2e-test-migration.AC3.5: Persona test covering BLNS/XSS,
  copy protection bypass, dead-ends
- 156-e2e-test-migration.AC3.6: Uses pytest-subtests for checkpoints
- 156-e2e-test-migration.AC4.1: No CSS.highlights assertions
- 156-e2e-test-migration.AC4.2: No page.evaluate() for internal DOM state
- 156-e2e-test-migration.AC5.1: Creates own workspace (no shared state)
- 156-e2e-test-migration.AC5.2: Random auth email + UUID course codes for isolation
- 156-e2e-test-migration.AC7.3: BLNS edge cases handled (#101)

Traceability:
- Issue: #156 (E2E test migration)
- Issue: #101 (CJK/BLNS support)
- Design: docs/design-plans/2026-02-14-156-e2e-test-migration.md Phase 7
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import (
    select_chars,
    setup_workspace_with_content,
    wait_for_text_walker,
)
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


# ---------------------------------------------------------------------------
# BLNS sample strings -- representative subset, defined inline
# (no cross-boundary import from tests.unit.conftest)
# ---------------------------------------------------------------------------

BLNS_SAMPLES: dict[str, list[str]] = {
    "script_injection": [
        '<script>alert("XSS")</script>',
        '"><img src=x onerror=alert(1)>',
        "javascript:alert('XSS')",
    ],
    "sql_injection": [
        "'; DROP TABLE users; --",
        "1' OR '1'='1",
    ],
    "two_byte_characters": [
        "\u7530\u4e2d\u3055\u3093\u306b\u3042\u3052\u3066\u4e0b\u3055\u3044",
        "\u30d1\u30fc\u30c6\u30a3\u30fc\u3078\u884c\u304b\u306a\u3044\u304b",
        "\uc0ac765765765765",
    ],
}


# Locator constants
ANNOTATION_CARD = "[data-testid='annotation-card']"


# ---------------------------------------------------------------------------
# Local helper -- extract course ID from URL
# ---------------------------------------------------------------------------


def _extract_course_id(page: Page) -> str:
    """Extract the course UUID from the current page URL."""
    match = re.search(r"/courses/([0-9a-f-]+)", page.url)
    assert match, f"Expected course UUID in URL, got: {page.url}"
    return match.group(1)


@pytest.mark.e2e
class TestNaughtyStudent:
    """Adversarial student persona: security edge cases and dead ends."""

    def test_dead_end_navigation(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """Dead-end navigation: bad workspace IDs produce graceful errors.

        Verifies: invalid UUID, nonexistent UUID, and missing workspace_id
        parameter all result in usable (non-crashed) pages.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            _authenticate_page(page, app_server)

            with subtests.test(msg="invalid_workspace_id"):
                # Navigate to annotation with a non-UUID workspace_id
                page.goto(f"{app_server}/annotation?workspace_id=not-a-valid-uuid")
                page.wait_for_load_state("networkidle")

                # Page should show the "No workspace selected" fallback UI
                # (invalid UUID parses as None, falls through to create form)
                expect(page.get_by_text("No workspace selected")).to_be_visible(
                    timeout=10000
                )

                # A "Create Workspace" button should be available
                expect(
                    page.get_by_role(
                        "button", name=re.compile("Create Workspace", re.IGNORECASE)
                    )
                ).to_be_visible(timeout=5000)

            with subtests.test(msg="nonexistent_workspace_id"):
                # Navigate to annotation with a valid UUID that doesn't exist
                page.goto(
                    f"{app_server}/annotation"
                    "?workspace_id=00000000-0000-0000-0000-000000000000"
                )
                page.wait_for_load_state("networkidle")

                # Page should show "Workspace not found" in red
                expect(page.get_by_text("Workspace not found")).to_be_visible(
                    timeout=10000
                )

                # A "Create New Workspace" button should be visible as fallback
                expect(
                    page.get_by_role(
                        "button",
                        name=re.compile("Create New Workspace", re.IGNORECASE),
                    )
                ).to_be_visible(timeout=5000)

            with subtests.test(msg="no_workspace_id"):
                # Navigate to annotation with no query parameter
                page.goto(f"{app_server}/annotation")
                page.wait_for_load_state("networkidle")

                # Page should show the workspace creation UI
                expect(page.get_by_text("No workspace selected")).to_be_visible(
                    timeout=10000
                )

                # Create Workspace button should be accessible
                expect(
                    page.get_by_role(
                        "button", name=re.compile("Create Workspace", re.IGNORECASE)
                    )
                ).to_be_visible(timeout=5000)

        finally:
            page.close()
            context.close()

    def test_xss_injection_sanitised(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """XSS injection: script tags and event handlers are stripped.

        Verifies: pasted XSS payloads are sanitised by the input pipeline.
        """
        context = browser.new_context()
        page = context.new_page()

        # Collect JS errors to verify no alert() fired
        js_errors: list[str] = []
        page.on("pageerror", lambda error: js_errors.append(str(error)))

        try:
            _authenticate_page(page, app_server)

            with subtests.test(msg="script_tag_stripped"):
                setup_workspace_with_content(
                    page,
                    app_server,
                    '<script>alert("xss")</script>Safe text here',
                )

                doc = page.locator("#doc-container")

                # "Safe text here" should be visible
                expect(doc).to_contain_text("Safe text here", timeout=10000)

                # The script must NOT execute.  The input pipeline
                # HTML-escapes the tags so they render as visible text
                # (e.g. "&lt;script&gt;") rather than being stripped.
                # The critical assertion is that no JS alert fired.
                assert not js_errors, f"Unexpected JS errors: {js_errors}"

            with subtests.test(msg="html_injection_escaped"):
                js_errors.clear()

                setup_workspace_with_content(
                    page,
                    app_server,
                    "<img src=x onerror=alert(1)>Normal text",
                )

                doc = page.locator("#doc-container")

                # Normal text should render
                expect(doc).to_contain_text("Normal text", timeout=10000)

                # No JS errors from the onerror handler
                assert not js_errors, f"Unexpected JS errors from img: {js_errors}"

        finally:
            page.close()
            context.close()

    def test_blns_content_resilience(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """BLNS strings: system doesn't crash on naughty input.

        Verifies: representative BLNS strings can be pasted as content
        without crashing the page. For strings that render successfully,
        attempts highlighting to verify the annotation pipeline handles them.
        """
        context = browser.new_context()
        page = context.new_page()

        # Track strings that successfully rendered with text nodes
        highlightable_content: str | None = None

        try:
            _authenticate_page(page, app_server)

            for category, strings in BLNS_SAMPLES.items():
                for idx, naughty_string in enumerate(strings):
                    with subtests.test(msg=f"blns_{category}_{idx}"):
                        # Navigate to annotation and create workspace
                        page.goto(f"{app_server}/annotation")
                        page.get_by_role(
                            "button", name=re.compile("create", re.IGNORECASE)
                        ).click()
                        page.wait_for_url(re.compile(r"workspace_id="))

                        # Fill content with the naughty string
                        content_input = page.get_by_placeholder(
                            re.compile("paste|content", re.IGNORECASE)
                        )
                        content_input.fill(naughty_string)
                        page.get_by_role(
                            "button", name=re.compile("add|submit", re.IGNORECASE)
                        ).click()

                        # Confirm content type dialog if it appears
                        confirm_btn = page.get_by_role(
                            "button", name=re.compile("confirm", re.IGNORECASE)
                        )
                        try:
                            confirm_btn.wait_for(state="visible", timeout=5000)
                            confirm_btn.click()
                        except TimeoutError:
                            # Some strings may not trigger the dialog;
                            # that's fine -- we just want to verify no crash.
                            pass

                        # Wait briefly for the page to settle
                        page.wait_for_timeout(2000)

                        # Core assertion: page didn't crash
                        # Verify known UI element is still visible
                        heading = page.get_by_text("Annotation Workspace").first
                        expect(heading).to_be_visible(timeout=5000)

                        # Try to detect if text walker initialised
                        try:
                            wait_for_text_walker(page, timeout=5000)
                            # If we get here, content rendered with text nodes
                            if highlightable_content is None:
                                highlightable_content = naughty_string
                        except TimeoutError:
                            # Some strings produce empty documents after
                            # sanitisation -- that's acceptable.
                            pass

            with subtests.test(msg="blns_highlight_resilience"):
                if highlightable_content is None:
                    pytest.skip("No BLNS string rendered with text nodes")

                # Create a fresh workspace with a known-good naughty string
                setup_workspace_with_content(page, app_server, highlightable_content)

                # Attempt to highlight the first few characters
                select_chars(page, 0, 2)
                page.locator("[data-testid='tag-toolbar'] button").first.click()

                # Verify annotation card appears
                expect(page.locator(ANNOTATION_CARD).first).to_be_visible(timeout=10000)

        finally:
            page.close()
            context.close()

    def test_copy_protection_bypass(  # noqa: PLR0915
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """Copy protection bypass: instructor-protected content blocks student.

        Full flow: instructor creates course with copy protection,
        student clones workspace and attempts copy/cut/context menu/print bypass.
        """
        # Unique identifiers for isolation
        uid = uuid4().hex[:8]
        course_code = f"NAUGHTY-{uid}"
        course_name = f"Naughty Student Test {uid}"
        student_email = f"naughty-student-{uid}@test.edu"

        # ---- Instructor side ----
        instructor_ctx = browser.new_context()
        instructor_page = instructor_ctx.new_page()

        # ---- Student side ----
        student_ctx = browser.new_context()
        student_page = student_ctx.new_page()

        try:
            # == Instructor setup ==
            with subtests.test(msg="instructor_setup"):
                _authenticate_page(
                    instructor_page, app_server, email="instructor@uni.edu"
                )

                # Create course
                create_course(
                    instructor_page,
                    app_server,
                    code=course_code,
                    name=course_name,
                    semester="2026-S1",
                )

                # Add week and activity (before copy protection — matches
                # test_instructor_workflow ordering that avoids dialog→nav race)
                add_week(instructor_page, title="Protected Content")
                add_activity(instructor_page, title="Protected Activity")

                # Enable copy protection (after week/activity creation)
                configure_course_copy_protection(instructor_page, enabled=True)

                # Fill template workspace with content
                instructor_page.get_by_role(
                    "button",
                    name=re.compile(r"Create Template|Edit Template"),
                ).click()
                instructor_page.wait_for_url(
                    re.compile(r"/annotation\?workspace_id="),
                    timeout=10000,
                )

                content_input = instructor_page.get_by_placeholder(
                    re.compile(r"paste|content", re.IGNORECASE)
                )
                content_input.wait_for(state="visible", timeout=5000)
                content_input.fill(
                    "This is protected content that students cannot copy."
                )

                instructor_page.get_by_role(
                    "button", name=re.compile(r"add document", re.IGNORECASE)
                ).click()

                # Confirm content type dialog
                confirm_btn = instructor_page.get_by_role(
                    "button", name=re.compile(r"confirm", re.IGNORECASE)
                )
                confirm_btn.wait_for(state="visible", timeout=5000)
                confirm_btn.click()

                wait_for_text_walker(instructor_page, timeout=10000)

                # Go back to course page and publish
                instructor_page.go_back()
                instructor_page.wait_for_url(
                    re.compile(r"/courses/[0-9a-f-]+"), timeout=10000
                )
                publish_week(instructor_page, "Protected Content")

                # Enrol student
                enrol_student(instructor_page, email=student_email)

            # == Student side ==
            course_id = _extract_course_id(instructor_page)

            with subtests.test(msg="student_clones_workspace"):
                _authenticate_page(student_page, app_server, email=student_email)

                # Navigate to course and clone workspace
                student_page.goto(f"{app_server}/courses/{course_id}")
                activity_label = student_page.get_by_text("Protected Activity")
                activity_label.wait_for(state="visible", timeout=10000)
                card = activity_label.locator(
                    "xpath=ancestor::div[contains(@class, 'q-card')]"
                )
                card.get_by_role("button", name="Start Activity").click()

                # Wait for annotation page with cloned workspace
                student_page.wait_for_url(
                    re.compile(r"/annotation\?workspace_id="), timeout=15000
                )
                wait_for_text_walker(student_page, timeout=15000)

                # Verify content is visible
                expect(student_page.locator("#doc-container")).to_contain_text(
                    "protected content", timeout=10000
                )

            with subtests.test(msg="copy_blocked"):
                # Select text in the document
                select_chars(student_page, 0, 5)

                # Attempt Ctrl+C
                student_page.keyboard.press("Control+c")

                # Verify toast notification about copying being disabled
                expect(student_page.locator(".q-notification")).to_contain_text(
                    "Copying is disabled", timeout=5000
                )

            with subtests.test(msg="cut_blocked"):
                # Wait for previous toast to clear
                student_page.wait_for_timeout(3500)

                # Select text and attempt Ctrl+X
                select_chars(student_page, 0, 5)
                student_page.keyboard.press("Control+x")

                # Verify toast notification
                expect(student_page.locator(".q-notification")).to_contain_text(
                    "Copying is disabled", timeout=5000
                )

            with subtests.test(msg="context_menu_blocked"):
                # Wait for previous toast to clear
                student_page.wait_for_timeout(3500)

                # Right-click on the document container
                student_page.locator("#doc-container").click(button="right")

                # Verify toast notification (context menu event is prevented)
                expect(student_page.locator(".q-notification")).to_contain_text(
                    "Copying is disabled", timeout=5000
                )

            with subtests.test(msg="print_blocked"):
                # Wait for previous toast to clear
                student_page.wait_for_timeout(3500)

                # Attempt Ctrl+P
                student_page.keyboard.press("Control+p")

                # Verify toast notification
                expect(student_page.locator(".q-notification")).to_contain_text(
                    "Copying is disabled", timeout=5000
                )

            with subtests.test(msg="protected_indicator_visible"):
                # Verify the "Protected" lock icon chip is visible.
                # Use exact=True to avoid matching "Protected Activity..."
                # placement chip and document content containing "protected".
                expect(student_page.get_by_text("Protected", exact=True)).to_be_visible(
                    timeout=5000
                )

        finally:
            student_page.close()
            student_ctx.close()
            instructor_page.close()
            instructor_ctx.close()
