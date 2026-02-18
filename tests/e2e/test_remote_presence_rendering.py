"""E2E tests for JS remote presence rendering functions.

Exercises the remote cursor and selection rendering functions in
annotation-highlight.js by calling them directly via page.evaluate()
and verifying the resulting DOM state and CSS.highlights entries.

Acceptance criteria verified:
- css-highlight-api.AC3.1: Remote cursor appears as coloured vertical line
  with name label at correct character position
- css-highlight-api.AC3.2: Remote selection appears as CSS Custom Highlight
  API entry distinct from annotation highlights

Traceability:
- Design: docs/implementation-plans/2026-02-11-css-highlight-api-150/phase_05.md
- Task 8: Unit tests for JS remote presence rendering
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.e2e.annotation_helpers import setup_workspace_with_content_highlight_api

if TYPE_CHECKING:
    from playwright.sync_api import Page


class TestRemoteCursorRendering:
    """Tests for renderRemoteCursor / removeRemoteCursor JS functions."""

    def test_render_cursor_creates_element(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """AC3.1: renderRemoteCursor creates a .remote-cursor div with name label."""
        page = authenticated_page
        content = "The plaintiff alleged that the defendant was negligent."
        setup_workspace_with_content_highlight_api(page, app_server, content)

        # Call renderRemoteCursor via JS
        page.evaluate(
            """() => {
                const container = document.getElementById('doc-container');
                renderRemoteCursor(container, 'test-user-1', 10, 'Alice', '#2196F3');
            }"""
        )

        # Verify cursor div exists
        cursor = page.locator("#remote-cursor-test-user-1")
        assert cursor.count() == 1, "Expected remote cursor element to exist"

        # Verify it has the remote-cursor class
        assert "remote-cursor" in (cursor.get_attribute("class") or "")

        # Verify it stores data attributes for repositioning
        assert cursor.get_attribute("data-char-idx") == "10"
        assert cursor.get_attribute("data-client-id") == "test-user-1"
        assert cursor.get_attribute("data-name") == "Alice"
        assert cursor.get_attribute("data-color") == "#2196F3"

        # Verify name label exists
        label = cursor.locator(".remote-cursor-label")
        assert label.count() == 1, "Expected name label inside cursor"
        assert label.text_content() == "Alice"

        # Verify cursor has non-zero dimensions (positioned correctly)
        box = cursor.bounding_box()
        assert box is not None, "Cursor should be visible with a bounding box"
        assert box["height"] > 0, "Cursor should have positive height"

    def test_render_cursor_updates_existing(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """renderRemoteCursor replaces existing cursor for same clientId."""
        page = authenticated_page
        content = "The plaintiff alleged that the defendant was negligent."
        setup_workspace_with_content_highlight_api(page, app_server, content)

        # Render cursor at position 5
        page.evaluate(
            """() => {
                const container = document.getElementById('doc-container');
                renderRemoteCursor(container, 'test-user-1', 5, 'Alice', '#2196F3');
            }"""
        )
        assert page.locator("#remote-cursor-test-user-1").count() == 1

        # Render same user at position 20 -- should replace, not duplicate
        page.evaluate(
            """() => {
                const container = document.getElementById('doc-container');
                renderRemoteCursor(container, 'test-user-1', 20, 'Alice', '#2196F3');
            }"""
        )

        # Still exactly one cursor for this user
        assert page.locator("#remote-cursor-test-user-1").count() == 1

        # Data attribute should reflect new position
        cursor = page.locator("#remote-cursor-test-user-1")
        assert cursor.get_attribute("data-char-idx") == "20"

    def test_remove_cursor(self, authenticated_page: Page, app_server: str) -> None:
        """removeRemoteCursor removes the cursor element from DOM."""
        page = authenticated_page
        content = "The plaintiff alleged that the defendant was negligent."
        setup_workspace_with_content_highlight_api(page, app_server, content)

        # Render then remove
        page.evaluate(
            """() => {
                const container = document.getElementById('doc-container');
                renderRemoteCursor(container, 'test-user-1', 10, 'Alice', '#2196F3');
            }"""
        )
        assert page.locator("#remote-cursor-test-user-1").count() == 1

        page.evaluate("() => removeRemoteCursor('test-user-1')")
        assert page.locator("#remote-cursor-test-user-1").count() == 0

    def test_remove_nonexistent_cursor_is_safe(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """removeRemoteCursor for non-existent clientId does not throw."""
        page = authenticated_page
        content = "Test content for safe removal."
        setup_workspace_with_content_highlight_api(page, app_server, content)

        # Should not throw
        page.evaluate("() => removeRemoteCursor('nonexistent-user')")


class TestRemoteSelectionRendering:
    """Tests for renderRemoteSelection / removeRemoteSelection JS functions."""

    def test_render_selection_creates_highlight(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """AC3.2: renderRemoteSelection registers a CSS.highlights entry."""
        page = authenticated_page
        content = "The plaintiff alleged that the defendant was negligent."
        setup_workspace_with_content_highlight_api(page, app_server, content)

        page.evaluate(
            """() => {
                renderRemoteSelection('test-user-1', 5, 20, 'Alice', '#2196F3');
            }"""
        )

        # Verify CSS.highlights entry exists
        has_highlight = page.evaluate("() => CSS.highlights.has('hl-sel-test-user-1')")
        assert has_highlight, "Expected hl-sel-test-user-1 in CSS.highlights"

        # Verify priority is -1 (below annotation highlights)
        priority = page.evaluate(
            "() => CSS.highlights.get('hl-sel-test-user-1').priority"
        )
        assert priority == -1, f"Expected priority -1, got {priority}"

        # Verify style element exists
        style = page.locator("#remote-sel-style-test-user-1")
        assert style.count() == 1, "Expected companion style element"

    def test_remove_selection(self, authenticated_page: Page, app_server: str) -> None:
        """removeRemoteSelection removes CSS.highlights entry and style element."""
        page = authenticated_page
        content = "The plaintiff alleged that the defendant was negligent."
        setup_workspace_with_content_highlight_api(page, app_server, content)

        # Render then remove
        page.evaluate(
            """() => {
                renderRemoteSelection('test-user-1', 5, 20, 'Alice', '#2196F3');
            }"""
        )
        assert page.evaluate("() => CSS.highlights.has('hl-sel-test-user-1')")

        page.evaluate("() => removeRemoteSelection('test-user-1')")

        has_highlight = page.evaluate("() => CSS.highlights.has('hl-sel-test-user-1')")
        assert not has_highlight, "Expected hl-sel-test-user-1 to be removed"

        style = page.locator("#remote-sel-style-test-user-1")
        assert style.count() == 0, "Expected style element to be removed"

    def test_render_selection_replaces_existing(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """renderRemoteSelection replaces existing selection for same clientId."""
        page = authenticated_page
        content = "The plaintiff alleged that the defendant was negligent."
        setup_workspace_with_content_highlight_api(page, app_server, content)

        # First selection
        page.evaluate(
            """() => {
                renderRemoteSelection('test-user-1', 0, 10, 'Alice', '#2196F3');
            }"""
        )

        # Second selection for same user -- should replace
        page.evaluate(
            """() => {
                renderRemoteSelection('test-user-1', 15, 30, 'Alice', '#2196F3');
            }"""
        )

        # Still exactly one entry in CSS.highlights for this user
        has_highlight = page.evaluate("() => CSS.highlights.has('hl-sel-test-user-1')")
        assert has_highlight

        # Still exactly one style element
        style = page.locator("#remote-sel-style-test-user-1")
        assert style.count() == 1


class TestMultipleUsers:
    """Tests for independent presence indicators for multiple users."""

    def test_multiple_cursors_independent(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Cursors for two different clientIds exist independently."""
        page = authenticated_page
        content = "The plaintiff alleged that the defendant was negligent."
        setup_workspace_with_content_highlight_api(page, app_server, content)

        page.evaluate(
            """() => {
                const container = document.getElementById('doc-container');
                renderRemoteCursor(container, 'user-alice', 5, 'Alice', '#2196F3');
                renderRemoteCursor(container, 'user-bob', 20, 'Bob', '#FF5722');
            }"""
        )

        alice_cursor = page.locator("#remote-cursor-user-alice")
        bob_cursor = page.locator("#remote-cursor-user-bob")
        assert alice_cursor.count() == 1
        assert bob_cursor.count() == 1

        # Labels are correct
        assert alice_cursor.locator(".remote-cursor-label").text_content() == "Alice"
        assert bob_cursor.locator(".remote-cursor-label").text_content() == "Bob"

        # Removing one does not affect the other
        page.evaluate("() => removeRemoteCursor('user-alice')")
        assert page.locator("#remote-cursor-user-alice").count() == 0
        assert page.locator("#remote-cursor-user-bob").count() == 1

    def test_multiple_selections_independent(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Selections for two different clientIds exist independently."""
        page = authenticated_page
        content = "The plaintiff alleged that the defendant was negligent."
        setup_workspace_with_content_highlight_api(page, app_server, content)

        page.evaluate(
            """() => {
                renderRemoteSelection('user-alice', 0, 10, 'Alice', '#2196F3');
                renderRemoteSelection('user-bob', 20, 35, 'Bob', '#FF5722');
            }"""
        )

        assert page.evaluate("() => CSS.highlights.has('hl-sel-user-alice')")
        assert page.evaluate("() => CSS.highlights.has('hl-sel-user-bob')")

        # Remove one, other remains
        page.evaluate("() => removeRemoteSelection('user-alice')")
        assert not page.evaluate("() => CSS.highlights.has('hl-sel-user-alice')")
        assert page.evaluate("() => CSS.highlights.has('hl-sel-user-bob')")


class TestRemoveAllRemotePresence:
    """Tests for removeAllRemotePresence cleanup function."""

    def test_remove_all_clears_cursors_and_selections(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """removeAllRemotePresence removes all remote cursors and selections."""
        page = authenticated_page
        content = "The plaintiff alleged that the defendant was negligent."
        setup_workspace_with_content_highlight_api(page, app_server, content)

        # Create multiple cursors and selections
        page.evaluate(
            """() => {
                const container = document.getElementById('doc-container');
                renderRemoteCursor(container, 'user-alice', 5, 'Alice', '#2196F3');
                renderRemoteCursor(container, 'user-bob', 20, 'Bob', '#FF5722');
                renderRemoteSelection('user-alice', 0, 10, 'Alice', '#2196F3');
                renderRemoteSelection('user-bob', 15, 30, 'Bob', '#FF5722');
            }"""
        )

        # Verify they exist
        assert page.locator(".remote-cursor").count() == 2
        assert page.evaluate("() => CSS.highlights.has('hl-sel-user-alice')")
        assert page.evaluate("() => CSS.highlights.has('hl-sel-user-bob')")
        assert page.locator("[id^='remote-sel-style-']").count() == 2

        # Remove all
        page.evaluate("() => removeAllRemotePresence()")

        # All gone
        assert page.locator(".remote-cursor").count() == 0
        assert not page.evaluate("() => CSS.highlights.has('hl-sel-user-alice')")
        assert not page.evaluate("() => CSS.highlights.has('hl-sel-user-bob')")
        assert page.locator("[id^='remote-sel-style-']").count() == 0


class TestUpdateRemoteCursorPositions:
    """Tests for updateRemoteCursorPositions reflow function."""

    def test_update_positions_adjusts_cursors(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """updateRemoteCursorPositions recalculates cursor positions."""
        page = authenticated_page
        content = "The plaintiff alleged that the defendant was negligent."
        setup_workspace_with_content_highlight_api(page, app_server, content)

        page.evaluate(
            """() => {
                const container = document.getElementById('doc-container');
                renderRemoteCursor(container, 'test-user', 10, 'Alice', '#2196F3');
            }"""
        )

        # Verify cursor has a position before update
        assert page.locator("#remote-cursor-test-user").evaluate(
            "el => el.style.top"
        ), "Cursor should have initial top position"

        # Call update -- should not throw, positions recalculated
        page.evaluate(
            """() => {
                const container = document.getElementById('doc-container');
                updateRemoteCursorPositions(container);
            }"""
        )

        # Cursor should still exist after update
        assert page.locator("#remote-cursor-test-user").count() == 1

        # Position should still be valid (non-empty style)
        updated_top = page.locator("#remote-cursor-test-user").evaluate(
            "el => el.style.top"
        )
        assert updated_top, "Cursor should have a top position after update"
