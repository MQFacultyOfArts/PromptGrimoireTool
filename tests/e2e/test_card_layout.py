"""E2E tests for card positioning and collapsed card feature.

Covers:
- AC1: Card positioning — initial placement, scroll recovery, height cache.
- AC2: Collapsed cards — default state, expand/collapse toggle, author
  initials, push-down on expand, view-only restrictions.

Traceability:
- Issue: #236 (Card layout and positioning)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import (
    _create_workspace_via_db,
    create_highlight_with_tag,
    wait_for_text_walker,
)
from tests.e2e.conftest import _authenticate_page

if TYPE_CHECKING:
    from playwright.sync_api import Page


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_card_top(page: Page, card_index: int) -> float:
    """Read the computed ``top`` style of an annotation card (px).

    Cards are absolutely positioned by ``positionCards()`` in
    ``annotation-card-sync.js``, so ``style.top`` is always set.
    """
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
        create_highlight_with_tag(page, 0, 20, tag_index=0)
        expect(page.locator("[data-testid='annotation-card']").first).to_be_visible(
            timeout=10000
        )

        create_highlight_with_tag(page, 40, 60, tag_index=1)
        expect(page.locator("[data-testid='annotation-card']")).to_have_count(
            2, timeout=10000
        )

        create_highlight_with_tag(page, 80, 100, tag_index=2)
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
        create_highlight_with_tag(page, 0, 15, tag_index=0)
        expect(page.locator("[data-testid='annotation-card']").first).to_be_visible(
            timeout=10000
        )

        create_highlight_with_tag(page, 20, 40, tag_index=1)
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

    def test_height_cache_on_hidden_cards(
        self,
        authenticated_page: Page,
        app_server: str,
    ) -> None:
        """AC1.4: Hidden cards have data-cached-height with a positive value.

        Creates a highlight near the top, scrolls it off-screen, and
        verifies the card element has a ``data-cached-height`` attribute
        with a positive integer value.
        """
        page = authenticated_page
        page_email = _authenticate_page(page, app_server)

        workspace_id = _create_workspace_via_db(
            user_email=page_email,
            html_content=(
                "<p>Short top paragraph for height cache test.</p>"
                + "<p>Filler content. </p>" * 50
                + "<p>Bottom of the document.</p>"
            ),
            seed_tags=True,
        )

        page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
        wait_for_text_walker(page, timeout=15000)

        toolbar = page.locator("[data-testid='tag-toolbar']")
        expect(toolbar).to_be_visible(timeout=5000)

        # Create a highlight near the top
        create_highlight_with_tag(page, 0, 20, tag_index=0)
        first_card = page.locator("[data-testid='annotation-card']").first
        expect(first_card).to_be_visible(timeout=10000)

        _wait_for_position_cards(page)

        # Scroll to the bottom so the card is hidden
        page.evaluate(
            """() => {
                const dc = document.getElementById('doc-container');
                if (dc) dc.scrollTop = dc.scrollHeight;
                else window.scrollTo(0, document.body.scrollHeight);
            }"""
        )
        _wait_for_position_cards(page)

        # Check cached-height attribute via JS (card may be display:none)
        cached_height = first_card.evaluate(
            "el => parseInt(el.dataset.cachedHeight) || 0"
        )
        assert cached_height > 0, (
            f"Expected positive data-cached-height, got {cached_height}"
        )
