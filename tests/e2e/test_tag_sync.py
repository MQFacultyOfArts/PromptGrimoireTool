"""E2E test: tag creation propagates to a second client in real time.

Verifies the full tag sync pipeline: DB write -> CRDT write -> broadcast ->
receiving client rebuilds tag_info_list -> toolbar updates.

Acceptance Criteria:
- tag-lifecycle-235-291.AC2.1: Creating a tag via quick create immediately
  appears on all connected clients' tag bars (no refresh)
- tag-lifecycle-235-291.AC2.2: Creating a tag via management dialog immediately
  appears on all connected clients

Traceability:
- Issues: #235, #291
- Phase: docs/implementation-plans/2026-03-06-tag-lifecycle-235-291/phase_03.md Task 5
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page


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
