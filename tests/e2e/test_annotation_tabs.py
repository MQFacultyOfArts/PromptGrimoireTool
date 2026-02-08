"""E2E tests for three-tab annotation interface.

Tests verify that the annotation page renders three tabs (Annotate, Organise,
Respond), that deferred rendering works for Tabs 2 and 3, and that switching
tabs preserves Tab 1 state. Phase 3 adds tests for Tab 2 tag columns and
highlight cards. Phase 5 adds tests for Tab 3 Milkdown editor and collaboration.
Phase 6 adds tests for warp navigation (locate buttons) and cross-tab reactivity.

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_01.md
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_03.md
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_05.md
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_06.md
- AC: three-tab-ui.AC1.1 through AC1.4
- AC: three-tab-ui.AC2.1, AC2.2, AC2.6
- AC: three-tab-ui.AC4.1 through AC4.5
- AC: three-tab-ui.AC5.1 through AC5.5
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import (
    create_highlight,
    create_highlight_with_tag,
    setup_workspace_with_content,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Page


# Skip if no database configured
pytestmark_db = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)


@pytest.fixture
def workspace_page(authenticated_page: Page, app_server: str) -> Generator[Page]:
    """Authenticated page with a workspace containing document content.

    Reuses the authenticated_page fixture and setup_workspace_with_content helper
    to create a workspace with plain text content. Yields a page ready for tab testing.
    """
    setup_workspace_with_content(
        authenticated_page,
        app_server,
        "Tab test content for annotation workspace verification",
    )
    yield authenticated_page


class TestTabHeaders:
    """Verify three tab headers render with correct names and default selection.

    Verifies: three-tab-ui.AC1.1
    """

    @pytestmark_db
    def test_tab_headers(self, workspace_page: Page) -> None:
        """Page renders Annotate, Organise, Respond tabs with Annotate selected."""
        page = workspace_page

        # Assert three tab elements exist
        tabs = page.locator("role=tab")
        expect(tabs).to_have_count(3, timeout=5000)

        # Verify tab names
        expect(tabs.nth(0)).to_contain_text("Annotate")
        expect(tabs.nth(1)).to_contain_text("Organise")
        expect(tabs.nth(2)).to_contain_text("Respond")

        # Verify Annotate is the selected/active tab
        annotate_tab = tabs.nth(0)
        expect(annotate_tab).to_have_attribute("aria-selected", "true")


class TestDeferredRendering:
    """Verify that Tab 2 and Tab 3 use deferred rendering.

    Verifies: three-tab-ui.AC1.3
    """

    @pytestmark_db
    def test_deferred_rendering(self, workspace_page: Page) -> None:
        """Tabs 2 and 3 render content on first visit (deferred rendering).

        Tab 2 (Organise) renders tag columns on first visit.
        Tab 3 (Respond) still shows placeholder until Phase 5.
        """
        page = workspace_page

        # Tab 1 (Annotate) should have document content (char spans)
        expect(page.locator("[data-char-index]").first).to_be_visible()

        # Click Organise tab -- triggers deferred render of tag columns
        page.locator("role=tab").nth(1).click()
        page.wait_for_timeout(500)

        # Organise panel should show tag columns (Phase 3 replaced placeholder)
        organise_panel = page.locator("[role='tabpanel']").nth(1)
        expect(organise_panel).to_be_visible()
        expect(
            organise_panel.locator('[data-testid="organise-columns"]')
        ).to_be_visible(timeout=3000)

        # Click Respond tab -- triggers deferred render of Milkdown editor
        page.locator("role=tab").nth(2).click()
        page.wait_for_timeout(1000)

        # Respond panel should show Milkdown editor container (Phase 5)
        respond_panel = page.locator("[role='tabpanel']").nth(2)
        expect(respond_panel).to_be_visible()
        expect(
            respond_panel.locator('[data-testid="milkdown-editor-container"]')
        ).to_be_visible(timeout=5000)


class TestTabStatePreservation:
    """Verify Tab 1 state is preserved when switching tabs.

    Verifies: three-tab-ui.AC1.2, three-tab-ui.AC1.4
    """

    @pytestmark_db
    def test_document_content_preserved_after_tab_switch(
        self, workspace_page: Page
    ) -> None:
        """Document content in Tab 1 survives round-trip to Tab 2 and back."""
        page = workspace_page

        # Verify content is visible in Tab 1
        char_spans = page.locator("[data-char-index]")
        initial_count = char_spans.count()
        assert initial_count > 0, "Expected char spans in Tab 1"

        # Switch to Organise tab
        page.locator("role=tab").nth(1).click()
        page.wait_for_timeout(300)

        # Switch back to Annotate tab
        page.locator("role=tab").nth(0).click()
        page.wait_for_timeout(300)

        # Verify document content is still there
        char_spans_after = page.locator("[data-char-index]")
        expect(char_spans_after.first).to_be_visible(timeout=3000)
        assert char_spans_after.count() == initial_count, (
            f"Char span count changed: {initial_count} -> {char_spans_after.count()}"
        )


class TestOrganiseTabColumns:
    """Verify Tab 2 shows tag columns with correct structure.

    Verifies: three-tab-ui.AC2.1
    """

    @pytestmark_db
    def test_organise_tab_shows_tag_columns(self, workspace_page: Page) -> None:
        """Navigate to Organise tab and verify tag column headers appear.

        Creates a highlight first to ensure the tab has content, then
        switches to Organise tab and checks for tag column headers.
        """
        page = workspace_page

        # Create a highlight on the first few characters
        create_highlight(page, 0, 5)
        page.wait_for_timeout(500)

        # Switch to Organise tab
        page.locator("role=tab").nth(1).click()
        page.wait_for_timeout(500)

        # Verify the organise columns container exists
        columns = page.locator('[data-testid="organise-columns"]')
        expect(columns).to_be_visible(timeout=3000)

        # Verify at least one tag column exists
        tag_columns = page.locator('[data-testid="tag-column"]')
        expect(tag_columns.first).to_be_visible(timeout=3000)

        # Verify "Jurisdiction" column exists (first tag)
        jurisdiction_col = page.locator(
            '[data-testid="tag-column"][data-tag-name="Jurisdiction"]'
        )
        expect(jurisdiction_col).to_be_visible()

    @pytestmark_db
    def test_organise_tab_highlight_in_correct_column(
        self, workspace_page: Page
    ) -> None:
        """Create a highlight with a tag, verify it appears in the correct column."""
        page = workspace_page

        # create_highlight clicks first tag button (Jurisdiction)
        create_highlight(page, 0, 5)
        page.wait_for_timeout(500)

        # Switch to Organise tab
        page.locator("role=tab").nth(1).click()
        page.wait_for_timeout(500)

        # The highlight should appear as a card in the Jurisdiction column
        jurisdiction_col = page.locator(
            '[data-testid="tag-column"][data-tag-name="Jurisdiction"]'
        )
        expect(jurisdiction_col).to_be_visible(timeout=3000)
        cards_in_col = jurisdiction_col.locator('[data-testid="organise-card"]')
        expect(cards_in_col).to_have_count(1, timeout=3000)

    @pytestmark_db
    def test_organise_tab_card_shows_author_and_text(
        self, workspace_page: Page
    ) -> None:
        """Create a highlight, verify the card shows author and text snippet."""
        page = workspace_page

        # Create a highlight
        create_highlight(page, 0, 5)
        page.wait_for_timeout(500)

        # Switch to Organise tab
        page.locator("role=tab").nth(1).click()
        page.wait_for_timeout(500)

        # Find the organise card
        card = page.locator('[data-testid="organise-card"]').first
        expect(card).to_be_visible(timeout=3000)

        # Card should show "by" author text
        expect(card).to_contain_text("by ")

        # Card should contain a text snippet (quoted text from the highlight)
        # The highlight text is the first few chars of "Tab test content..."
        expect(card.locator(".italic")).to_be_visible()

    @pytestmark_db
    def test_organise_tab_untagged_highlight_in_untagged_column(self) -> None:
        """Create a highlight without a tag, verify it appears in Untagged column.

        Verifies: three-tab-ui.AC2.6
        Note: This test depends on being able to create a highlight with no tag.
        If the UI always assigns a tag, this test will need adjustment.
        The unit test test_untagged_highlights_collected covers the logic path.
        """
        pytest.skip("No UI mechanism to create untagged highlights yet")


class TestRespondTabEditor:
    """Verify Tab 3 renders Milkdown editor with toolbar.

    Verifies: three-tab-ui.AC4.1
    """

    @pytestmark_db
    def test_respond_tab_shows_milkdown_editor(self, workspace_page: Page) -> None:
        """Navigate to Respond tab and verify Milkdown editor container appears."""
        page = workspace_page

        # Switch to Respond tab
        page.locator("role=tab").nth(2).click()
        page.wait_for_timeout(1500)

        # Verify the editor container is visible
        editor_container = page.locator('[data-testid="milkdown-editor-container"]')
        expect(editor_container).to_be_visible(timeout=10000)

        # Verify the editor column label
        editor_column = page.locator('[data-testid="respond-editor-column"]')
        expect(editor_column).to_be_visible()
        expect(editor_column).to_contain_text("Response Draft")

    @pytestmark_db
    def test_respond_tab_shows_reference_panel(self, workspace_page: Page) -> None:
        """Navigate to Respond tab and verify reference panel appears."""
        page = workspace_page

        # Switch to Respond tab
        page.locator("role=tab").nth(2).click()
        page.wait_for_timeout(1500)

        # Verify reference panel is visible
        ref_panel = page.locator('[data-testid="respond-reference-panel"]')
        expect(ref_panel).to_be_visible(timeout=5000)
        expect(ref_panel).to_contain_text("Highlight Reference")


class TestRespondTabReferenceHighlights:
    """Verify Tab 3 reference panel shows highlights grouped by tag.

    Verifies: three-tab-ui.AC4.4
    """

    @pytestmark_db
    def test_respond_tab_reference_panel_shows_highlights(
        self, workspace_page: Page
    ) -> None:
        """Create highlights with different tags, verify reference panel groups them."""
        page = workspace_page

        # Create highlights with different tags
        # Tag index 0 = Jurisdiction, index 1 = Procedural History
        create_highlight_with_tag(page, 0, 5, tag_index=0)
        page.wait_for_timeout(500)
        create_highlight_with_tag(page, 10, 15, tag_index=1)
        page.wait_for_timeout(500)

        # Switch to Respond tab
        page.locator("role=tab").nth(2).click()
        page.wait_for_timeout(1500)

        # Verify reference panel shows tag group sections
        ref_panel = page.locator('[data-testid="respond-reference-panel"]')
        expect(ref_panel).to_be_visible(timeout=5000)

        # Should have tag group sections for the tags with highlights
        tag_groups = ref_panel.locator('[data-testid="respond-tag-group"]')
        expect(tag_groups.first).to_be_visible(timeout=5000)

        # Should have reference cards
        ref_cards = ref_panel.locator('[data-testid="respond-reference-card"]')
        expect(ref_cards).to_have_count(2, timeout=5000)


class TestRespondTabEmptyState:
    """Verify Tab 3 with no highlights shows empty reference panel.

    Verifies: three-tab-ui.AC4.5
    """

    @pytestmark_db
    def test_respond_tab_no_highlights_shows_empty_reference(
        self, workspace_page: Page
    ) -> None:
        """Navigate to Respond tab with no highlights, verify empty message."""
        page = workspace_page

        # Switch to Respond tab (no highlights created)
        page.locator("role=tab").nth(2).click()
        page.wait_for_timeout(1500)

        # Verify the editor container is visible (editor still works)
        editor_container = page.locator('[data-testid="milkdown-editor-container"]')
        expect(editor_container).to_be_visible(timeout=10000)

        # Verify the empty-state message in the reference panel
        no_highlights = page.locator('[data-testid="respond-no-highlights"]')
        expect(no_highlights).to_be_visible(timeout=5000)
        expect(no_highlights).to_contain_text("No highlights yet")


class TestRespondTabCollaboration:
    """Verify Tab 3 real-time collaboration between two clients.

    Verifies: three-tab-ui.AC4.2, three-tab-ui.AC4.3

    These tests require two browser contexts viewing the same workspace.
    They use the two_annotation_contexts fixture from conftest.py.
    """

    @pytestmark_db
    def test_respond_tab_late_joiner_sync(
        self, two_annotation_contexts: tuple[Page, Page, str]
    ) -> None:
        """Client 1 types in editor, Client 2 joins and sees content.

        Verifies: three-tab-ui.AC4.3
        """
        page1, page2, _workspace_id = two_annotation_contexts

        # Client 1 switches to Respond tab
        page1.locator("role=tab").nth(2).click()
        page1.wait_for_timeout(2000)

        # Verify editor is visible for Client 1
        editor1 = page1.locator('[data-testid="milkdown-editor-container"]')
        expect(editor1).to_be_visible(timeout=10000)

        # Client 1 clicks in the editor and types
        editor1.locator(".ProseMirror").click()
        page1.wait_for_timeout(500)
        page1.keyboard.type("Initial content from client one")
        page1.wait_for_timeout(1000)

        # Client 2 switches to Respond tab (late joiner)
        page2.locator("role=tab").nth(2).click()
        page2.wait_for_timeout(3000)

        # Verify editor is visible for Client 2
        editor2 = page2.locator('[data-testid="milkdown-editor-container"]')
        expect(editor2).to_be_visible(timeout=10000)

        # Client 2 should see the content typed by Client 1
        prosemirror2 = editor2.locator(".ProseMirror")
        expect(prosemirror2).to_contain_text("Initial content", timeout=10000)

    @pytestmark_db
    def test_respond_tab_two_clients_real_time_sync(
        self, two_annotation_contexts: tuple[Page, Page, str]
    ) -> None:
        """Both clients on Respond tab, edits sync in real time.

        Verifies: three-tab-ui.AC4.2
        """
        page1, page2, _workspace_id = two_annotation_contexts

        # Both clients switch to Respond tab
        page1.locator("role=tab").nth(2).click()
        page1.wait_for_timeout(2000)
        page2.locator("role=tab").nth(2).click()
        page2.wait_for_timeout(2000)

        # Verify both editors are visible
        editor1 = page1.locator('[data-testid="milkdown-editor-container"]')
        editor2 = page2.locator('[data-testid="milkdown-editor-container"]')
        expect(editor1).to_be_visible(timeout=10000)
        expect(editor2).to_be_visible(timeout=10000)

        # Client 1 types in the editor
        editor1.locator(".ProseMirror").click()
        page1.wait_for_timeout(500)
        page1.keyboard.type("Hello World")
        page1.wait_for_timeout(2000)

        # Client 2 should see the content
        prosemirror2 = editor2.locator(".ProseMirror")
        expect(prosemirror2).to_contain_text("Hello World", timeout=10000)


class TestLocateButtonFromTab2:
    """Verify locate button on Tab 2 cards warps to Tab 1 and scrolls.

    Verifies: three-tab-ui.AC5.1
    """

    @pytestmark_db
    def test_locate_button_warps_to_tab1_and_scrolls(
        self, workspace_page: Page
    ) -> None:
        """Create highlight, switch to Organise, click locate -- warp."""
        page = workspace_page

        # Create a highlight on the first few characters
        create_highlight(page, 0, 5)
        page.wait_for_timeout(500)

        # Switch to Organise tab
        page.locator("role=tab").nth(1).click()
        page.wait_for_timeout(500)

        # Verify the organise card has a locate button
        card = page.locator('[data-testid="organise-card"]').first
        expect(card).to_be_visible(timeout=3000)
        locate_btn = card.locator("button", has=page.locator("text=my_location")).first
        # Fall back to tooltip-based lookup if icon text not directly visible
        if not locate_btn.is_visible(timeout=1000):
            locate_btn = card.locator('button[title="Locate in document"]').first
        if not locate_btn.is_visible(timeout=1000):
            # NiceGUI renders icon buttons with .q-icon containing the icon name
            locate_btn = card.locator("button").first

        expect(locate_btn).to_be_visible(timeout=3000)
        locate_btn.click()
        page.wait_for_timeout(1000)

        # Verify the active tab switched to Annotate
        annotate_tab = page.locator("role=tab").nth(0)
        expect(annotate_tab).to_have_attribute("aria-selected", "true", timeout=3000)

        # Verify char spans are visible (Tab 1 content rendered)
        expect(page.locator("[data-char-index='0']")).to_be_visible(timeout=3000)


class TestLocateButtonFromTab3:
    """Verify locate button on Tab 3 reference panel cards warps to Tab 1.

    Verifies: three-tab-ui.AC5.1
    """

    @pytestmark_db
    def test_locate_button_from_tab3_warps_to_tab1(self, workspace_page: Page) -> None:
        """Create highlight, switch to Respond, click locate -- verify warp to Tab 1."""
        page = workspace_page

        # Create a highlight
        create_highlight(page, 0, 5)
        page.wait_for_timeout(500)

        # Switch to Respond tab
        page.locator("role=tab").nth(2).click()
        page.wait_for_timeout(1500)

        # Verify reference panel has a card with locate button
        ref_panel = page.locator('[data-testid="respond-reference-panel"]')
        expect(ref_panel).to_be_visible(timeout=5000)

        ref_card = ref_panel.locator('[data-testid="respond-reference-card"]').first
        expect(ref_card).to_be_visible(timeout=5000)

        # Click the locate button on the reference card
        locate_btn = ref_card.locator("button").first
        expect(locate_btn).to_be_visible(timeout=3000)
        locate_btn.click()
        page.wait_for_timeout(1000)

        # Verify the active tab switched to Annotate
        annotate_tab = page.locator("role=tab").nth(0)
        expect(annotate_tab).to_have_attribute("aria-selected", "true", timeout=3000)

        # Verify char spans are visible (Tab 1 content rendered)
        expect(page.locator("[data-char-index='0']")).to_be_visible(timeout=3000)


class TestReturnToPreviousTab:
    """Verify user can return to previous tab after warp.

    Verifies: three-tab-ui.AC5.5
    """

    @pytestmark_db
    def test_return_to_previous_tab_after_warp(self, workspace_page: Page) -> None:
        """Warp to Tab 1 from Organise, then click Organise -- tab is still there."""
        page = workspace_page

        # Create a highlight
        create_highlight(page, 0, 5)
        page.wait_for_timeout(500)

        # Switch to Organise tab
        page.locator("role=tab").nth(1).click()
        page.wait_for_timeout(500)

        # Verify Organise content is rendered
        columns = page.locator('[data-testid="organise-columns"]')
        expect(columns).to_be_visible(timeout=3000)

        # Click locate button to warp to Tab 1
        card = page.locator('[data-testid="organise-card"]').first
        expect(card).to_be_visible(timeout=3000)
        locate_btn = card.locator("button").first
        locate_btn.click()
        page.wait_for_timeout(1000)

        # Verify we're on Tab 1
        annotate_tab = page.locator("role=tab").nth(0)
        expect(annotate_tab).to_have_attribute("aria-selected", "true", timeout=3000)

        # Click Organise tab to return
        page.locator("role=tab").nth(1).click()
        page.wait_for_timeout(500)

        # Verify Organise tab content is still rendered (not blank)
        columns_after = page.locator('[data-testid="organise-columns"]')
        expect(columns_after).to_be_visible(timeout=3000)

        # Verify Organise is the active tab
        organise_tab = page.locator("role=tab").nth(1)
        expect(organise_tab).to_have_attribute("aria-selected", "true")


class TestCrossTabHighlightReactivity:
    """Verify highlights created in Tab 1 appear in Tab 2 and Tab 3.

    Verifies: three-tab-ui.AC5.2

    These tests require two browser contexts viewing the same workspace.
    """

    @pytestmark_db
    def test_new_highlight_appears_in_tab2(
        self, two_annotation_contexts: tuple[Page, Page, str]
    ) -> None:
        """Client 1 creates highlight on Tab 1, Client 2 sees it on Tab 2.

        Verifies: three-tab-ui.AC5.2
        """
        page1, page2, _workspace_id = two_annotation_contexts

        # Client 2 switches to Organise tab
        page2.locator("role=tab").nth(1).click()
        page2.wait_for_timeout(500)

        # Client 1 creates a highlight on Tab 1 (Annotate)
        create_highlight(page1, 0, 5)
        page1.wait_for_timeout(1000)

        # Client 2 should see the new highlight appear in Organise tab
        card = page2.locator('[data-testid="organise-card"]')
        expect(card.first).to_be_visible(timeout=10000)

    @pytestmark_db
    def test_new_highlight_appears_in_tab3_reference(
        self, two_annotation_contexts: tuple[Page, Page, str]
    ) -> None:
        """Client 1 creates highlight on Tab 1, Client 2 sees it in Tab 3 reference.

        Verifies: three-tab-ui.AC5.2
        """
        page1, page2, _workspace_id = two_annotation_contexts

        # Client 2 switches to Respond tab (initialises Milkdown + reference panel)
        page2.locator("role=tab").nth(2).click()
        page2.wait_for_timeout(2000)

        # Verify reference panel shows empty state initially
        ref_panel = page2.locator('[data-testid="respond-reference-panel"]')
        expect(ref_panel).to_be_visible(timeout=5000)

        # Client 1 creates a highlight on Tab 1 (Annotate)
        create_highlight(page1, 0, 5)
        page1.wait_for_timeout(1000)

        # Client 2's reference panel should show the new highlight
        ref_card = ref_panel.locator('[data-testid="respond-reference-card"]')
        expect(ref_card.first).to_be_visible(timeout=10000)


class TestWarpDoesNotAffectOtherUsers:
    """Verify that warp navigation is per-client only.

    Verifies: three-tab-ui.AC5.4
    """

    @pytestmark_db
    def test_warp_does_not_affect_other_user(
        self, two_annotation_contexts: tuple[Page, Page, str]
    ) -> None:
        """Client 1 warps from Tab 2, Client 2 stays on their current tab.

        Verifies: three-tab-ui.AC5.4
        """
        page1, page2, _workspace_id = two_annotation_contexts

        # Client 1 creates a highlight
        create_highlight(page1, 0, 5)
        page1.wait_for_timeout(500)

        # Both clients switch to Organise tab
        page1.locator("role=tab").nth(1).click()
        page1.wait_for_timeout(500)
        page2.locator("role=tab").nth(1).click()
        page2.wait_for_timeout(500)

        # Verify both are on Organise
        expect(page1.locator("role=tab").nth(1)).to_have_attribute(
            "aria-selected", "true", timeout=3000
        )
        expect(page2.locator("role=tab").nth(1)).to_have_attribute(
            "aria-selected", "true", timeout=3000
        )

        # Client 1 clicks locate on a card (warps to Tab 1)
        card1 = page1.locator('[data-testid="organise-card"]').first
        expect(card1).to_be_visible(timeout=3000)
        locate_btn = card1.locator("button").first
        locate_btn.click()
        page1.wait_for_timeout(1000)

        # Client 1 should now be on Annotate tab
        expect(page1.locator("role=tab").nth(0)).to_have_attribute(
            "aria-selected", "true", timeout=3000
        )

        # Client 2 should STILL be on Organise tab (not affected by warp)
        expect(page2.locator("role=tab").nth(1)).to_have_attribute(
            "aria-selected", "true", timeout=3000
        )
