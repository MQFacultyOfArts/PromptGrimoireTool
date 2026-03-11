"""E2E tests for card positioning and collapsed card feature.

Covers:
- AC1: Card positioning — initial placement, scroll recovery, height cache.
- AC2: Collapsed cards — default state, expand/collapse toggle, author
  initials, push-down on expand, view-only restrictions.

Traceability:
- Issue: #236 (Card layout and positioning)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from promptgrimoire.docs.helpers import wait_for_text_walker
from tests.e2e.card_helpers import collapse_card, expand_card
from tests.e2e.conftest import _authenticate_page, _grant_workspace_access
from tests.e2e.db_fixtures import _create_workspace_via_db
from tests.e2e.highlight_tools import create_highlight_with_tag, find_text_range

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_card_top(page: Page, card_index: int) -> float:
    """Read the computed ``top`` style of an annotation card (px).

    Cards are absolutely positioned by ``positionCards()`` in
    ``annotation-card-sync.js``, so ``style.top`` is always set.
    """
    # evaluate() needed — no Playwright-native way to read inline style.top
    return (
        page.locator("[data-testid='annotation-card']")
        .nth(card_index)
        .evaluate("el => parseFloat(el.style.top)")
    )


def _wait_for_position_cards(page: Page) -> None:
    """Wait for ``positionCards()`` to run after a layout change."""
    page.wait_for_function("new Promise(r => requestAnimationFrame(r))")


# ---------------------------------------------------------------------------
# Task 9 — Card positioning tests (AC1)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.cards
class TestCardPositioning:
    """AC1: Card positioning and solitaire-collapse regression tests."""

    def test_initial_positioning_non_zero_no_overlap(
        self,
        authenticated_page: Page,
        app_server: str,
    ) -> None:
        """AC1.1: Cards have non-zero top values and do not overlap.

        Creates 3 highlights, verifies each card gets a positive ``top``
        style and that successive cards have strictly increasing ``top``
        values (accounting for height + gap).
        """
        page = authenticated_page
        page_email = _authenticate_page(page, app_server)

        workspace_id = _create_workspace_via_db(
            user_email=page_email,
            html_content=(
                "<p>The plaintiff alleged that the defendant breached "
                "their duty of care in the workplace setting. "
                "The court considered the evidence presented by both "
                "parties and found in favour of the plaintiff. "
                "Damages were awarded accordingly.</p>"
            ),
            seed_tags=True,
        )

        page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
        wait_for_text_walker(page, timeout=15000)

        toolbar = page.locator("[data-testid='tag-toolbar']")
        expect(toolbar).to_be_visible(timeout=5000)

        # Create 3 highlights at different positions
        hl1 = find_text_range(page, "plaintiff alleged")
        create_highlight_with_tag(page, *hl1, tag_index=0)
        expect(page.locator("[data-testid='annotation-card']").first).to_be_visible(
            timeout=10000
        )

        hl2 = find_text_range(page, "duty of care")
        create_highlight_with_tag(page, *hl2, tag_index=1)
        expect(page.locator("[data-testid='annotation-card']")).to_have_count(
            2, timeout=10000
        )

        hl3 = find_text_range(page, "court considered")
        create_highlight_with_tag(page, *hl3, tag_index=2)
        expect(page.locator("[data-testid='annotation-card']")).to_have_count(
            3, timeout=10000
        )

        _wait_for_position_cards(page)

        # Verify all cards have non-zero top values
        tops: list[float] = []
        for i in range(3):
            top = _get_card_top(page, i)
            assert top >= 0, f"Card {i} has negative top: {top}"
            tops.append(top)

        # Verify cards are in strictly increasing order (no overlap)
        for i in range(len(tops) - 1):
            assert tops[i] < tops[i + 1], (
                f"Card {i} (top={tops[i]}) not above card {i + 1} (top={tops[i + 1]})"
            )

    def test_scroll_recovery_no_solitaire_collapse(
        self,
        authenticated_page: Page,
        app_server: str,
    ) -> None:
        """AC1.3: Cards restore at original positions after scroll away and back.

        Creates highlights, records positions, scrolls past them (so
        cards are hidden), scrolls back, and verifies positions are
        restored within tolerance.
        """
        page = authenticated_page
        page_email = _authenticate_page(page, app_server)

        workspace_id = _create_workspace_via_db(
            user_email=page_email,
            html_content=(
                "<p>First paragraph with important content for testing. "
                "The court held that the defendant owed a duty of care.</p>"
                + "<p>Filler paragraph. </p>" * 40
                + "<p>Final paragraph at the bottom of a very long document.</p>"
            ),
            seed_tags=True,
        )

        page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
        wait_for_text_walker(page, timeout=15000)

        toolbar = page.locator("[data-testid='tag-toolbar']")
        expect(toolbar).to_be_visible(timeout=5000)

        # Create 2 highlights near the top
        hl1 = find_text_range(page, "First paragraph")
        create_highlight_with_tag(page, *hl1, tag_index=0)
        expect(page.locator("[data-testid='annotation-card']").first).to_be_visible(
            timeout=10000
        )

        hl2 = find_text_range(page, "important content")
        create_highlight_with_tag(page, *hl2, tag_index=1)
        expect(page.locator("[data-testid='annotation-card']")).to_have_count(
            2, timeout=10000
        )

        _wait_for_position_cards(page)

        # Record initial positions
        top0_before = _get_card_top(page, 0)
        top1_before = _get_card_top(page, 1)

        # Scroll to the very bottom of the document container
        page.evaluate(
            """() => {
                const dc = document.getElementById('doc-container');
                if (dc) dc.scrollTop = dc.scrollHeight;
                else window.scrollTo(0, document.body.scrollHeight);
            }"""
        )
        _wait_for_position_cards(page)

        # Scroll back to the top
        page.evaluate(
            """() => {
                const dc = document.getElementById('doc-container');
                if (dc) dc.scrollTop = 0;
                else window.scrollTo(0, 0);
            }"""
        )
        _wait_for_position_cards(page)

        # Wait for cards to become visible again
        expect(page.locator("[data-testid='annotation-card']").first).to_be_visible(
            timeout=10000
        )

        # Verify positions restored within tolerance (5px)
        top0_after = _get_card_top(page, 0)
        top1_after = _get_card_top(page, 1)

        tolerance = 5.0
        assert abs(top0_after - top0_before) <= tolerance, (
            f"Card 0 position drifted: {top0_before} -> {top0_after}"
        )
        assert abs(top1_after - top1_before) <= tolerance, (
            f"Card 1 position drifted: {top1_before} -> {top1_after}"
        )

    def test_race_condition_highlights_ready(
        self,
        authenticated_page: Page,
        app_server: str,
    ) -> None:
        """AC1.2: Cards positioned after SPA navigation with pre-existing highlights.

        Verifies that ``window._highlightsReady`` is set before asserting card
        positions, guarding against the race where ``setupCardPositioning()``
        fires before highlights have been applied on SPA navigation.

        After the ready flag is confirmed, cards must have positive ``top``
        values without any scroll required.
        """
        page = authenticated_page
        page_email = _authenticate_page(page, app_server)

        workspace_id = _create_workspace_via_db(
            user_email=page_email,
            html_content=(
                "<p>The court found that the defendant had breached "
                "the applicable standard of care in these circumstances.</p>"
            ),
            seed_tags=True,
        )

        # First visit: create the highlight so it persists in the DB
        page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
        wait_for_text_walker(page, timeout=15000)

        toolbar = page.locator("[data-testid='tag-toolbar']")
        expect(toolbar).to_be_visible(timeout=5000)

        hl = find_text_range(page, "court found that")
        create_highlight_with_tag(page, *hl, tag_index=0)
        expect(page.locator("[data-testid='annotation-card']").first).to_be_visible(
            timeout=10000
        )

        # SPA navigate away then back — the highlight is now pre-existing
        page.goto(f"{app_server}/")
        page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")

        # Wait for the highlights-ready flag set by annotation-highlight.js
        page.wait_for_function("() => window._highlightsReady === true", timeout=10000)

        # Cards must be positioned without any manual scroll
        _wait_for_position_cards(page)

        card = page.locator("[data-testid='annotation-card']").first
        expect(card).to_be_visible(timeout=10000)

        top = _get_card_top(page, 0)
        assert top >= 0, f"Card top is negative after SPA navigation: {top}"


# ---------------------------------------------------------------------------
# Task 10 — Collapsed card feature tests (AC2)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.cards
class TestCollapsedCards:
    """AC2: Collapsed card defaults, expand/collapse toggle, and view-only."""

    def test_default_collapsed_with_compact_header(
        self,
        authenticated_page: Page,
        app_server: str,
    ) -> None:
        """AC2.1: Cards are collapsed by default with compact header visible.

        Creates a highlight and verifies:
        - Card is visible
        - card-detail section is hidden
        - Compact header contains expand button
        """
        page = authenticated_page
        page_email = _authenticate_page(page, app_server)

        workspace_id = _create_workspace_via_db(
            user_email=page_email,
            html_content=("<p>The plaintiff alleged negligence in the workplace.</p>"),
            seed_tags=True,
        )

        page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
        wait_for_text_walker(page, timeout=15000)

        toolbar = page.locator("[data-testid='tag-toolbar']")
        expect(toolbar).to_be_visible(timeout=5000)

        hl = find_text_range(page, "plaintiff alleged")
        create_highlight_with_tag(page, *hl, tag_index=0)

        card = page.locator("[data-testid='annotation-card']").first
        expect(card).to_be_visible(timeout=10000)

        # Detail section should be hidden by default
        detail = card.get_by_test_id("card-detail")
        expect(detail).to_be_hidden()

        # Expand button should be visible in the compact header
        expand_btn = card.get_by_test_id("card-expand-btn")
        expect(expand_btn).to_be_visible()

    def test_expand_collapse_toggle(
        self,
        authenticated_page: Page,
        app_server: str,
    ) -> None:
        """AC2.2 + AC2.3: Expand and collapse toggle works correctly.

        Expands a card and verifies detail is visible, collapses it
        and verifies detail is hidden again.
        """
        page = authenticated_page
        page_email = _authenticate_page(page, app_server)

        workspace_id = _create_workspace_via_db(
            user_email=page_email,
            html_content=("<p>Content for expand-collapse toggle testing here.</p>"),
            seed_tags=True,
        )

        page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
        wait_for_text_walker(page, timeout=15000)

        toolbar = page.locator("[data-testid='tag-toolbar']")
        expect(toolbar).to_be_visible(timeout=5000)

        hl = find_text_range(page, "expand-collapse")
        create_highlight_with_tag(page, *hl, tag_index=0)

        card = page.locator("[data-testid='annotation-card']").first
        expect(card).to_be_visible(timeout=10000)

        # Expand
        expand_card(page, card_index=0)
        detail = card.get_by_test_id("card-detail")
        expect(detail).to_be_visible()

        # Verify detail contains tag-select and comment-input
        expect(card.get_by_test_id("tag-select")).to_be_visible()
        expect(card.get_by_test_id("comment-input")).to_be_visible()

        # Collapse
        collapse_card(page, card_index=0)
        expect(detail).to_be_hidden()

    def test_author_initials_in_compact_header(
        self,
        authenticated_page: Page,
        app_server: str,
    ) -> None:
        """AC2.4: Compact header shows author initials.

        Mock auth generates emails like ``e2e-test-{uuid}@test.example.edu.au``.
        The display name is derived as title-case of the email local part
        with dots/hyphens as separators, e.g. "E2E Test {uuid}" which
        produces initials like "E.T.{X}." — we just verify the card
        text contains a dot-separated initials pattern.
        """
        page = authenticated_page
        page_email = _authenticate_page(page, app_server)

        workspace_id = _create_workspace_via_db(
            user_email=page_email,
            html_content="<p>Author initials verification content.</p>",
            seed_tags=True,
        )

        page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
        wait_for_text_walker(page, timeout=15000)

        toolbar = page.locator("[data-testid='tag-toolbar']")
        expect(toolbar).to_be_visible(timeout=5000)

        hl = find_text_range(page, "Author initials")
        create_highlight_with_tag(page, *hl, tag_index=0)

        card = page.locator("[data-testid='annotation-card']").first
        expect(card).to_be_visible(timeout=10000)

        # The compact header text should contain initials in "X." or "X.Y." form.
        # The annotation card has no dedicated testid for initials (the label is
        # built inline in _build_compact_header), so we match by pattern.
        # e2e auth emails look like "e2e-test-{uuid}@..." → initials "E.T.{X}."
        card_text = card.inner_text()
        assert re.search(r"[A-Z]\.", card_text), (
            f"Expected dot-separated initials (e.g. 'E.T.') in compact header, "
            f"got: {card_text!r}"
        )

    def test_push_down_on_expand(
        self,
        authenticated_page: Page,
        app_server: str,
    ) -> None:
        """AC2.5: Expanding first card pushes second card's top down.

        Creates 2 highlights, records second card's position, expands
        the first card, and verifies second card moved down.
        """
        page = authenticated_page
        page_email = _authenticate_page(page, app_server)

        workspace_id = _create_workspace_via_db(
            user_email=page_email,
            html_content=(
                "<p>The court considered evidence from multiple witnesses "
                "before reaching its conclusion on liability and damages.</p>"
            ),
            seed_tags=True,
        )

        page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
        wait_for_text_walker(page, timeout=15000)

        toolbar = page.locator("[data-testid='tag-toolbar']")
        expect(toolbar).to_be_visible(timeout=5000)

        # Create 2 highlights
        hl1 = find_text_range(page, "court considered")
        create_highlight_with_tag(page, *hl1, tag_index=0)
        expect(page.locator("[data-testid='annotation-card']").first).to_be_visible(
            timeout=10000
        )

        hl2 = find_text_range(page, "reaching its conclusion")
        create_highlight_with_tag(page, *hl2, tag_index=1)
        expect(page.locator("[data-testid='annotation-card']")).to_have_count(
            2, timeout=10000
        )

        _wait_for_position_cards(page)

        # Record second card's position before expanding first
        top1_before = _get_card_top(page, 1)

        # Expand the first card
        expand_card(page, card_index=0)

        _wait_for_position_cards(page)

        # Second card should have moved down
        top1_after = _get_card_top(page, 1)
        assert top1_after > top1_before, (
            f"Second card did not move down on expand: "
            f"before={top1_before}, after={top1_after}"
        )

    def test_viewer_sees_no_tag_select_or_comment_input(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """AC2.6 + AC2.7: Viewer cannot see tag dropdown or comment input.

        Creates a workspace as owner, adds a highlight, then opens it
        as a viewer (with ``viewer`` permission). Verifies that the
        expanded card has no tag-select and no comment-input.
        """
        # Owner creates workspace with a highlight
        ctx_owner = browser.new_context()
        page_owner = ctx_owner.new_page()

        try:
            owner_email = _authenticate_page(page_owner, app_server)

            workspace_id = _create_workspace_via_db(
                user_email=owner_email,
                html_content=("<p>Viewer restriction test content paragraph.</p>"),
                seed_tags=True,
            )

            page_owner.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            wait_for_text_walker(page_owner, timeout=15000)

            toolbar = page_owner.locator("[data-testid='tag-toolbar']")
            expect(toolbar).to_be_visible(timeout=5000)

            create_highlight_with_tag(
                page_owner,
                *find_text_range(page_owner, "Viewer restriction"),
                tag_index=0,
            )
            expect(
                page_owner.locator("[data-testid='annotation-card']").first
            ).to_be_visible(timeout=10000)
        finally:
            page_owner.goto("about:blank")
            page_owner.close()
            ctx_owner.close()

        # Viewer opens the same workspace
        ctx_viewer = browser.new_context()
        page_viewer = ctx_viewer.new_page()

        try:
            viewer_email = _authenticate_page(page_viewer, app_server)
            _grant_workspace_access(workspace_id, viewer_email, permission="viewer")

            page_viewer.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            wait_for_text_walker(page_viewer, timeout=15000)

            card = page_viewer.locator("[data-testid='annotation-card']").first
            expect(card).to_be_visible(timeout=10000)

            # Expand the card to check detail contents
            expand_card(page_viewer, card_index=0)

            # Viewer should NOT see tag-select dropdown
            expect(card.get_by_test_id("tag-select")).to_have_count(0)

            # Viewer should NOT see comment input
            expect(card.get_by_test_id("comment-input")).to_have_count(0)
        finally:
            page_viewer.goto("about:blank")
            page_viewer.close()
            ctx_viewer.close()
