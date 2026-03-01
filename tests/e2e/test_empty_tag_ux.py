"""E2E test: empty-tag annotation UX.

Verifies the floating highlight menu behaviour when a workspace
has zero tags or when the user lacks tag creation permission,
and toolbar button label expansion / tooltip behaviour.

Acceptance Criteria (Phase 1 -- floating menu):
- empty-tag-ux-210.AC1.1: Floating menu shows "+ New" button in zero-tag workspace
- empty-tag-ux-210.AC1.2: Clicking "+ New" creates tag and auto-applies highlight
- empty-tag-ux-210.AC1.3: "+ New" appears alongside tag buttons when tags exist
- empty-tag-ux-210.AC1.4: "No tags available" shown when user lacks permission
- empty-tag-ux-210.AC1.5: Cancelling dialog creates no highlight
- empty-tag-ux-210.AC3.1: Tooltip on "+ New" button

Acceptance Criteria (Phase 2 -- toolbar labels & tooltips):
- empty-tag-ux-210.AC2.1: 0-4 tags: "+" button shows "Create New Tag"
- empty-tag-ux-210.AC2.2: 0-4 tags: gear button shows "Manage Tags"
- empty-tag-ux-210.AC2.3: 5+ tags: both buttons revert to compact icon-only
- empty-tag-ux-210.AC2.4: Creating 5th tag causes live rebuild to compact
- empty-tag-ux-210.AC3.2: Toolbar create button tooltip text
- empty-tag-ux-210.AC3.3: Toolbar manage button tooltip text
- empty-tag-ux-210.AC3.4: Tooltips display at all tag counts

Traceability:
- Issue: #210 (Empty-tag annotation UX)
- Design: docs/implementation-plans/2026-03-01-empty-tag-ux-210/phase_01.md
- Design: docs/implementation-plans/2026-03-01-empty-tag-ux-210/phase_02.md
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
    from playwright.sync_api import Browser, Page
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


# ---------------------------------------------------------------------------
# Phase 2: Toolbar expanded labels and tooltips
# ---------------------------------------------------------------------------


def _create_tag_via_toolbar(page: Page, tag_name: str) -> None:
    """Create a tag using the toolbar create button and quick-create dialog.

    Clicks the ``tag-create-btn``, fills in the name, and clicks Create.
    Waits for the dialog to close and the new tag to appear in the toolbar.

    Args:
        page: Playwright page with annotation workspace loaded.
        tag_name: Name for the new tag.
    """
    create_btn = page.get_by_test_id("tag-create-btn")
    create_btn.click()

    dialog = page.get_by_test_id("tag-quick-create-dialog")
    expect(dialog).to_be_visible(timeout=5000)

    dialog.get_by_test_id("tag-quick-create-name-input").fill(tag_name)
    dialog.get_by_role("button", name="Create").click()

    expect(dialog).to_be_hidden(timeout=5000)

    toolbar = page.get_by_test_id("tag-toolbar")
    expect(toolbar).to_contain_text(tag_name, timeout=5000)


@pytest.mark.e2e
class TestToolbarExpandedLabels:
    """Toolbar button labels expand when fewer than 5 tags exist.

    Verifies: empty-tag-ux-210.AC2.1, AC2.2, AC2.3, AC2.4
    """

    def test_expanded_labels_at_zero_tags(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC2.1, AC2.2: Expanded labels with 0 tags."""
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)

            workspace_id = _create_workspace_no_tags(email)
            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            wait_for_text_walker(page, timeout=15000)

            with subtests.test(msg="ac2_1_create_button_shows_text"):
                # AC2.1: Create button shows "Create New Tag" text
                create_btn = page.get_by_test_id("tag-create-btn")
                expect(create_btn).to_be_visible(timeout=5000)
                expect(create_btn).to_contain_text("Create New Tag")

            with subtests.test(msg="ac2_2_manage_button_shows_text"):
                # AC2.2: Manage button shows "Manage Tags" text
                manage_btn = page.get_by_test_id("tag-settings-btn")
                expect(manage_btn).to_be_visible(timeout=5000)
                expect(manage_btn).to_contain_text("Manage Tags")

        finally:
            page.close()
            context.close()

    def test_compact_buttons_at_five_plus_tags(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC2.3: Compact icon-only buttons with 5+ tags (10 seeded)."""
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)

            # seed_tags=True gives 10 tags (well above threshold of 5)
            workspace_id = _create_workspace_via_db(
                user_email=email,
                html_content="<p>Compact toolbar test content.</p>",
                seed_tags=True,
            )
            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            wait_for_text_walker(page, timeout=15000)

            with subtests.test(msg="ac2_3_create_button_icon_only"):
                # AC2.3: Create button should NOT contain text labels
                create_btn = page.get_by_test_id("tag-create-btn")
                expect(create_btn).to_be_visible(timeout=5000)
                expect(create_btn).not_to_contain_text("Create New Tag")

            with subtests.test(msg="ac2_3_manage_button_icon_only"):
                # AC2.3: Manage button should NOT contain text labels
                manage_btn = page.get_by_test_id("tag-settings-btn")
                expect(manage_btn).to_be_visible(timeout=5000)
                expect(manage_btn).not_to_contain_text("Manage Tags")

        finally:
            page.close()
            context.close()

    def test_transition_to_compact_on_fifth_tag(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC2.4: Creating 5th tag triggers live rebuild with compact buttons."""
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)

            workspace_id = _create_workspace_no_tags(email)
            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            wait_for_text_walker(page, timeout=15000)

            with subtests.test(msg="ac2_4_expanded_with_four_tags"):
                # Create 4 tags -- should still show expanded labels
                for i in range(1, 5):
                    _create_tag_via_toolbar(page, f"Tag{i}")

                create_btn = page.get_by_test_id("tag-create-btn")
                expect(create_btn).to_contain_text("Create New Tag")

                manage_btn = page.get_by_test_id("tag-settings-btn")
                expect(manage_btn).to_contain_text("Manage Tags")

            with subtests.test(msg="ac2_4_compact_after_fifth_tag"):
                # Create 5th tag -- buttons should switch to compact
                _create_tag_via_toolbar(page, "Tag5")

                create_btn = page.get_by_test_id("tag-create-btn")
                expect(create_btn).not_to_contain_text("Create New Tag")

                manage_btn = page.get_by_test_id("tag-settings-btn")
                expect(manage_btn).not_to_contain_text("Manage Tags")

        finally:
            page.close()
            context.close()


@pytest.mark.e2e
class TestToolbarTooltips:
    """Tooltips on toolbar action buttons at all tag counts.

    Verifies: empty-tag-ux-210.AC3.2, AC3.3, AC3.4
    """

    def test_tooltips_at_zero_tags(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC3.2, AC3.3, AC3.4 (0 tags): Tooltips on create and manage buttons."""
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)

            workspace_id = _create_workspace_no_tags(email)
            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            wait_for_text_walker(page, timeout=15000)

            with subtests.test(msg="ac3_2_create_tooltip_at_zero"):
                # AC3.2: Hover create button, verify tooltip
                create_btn = page.get_by_test_id("tag-create-btn")
                create_btn.hover()
                # NiceGUI .tooltip() renders a q-tooltip child with no testid surface;
                # get_by_role("tooltip") is the correct Playwright accessor here.
                tooltip = page.get_by_role(
                    "tooltip",
                    name="Create a new tag for highlighting and annotating text",
                )
                expect(tooltip).to_be_visible(timeout=5000)

            with subtests.test(msg="ac3_3_manage_tooltip_at_zero"):
                # AC3.3: Hover manage button, verify tooltip
                # Move mouse away first to dismiss previous tooltip
                page.mouse.move(0, 0)
                page.wait_for_timeout(300)

                manage_btn = page.get_by_test_id("tag-settings-btn")
                manage_btn.hover()
                # NiceGUI .tooltip() renders a q-tooltip child with no testid surface;
                # get_by_role("tooltip") is the correct Playwright accessor here.
                tooltip = page.get_by_role("tooltip", name="Manage tags")
                expect(tooltip).to_be_visible(timeout=5000)

        finally:
            page.close()
            context.close()

    def test_tooltips_at_five_plus_tags(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """AC3.4 (5+ tags): Tooltips still display on compact buttons."""
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)

            # 10 seeded tags
            workspace_id = _create_workspace_via_db(
                user_email=email,
                html_content="<p>Tooltip test content with many tags.</p>",
                seed_tags=True,
            )
            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            wait_for_text_walker(page, timeout=15000)

            with subtests.test(msg="ac3_2_create_tooltip_at_five_plus"):
                # AC3.2 at 5+: Hover create button
                create_btn = page.get_by_test_id("tag-create-btn")
                create_btn.hover()
                # NiceGUI .tooltip() renders a q-tooltip child with no testid surface;
                # get_by_role("tooltip") is the correct Playwright accessor here.
                tooltip = page.get_by_role(
                    "tooltip",
                    name="Create a new tag for highlighting and annotating text",
                )
                expect(tooltip).to_be_visible(timeout=5000)

            with subtests.test(msg="ac3_3_manage_tooltip_at_five_plus"):
                # AC3.3 at 5+: Hover manage button
                page.mouse.move(0, 0)
                page.wait_for_timeout(300)

                manage_btn = page.get_by_test_id("tag-settings-btn")
                manage_btn.hover()
                # NiceGUI .tooltip() renders a q-tooltip child with no testid surface;
                # get_by_role("tooltip") is the correct Playwright accessor here.
                tooltip = page.get_by_role("tooltip", name="Manage tags")
                expect(tooltip).to_be_visible(timeout=5000)

        finally:
            page.close()
            context.close()
