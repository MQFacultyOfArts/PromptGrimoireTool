"""E2E test: student user can access and use tag import.

Verifies that the instructor gate on tag import has been removed
(AC3.6) so any user can import tags from an accessible workspace.

The test creates two workspaces via direct DB operations:
- A source workspace with seeded tags (student has read access)
- A target workspace with no tags (student is owner)

The student opens the target workspace, opens the tag management
dialog, uses the workspace picker to select the source, imports
tags, and verifies they appear in the toolbar.

Acceptance Criteria:
- tag-lifecycle-235-291.AC3.6: Import available to all users
- tag-deletion-guards-413.AC4.5: Notification reports created/skipped counts
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from promptgrimoire.docs.helpers import wait_for_text_walker
from tests.e2e.conftest import _authenticate_page
from tests.e2e.db_fixtures import _create_workspace_via_db

if TYPE_CHECKING:
    from playwright.sync_api import Browser


@pytest.mark.e2e
class TestStudentTagImport:
    """Student can access and use the workspace-based tag import."""

    def test_student_can_import_tags(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """A non-instructor user can see and use the import picker.

        Steps:
        1. Authenticate as a regular student (not instructor, not admin)
        2. Create a source workspace with tags and a target without tags
        3. Grant student read access to source, owner on target
        4. Open the target workspace
        5. Open tag management dialog
        6. Verify import section is visible
        7. Select source workspace and click Import
        8. Verify imported tags appear in the tag toolbar

        Verifies: tag-lifecycle-235-291.AC3.6
        """
        uid = uuid4().hex[:8]
        student_email = f"import-student-{uid}@test.edu"

        context = browser.new_context()
        page = context.new_page()

        try:
            # Authenticate as student (random email = no admin/instructor role)
            _authenticate_page(page, app_server, email=student_email)

            # Create source workspace WITH tags
            _create_workspace_via_db(
                user_email=student_email,
                html_content="<p>Source workspace content</p>",
                seed_tags=True,
            )

            # Create target workspace WITHOUT tags
            target_ws_id = _create_workspace_via_db(
                user_email=student_email,
                html_content="<p>Target workspace content</p>",
                seed_tags=False,
            )

            # Navigate to the target workspace
            page.goto(f"{app_server}/annotation?workspace_id={target_ws_id}")
            wait_for_text_walker(page, timeout=15000)

            # Verify no tag buttons in toolbar initially
            toolbar = page.locator("[data-testid='tag-toolbar']")
            toolbar.wait_for(state="visible", timeout=5000)
            tag_buttons = toolbar.locator("[data-tag-id]")
            expect(tag_buttons).to_have_count(0, timeout=3000)

            # Open tag management dialog via the manage button
            page.get_by_test_id("tag-settings-btn").click()
            dialog = page.get_by_test_id("tag-management-dialog")
            expect(dialog).to_be_visible(timeout=5000)

            # Verify the import section is visible (AC3.6 -- not instructor-gated)
            import_select = dialog.get_by_test_id("import-workspace-select")
            expect(import_select).to_be_visible(timeout=5000)

            import_btn = dialog.get_by_test_id("import-tags-btn")
            expect(import_btn).to_be_visible(timeout=3000)

            # Select the source workspace from the dropdown
            # The dropdown is a Quasar q-select; click to open, then pick
            import_select.click()
            # Wait for dropdown options to appear, then click the source option
            source_option = page.get_by_role("option").first  # noqa: PG002 — Quasar dropdown options
            source_option.wait_for(state="visible", timeout=5000)
            source_option.click()

            # Click Import
            import_btn.click()

            # Wait for the success notification
            expect(page.locator(".q-notification")).to_contain_text(
                re.compile(r"Imported \d+ tag"), timeout=10000
            )

            # Close the dialog
            dialog.get_by_test_id("tag-management-done-btn").click()
            expect(dialog).to_be_hidden(timeout=5000)

            # Verify imported tags appear in the toolbar
            toolbar = page.locator("[data-testid='tag-toolbar']")
            tag_buttons = toolbar.locator("[data-tag-id]")
            expect(tag_buttons.first).to_be_visible(timeout=10000)

            # Should have the seed tags (10 tags from Legal Case Brief set)
            count = tag_buttons.count()
            assert count > 0, "Expected imported tags in toolbar"

        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_reimport_shows_no_new_tags_notification(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Re-importing tags that already exist shows "No new tags" notification.

        Steps:
        1. Create source workspace with tags and target without tags
        2. Import tags (first import -- creates tags)
        3. Close and reopen dialog
        4. Import again from same source
        5. Verify notification says "No new tags to import"

        Verifies: tag-deletion-guards-413.AC4.5
        """
        uid = uuid4().hex[:8]
        email = f"reimport-{uid}@test.edu"

        context = browser.new_context()
        page = context.new_page()

        try:
            _authenticate_page(page, app_server, email=email)

            _create_workspace_via_db(
                user_email=email,
                html_content="<p>Source for reimport test</p>",
                seed_tags=True,
            )

            target_ws_id = _create_workspace_via_db(
                user_email=email,
                html_content="<p>Target for reimport test</p>",
                seed_tags=False,
            )

            page.goto(f"{app_server}/annotation?workspace_id={target_ws_id}")
            wait_for_text_walker(page, timeout=15000)

            # --- First import ---
            page.get_by_test_id("tag-settings-btn").click()
            dialog = page.get_by_test_id("tag-management-dialog")
            expect(dialog).to_be_visible(timeout=5000)

            import_select = dialog.get_by_test_id("import-workspace-select")
            expect(import_select).to_be_visible(timeout=5000)
            import_select.click()

            source_option = page.get_by_role("option").first  # noqa: PG002
            source_option.wait_for(state="visible", timeout=5000)
            source_option.click()

            import_btn = dialog.get_by_test_id("import-tags-btn")
            import_btn.click()

            expect(page.locator(".q-notification")).to_contain_text(
                re.compile(r"Imported \d+ tag"), timeout=10000
            )

            # Wait for the first notification to dismiss before proceeding —
            # Firefox animation timing can leave it visible when the second
            # notification arrives, causing a strict-mode violation on the
            # `.q-notification` locator (resolves to 2 elements).
            expect(page.locator(".q-notification")).to_have_count(0, timeout=10000)

            # Close dialog
            dialog.get_by_test_id("tag-management-done-btn").click()
            expect(dialog).to_be_hidden(timeout=5000)

            # --- Second import (re-import) ---
            page.get_by_test_id("tag-settings-btn").click()
            dialog = page.get_by_test_id("tag-management-dialog")
            expect(dialog).to_be_visible(timeout=5000)

            import_select = dialog.get_by_test_id("import-workspace-select")
            expect(import_select).to_be_visible(timeout=5000)
            import_select.click()

            source_option = page.get_by_role("option").first  # noqa: PG002
            source_option.wait_for(state="visible", timeout=5000)
            source_option.click()

            import_btn = dialog.get_by_test_id("import-tags-btn")
            import_btn.click()

            # Should show "No new tags to import"
            expect(page.locator(".q-notification")).to_contain_text(
                "No new tags to import", timeout=10000
            )

        finally:
            page.goto("about:blank")
            page.close()
            context.close()
