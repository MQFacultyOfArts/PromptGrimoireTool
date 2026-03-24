"""E2E tests: deletion guard notifications for tags, groups, and documents.

Verifies that the UI surfaces warning notifications or disabled states
when deletion is blocked by business rules (tags have highlights,
groups have tags, documents have annotations).

Acceptance Criteria:
- tag-deletion-guards-413.AC1.3: Delete a group with tags -> warning
  notification naming the tag count
- tag-deletion-guards-413.AC2.3: Delete a tag with highlights -> warning
  notification naming the highlight count
- tag-deletion-guards-413.AC3.3: Delete a document with annotations ->
  delete button disabled with tooltip naming the annotation count

Traceability:
- Issue: #413
- Phase: docs/implementation-plans/2026-03-24-tag-deletion-guards-413/phase_02.md Task 3
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page


@pytest.mark.e2e
class TestTagDeletionGuards:
    """Deletion guard notifications in the annotation UI."""

    def test_delete_group_with_tags_shows_warning(
        self,
        two_annotation_contexts: tuple[Page, Page, str],
    ) -> None:
        """Deleting a group that has tags shows an amber warning notification.

        Steps:
        1. Open tag management dialog
        2. Click delete on the "Case ID" group (has 4 seeded tags)
        3. Confirm deletion in the dialog
        4. Assert warning notification appears with tag count text
        5. Assert group still exists (dialog still shows it)

        AC1.3: UI shows warning notification naming the tag count.
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

        # Click the delete button for "Case ID" group
        delete_btn = page.get_by_test_id(f"group-delete-btn-{group_id}")
        expect(delete_btn).to_be_visible(timeout=5000)
        delete_btn.click()

        # Confirm deletion in the confirmation dialog
        # The dialog has a "Delete" button (color=negative)
        confirm_btn = page.locator("button").filter(has_text="Delete").last
        expect(confirm_btn).to_be_visible(timeout=5000)
        confirm_btn.click()

        # Assert warning notification appears with tag count.
        # Quasar notifications render as role="alert" elements.
        # "Case ID" group has 4 seeded tags.
        alert = page.get_by_role("alert").filter(has_text="tag")  # noqa: PG002 — Quasar ui.notify() renders as role="alert", no data-testid injectable
        expect(alert).to_be_visible(timeout=5000)
        # Verify it mentions a count (the word "4" for 4 tags)
        expect(alert).to_contain_text("4")

        # Group should still exist in the management dialog
        group_name_input = page.get_by_test_id(f"group-name-input-{group_id}")
        expect(group_name_input).to_be_visible(timeout=5000)

    def test_delete_tag_with_highlights_shows_warning(
        self,
        two_annotation_contexts: tuple[Page, Page, str],
    ) -> None:
        """Deleting a tag that has highlights shows an amber warning notification.

        Steps:
        1. Create a highlight using the first seeded tag (Jurisdiction)
        2. Open tag management dialog
        3. Click delete on the Jurisdiction tag
        4. Confirm deletion in the dialog
        5. Assert warning notification appears with highlight count text
        6. Assert tag still visible in toolbar

        AC2.3: UI shows warning notification naming the highlight count.
        """
        from tests.e2e.highlight_tools import create_highlight_with_tag, find_text_range
        from tests.e2e.tag_helpers import seed_tag_id

        page, _page_b, workspace_id = two_annotation_contexts

        tag_id = seed_tag_id(workspace_id, "Jurisdiction")

        # Create a highlight using the Jurisdiction tag (index 0)
        start, end = find_text_range(page, "Sync")
        create_highlight_with_tag(page, start, end, tag_index=0)

        # Wait for the annotation card to confirm highlight was saved
        expect(page.locator("[data-testid='annotation-card']").first).to_be_visible(
            timeout=10000
        )

        # Open tag management dialog
        settings_btn = page.get_by_test_id("tag-settings-btn")
        settings_btn.scroll_into_view_if_needed()
        expect(settings_btn).to_be_visible(timeout=5000)
        settings_btn.click()

        done_btn = page.get_by_test_id("tag-management-done-btn")
        expect(done_btn).to_be_visible(timeout=15000)

        # Click delete on the Jurisdiction tag
        delete_btn = page.get_by_test_id(f"tag-delete-btn-{tag_id}")
        expect(delete_btn).to_be_visible(timeout=5000)
        delete_btn.click()

        # Confirm deletion in the confirmation dialog
        confirm_btn = page.locator("button").filter(has_text="Delete").last
        expect(confirm_btn).to_be_visible(timeout=5000)
        confirm_btn.click()

        # Assert warning notification with highlight count
        alert = page.get_by_role("alert").filter(has_text="highlight")  # noqa: PG002 — Quasar ui.notify() renders as role="alert", no data-testid injectable
        expect(alert).to_be_visible(timeout=5000)
        # Should mention "1" highlight
        expect(alert).to_contain_text("1")

        # Close the management dialog
        done_btn = page.get_by_test_id("tag-management-done-btn")
        if done_btn.is_visible():
            done_btn.click()

        # Tag should still be visible in the toolbar
        tag_btn = page.get_by_test_id(f"tag-btn-{tag_id}")
        expect(tag_btn).to_be_visible(timeout=5000)

    def test_delete_document_with_annotations_button_disabled(
        self,
        two_annotation_contexts: tuple[Page, Page, str],
    ) -> None:
        """Document delete button is disabled when the document has annotations.

        The UI disables the delete button and shows a tooltip with the
        annotation count. The HasAnnotationsError catch in _do_delete_document
        is defence-in-depth for race conditions.

        Steps:
        1. Create a highlight on the document
        2. Open document management dialog
        3. Assert delete button is disabled
        4. Assert tooltip text contains annotation count

        AC3.3: UI prevents deletion, naming the annotation count.
        """
        from tests.e2e.highlight_tools import create_highlight_with_tag, find_text_range

        page, _page_b, _workspace_id = two_annotation_contexts

        # Create a highlight using the first tag
        start, end = find_text_range(page, "Sync")
        create_highlight_with_tag(page, start, end, tag_index=0)

        # Wait for annotation card to confirm highlight was saved
        expect(page.locator("[data-testid='annotation-card']").first).to_be_visible(
            timeout=10000
        )

        # Open document management dialog
        manage_docs_btn = page.get_by_test_id("manage-documents-btn")
        expect(manage_docs_btn).to_be_visible(timeout=5000)
        manage_docs_btn.click()

        # Find the delete button for the document.
        # There should be exactly one delete-doc-btn since there is one document.
        delete_btn = page.locator('[data-testid^="delete-doc-btn-"]').first
        expect(delete_btn).to_be_visible(timeout=5000)

        # The button should be disabled (has Quasar "disabled" attribute)
        expect(delete_btn).to_be_disabled(timeout=5000)

        # Hover to trigger tooltip and verify it mentions annotation count
        delete_btn.hover()
        tooltip = page.locator(".q-tooltip").filter(has_text="annotation")
        expect(tooltip).to_be_visible(timeout=5000)
        # Should mention "1" annotation
        expect(tooltip).to_contain_text("1")
