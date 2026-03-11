"""E2E tests for drag-and-drop in the Organise tab.

Tests verify that highlight cards can be dragged within columns (reorder)
and between columns (tag reassignment), that changes persist in the CRDT,
and that broadcasts propagate to other connected clients.

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui-98/phase_04.md Task 3
- AC: three-tab-ui.AC2.3, AC2.4, AC2.5
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from promptgrimoire.config import get_settings
from tests.e2e.annotation_helpers import (
    _create_workspace_via_db,
    create_highlight,
    create_highlight_with_tag,
    find_text_range,
    wait_for_text_walker,
)
from tests.e2e.conftest import _authenticate_page

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Browser, Locator, Page


_DRAG_CONTENT_HTML = (
    "<p>Alpha Bravo Charlie Delta Echo Foxtrot Golf Hotel India Juliet</p>"
)


# Skip if no database configured
pytestmark_db = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


def _switch_to_organise(page: Page) -> None:
    """Click the Organise tab and wait for columns to render."""
    page.get_by_test_id("tab-organise").click()
    expect(page.locator('[data-testid="organise-columns"]')).to_be_visible(timeout=5000)


def _switch_to_annotate(page: Page) -> None:
    """Click the Annotate tab and wait for it to be active."""
    page.get_by_test_id("tab-annotate").click()
    expect(page.locator("#doc-container")).to_be_visible(timeout=5000)


def _get_card_ids_in_column(page: Page, tag_name: str) -> list[str]:
    """Return ordered list of highlight IDs in a tag column."""
    column = page.locator(f'[data-testid="tag-column"][data-tag-name="{tag_name}"]')
    cards = column.locator('[data-testid="organise-card"]')
    count = cards.count()
    ids = []
    for i in range(count):
        hid = cards.nth(i).get_attribute("data-highlight-id")
        if hid:
            ids.append(hid)
    return ids


def _get_sortable_for_tag(page: Page, tag_name: str) -> Locator:
    """Find the SortableJS container inside a tag column by display name.

    Sortable IDs use tag UUIDs (``sort-{uuid}``), not snake_case names,
    so we locate via the column's ``data-tag-name`` attribute then find
    the ``[id^="sort-"]`` child.
    """
    column = page.locator(f'[data-testid="tag-column"][data-tag-name="{tag_name}"]')
    return column.locator('[id^="sort-"]')


@pytest.fixture
def drag_workspace_page(browser: Browser, app_server: str) -> Generator[Page]:
    """Workspace page with content and tags pre-seeded via DB.

    Creates everything via direct DB operations (no UI clicks for workspace
    creation), then navigates directly to the workspace.  This eliminates
    flakiness from the multi-step UI creation flow.

    Provides a long text string so multiple non-overlapping highlights
    can be created at different character ranges.
    """
    context = browser.new_context()
    page = context.new_page()
    email = _authenticate_page(page, app_server)

    workspace_id = _create_workspace_via_db(
        user_email=email,
        html_content=_DRAG_CONTENT_HTML,
    )

    page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
    wait_for_text_walker(page, timeout=15000)

    yield page

    with contextlib.suppress(Exception):
        page.goto("about:blank")
    page.close()
    context.close()


class TestDragCards:
    """Verify that Organise tab cards have drag affordance.

    Verifies: three-tab-ui.AC2.3 (partially -- drag mechanics)
    """

    @pytestmark_db
    def test_cards_are_draggable(self, drag_workspace_page: Page) -> None:
        """Cards in Organise tab are inside a SortableJS container with grab cursor."""
        page = drag_workspace_page

        # Create a highlight (tag index 0 = Jurisdiction)
        create_highlight(page, *find_text_range(page, "Alpha"))

        _switch_to_organise(page)

        # Wait for the true boundary: the card appears in the Organise tab
        card = page.locator('[data-testid="organise-card"]').first
        expect(card).to_be_visible(timeout=5000)

        # Verify card is inside a SortableJS container (has sort- prefixed id)
        sortable_container = page.locator('[id^="sort-"]').first
        expect(sortable_container).to_be_visible(timeout=3000)
        inner_card = sortable_container.locator('[data-testid="organise-card"]').first
        expect(inner_card).to_be_visible()

        # Verify grab cursor class is applied
        expect(card).to_have_css("cursor", "grab")


class TestDragReorderWithinColumn:
    """Verify reordering cards within a column via drag.

    Verifies: three-tab-ui.AC2.3
    """

    @pytestmark_db
    def test_drag_reorder_within_column(self, drag_workspace_page: Page) -> None:
        """Drag second card above first within same column, verify new order persists.

        Creates two highlights with the same tag (Jurisdiction), switches to
        Organise tab, drags the second card onto the first, then verifies the
        reorder persisted by switching tabs and back.
        """
        page = drag_workspace_page

        # Create two highlights with same tag (Jurisdiction = index 0)
        create_highlight_with_tag(page, *find_text_range(page, "Alpha"), tag_index=0)
        expect(page.locator("[data-testid='annotation-card']")).to_have_count(
            1, timeout=5000
        )

        create_highlight_with_tag(page, *find_text_range(page, "Bravo"), tag_index=0)
        expect(page.locator("[data-testid='annotation-card']")).to_have_count(
            2, timeout=5000
        )

        _switch_to_organise(page)

        # Get initial card order
        initial_ids = _get_card_ids_in_column(page, "Jurisdiction")
        assert len(initial_ids) == 2, (
            f"Expected 2 cards in Jurisdiction, got {len(initial_ids)}"
        )

        # Drag second card onto first card
        jurisdiction_col = page.locator(
            '[data-testid="tag-column"][data-tag-name="Jurisdiction"]'
        )
        cards = jurisdiction_col.locator('[data-testid="organise-card"]')
        source = cards.nth(1)
        target = cards.nth(0)

        source.drag_to(target)

        # Wait for optimistic UI update
        expect(cards.nth(0)).to_have_attribute(
            "data-highlight-id", initial_ids[1], timeout=5000
        )

        # Switch to Annotate and back to force re-render from CRDT
        _switch_to_annotate(page)
        _switch_to_organise(page)

        # Verify the order changed (second card should now be moved)
        # This expect polling checks the true boundary: the server re-rendered the order
        expect(cards.nth(0)).to_have_attribute(
            "data-highlight-id", initial_ids[1], timeout=10000
        )
        expect(cards.nth(1)).to_have_attribute(
            "data-highlight-id", initial_ids[0], timeout=10000
        )


class TestDragBetweenColumns:
    """Verify moving cards between tag columns via drag.

    Verifies: three-tab-ui.AC2.4
    """

    @pytestmark_db
    def test_drag_between_columns_changes_tag(self, drag_workspace_page: Page) -> None:
        """Drag card from Jurisdiction to Procedural History column.

        Creates a highlight with Jurisdiction tag, switches to Organise tab,
        drags the card to the Procedural History column, and verifies:
        - Card appears in Procedural History column
        - Card no longer appears in Jurisdiction column
        """
        page = drag_workspace_page

        # Create highlight with Jurisdiction tag (index 0)
        create_highlight_with_tag(page, *find_text_range(page, "Alpha"), tag_index=0)
        expect(page.locator("[data-testid='annotation-card']")).to_have_count(
            1, timeout=5000
        )

        _switch_to_organise(page)

        # Verify card is in Jurisdiction column
        jurisdiction_col = page.locator(
            '[data-testid="tag-column"][data-tag-name="Jurisdiction"]'
        )
        source_card = jurisdiction_col.locator('[data-testid="organise-card"]').first
        expect(source_card).to_be_visible(timeout=3000)

        highlight_id = source_card.get_attribute("data-highlight-id")

        # Find the Procedural History Sortable container as drop target
        proc_history_sortable = _get_sortable_for_tag(page, "Procedural History")
        expect(proc_history_sortable).to_be_visible(timeout=3000)

        # Drag the card to the Procedural History sortable container
        source_card.drag_to(proc_history_sortable)

        # Wait for optimistic UI update
        proc_history_col = page.locator(
            '[data-testid="tag-column"][data-tag-name="Procedural History"]'
        )
        expect(
            proc_history_col.locator(f'[data-highlight-id="{highlight_id}"]')
        ).to_be_visible(timeout=5000)

        # Switch tabs and back to verify persistence (CRDT boundary)
        _switch_to_annotate(page)
        _switch_to_organise(page)

        # Wait for the true boundary: the server re-renders the card in the new column
        proc_history_col = page.locator(
            '[data-testid="tag-column"][data-tag-name="Procedural History"]'
        )
        expect(
            proc_history_col.locator(f'[data-highlight-id="{highlight_id}"]')
        ).to_be_visible(timeout=10000)

        # Verify card no longer in Jurisdiction
        expect(
            jurisdiction_col.locator(f'[data-highlight-id="{highlight_id}"]')
        ).to_be_hidden(timeout=5000)

    @pytestmark_db
    def test_drag_between_columns_updates_tab1_sidebar(
        self, drag_workspace_page: Page
    ) -> None:
        """Drag card to adjacent tag column, verify Tab 1 sidebar shows new tag.

        Uses Procedural History (adjacent to Jurisdiction) to avoid
        horizontal-scroll issues that break Playwright drag_to with
        distant SortableJS containers.

        Verifies: three-tab-ui.AC2.4 (Tab 1 reactivity)
        """
        page = drag_workspace_page

        # Create highlight with Jurisdiction tag (index 0)
        create_highlight_with_tag(page, *find_text_range(page, "Alpha"), tag_index=0)
        expect(page.locator("[data-testid='annotation-card']")).to_have_count(
            1, timeout=5000
        )

        _switch_to_organise(page)

        # Drag card to Procedural History column (adjacent, avoids
        # horizontal-scroll issues with distant columns like Legal Issues)
        jurisdiction_col = page.locator(
            '[data-testid="tag-column"][data-tag-name="Jurisdiction"]'
        )
        source_card = jurisdiction_col.locator('[data-testid="organise-card"]').first
        expect(source_card).to_be_visible(timeout=3000)
        highlight_id = source_card.get_attribute("data-highlight-id")

        proc_history_sortable = _get_sortable_for_tag(page, "Procedural History")
        expect(proc_history_sortable).to_be_visible(timeout=3000)

        source_card.drag_to(proc_history_sortable)

        # Verify the drag actually moved the card via optimistic update
        proc_history_col = page.locator(
            '[data-testid="tag-column"][data-tag-name="Procedural History"]'
        )
        expect(
            proc_history_col.locator(f'[data-highlight-id="{highlight_id}"]')
        ).to_be_visible(timeout=5000)

        # Switch to Annotate tab
        _switch_to_annotate(page)

        from tests.e2e.card_helpers import expand_card

        # Find the annotation card in the sidebar
        # The true boundary is the sidebar card showing the new tag (Procedural History)
        sidebar_card = page.locator(".ann-card-positioned").first
        expect(sidebar_card).to_be_visible(timeout=3000)

        # Expand the card first, as they are collapsed by default
        expand_card(page, 0)

        # Wait for the CRDT update to reflect in the Annotate tab's dropdown
        tag_select = sidebar_card.get_by_test_id("tag-select")
        expect(tag_select).to_be_visible(timeout=5000)
        expect(tag_select).to_contain_text("Procedural History", timeout=10000)


class TestConcurrentDrag:
    """Verify concurrent drag operations produce consistent results.

    Verifies: three-tab-ui.AC2.5
    """

    @pytestmark_db
    def test_concurrent_drag_produces_consistent_result(  # noqa: PLR0915
        self, two_annotation_contexts: tuple[Page, Page, str]
    ) -> None:
        """Two clients drag different cards simultaneously, both persist.

        Context 1 drags highlight X from Jurisdiction to Legal Issues.
        Context 2 drags highlight Y from Jurisdiction to Procedural History.
        Both operations should complete and both contexts should show
        consistent final state.
        """
        page1, page2, _workspace_id = two_annotation_contexts

        # Create two highlights on page1 (both Jurisdiction = index 0)
        create_highlight_with_tag(page1, *find_text_range(page1, "Sync"), tag_index=0)
        expect(page1.locator("[data-testid='annotation-card']")).to_have_count(
            1, timeout=5000
        )

        create_highlight_with_tag(page1, *find_text_range(page1, "test"), tag_index=0)
        expect(page1.locator("[data-testid='annotation-card']")).to_have_count(
            2, timeout=5000
        )

        # Wait for page2 to sync (broadcast boundary: cards appear on second client)
        expect(page2.locator("[data-testid='annotation-card']")).to_have_count(
            2, timeout=10000
        )

        # Both switch to Organise tab
        _switch_to_organise(page1)
        _switch_to_organise(page2)

        # Get initial cards in Jurisdiction on page1
        jurisdiction_col_p1 = page1.locator(
            '[data-testid="tag-column"][data-tag-name="Jurisdiction"]'
        )
        # Ensure they are rendered in the column
        expect(
            jurisdiction_col_p1.locator('[data-testid="organise-card"]')
        ).to_have_count(2, timeout=5000)

        initial_ids = _get_card_ids_in_column(page1, "Jurisdiction")
        assert len(initial_ids) == 2, (
            f"Expected 2 cards in Jurisdiction, got {len(initial_ids)}"
        )
        card_x_id = initial_ids[0]
        card_y_id = initial_ids[1]

        # Page1: drag first card to Decision
        card_x = jurisdiction_col_p1.locator(f'[data-highlight-id="{card_x_id}"]')
        decision_sortable_p1 = _get_sortable_for_tag(page1, "Decision")
        card_x.drag_to(decision_sortable_p1)

        # Wait for optimistic update on Page 1
        decision_col_p1 = page1.locator(
            '[data-testid="tag-column"][data-tag-name="Decision"]'
        )
        expect(
            decision_col_p1.locator(f'[data-highlight-id="{card_x_id}"]')
        ).to_be_visible(timeout=5000)

        # Wait for broadcast to Page 2
        # The Organise tab doesn't auto-refresh for remote drags, so we must
        # switch tabs to trigger a re-render from the CRDT state.
        import time

        start_time = time.time()
        while True:
            _switch_to_annotate(page2)
            _switch_to_organise(page2)
            col = page2.locator('[data-testid="tag-column"][data-tag-name="Decision"]')
            if col.locator(f'[data-highlight-id="{card_x_id}"]').is_visible():
                break
            if time.time() - start_time > 10:
                raise TimeoutError("Broadcast not received on Page 2")
            page2.wait_for_timeout(500)

        # Page2: drag (remaining) card to Procedural History
        jurisdiction_col_p2 = page2.locator(
            '[data-testid="tag-column"][data-tag-name="Jurisdiction"]'
        )
        card_y = jurisdiction_col_p2.locator(f'[data-highlight-id="{card_y_id}"]')
        proc_history_sortable_p2 = _get_sortable_for_tag(page2, "Procedural History")
        card_y.drag_to(proc_history_sortable_p2)

        # Wait for optimistic update on Page 2
        proc_history_col_p2 = page2.locator(
            '[data-testid="tag-column"][data-tag-name="Procedural History"]'
        )
        expect(
            proc_history_col_p2.locator(f'[data-highlight-id="{card_y_id}"]')
        ).to_be_visible(timeout=5000)

        # Wait for broadcast back to Page 1
        start_time = time.time()
        while True:
            _switch_to_annotate(page1)
            _switch_to_organise(page1)
            col = page1.locator(
                '[data-testid="tag-column"][data-tag-name="Procedural History"]'
            )
            if col.locator(f'[data-highlight-id="{card_y_id}"]').is_visible():
                break
            if time.time() - start_time > 10:
                raise TimeoutError("Broadcast not received on Page 1")
            page1.wait_for_timeout(500)

        # Verify both pages show consistent state
        p1_jurisdiction = _get_card_ids_in_column(page1, "Jurisdiction")
        p2_jurisdiction = _get_card_ids_in_column(page2, "Jurisdiction")
        p1_decision = _get_card_ids_in_column(page1, "Decision")
        p2_decision = _get_card_ids_in_column(page2, "Decision")

        # Both pages should agree on what's in Jurisdiction and Decision
        assert set(p1_jurisdiction) == set(p2_jurisdiction), (
            f"Jurisdiction mismatch: p1={p1_jurisdiction}, p2={p2_jurisdiction}"
        )
        assert set(p1_decision) == set(p2_decision), (
            f"Decision mismatch: p1={p1_decision}, p2={p2_decision}"
        )

        # Both cards should have moved out of Jurisdiction
        assert len(p1_jurisdiction) == 0, (
            "All cards should have moved out of Jurisdiction"
        )
