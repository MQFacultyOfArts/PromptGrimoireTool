"""E2E test: empty-tag annotation UX.

Verifies the floating highlight menu behaviour when a workspace
has zero tags or when the user lacks tag creation permission.

Acceptance Criteria:
- empty-tag-ux-210.AC1.1: Floating menu shows "+ New" button in zero-tag workspace
- empty-tag-ux-210.AC1.2: Clicking "+ New" creates tag and auto-applies highlight
- empty-tag-ux-210.AC1.3: "+ New" appears alongside tag buttons when tags exist
- empty-tag-ux-210.AC1.4: "No tags available" shown when user lacks permission
- empty-tag-ux-210.AC1.5: Cancelling dialog creates no highlight
- empty-tag-ux-210.AC3.1: Tooltip on "+ New" button

Traceability:
- Issue: #210 (Empty-tag annotation UX)
- Design: docs/implementation-plans/2026-03-01-empty-tag-ux-210/phase_01.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import (
    _create_workspace_no_tag_permission,
    _create_workspace_via_db,
    select_chars,
    wait_for_text_walker,
)
from tests.e2e.conftest import _authenticate_page

if TYPE_CHECKING:
    from playwright.sync_api import Browser
    from pytest_subtests import SubTests


def _create_workspace_no_tags(user_email: str) -> str:
    """Create a workspace with content but no seeded tags.

    Uses ``_create_workspace_via_db`` with ``seed_tags=False``.
    Standalone workspaces have ``allow_tag_creation=True`` by default,
    so the owner can create tags via the "+ New" button.

    Args:
        user_email: Email of the workspace owner.

    Returns:
        workspace_id as string.
    """
    return _create_workspace_via_db(
        user_email=user_email,
        html_content=(
            "<p>Empty tag test content for verifying the floating menu.</p>"
            "<p>Second paragraph with more words to select from.</p>"
        ),
        seed_tags=False,
    )


@pytest.mark.e2e
class TestEmptyTagFloatingMenu:
    """Floating highlight menu behaviour in zero-tag and with-tag workspaces."""

    def test_zero_tag_new_button_and_tooltip(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC1.1, AC1.5, AC3.1: "+ New" button, cancel, and tooltip."""
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)

            workspace_id = _create_workspace_no_tags(email)
            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            wait_for_text_walker(page, timeout=15000)

            with subtests.test(msg="ac1_1_new_button_in_zero_tag_workspace"):
                # AC1.1: Select text and verify "+ New" button appears
                select_chars(page, 5, 20)

                new_btn = page.get_by_test_id("highlight-menu-new-tag")
                expect(new_btn).to_be_visible(timeout=5000)

                # Verify "No tags available" is NOT present
                menu = page.get_by_test_id("highlight-menu")
                expect(menu.get_by_text("No tags available")).not_to_be_attached()

            with subtests.test(msg="ac3_1_tooltip_on_new_button"):
                # AC3.1: Verify tooltip text on the "+ New" button
                new_btn = page.get_by_test_id("highlight-menu-new-tag")
                new_btn.hover()
                tooltip = page.get_by_text(
                    "Create a new tag and apply it to your selection"
                )
                expect(tooltip).to_be_visible(timeout=5000)

            with subtests.test(msg="ac1_5_cancel_dialog_no_highlight"):
                # AC1.5: Click "+ New", cancel dialog, no highlight created
                select_chars(page, 5, 20)

                new_btn = page.get_by_test_id("highlight-menu-new-tag")
                expect(new_btn).to_be_visible(timeout=5000)
                new_btn.click()

                dialog = page.get_by_test_id("tag-quick-create-dialog")
                expect(dialog).to_be_visible(timeout=5000)

                dialog.get_by_role("button", name="Cancel").click()

                page.wait_for_timeout(500)
                cards = page.locator("[data-testid='annotation-card']")
                expect(cards).to_have_count(0)

        finally:
            page.close()
            context.close()

    def test_create_tag_and_alongside_existing(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC1.2, AC1.3: Create tag via "+ New" and verify alongside existing."""
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)

            workspace_id = _create_workspace_no_tags(email)
            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            wait_for_text_walker(page, timeout=15000)

            with subtests.test(msg="ac1_2_new_button_creates_highlight"):
                # AC1.2: Click "+ New", create tag, verify highlight
                select_chars(page, 5, 20)

                new_btn = page.get_by_test_id("highlight-menu-new-tag")
                expect(new_btn).to_be_visible(timeout=5000)
                new_btn.click()

                dialog = page.get_by_test_id("tag-quick-create-dialog")
                expect(dialog).to_be_visible(timeout=5000)

                dialog.get_by_test_id("tag-quick-create-name-input").fill("TestTag")
                dialog.get_by_role("button", name="Create").click()

                card = page.locator("[data-testid='annotation-card']").first
                expect(card).to_be_visible(timeout=10000)

            with subtests.test(msg="ac1_3_new_button_alongside_tags"):
                # AC1.3: With tags now existing, "+ New" alongside tag buttons
                page.locator("#doc-container").click(position={"x": 5, "y": 5})
                page.wait_for_timeout(500)

                select_chars(page, 30, 50)

                menu = page.get_by_test_id("highlight-menu")
                expect(menu).to_be_visible(timeout=5000)

                tag_buttons = menu.get_by_test_id("highlight-menu-tag-btn")
                expect(tag_buttons.first).to_be_visible(timeout=5000)

                new_btn = page.get_by_test_id("highlight-menu-new-tag")
                expect(new_btn).to_be_visible(timeout=5000)

        finally:
            page.close()
            context.close()


@pytest.mark.e2e
class TestEmptyTagNoPermission:
    """Floating menu for users without tag creation permission."""

    def test_no_tags_no_permission_shows_dead_end(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC1.4: "No tags available" shown when user lacks permission."""
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)

            workspace_id = _create_workspace_no_tag_permission(email)
            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            wait_for_text_walker(page, timeout=15000)

            menu = page.get_by_test_id("highlight-menu")

            with subtests.test(msg="ac1_4_no_permission_dead_end"):
                select_chars(page, 2, 15)

                expect(menu).to_be_visible(timeout=5000)

                no_tags_label = menu.get_by_text("No tags available")
                expect(no_tags_label).to_be_visible(timeout=5000)

                expect(
                    page.get_by_test_id("highlight-menu-new-tag")
                ).not_to_be_attached()

            with subtests.test(msg="ac1_4_tooltip_mentions_instructor"):
                no_tags_label = menu.get_by_text("No tags available")
                no_tags_label.hover()
                tooltip = page.get_by_text("Ask your instructor")
                expect(tooltip).to_be_visible(timeout=5000)

        finally:
            page.close()
            context.close()
