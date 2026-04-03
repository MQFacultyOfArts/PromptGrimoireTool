"""E2E spike: validate Vue component rendering in a real browser.

Exercises the Phase 3-4 go/no-go criteria that NiceGUI user_simulation
cannot test (no Vue runtime server-side):

1. Component renders in Chromium (Vue template produces real DOM nodes)
2. Props arrive in Vue (items rendered with correct data-* attributes)
3. Vue $emit reaches Python (click → test_event → Python handler → label update)
4. Prop updates re-render (set_items → DOM card count changes)
5. DOM exposes data-testid and data-* attributes

Uses the test page at /test/vue-sidebar-spike registered in
``_server_script.py``.  No authentication or database required.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import _authenticate_page

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Browser, Page


@pytest.fixture
def spike_page(browser: Browser, app_server: str) -> Generator[Page]:
    """Open the Vue sidebar spike test page with an authenticated session.

    NiceGUI requires a session cookie for the websocket connection that
    delivers element data to the browser.  Without authentication, the
    page loads but Vue never mounts (blank white page).
    """
    context = browser.new_context()
    page = context.new_page()
    _authenticate_page(page, app_server)
    page.goto(f"{app_server}/test/vue-sidebar-spike")
    # Wait for the sidebar component to render its cards
    page.wait_for_selector("[data-testid='annotation-card']", timeout=15000)
    yield page
    page.goto("about:blank")
    page.close()
    context.close()


def test_go1_component_renders(spike_page: Page) -> None:
    """GO1: Vue component renders in the browser — cards are real DOM nodes."""
    cards = spike_page.locator("[data-testid='annotation-card']")
    expect(cards).to_have_count(2)


def test_go2_props_arrive_in_vue(spike_page: Page) -> None:
    """GO2: Python props arrive in Vue — items rendered with correct attributes."""
    cards = spike_page.locator("[data-testid='annotation-card']")

    # Card 1: hl-1, start_char=10, end_char=50
    card1 = cards.nth(0)
    expect(card1).to_have_attribute("data-highlight-id", "hl-1")
    expect(card1).to_have_attribute("data-start-char", "10")
    expect(card1).to_have_attribute("data-end-char", "50")

    # Card 2: hl-2, start_char=60, end_char=90
    card2 = cards.nth(1)
    expect(card2).to_have_attribute("data-highlight-id", "hl-2")
    expect(card2).to_have_attribute("data-start-char", "60")
    expect(card2).to_have_attribute("data-end-char", "90")


def test_go2_compact_header_content(spike_page: Page) -> None:
    """GO2 extended: compact header shows tag, initials, para ref, comment badge."""
    card1 = spike_page.locator("[data-testid='annotation-card']").nth(0)

    # Tag display
    expect(card1).to_contain_text("Jurisdiction")
    # Initials (Alice → A.)
    expect(card1).to_contain_text("A.")
    # Para ref
    expect(card1).to_contain_text("[3]")
    # Comment count badge (1 comment)
    badge = card1.locator("[data-testid='comment-count-badge']")
    expect(badge).to_have_text("1")

    # Card 2 should NOT have a comment badge (0 comments)
    card2 = spike_page.locator("[data-testid='annotation-card']").nth(1)
    expect(card2.locator("[data-testid='comment-count-badge']")).to_have_count(0)


def test_go3_emit_reaches_python(spike_page: Page) -> None:
    """GO3: Vue $emit('toggle_expand') reaches Python handler via websocket."""
    # Label starts at "event:none"
    event_label = spike_page.get_by_test_id("spike-event-label")
    expect(event_label).to_have_text("event:none")

    # Click first card's header row — triggers toggle_expand event
    card1 = spike_page.locator("[data-testid='card-header']").nth(0)
    card1.click()

    # Python handler updates the label with the event payload.
    # Validates the full Vue $emit -> websocket -> Python handler path.
    expect(event_label).to_have_text("event:hl-1", timeout=5000)


def test_go4_prop_updates_rerender(spike_page: Page) -> None:
    """GO4: set_items() from Python re-renders Vue component (card count changes)."""
    # Initial: 2 cards
    cards = spike_page.locator("[data-testid='annotation-card']")
    expect(cards).to_have_count(2)

    # Click the update button (calls set_items with 1 item)
    spike_page.get_by_test_id("spike-update-btn").click()

    # Wait for re-render: should now have exactly 1 card
    expect(cards).to_have_count(1, timeout=5000)

    # Verify the new card has the updated highlight ID
    expect(cards.nth(0)).to_have_attribute("data-highlight-id", "hl-3")


def test_go5_dom_data_attributes(spike_page: Page) -> None:
    """GO5: DOM exposes data-testid and data-* attributes for E2E testing."""
    card = spike_page.locator("[data-testid='annotation-card']").nth(0)

    # All required data-* attributes are present
    expect(card).to_have_attribute("data-highlight-id", "hl-1")
    expect(card).to_have_attribute("data-start-char", "10")
    expect(card).to_have_attribute("data-end-char", "50")

    # Expand button placeholder exists
    expect(card.locator("[data-testid='expand-btn']")).to_have_count(1)

    # Delete button visible for can_delete=True card (u-1 owns hl-1)
    expect(card.locator("[data-testid='delete-highlight-btn']")).to_have_count(1)

    # Card 2: can_delete=False (u-3 owns hl-2, viewer is u-1)
    card2 = spike_page.locator("[data-testid='annotation-card']").nth(1)
    expect(card2.locator("[data-testid='delete-highlight-btn']")).to_have_count(0)
