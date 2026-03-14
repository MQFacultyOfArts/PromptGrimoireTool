"""E2E tests for cross-tab card flow: Annotate -> Organise -> Respond.

Characterisation tests verifying that highlight creation and commenting
on the Annotate tab propagates correctly to the Organise and Respond tabs.

Covers gaps not tested elsewhere:
- Comment text visible on Respond tab reference cards after adding on Annotate
- Focused cross-tab content consistency (single test covering all three tabs)

Traceability:
- Plan: phase_01.md Task 6 (multi-doc-tabs-186)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from promptgrimoire.docs.helpers import wait_for_text_walker
from tests.e2e.card_helpers import add_comment_to_highlight
from tests.e2e.conftest import _authenticate_page
from tests.e2e.db_fixtures import _create_workspace_via_db
from tests.e2e.highlight_tools import create_highlight_with_tag, find_text_range

if TYPE_CHECKING:
    from playwright.sync_api import Page


@pytest.mark.e2e
@pytest.mark.cards
class TestCrossTabCardFlow:
    """Cross-tab card flow: highlight + comment on Annotate -> Organise -> Respond."""

    def test_comment_visible_on_respond_tab(
        self,
        authenticated_page: Page,
        app_server: str,
    ) -> None:
        """Comment added on Annotate tab appears on Respond tab reference card.

        This gap is not covered by test_law_student (which checks ref card
        count but not comment content) or test_annotation_canvas (which
        checks comments on Organise but not Respond).

        Steps:
        1. Create workspace with seeded tags
        2. Create highlight on Annotate tab
        3. Add a comment with unique text
        4. Switch to Respond tab
        5. Verify comment text is visible on the reference card
        """
        page = authenticated_page
        page_email = _authenticate_page(page, app_server)

        workspace_id = _create_workspace_via_db(
            user_email=page_email,
            html_content=(
                "<p>The defendant failed to maintain safe working "
                "conditions despite repeated complaints from employees "
                "about the hazardous machinery on the factory floor.</p>"
            ),
            seed_tags=True,
        )

        page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
        wait_for_text_walker(page, timeout=15000)

        toolbar = page.locator("[data-testid='tag-toolbar']")
        expect(toolbar).to_be_visible(timeout=5000)

        # Create highlight
        hl = find_text_range(page, "failed to maintain")
        create_highlight_with_tag(page, *hl, tag_index=0)

        card = page.locator("[data-testid='annotation-card']").first
        expect(card).to_be_visible(timeout=10000)

        # Add comment with unique text
        comment_text = "Cross-tab comment verification marker"
        add_comment_to_highlight(page, comment_text, card_index=0)

        # Switch to Respond tab
        page.get_by_test_id("tab-respond").click()

        # Wait for respond reference panel
        ref_panel = page.locator("[data-testid='respond-reference-panel']")
        expect(ref_panel).to_be_visible(timeout=10000)

        # Verify reference card exists
        ref_card = ref_panel.locator("[data-testid='respond-reference-card']")
        expect(ref_card.first).to_be_visible(timeout=5000)

        # Verify comment text appears on the reference card
        expect(ref_card.first).to_contain_text(comment_text, timeout=5000)

    def test_highlight_appears_across_all_three_tabs(
        self,
        authenticated_page: Page,
        app_server: str,
    ) -> None:
        """Highlight created on Annotate tab appears on Organise and Respond.

        Focused cross-tab consistency test: creates a single highlight,
        then verifies card/content presence on all three tabs.
        """
        page = authenticated_page
        page_email = _authenticate_page(page, app_server)

        workspace_id = _create_workspace_via_db(
            user_email=page_email,
            html_content=(
                "<p>The plaintiff suffered significant emotional distress "
                "as a result of the negligent supervision provided by "
                "the school administration during the field trip.</p>"
            ),
            seed_tags=True,
        )

        page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
        wait_for_text_walker(page, timeout=15000)

        toolbar = page.locator("[data-testid='tag-toolbar']")
        expect(toolbar).to_be_visible(timeout=5000)

        # Create highlight with known text
        highlight_text = "negligent supervision"
        hl = find_text_range(page, highlight_text)
        create_highlight_with_tag(page, *hl, tag_index=0)

        # Verify on Annotate tab
        card = page.locator("[data-testid='annotation-card']").first
        expect(card).to_be_visible(timeout=10000)

        # Switch to Organise tab and verify
        page.get_by_test_id("tab-organise").click()
        organise_card = page.locator("[data-testid='organise-card']").first
        expect(organise_card).to_be_visible(timeout=10000)
        expect(organise_card).to_contain_text(highlight_text, timeout=5000)

        # Switch to Respond tab and verify
        page.get_by_test_id("tab-respond").click()
        ref_panel = page.locator("[data-testid='respond-reference-panel']")
        expect(ref_panel).to_be_visible(timeout=10000)
        ref_card = ref_panel.locator("[data-testid='respond-reference-card']")
        expect(ref_card.first).to_be_visible(timeout=5000)
        expect(ref_card.first).to_contain_text(highlight_text, timeout=5000)
