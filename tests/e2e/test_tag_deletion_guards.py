"""E2E tests: deletion guard UI for tags, groups, and documents.

Verifies that delete buttons are disabled with explanatory tooltips
when deletion is blocked by business rules (tags have highlights,
groups have tags, documents have annotations).

Acceptance Criteria:
- tag-deletion-guards-413.AC1.3: Group with tags -> delete button
  disabled with tooltip naming the tag count
- tag-deletion-guards-413.AC2.3: Tag with highlights -> delete button
  disabled with tooltip naming the highlight count
- tag-deletion-guards-413.AC3.3: Document with annotations -> delete
  button disabled with tooltip naming the annotation count

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

    def test_delete_group_with_tags_button_disabled(
        self,
        two_annotation_contexts: tuple[Page, Page, str],
    ) -> None:
        """Group delete button is disabled when the group has tags.

        Steps:
        1. Open tag management dialog
        2. Find delete button for the "Case ID" group (has 4 seeded tags)
        3. Assert button is disabled
        4. Hover to verify tooltip mentions tag count

        AC1.3: UI prevents deletion, naming the tag count.
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

        # Find the delete button for "Case ID" group
        delete_btn = page.get_by_test_id(f"group-delete-btn-{group_id}")
        expect(delete_btn).to_be_visible(timeout=5000)

        # Button should be disabled (group has 4 tags)
        expect(delete_btn).to_be_disabled(timeout=5000)

        # Hover to trigger tooltip and verify it mentions tag count
        delete_btn.hover()
        tooltip = page.locator(".q-tooltip").filter(has_text="tag")
        expect(tooltip).to_be_visible(timeout=5000)
        expect(tooltip).to_contain_text("4")

    def test_delete_tag_with_highlights_button_disabled(
        self,
        two_annotation_contexts: tuple[Page, Page, str],
    ) -> None:
        """Tag delete button is disabled when the tag has highlights.

        Steps:
        1. Create a highlight using the first seeded tag (Jurisdiction)
        2. Open tag management dialog
        3. Find delete button for the Jurisdiction tag
        4. Assert button is disabled
        5. Hover to verify tooltip mentions highlight count

        AC2.3: UI prevents deletion, naming the highlight count.
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

        # Find delete button for the Jurisdiction tag
        delete_btn = page.get_by_test_id(f"tag-delete-btn-{tag_id}")
        expect(delete_btn).to_be_visible(timeout=5000)

        # Button should be disabled (tag has 1 highlight)
        expect(delete_btn).to_be_disabled(timeout=5000)

        # Hover to trigger tooltip and verify it mentions highlight count
        delete_btn.hover()
        tooltip = page.locator(".q-tooltip").filter(has_text="highlight")
        expect(tooltip).to_be_visible(timeout=5000)
        expect(tooltip).to_contain_text("1")

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
