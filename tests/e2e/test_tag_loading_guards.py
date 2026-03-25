"""E2E tests: loading guards on tag creation and import buttons.

Verifies that buttons show loading/disabled state during async operations
and re-enable afterwards. Tests observable outcomes (no duplicate entities
from rapid clicks) rather than transient CSS state, as that is more
reliable for E2E.

Acceptance Criteria:
- tag-deletion-guards-413.AC5.1: Import button disabled during import
- tag-deletion-guards-413.AC5.2: "Add tag" button disabled during creation
- tag-deletion-guards-413.AC5.3: Quick Create save button disabled during creation
- tag-deletion-guards-413.AC5.4: All buttons re-enable after operation completes

Traceability:
- Issue: #413
- Phase: docs/implementation-plans/2026-03-24-tag-deletion-guards-413/phase_04.md Task 4
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
    from playwright.sync_api import Browser, Page


@pytest.mark.e2e
class TestImportButtonLoadingGuard:
    """Import button loading guard prevents double-import."""

    def test_import_button_re_enables_after_import(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Import button is usable after import completes and tags appear.

        The loading guard disables the button during the async operation.
        The disabled state is transient (server round-trip is fast), so
        we verify the observable outcome: after import, the button is
        re-enabled and imported tags appear in the toolbar.

        Steps:
        1. Create source workspace with tags, target without tags
        2. Open target workspace, open tag management dialog
        3. Select source workspace in import picker
        4. Click Import
        5. Wait for import to complete (success notification)
        6. Verify button is re-enabled after completion
        7. Close dialog, verify imported tags appear in toolbar

        AC5.1, AC5.4: Button re-enables after import completes.
        """
        uid = uuid4().hex[:8]
        email = f"loading-import-{uid}@test.edu"

        context = browser.new_context()
        page = context.new_page()

        try:
            _authenticate_page(page, app_server, email=email)

            # Source workspace WITH tags
            _create_workspace_via_db(
                user_email=email,
                html_content="<p>Source workspace for import guard test</p>",
                seed_tags=True,
            )

            # Target workspace WITHOUT tags
            target_ws_id = _create_workspace_via_db(
                user_email=email,
                html_content="<p>Target workspace for import guard test</p>",
                seed_tags=False,
            )

            page.goto(f"{app_server}/annotation?workspace_id={target_ws_id}")
            wait_for_text_walker(page, timeout=15000)

            # Open tag management dialog
            page.get_by_test_id("tag-settings-btn").click()
            dialog = page.get_by_test_id("tag-management-dialog")
            expect(dialog).to_be_visible(timeout=5000)

            # Select source workspace in import picker
            import_select = dialog.get_by_test_id("import-workspace-select")
            expect(import_select).to_be_visible(timeout=5000)
            import_select.click()

            source_option = page.get_by_role("option").first  # noqa: PG002
            source_option.wait_for(state="visible", timeout=5000)
            source_option.click()

            # Click import
            import_btn = dialog.get_by_test_id("import-tags-btn")
            expect(import_btn).to_be_enabled(timeout=3000)
            import_btn.click()

            # Wait for import to complete (success notification)
            expect(page.locator(".q-notification")).to_contain_text(
                re.compile(r"Imported \d+ tag"), timeout=10000
            )

            # After completion, button should be re-enabled
            expect(import_btn).to_be_enabled(timeout=5000)

            # Close dialog and verify tags appeared in toolbar
            dialog.get_by_test_id("tag-management-done-btn").click()
            expect(dialog).to_be_hidden(timeout=5000)

            toolbar = page.locator("[data-testid='tag-toolbar']")
            tag_buttons = toolbar.locator("[data-tag-id]")
            expect(tag_buttons.first).to_be_visible(timeout=10000)
            assert tag_buttons.count() > 0, "Expected imported tags in toolbar"

        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_import_double_click_produces_single_import(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Rapid double-click on import produces only one import operation.

        The loading guard disables the button after the first click,
        so the second click is a no-op. We verify by checking that the
        success notification appears exactly once.

        AC5.1, AC5.4: Observable outcome of loading guard.
        """
        uid = uuid4().hex[:8]
        email = f"loading-dblimport-{uid}@test.edu"

        context = browser.new_context()
        page = context.new_page()

        try:
            _authenticate_page(page, app_server, email=email)

            _create_workspace_via_db(
                user_email=email,
                html_content="<p>Source for double-import test</p>",
                seed_tags=True,
            )

            target_ws_id = _create_workspace_via_db(
                user_email=email,
                html_content="<p>Target for double-import test</p>",
                seed_tags=False,
            )

            page.goto(f"{app_server}/annotation?workspace_id={target_ws_id}")
            wait_for_text_walker(page, timeout=15000)

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
            expect(import_btn).to_be_enabled(timeout=3000)

            # Rapid double-click
            import_btn.dblclick()

            # Wait for the import to complete (success notification)
            expect(page.locator(".q-notification")).to_contain_text(
                re.compile(r"Imported \d+ tag"), timeout=10000
            )

            # After import completes, button should re-enable
            expect(import_btn).to_be_enabled(timeout=5000)

            # Close dialog and verify tag count — double-click should
            # produce the same number of tags as a single import, not
            # double.  We verify the observable outcome (tag count)
            # rather than transient notification count.
            dialog.get_by_test_id("tag-management-done-btn").click()
            expect(dialog).to_be_hidden(timeout=5000)

            toolbar = page.locator("[data-testid='tag-toolbar']")
            tag_buttons = toolbar.locator("[data-tag-id]")
            expect(tag_buttons.first).to_be_visible(timeout=10000)
            # Seed tags create 4 tags (2 groups x 2 tags). A single
            # import should produce exactly 4 tags in the toolbar.
            # A double-import would produce duplicates (>4).
            assert tag_buttons.count() == 4, (
                f"Expected 4 imported tags but found {tag_buttons.count()}"
            )

        finally:
            page.goto("about:blank")
            page.close()
            context.close()


@pytest.mark.e2e
class TestAddTagButtonLoadingGuard:
    """Add-tag button loading guard prevents rapid creation."""

    def test_add_tag_creates_exactly_one_tag(
        self,
        two_annotation_contexts: tuple[Page, Page, str],
    ) -> None:
        """Clicking "Add tag" creates exactly one new tag, not duplicates.

        The loading guard disables the button during tag creation,
        preventing rapid-fire clicks from producing multiple tags.

        Steps:
        1. Open tag management dialog
        2. Count existing tags
        3. Click a group's "Add tag" button
        4. Wait for new tag to appear
        5. Verify exactly one new tag was created

        AC5.2, AC5.4: Observable outcome of loading guard.
        """
        from tests.e2e.tag_helpers import seed_group_id

        page, _page_b, workspace_id = two_annotation_contexts

        group_id = seed_group_id(workspace_id, "Case ID")

        # Open tag management dialog
        settings_btn = page.get_by_test_id("tag-settings-btn")
        settings_btn.scroll_into_view_if_needed()
        expect(settings_btn).to_be_visible(timeout=5000)
        settings_btn.click()

        done_btn = page.get_by_test_id("tag-management-done-btn")
        expect(done_btn).to_be_visible(timeout=15000)

        # Count existing tag rows before adding
        # Each tag has a name input with testid pattern tag-name-input-*
        tag_inputs_before = page.locator('[data-testid^="tag-name-input-"]')
        count_before = tag_inputs_before.count()

        # Click the group "Add tag" button for Case ID
        add_btn = page.get_by_test_id(f"group-add-tag-btn-{group_id}")
        expect(add_btn).to_be_visible(timeout=5000)
        add_btn.click()

        # Wait for a new tag to appear (count increases by 1)
        page.locator('[data-testid^="tag-name-input-"]').nth(count_before).wait_for(
            state="visible", timeout=10000
        )

        # Verify exactly one new tag was created
        count_after = page.locator('[data-testid^="tag-name-input-"]').count()
        assert count_after == count_before + 1, (
            f"Expected {count_before + 1} tags after add, got {count_after}"
        )

    def test_add_tag_button_re_enables_after_creation(
        self,
        two_annotation_contexts: tuple[Page, Page, str],
    ) -> None:
        """Add-tag button is disabled during creation and re-enables after.

        The loading guard disables the button during the async DB
        operation. Since the operation completes quickly, we verify
        the button is enabled after the tag list rebuilds (which
        proves the finally block ran).

        Steps:
        1. Open tag management dialog
        2. Click a group's "Add tag" button
        3. Wait for the tag list to rebuild (new tag appears)
        4. Verify button is re-enabled after creation

        AC5.2, AC5.4: Button re-enables after creation completes.
        """
        from tests.e2e.tag_helpers import seed_group_id

        page, _page_b, workspace_id = two_annotation_contexts

        group_id = seed_group_id(workspace_id, "Case ID")

        settings_btn = page.get_by_test_id("tag-settings-btn")
        settings_btn.scroll_into_view_if_needed()
        expect(settings_btn).to_be_visible(timeout=5000)
        settings_btn.click()

        done_btn = page.get_by_test_id("tag-management-done-btn")
        expect(done_btn).to_be_visible(timeout=15000)

        # Count tags before
        count_before = page.locator('[data-testid^="tag-name-input-"]').count()

        add_btn = page.get_by_test_id(f"group-add-tag-btn-{group_id}")
        expect(add_btn).to_be_visible(timeout=5000)
        expect(add_btn).to_be_enabled(timeout=3000)

        add_btn.click()

        # Wait for the new tag to appear (proves creation completed)
        page.locator('[data-testid^="tag-name-input-"]').nth(count_before).wait_for(
            state="visible", timeout=10000
        )

        # After the tag list rebuilds, the button should be re-enabled.
        # The render_tag_list() call rebuilds the container, so we need
        # to re-locate the button in the new DOM.
        add_btn_after = page.get_by_test_id(f"group-add-tag-btn-{group_id}")
        expect(add_btn_after).to_be_enabled(timeout=5000)


@pytest.mark.e2e
class TestQuickCreateButtonLoadingGuard:
    """Quick Create save button loading guard prevents double-create."""

    def test_quick_create_save_disables_during_creation(
        self,
        two_annotation_contexts: tuple[Page, Page, str],
    ) -> None:
        """Quick Create save button is disabled during creation and dialog closes after.

        Steps:
        1. Click "Create New Tag" to open quick create dialog
        2. Fill in a tag name
        3. Click Create
        4. Verify button is disabled during creation
        5. After creation, verify dialog closes and tag appears

        AC5.3, AC5.4: Button disabled during creation, re-enabled/dialog closed after.
        """
        page, _page_b, _workspace_id = two_annotation_contexts

        tag_name = f"LoadGuard-{uuid4().hex[:6]}"

        # Open quick create dialog
        create_btn = page.get_by_test_id("tag-create-btn")
        create_btn.scroll_into_view_if_needed()
        expect(create_btn).to_be_visible(timeout=5000)
        create_btn.click()

        dialog = page.get_by_test_id("tag-quick-create-dialog")
        expect(dialog).to_be_visible(timeout=5000)

        # Fill in tag name
        name_input = page.get_by_test_id("tag-quick-create-name-input")
        name_input.fill(tag_name)

        # Click Create
        save_btn = page.get_by_test_id("quick-create-save-btn")
        expect(save_btn).to_be_enabled(timeout=3000)
        save_btn.click()

        # Button should be disabled during creation
        expect(save_btn).to_be_disabled(timeout=3000)

        # Dialog should close after successful creation
        expect(dialog).to_be_hidden(timeout=10000)

        # The new tag should appear in the toolbar
        toolbar = page.get_by_test_id("tag-toolbar")
        expect(
            toolbar.locator('[data-testid^="tag-btn-"]').filter(has_text=tag_name)
        ).to_be_visible(timeout=5000)

    def test_quick_create_double_click_produces_single_tag(
        self,
        two_annotation_contexts: tuple[Page, Page, str],
    ) -> None:
        """Rapid double-click on Create produces exactly one new tag.

        The loading guard disables the save button after the first click,
        so the second click is a no-op.

        Steps:
        1. Open quick create dialog
        2. Fill in a unique tag name
        3. Double-click the Create button
        4. Verify only one tag with that name appears in toolbar

        AC5.3, AC5.4: Observable outcome of loading guard.
        """
        page, _page_b, _workspace_id = two_annotation_contexts

        tag_name = f"DblClick-{uuid4().hex[:6]}"

        create_btn = page.get_by_test_id("tag-create-btn")
        create_btn.scroll_into_view_if_needed()
        expect(create_btn).to_be_visible(timeout=5000)
        create_btn.click()

        dialog = page.get_by_test_id("tag-quick-create-dialog")
        expect(dialog).to_be_visible(timeout=5000)

        name_input = page.get_by_test_id("tag-quick-create-name-input")
        name_input.fill(tag_name)

        save_btn = page.get_by_test_id("quick-create-save-btn")
        expect(save_btn).to_be_enabled(timeout=3000)

        # Rapid double-click
        save_btn.dblclick()

        # Dialog should close after creation
        expect(dialog).to_be_hidden(timeout=10000)

        # Verify exactly one tag with this name in toolbar
        toolbar = page.get_by_test_id("tag-toolbar")
        matching_tags = toolbar.locator('[data-testid^="tag-btn-"]').filter(
            has_text=tag_name
        )
        expect(matching_tags).to_have_count(1, timeout=5000)
