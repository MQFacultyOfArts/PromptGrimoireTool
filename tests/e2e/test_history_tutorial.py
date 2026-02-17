"""E2E test: two history students collaborating in a tutorial.

Narrative persona test covering bidirectional real-time sync:
authenticate two users -> shared workspace -> highlights sync both ways ->
comments sync -> tag changes sync -> concurrent edits -> user count -> leave.

Each step is a discrete subtest checkpoint using pytest-subtests.

Replaces skipped test_annotation_sync.py and test_annotation_collab.py.

Acceptance Criteria:
- 156-e2e-test-migration.AC3.4: Persona test covering bidirectional sync
- 156-e2e-test-migration.AC3.6: Uses pytest-subtests for checkpoints
- 156-e2e-test-migration.AC4.1: No CSS.highlights assertions
- 156-e2e-test-migration.AC4.2: No page.evaluate() for internal DOM state
- 156-e2e-test-migration.AC5.1: Creates own workspace (no shared state)
- 156-e2e-test-migration.AC5.2: Random auth emails, no cross-test DB dependency

Traceability:
- Issue: #156 (E2E test migration)
- Design: docs/design-plans/2026-02-14-156-e2e-test-migration.md Phase 6
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import (
    create_highlight_with_tag,
    select_chars,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page
    from pytest_subtests import SubTests

# Locator constants
ANNOTATION_CARD = "[data-testid='annotation-card']"
USER_COUNT = "[data-testid='user-count']"


@pytest.mark.e2e
class TestHistoryTutorial:
    """Two history students collaborating on a shared annotation workspace."""

    def test_bidirectional_sync_workflow(
        self,
        two_authenticated_contexts: tuple[Page, Page, str, str, str],
        subtests: SubTests,
    ) -> None:
        """Complete collaboration workflow with 11 checkpoints.

        Tests bidirectional sync: highlights, comments, tag changes,
        concurrent edits, user count, and user departure.
        """
        page1, page2, _workspace_id, _user1_email, _user2_email = (
            two_authenticated_contexts
        )

        # UUID for cross-subtest comment verification
        comment_uuid = ""

        with subtests.test(msg="student_a_highlights_text"):
            # Student A highlights "Coll" (chars 0-4) with Jurisdiction tag
            create_highlight_with_tag(page1, 0, 4, tag_index=0)

            # Verify annotation card appears on page1
            expect(page1.locator(ANNOTATION_CARD).first).to_be_visible(timeout=10000)

        with subtests.test(msg="highlight_syncs_to_student_b"):
            # Student B should see the annotation card appear
            expect(page2.locator(ANNOTATION_CARD).first).to_be_visible(timeout=10000)

        with subtests.test(msg="student_b_highlights_different_text"):
            # Student B highlights "word1" (chars 18-23) with Procedural History tag
            create_highlight_with_tag(page2, 18, 23, tag_index=1)

            # Verify Student B now sees 2 annotation cards
            expect(page2.locator(ANNOTATION_CARD)).to_have_count(2, timeout=10000)

        with subtests.test(msg="second_highlight_syncs_to_student_a"):
            # Student A should see 2 annotation cards
            expect(page1.locator(ANNOTATION_CARD)).to_have_count(2, timeout=10000)

        with subtests.test(msg="student_a_adds_comment"):
            # Generate unique comment text
            comment_uuid = uuid4().hex

            # Click first annotation card to ensure comment input visible
            page1.locator(ANNOTATION_CARD).first.click()

            # Fill and post comment
            page1.get_by_placeholder("Add comment").first.fill(comment_uuid)
            page1.locator(ANNOTATION_CARD).first.get_by_text("Post").click()

            # Verify comment appears on page1
            expect(page1.get_by_text(comment_uuid)).to_be_visible(timeout=10000)

        with subtests.test(msg="comment_syncs_to_student_b"):
            # Student B should see the comment
            expect(page2.locator(ANNOTATION_CARD).first).to_contain_text(
                comment_uuid, timeout=10000
            )

        with subtests.test(msg="student_a_changes_tag"):
            # Change first card's tag from Jurisdiction to Procedural History
            first_card = page1.locator(ANNOTATION_CARD).first
            tag_select = first_card.locator(".q-select").first

            # Open dropdown
            tag_select.click()

            # Select Procedural History from menu
            page1.locator(".q-menu .q-item").filter(
                has_text="Procedural History"
            ).click()

            # Verify tag changed on page1
            expect(tag_select).to_contain_text("Procedural History", timeout=5000)

        with subtests.test(msg="tag_change_syncs_to_student_b"):
            # Student B should see the updated tag
            expect(page2.locator(ANNOTATION_CARD).first).to_contain_text(
                "Procedural History", timeout=10000
            )

        with subtests.test(msg="concurrent_highlights"):
            # Both students highlight different ranges simultaneously
            # Student A: chars 24-29 (" word2")
            select_chars(page1, 24, 29)
            page1.locator("[data-testid='tag-toolbar'] button").first.click()

            # Student B: chars 30-35 (" word3")
            select_chars(page2, 30, 35)
            page2.locator("[data-testid='tag-toolbar'] button").first.click()

            # Wait for sync; both pages should have 4 cards total
            expect(page1.locator(ANNOTATION_CARD)).to_have_count(4, timeout=10000)
            expect(page2.locator(ANNOTATION_CARD)).to_have_count(4, timeout=10000)

        with subtests.test(msg="user_count_shows_two"):
            # Both pages should show user count of 2
            expect(page1.locator(USER_COUNT)).to_contain_text("2", timeout=10000)
            expect(page2.locator(USER_COUNT)).to_contain_text("2", timeout=10000)

        with subtests.test(msg="student_b_leaves"):
            # Close page2's browser context to simulate user leaving
            page2.context.close()

            # Student A's user count should drop to 1
            expect(page1.locator(USER_COUNT)).to_contain_text("1", timeout=10000)
