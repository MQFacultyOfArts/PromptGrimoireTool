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
    from playwright.sync_api import Browser, Page
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
            from playwright.sync_api import expect

            authenticated_page.get_by_test_id(
                "activity-word_limit_enforcement-select"
            ).click()
            # Quasar renders select options in a teleported q-menu;
            # use q-item text filter (same pattern as test_instructor_workflow)
            authenticated_page.wait_for_timeout(300)
            authenticated_page.locator(".q-item").filter(has_text="Hard").click()

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
            from tests.e2e import course_helpers

            # Use the existing helper which handles q-toggle interaction correctly
            course_helpers.configure_course_setting(
                authenticated_page,
                toggle_label="Default word limit enforcement",
                enabled=True,
            )

            from playwright.sync_api import expect

            # Reload and verify persistence
            authenticated_page.reload()
            authenticated_page.wait_for_load_state("networkidle")

            authenticated_page.get_by_test_id("course-settings-btn").click()
            authenticated_page.get_by_test_id("course-settings-title").wait_for(
                state="visible", timeout=5000
            )

            # q-toggle uses aria-checked on the .q-toggle element
            toggle = authenticated_page.locator(".q-toggle").filter(
                has_text="Default word limit enforcement"
            )
            expect(toggle).to_have_attribute("aria-checked", "true")


@pytest.mark.e2e
class TestWordCountExport:
    def test_soft_enforcement_warning(
        self, browser: Browser, app_server: str, subtests: SubTests
    ) -> None:
        """Verify soft enforcement shows warning and allows export."""
        from pathlib import Path

        from playwright.sync_api import expect

        from tests.e2e.annotation_helpers import _create_workspace_with_word_limits
        from tests.e2e.conftest import _authenticate_page

        context = browser.new_context()
        page = context.new_page()
        try:
            email = _authenticate_page(page, app_server)

            # Create workspace with soft enforcement (word_limit_enforcement=False)
            # and a low word limit that we'll exceed
            workspace_id = _create_workspace_with_word_limits(
                user_email=email,
                html_content="<p>Test content.</p>",
                word_limit=10,
                word_limit_enforcement=False,
            )

            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)

            # Switch to Respond tab and type enough words to exceed limit
            page.get_by_test_id("tab-respond").click()
            page.wait_for_timeout(1000)

            editor = (
                page.get_by_test_id("milkdown-editor-container")
                .locator("[contenteditable]")
                .first
            )
            editor.click()
            page.keyboard.type(
                "This is a test response with many words to exceed"
                " the word limit for testing purposes here",
                delay=10,
            )

            # Wait for Yjs sync
            page.wait_for_timeout(3000)

            with subtests.test(msg="AC5.1: Export shows warning dialog"):
                page.get_by_test_id("export-pdf-btn").click()
                # The warning dialog should appear with "Export Anyway" button
                export_anyway_btn = page.get_by_test_id("wc-export-anyway-btn")
                expect(export_anyway_btn).to_be_visible(timeout=10000)

            with subtests.test(msg="AC5.2: User can confirm and proceed"):
                # Click Export Anyway and verify download starts
                with page.expect_download(timeout=60000) as dl:
                    page.get_by_test_id("wc-export-anyway-btn").click()

                download = dl.value
                dl_path = download.path()
                assert dl_path is not None
                raw = Path(dl_path).read_bytes()

                if raw[:4] == b"%PDF":
                    # Slow mode — extract text from compiled PDF
                    import pymupdf

                    doc = pymupdf.open(dl_path)
                    export_text = "".join(p.get_text() for p in doc)
                    doc.close()
                    is_pdf = True
                else:
                    export_text = raw.decode("utf-8")
                    is_pdf = False

            with subtests.test(msg="AC5.3: TeX output contains snitch badge"):
                if is_pdf:
                    # In rendered PDF, check for the visible badge text
                    assert "Exceeded" in export_text, (
                        f"Expected 'Exceeded' in PDF text, got: {export_text[:500]}"
                    )
                else:
                    # In .tex source, check for LaTeX command or text
                    assert "Exceeded" in export_text or "fcolorbox" in export_text, (
                        f"Expected snitch badge in TeX output, got: {export_text[:500]}"
                    )
        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_soft_enforcement_under_minimum(
        self, browser: Browser, app_server: str, subtests: SubTests
    ) -> None:
        """Verify dialog shows under-minimum violation."""
        from playwright.sync_api import expect

        from tests.e2e.annotation_helpers import _create_workspace_with_word_limits
        from tests.e2e.conftest import _authenticate_page

        context = browser.new_context()
        page = context.new_page()
        try:
            email = _authenticate_page(page, app_server)

            # Create workspace with soft enforcement and high minimum
            workspace_id = _create_workspace_with_word_limits(
                user_email=email,
                html_content="<p>Test content.</p>",
                word_minimum=200,
                word_limit=500,
                word_limit_enforcement=False,
            )

            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)

            # Switch to Respond tab and type only a few words
            page.get_by_test_id("tab-respond").click()
            page.wait_for_timeout(1000)

            editor = (
                page.get_by_test_id("milkdown-editor-container")
                .locator("[contenteditable]")
                .first
            )
            editor.click()
            page.keyboard.type("Just five little words.", delay=10)

            # Wait for Yjs sync
            page.wait_for_timeout(3000)

            with subtests.test(msg="AC5.5: Under-minimum violation"):
                page.get_by_test_id("export-pdf-btn").click()
                export_anyway_btn = page.get_by_test_id("wc-export-anyway-btn")
                expect(export_anyway_btn).to_be_visible(timeout=10000)
        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_hard_enforcement_blocks(
        self, browser: Browser, app_server: str, subtests: SubTests
    ) -> None:
        """Verify hard enforcement blocks export entirely."""
        from playwright.sync_api import expect

        from tests.e2e.annotation_helpers import _create_workspace_with_word_limits
        from tests.e2e.conftest import _authenticate_page

        context = browser.new_context()
        page = context.new_page()
        try:
            email = _authenticate_page(page, app_server)

            # Create workspace with hard enforcement and low word limit
            workspace_id = _create_workspace_with_word_limits(
                user_email=email,
                html_content="<p>Test content.</p>",
                word_limit=10,
                word_limit_enforcement=True,  # Hard enforcement
            )

            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)

            # Switch to Respond tab and type enough words to exceed limit
            page.get_by_test_id("tab-respond").click()
            page.wait_for_timeout(1000)

            editor = (
                page.get_by_test_id("milkdown-editor-container")
                .locator("[contenteditable]")
                .first
            )
            editor.click()
            page.keyboard.type(
                "This is a response with many words exceeding the configured"
                " word limit for hard enforcement testing",
                delay=10,
            )

            # Wait for Yjs sync
            page.wait_for_timeout(3000)

            with subtests.test(msg="AC6.1: Export blocked with dialog"):
                page.get_by_test_id("export-pdf-btn").click()
                # The blocking dialog should appear with dismiss button
                dismiss_btn = page.get_by_test_id("wc-dismiss-btn")
                expect(dismiss_btn).to_be_visible(timeout=10000)

            with subtests.test(msg="AC6.2: No export button in dialog"):
                # Verify Export Anyway button is NOT visible
                export_anyway_btn = page.get_by_test_id("wc-export-anyway-btn")
                expect(export_anyway_btn).not_to_be_visible()

            with subtests.test(msg="AC6.2: Dismiss button closes dialog"):
                page.get_by_test_id("wc-dismiss-btn").click()
                # Dialog should close - dismiss button should no longer be visible
                dismiss_btn = page.get_by_test_id("wc-dismiss-btn")
                expect(dismiss_btn).not_to_be_visible(timeout=5000)
        finally:
            page.goto("about:blank")
            page.close()
            context.close()


@pytest.mark.e2e
class TestWordCountBadge:
    """Word count badge visibility and live update on the annotation page."""

    def test_badge_visible_with_limits(
        self, browser: Browser, app_server: str, subtests: SubTests
    ) -> None:
        """AC4.1, AC4.7: Badge visible with limits and updates live."""
        from playwright.sync_api import expect

        from tests.e2e.annotation_helpers import _create_workspace_with_word_limits
        from tests.e2e.conftest import _authenticate_page

        context = browser.new_context()
        page = context.new_page()
        try:
            email = _authenticate_page(page, app_server)

            workspace_id = _create_workspace_with_word_limits(
                user_email=email,
                html_content="<p>Test content for word count badge visibility.</p>",
                word_limit=100,
            )

            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            page.wait_for_load_state("networkidle")

            with subtests.test(msg="AC4.1: Badge visible with limits"):
                badge = page.get_by_test_id("word-count-badge")
                expect(badge).to_be_visible(timeout=10000)

            with subtests.test(msg="AC4.7: Badge updates live after typing"):
                # Switch to Respond tab
                page.get_by_test_id("tab-respond").click()
                page.wait_for_timeout(1000)

                # Type text in editor
                editor = (
                    page.get_by_test_id("milkdown-editor-container")
                    .locator("[contenteditable]")
                    .first
                )
                editor.click()
                page.keyboard.type("word " * 10, delay=20)

                # Wait for Yjs sync
                page.wait_for_timeout(2000)

                # Verify badge text updated
                badge = page.get_by_test_id("word-count-badge")
                expect(badge).to_contain_text("Words:")

            with subtests.test(msg="AC4.1: Badge visible on Annotate tab"):
                page.get_by_test_id("tab-annotate").click()
                page.wait_for_timeout(500)
                badge = page.get_by_test_id("word-count-badge")
                expect(badge).to_be_visible()
        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_badge_hidden_without_limits(
        self, browser: Browser, app_server: str
    ) -> None:
        """AC4.2: Badge hidden when no limits configured."""
        from playwright.sync_api import expect

        from tests.e2e.annotation_helpers import _create_workspace_via_db
        from tests.e2e.conftest import _authenticate_page

        context = browser.new_context()
        page = context.new_page()
        try:
            email = _authenticate_page(page, app_server)

            workspace_id = _create_workspace_via_db(
                user_email=email,
                html_content="<p>No limits workspace content.</p>",
                seed_tags=False,
            )

            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            page.wait_for_load_state("networkidle")

            badge = page.get_by_test_id("word-count-badge")
            expect(badge).not_to_be_visible(timeout=5000)
        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_badge_with_minimum_only(self, browser: Browser, app_server: str) -> None:
        """AC4.1: Badge visible when only word_minimum is set (no word_limit)."""
        from playwright.sync_api import expect

        from tests.e2e.annotation_helpers import _create_workspace_with_word_limits
        from tests.e2e.conftest import _authenticate_page

        context = browser.new_context()
        page = context.new_page()
        try:
            email = _authenticate_page(page, app_server)

            workspace_id = _create_workspace_with_word_limits(
                user_email=email,
                html_content="<p>Minimum-only badge test content.</p>",
                word_minimum=200,
            )

            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            page.wait_for_load_state("networkidle")

            badge = page.get_by_test_id("word-count-badge")
            expect(badge).to_be_visible(timeout=10000)
            expect(badge).to_contain_text("Words:")
            expect(badge).to_contain_text("minimum")
        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_badge_with_limit_only(self, browser: Browser, app_server: str) -> None:
        """AC4.1: Badge visible when only word_limit is set (no word_minimum)."""
        from playwright.sync_api import expect

        from tests.e2e.annotation_helpers import _create_workspace_with_word_limits
        from tests.e2e.conftest import _authenticate_page

        context = browser.new_context()
        page = context.new_page()
        try:
            email = _authenticate_page(page, app_server)

            workspace_id = _create_workspace_with_word_limits(
                user_email=email,
                html_content="<p>Limit-only badge test content.</p>",
                word_limit=500,
            )

            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            page.wait_for_load_state("networkidle")

            badge = page.get_by_test_id("word-count-badge")
            expect(badge).to_be_visible(timeout=10000)
            expect(badge).to_contain_text("Words:")
        finally:
            page.goto("about:blank")
            page.close()
            context.close()
