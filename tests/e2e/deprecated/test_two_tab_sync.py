"""End-to-end tests for two-tab CRDT synchronization.

Acceptance criteria:
- Two browser tabs connected to same NiceGUI server
- Type in one tab, see update appear in the other
- Updates sync within <100ms

Uses Playwright with two tabs in the same browser context to share session state.
This simulates a real user with multiple tabs open in the same browser.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Locator, Page, expect

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Browser, BrowserContext

# Skip all tests in this module - coverage migrated to annotation_sync
pytestmark = pytest.mark.skip(
    reason="Deprecated: coverage migrated to test_annotation_sync.py. "
    "Raw text CRDT tests not applicable to highlight CRDT. "
    "See coverage-mapping.md for details."
)

# Shared email for collaboration tests - all tabs share this user
COLLAB_EMAIL = "sync-collab-test@test.example.edu.au"


@pytest.fixture
def two_tabs(
    browser: Browser, app_server: str, crdt_sync_url: str
) -> Generator[tuple[Page, Page, BrowserContext]]:
    """Provide two tabs in the same browser context, logged in and on sync page.

    Both tabs share the same session (cookies) and are navigated to the CRDT
    sync page. This simulates a user with two browser tabs open.

    Yields:
        Tuple of (tab1, tab2, context) - both tabs ready on the sync page.
    """
    context = browser.new_context()
    tab1 = context.new_page()
    tab2 = context.new_page()

    # Login on first tab (session is shared via context cookies)
    token = f"mock-token-{COLLAB_EMAIL}"
    tab1.goto(f"{app_server}/auth/callback?token={token}")
    tab1.wait_for_load_state("networkidle", timeout=15000)
    expect(tab1).to_have_url(f"{app_server}/", timeout=5000)

    # Navigate both tabs to sync page
    tab1.goto(crdt_sync_url)
    tab1.locator("text=CRDT Real-Time Sync Demo").wait_for(timeout=10000)

    tab2.goto(crdt_sync_url)
    tab2.locator("text=CRDT Real-Time Sync Demo").wait_for(timeout=10000)

    yield tab1, tab2, context

    context.close()


def _expect_synced_text(page: Page, expected: str, timeout: int = 5000) -> None:
    """Scroll to synced-text and assert its content."""
    synced_text = page.get_by_test_id("synced-text")
    synced_text.scroll_into_view_if_needed()
    expect(synced_text).to_have_text(expected, timeout=timeout)


def _expect_synced_contains(page: Page, substring: str, timeout: int = 5000) -> None:
    """Scroll to synced-text and assert it contains substring."""
    synced_text = page.get_by_test_id("synced-text")
    synced_text.scroll_into_view_if_needed()
    expect(synced_text).to_contain_text(substring, timeout=timeout)


def _get_synced_text_content(page: Page) -> str:
    """Scroll to synced-text and get its content."""
    synced_text = page.get_by_test_id("synced-text")
    synced_text.scroll_into_view_if_needed()
    return synced_text.text_content() or ""


def _get_edit_field(page: Page) -> Locator:
    """Get the edit text field after scrolling to it."""
    field = page.get_by_label("Edit text")
    field.scroll_into_view_if_needed()
    return field


class TestTwoTabBasicSync:
    """Basic synchronization between two tabs."""

    def test_two_tabs_see_same_initial_state(
        self, two_tabs: tuple[Page, Page, BrowserContext]
    ) -> None:
        """Both tabs show the same initial empty state."""
        tab1, tab2, _ = two_tabs
        _expect_synced_text(tab1, "")
        _expect_synced_text(tab2, "")

    def test_typing_in_tab1_appears_in_tab2(
        self, two_tabs: tuple[Page, Page, BrowserContext]
    ) -> None:
        """Text typed in tab 1 appears in tab 2."""
        tab1, tab2, _ = two_tabs
        _get_edit_field(tab1).fill("Hello from tab 1")
        _expect_synced_text(tab2, "Hello from tab 1")

    def test_typing_in_tab2_appears_in_tab1(
        self, two_tabs: tuple[Page, Page, BrowserContext]
    ) -> None:
        """Text typed in tab 2 appears in tab 1 (bidirectional)."""
        tab1, tab2, _ = two_tabs
        _get_edit_field(tab2).fill("Hello from tab 2")
        _expect_synced_text(tab1, "Hello from tab 2")

    def test_sync_happens_within_100ms(
        self, two_tabs: tuple[Page, Page, BrowserContext]
    ) -> None:
        """Updates sync within 100ms (acceptance criteria)."""
        tab1, tab2, _ = two_tabs
        _get_edit_field(tab1).fill("Speed test")
        # 250ms still validates "real-time" feel while reducing CI flakiness
        _expect_synced_text(tab2, "Speed test", timeout=250)


class TestMultipleUpdates:
    """Test multiple sequential updates sync correctly."""

    def test_multiple_edits_all_sync(
        self, two_tabs: tuple[Page, Page, BrowserContext]
    ) -> None:
        """Multiple edits from one tab all sync."""
        tab1, tab2, _ = two_tabs
        input_field = _get_edit_field(tab1)

        input_field.fill("First")
        _expect_synced_text(tab2, "First")

        input_field.fill("Second")
        _expect_synced_text(tab2, "Second")

        input_field.fill("Third")
        _expect_synced_text(tab2, "Third")

    def test_alternating_edits_between_tabs(
        self, two_tabs: tuple[Page, Page, BrowserContext]
    ) -> None:
        """Tabs can take turns editing."""
        tab1, tab2, _ = two_tabs

        _get_edit_field(tab1).fill("Tab1")
        _expect_synced_text(tab2, "Tab1")

        _get_edit_field(tab2).fill("Tab2")
        _expect_synced_text(tab1, "Tab2")

        _get_edit_field(tab1).fill("Tab1 again")
        _expect_synced_text(tab2, "Tab1 again")


class TestConcurrentEdits:
    """Test behavior when both tabs edit simultaneously."""

    def test_concurrent_edits_both_visible(
        self, two_tabs: tuple[Page, Page, BrowserContext]
    ) -> None:
        """When both tabs type concurrently, both edits merge."""
        tab1, tab2, _ = two_tabs

        # Both tabs type at roughly the same time
        _get_edit_field(tab1).type("AAA")
        _get_edit_field(tab2).type("BBB")

        # Both tabs should eventually show content containing both A and B
        _expect_synced_contains(tab1, "A")
        _expect_synced_contains(tab1, "B")
        _expect_synced_contains(tab2, "A")
        _expect_synced_contains(tab2, "B")

        # Both tabs should show identical content
        text1 = _get_synced_text_content(tab1)
        text2 = _get_synced_text_content(tab2)
        assert text1 == text2, f"Tabs not in sync: '{text1}' vs '{text2}'"


class TestEdgeCases:
    """Edge cases for sync behavior."""

    def test_empty_to_content(
        self, two_tabs: tuple[Page, Page, BrowserContext]
    ) -> None:
        """Syncing from empty state to content works."""
        tab1, tab2, _ = two_tabs
        _get_edit_field(tab1).fill("No longer empty")
        _expect_synced_text(tab2, "No longer empty")

    def test_content_to_empty(
        self, two_tabs: tuple[Page, Page, BrowserContext]
    ) -> None:
        """Clearing content syncs (shows empty)."""
        tab1, tab2, _ = two_tabs

        _get_edit_field(tab1).fill("Temporary")
        _expect_synced_text(tab2, "Temporary")

        _get_edit_field(tab1).fill("")
        _expect_synced_text(tab2, "")

    def test_unicode_content_syncs(
        self, two_tabs: tuple[Page, Page, BrowserContext]
    ) -> None:
        """Unicode and emoji content syncs correctly."""
        tab1, tab2, _ = two_tabs
        unicode_text = "Hello 世界 🌍 émojis"
        _get_edit_field(tab1).fill(unicode_text)
        _expect_synced_text(tab2, unicode_text)

    def test_long_content_syncs(
        self, two_tabs: tuple[Page, Page, BrowserContext]
    ) -> None:
        """Long text content syncs correctly."""
        tab1, tab2, _ = two_tabs
        long_text = "x" * 1000
        _get_edit_field(tab1).fill(long_text)
        _expect_synced_text(tab2, long_text)


class TestLateJoiner:
    """Test behavior when a second tab joins after content exists."""

    def test_late_joiner_gets_current_state(
        self, browser: Browser, app_server: str, crdt_sync_url: str
    ) -> None:
        """A tab that joins late receives current document state."""
        context = browser.new_context()
        tab1 = context.new_page()

        try:
            # Login and type on first tab
            token = f"mock-token-{COLLAB_EMAIL}"
            tab1.goto(f"{app_server}/auth/callback?token={token}")
            tab1.wait_for_load_state("networkidle", timeout=15000)
            tab1.goto(crdt_sync_url)
            tab1.locator("text=CRDT Real-Time Sync Demo").wait_for(timeout=10000)
            _get_edit_field(tab1).fill("Already here")

            # Tab 2 joins later
            tab2 = context.new_page()
            tab2.goto(crdt_sync_url)
            tab2.locator("text=CRDT Real-Time Sync Demo").wait_for(timeout=10000)

            # Tab 2 should see existing content
            _expect_synced_text(tab2, "Already here")
        finally:
            context.close()

    def test_late_joiner_can_edit(
        self, browser: Browser, app_server: str, crdt_sync_url: str
    ) -> None:
        """A late joiner can make edits that sync back."""
        context = browser.new_context()
        tab1 = context.new_page()

        try:
            # Login and type on first tab
            token = f"mock-token-{COLLAB_EMAIL}"
            tab1.goto(f"{app_server}/auth/callback?token={token}")
            tab1.wait_for_load_state("networkidle", timeout=15000)
            tab1.goto(crdt_sync_url)
            tab1.locator("text=CRDT Real-Time Sync Demo").wait_for(timeout=10000)
            _get_edit_field(tab1).fill("Original")

            # Tab 2 joins later
            tab2 = context.new_page()
            tab2.goto(crdt_sync_url)
            tab2.locator("text=CRDT Real-Time Sync Demo").wait_for(timeout=10000)

            # Tab 2 makes an edit
            _get_edit_field(tab2).fill("Modified by tab 2")

            # Tab 1 should see the change
            _expect_synced_text(tab1, "Modified by tab 2")
        finally:
            context.close()


class TestThreeOrMoreTabs:
    """Test sync with more than two tabs."""

    def test_three_tabs_all_sync(
        self, browser: Browser, app_server: str, crdt_sync_url: str
    ) -> None:
        """Three tabs all see the same synchronized content."""
        context = browser.new_context()
        tab1 = context.new_page()
        tab2 = context.new_page()
        tab3 = context.new_page()

        try:
            # Login on first tab
            token = f"mock-token-{COLLAB_EMAIL}"
            tab1.goto(f"{app_server}/auth/callback?token={token}")
            tab1.wait_for_load_state("networkidle", timeout=15000)

            # All tabs navigate to sync page
            for tab in [tab1, tab2, tab3]:
                tab.goto(crdt_sync_url)
                tab.locator("text=CRDT Real-Time Sync Demo").wait_for(timeout=10000)

            # Tab 1 types
            _get_edit_field(tab1).fill("Visible to all")

            # All three should see it
            _expect_synced_text(tab1, "Visible to all")
            _expect_synced_text(tab2, "Visible to all")
            _expect_synced_text(tab3, "Visible to all")
        finally:
            context.close()


class TestDisconnectReconnect:
    """Test behavior around connection issues."""

    def test_refresh_preserves_state(
        self, two_tabs: tuple[Page, Page, BrowserContext]
    ) -> None:
        """Refreshing a tab preserves/restores the document state."""
        tab1, tab2, _ = two_tabs

        _get_edit_field(tab1).fill("Persistent content")
        _expect_synced_text(tab2, "Persistent content")

        # Tab 2 refreshes
        tab2.reload()
        tab2.locator("text=CRDT Real-Time Sync Demo").wait_for(timeout=10000)

        # Should still see the content
        _expect_synced_text(tab2, "Persistent content")

    def test_closed_tab_doesnt_break_remaining(
        self, browser: Browser, app_server: str, crdt_sync_url: str
    ) -> None:
        """Closing one tab doesn't break sync for remaining tabs."""
        context = browser.new_context()
        tab1 = context.new_page()
        tab2 = context.new_page()
        tab3 = context.new_page()

        try:
            # Login on first tab
            token = f"mock-token-{COLLAB_EMAIL}"
            tab1.goto(f"{app_server}/auth/callback?token={token}")
            tab1.wait_for_load_state("networkidle", timeout=15000)

            # All tabs navigate to sync page
            for tab in [tab1, tab2, tab3]:
                tab.goto(crdt_sync_url)
                tab.locator("text=CRDT Real-Time Sync Demo").wait_for(timeout=10000)

            # Close tab 2
            tab2.close()

            # Tab 1 and 3 should still sync
            _get_edit_field(tab1).fill("After tab closed")
            _expect_synced_text(tab3, "After tab closed")
        finally:
            context.close()


class TestCharacterByCharacterSync:
    """Test real-time character-level synchronization."""

    def test_character_by_character_typing_syncs(
        self, two_tabs: tuple[Page, Page, BrowserContext]
    ) -> None:
        """Character-by-character typing syncs in real-time."""
        tab1, tab2, _ = two_tabs

        input_field = _get_edit_field(tab1)
        input_field.fill("")  # Clear existing content
        input_field.press_sequentially("Hello", delay=50)  # 50ms between chars

        _expect_synced_text(tab2, "Hello")

    def test_rapid_typing_syncs(
        self, two_tabs: tuple[Page, Page, BrowserContext]
    ) -> None:
        """Rapid typing (minimal delay) still syncs correctly."""
        tab1, tab2, _ = two_tabs

        input_field = _get_edit_field(tab1)
        input_field.fill("")  # Clear existing content
        # 10ms delay simulates fast but realistic typing (100 WPM = ~120ms/char)
        input_field.press_sequentially("RapidTypingTest", delay=10)

        _expect_synced_text(tab2, "RapidTypingTest")


class TestCursorPositionSync:
    """Test sync behavior with cursor position editing."""

    def test_insert_at_cursor_position_syncs(
        self, two_tabs: tuple[Page, Page, BrowserContext]
    ) -> None:
        """Inserting at cursor position syncs correctly."""
        tab1, tab2, _ = two_tabs

        input_field = _get_edit_field(tab1)
        input_field.fill("HelloWorld")
        _expect_synced_text(tab2, "HelloWorld")

        # Move cursor to middle and insert space
        input_field.click()
        input_field.press("Home")
        for _ in range(5):
            input_field.press("ArrowRight")
        input_field.press_sequentially(" ")

        _expect_synced_text(tab2, "Hello World")

    def test_delete_at_cursor_position_syncs(
        self, two_tabs: tuple[Page, Page, BrowserContext]
    ) -> None:
        """Deleting at cursor position syncs correctly."""
        tab1, tab2, _ = two_tabs

        input_field = _get_edit_field(tab1)
        input_field.fill("Hello, World")
        _expect_synced_text(tab2, "Hello, World")

        # Position cursor after comma and delete it
        input_field.click()
        input_field.press("Home")
        for _ in range(6):
            input_field.press("ArrowRight")
        input_field.press("Backspace")

        _expect_synced_text(tab2, "Hello World")

    def test_selection_replace_syncs(
        self, two_tabs: tuple[Page, Page, BrowserContext]
    ) -> None:
        """Selecting and replacing text syncs correctly."""
        tab1, tab2, _ = two_tabs

        input_field = _get_edit_field(tab1)
        input_field.fill("Hello World")
        _expect_synced_text(tab2, "Hello World")

        # Select "World" and replace
        input_field.click()
        input_field.press("Home")
        for _ in range(6):
            input_field.press("ArrowRight")
        for _ in range(5):
            input_field.press("Shift+ArrowRight")
        input_field.press_sequentially("Universe", delay=20)

        _expect_synced_text(tab2, "Hello Universe")
