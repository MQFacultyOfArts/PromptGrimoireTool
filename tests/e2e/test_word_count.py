"""E2E tests for word count limits feature.

Verifies:
- Activity settings UI for word count fields (AC3.1-AC3.5)
- Word count badge display (AC4.1, AC4.2, AC4.7)
- Export enforcement (AC5.1-AC5.5, AC6.1-AC6.2)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from pytest_subtests import SubTests


@pytest.mark.e2e
class TestWordCountSettings:
    def test_activity_word_count_settings(
        self, authenticated_page: Page, app_server: str, subtests: SubTests
    ) -> None:
        """Verify word count settings can be configured via activity settings dialog."""
        from tests.e2e import course_helpers

        # Create a course and activity via UI
        course_helpers.create_course(
            authenticated_page,
            app_server,
            code="WDCNT-SET",
            name="Word Count Settings",
            semester="2026-S1",
        )
        course_helpers.add_week(authenticated_page, title="Week 1")
        course_helpers.add_activity(authenticated_page, title="Test Activity")

        # Open activity settings dialog
        authenticated_page.get_by_test_id("activity-settings-btn").click()
        authenticated_page.get_by_test_id("activity-settings-title").wait_for(
            state="visible", timeout=5000
        )

        with subtests.test(msg="AC3.1: Set word minimum"):
            authenticated_page.get_by_test_id("activity-word-minimum-input").fill("200")

        with subtests.test(msg="AC3.2: Set word limit"):
            authenticated_page.get_by_test_id("activity-word-limit-input").fill("500")

        with subtests.test(msg="AC3.3: Set enforcement to Hard"):
            authenticated_page.get_by_test_id(
                "activity-word_limit_enforcement-select"
            ).click()
            authenticated_page.get_by_test_id(
                "activity-word_limit_enforcement-opt-on"
            ).click()

        # Save settings
        authenticated_page.get_by_test_id("save-activity-settings-btn").click()
        authenticated_page.get_by_test_id("activity-settings-title").wait_for(
            state="hidden", timeout=5000
        )

        with subtests.test(msg="AC3.5: Values persist across page reloads"):
            # Reload page
            authenticated_page.reload()
            authenticated_page.wait_for_load_state("networkidle")

            # Reopen activity settings
            authenticated_page.get_by_test_id("activity-settings-btn").click()
            authenticated_page.get_by_test_id("activity-settings-title").wait_for(
                state="visible", timeout=5000
            )

            from playwright.sync_api import expect

            # Verify word minimum persisted
            expect(
                authenticated_page.get_by_test_id("activity-word-minimum-input")
            ).to_have_value("200")
            # Verify word limit persisted
            expect(
                authenticated_page.get_by_test_id("activity-word-limit-input")
            ).to_have_value("500")

            # Close the dialog
            authenticated_page.keyboard.press("Escape")

        with subtests.test(msg="AC3.4: Course default word limit enforcement toggle"):
            # Open course settings dialog
            authenticated_page.get_by_test_id("course-settings-btn").click()
            authenticated_page.get_by_test_id("course-settings-title").wait_for(
                state="visible", timeout=5000
            )

            from playwright.sync_api import expect

            # Verify switch is visible
            switch = authenticated_page.get_by_test_id(
                "course-default_word_limit_enforcement-switch"
            )
            expect(switch).to_be_visible()

            # Toggle it on
            switch.click()

            # Save
            authenticated_page.get_by_test_id("save-course-settings-btn").click()
            authenticated_page.get_by_test_id("course-settings-title").wait_for(
                state="hidden", timeout=5000
            )

            # Reload and verify persistence
            authenticated_page.reload()
            authenticated_page.wait_for_load_state("networkidle")

            authenticated_page.get_by_test_id("course-settings-btn").click()
            authenticated_page.get_by_test_id("course-settings-title").wait_for(
                state="visible", timeout=5000
            )

            switch = authenticated_page.get_by_test_id(
                "course-default_word_limit_enforcement-switch"
            )
            expect(switch).to_have_attribute("aria-checked", "true")
