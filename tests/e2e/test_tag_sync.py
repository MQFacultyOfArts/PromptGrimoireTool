"""E2E test: tag sync propagation between connected clients.

Verifies the full tag sync pipeline: DB write -> CRDT write -> broadcast ->
receiving client rebuilds tag_info_list -> toolbar updates.

Acceptance Criteria:
- tag-lifecycle-235-291.AC2.1: Creating a tag via quick create immediately
  appears on all connected clients' tag bars (no refresh)
- tag-lifecycle-235-291.AC2.2: Creating a tag via management dialog immediately
  appears on all connected clients
- tag-lifecycle-235-291.AC5.2: Reassigning a tag to a different group
  propagates to all connected clients
- tag-lifecycle-235-291.AC5.3: Dragging a highlight between tag columns
  updates the tag's highlight list in the CRDT

Traceability:
- Issues: #235, #291
- Phase: docs/implementation-plans/2026-03-06-tag-lifecycle-235-291/phase_03.md Task 5
- Phase: docs/implementation-plans/2026-03-06-tag-lifecycle-235-291/phase_05.md Task 4
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page


ANNOTATION_CARD = "[data-testid='annotation-card']"


@pytest.mark.e2e
class TestTagSync:
    """Tag CRDT sync between two connected clients."""

    def test_tag_create_propagates_to_second_client(
        self,
        two_annotation_contexts: tuple[Page, Page, str],
    ) -> None:
        """Quick-creating a tag on client A appears on client B without refresh.

        Steps:
        1. Client A clicks the "Create New Tag" button to open quick create
        2. Client A fills in a tag name and saves
        3. Client B sees the new tag button appear in the toolbar

        The two_annotation_contexts fixture provides two independent browser
        contexts viewing the same workspace, both authenticated and with the
        text walker ready.
        """
        page_a, page_b, _workspace_id = two_annotation_contexts

        tag_name = "SyncTestTag"

        # --- Client A: open quick create dialog ---
        create_btn = page_a.get_by_test_id("tag-create-btn")
        create_btn.scroll_into_view_if_needed()
        expect(create_btn).to_be_visible(timeout=5000)
        create_btn.click()

        # Wait for the quick create dialog to appear
        dialog = page_a.get_by_test_id("tag-quick-create-dialog")
        expect(dialog).to_be_visible(timeout=5000)

        # Fill in the tag name
        name_input = page_a.get_by_test_id("tag-quick-create-name-input")
        name_input.fill(tag_name)

        # Click save
        save_btn = page_a.get_by_test_id("quick-create-save-btn")
        save_btn.click()

        # Wait for dialog to close (confirms save completed)
        expect(dialog).to_be_hidden(timeout=10000)

        # --- Client A: verify the tag appeared locally ---
        # Buttons render as "[N] TagName" — use substring match
        toolbar_a = page_a.get_by_test_id("tag-toolbar")
        expect(toolbar_a.get_by_text(tag_name)).to_be_visible(timeout=5000)

        # --- Client B: verify the tag appeared via broadcast (no refresh) ---
        toolbar_b = page_b.get_by_test_id("tag-toolbar")
        expect(toolbar_b.get_by_text(tag_name)).to_be_visible(
            timeout=15000,
        )


@pytest.mark.e2e
class TestOrganiseTabSync:
    """Organise tab highlight drag and group reassignment propagation."""

    def test_highlight_drag_between_tags_persists(
        self,
        two_annotation_contexts: tuple[Page, Page, str],
    ) -> None:
        """Moving a highlight between tag columns persists after page refresh.

        Steps:
        1. Client A creates a highlight with the first tag (Jurisdiction)
        2. Client A switches to the Organise tab
        3. Verify the highlight card appears in the Jurisdiction column
        4. Drag the highlight card from Jurisdiction to Procedural History
        5. Verify the highlight card now appears in the Procedural History column
        6. Refresh the page
        7. Switch to Organise tab again
        8. Verify the highlight is still in the Procedural History column

        AC5.3: Dragging a highlight between tag columns updates the CRDT.
        """
        from tests.e2e.annotation_helpers import (
            create_highlight_with_tag,
            wait_for_text_walker,
        )

        page_a, _page_b, _workspace_id = two_annotation_contexts

        # 1. Create a highlight with Jurisdiction tag (index 0 in seeded tags)
        create_highlight_with_tag(page_a, 0, 4, tag_index=0)

        # Wait for the annotation card to appear (confirms highlight saved)
        expect(page_a.locator(ANNOTATION_CARD).first).to_be_visible(timeout=10000)

        # 2. Switch to Organise tab — wait for columns to render
        page_a.get_by_test_id("tab-organise").click()

        # 3. Verify the highlight card appears in the Jurisdiction column
        jurisdiction_col = page_a.locator(
            '[data-testid="tag-column"][data-tag-name="Jurisdiction"]'
        )
        expect(jurisdiction_col).to_be_visible(timeout=10000)
        highlight_card = jurisdiction_col.locator('[data-testid="organise-card"]')
        expect(highlight_card).to_have_count(1, timeout=5000)

        # 4. Drag the highlight from Jurisdiction column to Procedural History column
        proc_hist_col = page_a.locator(
            '[data-testid="tag-column"][data-tag-name="Procedural History"]'
        )
        expect(proc_hist_col).to_be_visible(timeout=5000)

        # Drag the card to the target column's sortable container
        source_card = jurisdiction_col.locator('[data-testid="organise-card"]').first
        target_sortable = proc_hist_col.locator(".nicegui-sortable").first
        source_card.drag_to(target_sortable)

        # 5. Verify the highlight now appears in Procedural History
        proc_cards = proc_hist_col.locator('[data-testid="organise-card"]')
        expect(proc_cards).to_have_count(1, timeout=5000)

        # Jurisdiction column should now be empty (just "No highlights" label)
        juris_cards = jurisdiction_col.locator('[data-testid="organise-card"]')
        expect(juris_cards).to_have_count(0, timeout=5000)

        # 6. Refresh the page
        page_a.reload()
        wait_for_text_walker(page_a, timeout=15000)

        # 7. Switch to Organise tab again — wait for columns
        page_a.get_by_test_id("tab-organise").click()

        # 8. Verify the highlight is still in Procedural History after refresh
        proc_hist_col_after = page_a.locator(
            '[data-testid="tag-column"][data-tag-name="Procedural History"]'
        )
        expect(proc_hist_col_after).to_be_visible(timeout=10000)
        proc_cards_after = proc_hist_col_after.locator('[data-testid="organise-card"]')
        expect(proc_cards_after).to_have_count(1, timeout=5000)

        juris_col_after = page_a.locator(
            '[data-testid="tag-column"][data-tag-name="Jurisdiction"]'
        )
        juris_cards_after = juris_col_after.locator('[data-testid="organise-card"]')
        expect(juris_cards_after).to_have_count(0, timeout=5000)

    def test_tag_group_reassignment_propagates(
        self,
        two_annotation_contexts: tuple[Page, Page, str],
    ) -> None:
        """Changing a tag's group on client A propagates to client B's organise tab.

        Steps:
        1. Client B switches to the Organise tab
        2. Client B notes the Jurisdiction tag is visible (under Case ID group)
        3. Client A opens the tag management dialog
        4. Client A changes Jurisdiction's group from "Case ID" to "Analysis"
        5. Client A clicks Done to save
        6. Client B's toolbar updates to show the tag in its new position
           (broadcast triggers toolbar rebuild)

        AC5.2: Reassigning a tag to a different group propagates to all clients.
        """
        from tests.e2e.annotation_helpers import seed_tag_id

        page_a, page_b, workspace_id = two_annotation_contexts

        tag_id = seed_tag_id(workspace_id, "Jurisdiction")

        # 1. Client A: open tag management dialog
        toolbar_a = page_a.get_by_test_id("tag-toolbar")
        expect(toolbar_a).to_be_visible(timeout=10000)

        settings_btn = page_a.get_by_test_id("tag-settings-btn")
        settings_btn.scroll_into_view_if_needed()
        expect(settings_btn).to_be_visible(timeout=5000)
        settings_btn.click()

        done_btn = page_a.get_by_test_id("tag-management-done-btn")
        expect(done_btn).to_be_visible(timeout=15000)

        # 2. Change Jurisdiction's group to "Analysis" via the group select
        group_select = page_a.get_by_test_id(f"tag-group-select-{tag_id}")
        expect(group_select).to_be_visible(timeout=5000)

        # Click the select to open the dropdown — wait for menu to appear
        group_select.click()
        q_menu = page_a.locator(".q-menu")
        expect(q_menu).to_be_visible(timeout=5000)

        # Select "Analysis" from the dropdown options
        q_menu.locator(".q-item").filter(has_text="Analysis").click()
        expect(q_menu).to_be_hidden(timeout=5000)

        # 3. Click Done to save all changes
        done_btn.click()
        dialog = page_a.get_by_test_id("tag-management-dialog")
        expect(dialog).to_be_hidden(timeout=10000)

        # 4. Client B: verify the toolbar was rebuilt (tag still exists)
        # The tag should still be visible on client B's toolbar
        # (broadcast triggers _refresh_tag_state which rebuilds tags)
        btn_b = page_b.get_by_test_id(f"tag-btn-{tag_id}")
        expect(btn_b).to_be_visible(timeout=15000)

        # 5. Client B: switch to Organise tab and verify the tag column
        # still exists (the tag was reassigned to Analysis group, not deleted)
        page_b.get_by_test_id("tab-organise").click()

        # Verify Jurisdiction column still renders (tag exists, just in new group)
        jurisdiction_col = page_b.locator(
            '[data-testid="tag-column"][data-tag-name="Jurisdiction"]'
        )
        expect(jurisdiction_col).to_be_visible(timeout=10000)

        # 6. Verify the group change persisted by reopening the management
        # dialog on client B and checking the group selector value
        settings_btn_b = page_b.get_by_test_id("tag-settings-btn")
        settings_btn_b.scroll_into_view_if_needed()
        expect(settings_btn_b).to_be_visible(timeout=5000)
        settings_btn_b.click()

        done_btn_b = page_b.get_by_test_id("tag-management-done-btn")
        expect(done_btn_b).to_be_visible(timeout=15000)

        # The group select for Jurisdiction should now show "Analysis"
        group_select_b = page_b.get_by_test_id(f"tag-group-select-{tag_id}")
        expect(group_select_b).to_be_visible(timeout=5000)

        # Verify the select displays "Analysis" as the selected group.
        expect(group_select_b).to_contain_text("Analysis", timeout=10000)

        # Close dialog on client B
        done_btn_b.click()
        dialog_b = page_b.get_by_test_id("tag-management-dialog")
        expect(dialog_b).to_be_hidden(timeout=10000)
