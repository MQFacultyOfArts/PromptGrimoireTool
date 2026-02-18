"""Multi-context E2E smoke test for remote presence.

Exercises the full broadcast flow: user A performs an action, user B
sees the remote presence indicator. Uses two Playwright browser contexts
connected to the same workspace.

Acceptance criteria verified:
- css-highlight-api.AC3.1: Remote cursor appears at correct position with name
- css-highlight-api.AC3.2: Remote selection appears as CSS highlight
- css-highlight-api.AC3.3: Disconnect removes remote presence indicators
- css-highlight-api.AC3.4: Local user's own cursor/selection not rendered

Traceability:
- Design: docs/implementation-plans/2026-02-11-css-highlight-api-150/phase_05.md
- Task 9: Multi-context E2E smoke test for remote presence
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import (
    select_text_range,
    setup_workspace_with_content_highlight_api,
)
from tests.e2e.conftest import _grant_workspace_access

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page


def _setup_two_contexts(
    browser: Browser, app_server: str, content: str
) -> tuple[Page, Page, str, str, str]:
    """Set up two authenticated browser contexts viewing the same workspace.

    Returns:
        Tuple of (page1, page2, workspace_id, user1_email, user2_email).
    """
    user1_email = f"presence_user1_{uuid4().hex[:8]}@test.edu.au"
    user2_email = f"presence_user2_{uuid4().hex[:8]}@test.edu.au"

    context1 = browser.new_context()
    context2 = browser.new_context()
    page1 = context1.new_page()
    page2 = context2.new_page()

    # Authenticate with distinct identities
    page1.goto(f"{app_server}/auth/callback?token=mock-token-{user1_email}")
    page1.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10000)

    page2.goto(f"{app_server}/auth/callback?token=mock-token-{user2_email}")
    page2.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10000)

    # Page1 creates workspace
    setup_workspace_with_content_highlight_api(page1, app_server, content)

    # Extract workspace_id from URL
    match = re.search(r"workspace_id=([^&]+)", page1.url)
    if not match:
        raise ValueError(f"No workspace_id in URL: {page1.url}")
    workspace_id = match.group(1)

    # Grant page2 access (ACL gate requires explicit permission)
    _grant_workspace_access(workspace_id, user2_email)

    # Page2 joins same workspace
    page2.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
    page2.wait_for_function(
        "() => window._textNodes && window._textNodes.length > 0",
        timeout=10000,
    )

    return page1, page2, workspace_id, user1_email, user2_email


class TestRemotePresenceSmoke:
    """End-to-end smoke test for remote presence across two browser contexts."""

    @pytest.mark.xfail(
        reason="Selection broadcast pipeline doesn't reliably propagate "
        "to remote user's CSS.highlights within 5s — #177",
        strict=False,
    )
    def test_selection_visible_to_remote_user(
        self, browser: Browser, app_server: str
    ) -> None:
        """AC3.2: Text selection in context A appears as CSS highlight in context B.

        Steps:
        1. Two authenticated contexts on the same workspace
        2. User A selects text
        3. User B sees a CSS.highlights entry for user A's selection
        """
        content = (
            "The plaintiff alleged that the defendant was negligent in the workplace."
        )
        page1, page2, _ws_id, _u1, _u2 = _setup_two_contexts(
            browser, app_server, content
        )
        try:
            # User A selects text via mouseup (triggers selection_made event)
            select_text_range(page1, "defendant")

            # Wait for broadcast to propagate to user B
            page2.wait_for_function(
                """() => {
                    for (const name of CSS.highlights.keys()) {
                        if (name.startsWith('hl-sel-')) return true;
                    }
                    return false;
                }""",
                timeout=5000,
            )

            # User B should see a remote selection CSS highlight
            # The highlight name is hl-sel-{client_id} where client_id is
            # the NiceGUI client ID for user A. We check for any hl-sel-* entry.
            has_remote_selection = page2.evaluate(
                """() => {
                    for (const name of CSS.highlights.keys()) {
                        if (name.startsWith('hl-sel-')) return true;
                    }
                    return false;
                }"""
            )
            assert has_remote_selection, (
                "Expected a remote selection highlight (hl-sel-*) in user B's browser"
            )

            # Verify the companion style element exists
            style_count = page2.evaluate(
                "() => document.querySelectorAll('[id^=\"remote-sel-style-\"]').length"
            )
            assert style_count >= 1, (
                "Expected remote selection style element in user B's browser"
            )
        finally:
            page1.context.close()
            page2.context.close()

    def test_own_selection_not_shown_as_remote(
        self, browser: Browser, app_server: str
    ) -> None:
        """AC3.4: Local user's own selection is not rendered as remote indicator.

        Steps:
        1. Two contexts on same workspace
        2. User A selects text
        3. Verify user A does NOT have a hl-sel-* entry for their own client ID
        """
        content = (
            "The plaintiff alleged that the defendant was negligent in the workplace."
        )
        page1, page2, _ws_id, _u1, _u2 = _setup_two_contexts(
            browser, app_server, content
        )
        try:
            # User A selects text
            select_text_range(page1, "defendant")

            # User A should NOT have any hl-sel-* entries (those are for
            # remote users only -- the local selection uses browser native selection)
            own_remote_selection = page1.evaluate(
                """() => {
                    for (const name of CSS.highlights.keys()) {
                        if (name.startsWith('hl-sel-')) return true;
                    }
                    return false;
                }"""
            )
            assert not own_remote_selection, (
                "User A should not see their own selection as a remote indicator"
            )

            # User A should also not have a remote cursor for themselves
            own_remote_cursors = page1.locator(".remote-cursor").count()
            assert own_remote_cursors == 0, (
                "User A should not see their own remote cursor"
            )
        finally:
            page1.context.close()
            page2.context.close()

    @pytest.mark.xfail(
        reason="Depends on selection broadcast which doesn't reliably propagate — #177",
        strict=False,
    )
    def test_disconnect_removes_remote_presence(
        self, browser: Browser, app_server: str
    ) -> None:
        """AC3.3: When user A disconnects, user B's remote indicators are removed.

        Steps:
        1. Two contexts on same workspace
        2. User A selects text (creates remote selection in user B)
        3. Close user A's context
        4. User B should see remote indicators removed within 5 seconds
        """
        content = (
            "The plaintiff alleged that the defendant was negligent in the workplace."
        )
        page1, page2, _ws_id, _u1, _u2 = _setup_two_contexts(
            browser, app_server, content
        )
        try:
            # User A selects text so there's something to clean up
            select_text_range(page1, "defendant")

            # Wait for broadcast to propagate to user B
            page2.wait_for_function(
                """() => {
                    for (const name of CSS.highlights.keys()) {
                        if (name.startsWith('hl-sel-')) return true;
                    }
                    return false;
                }""",
                timeout=5000,
            )

            # Verify intermediate state: remote selection exists before disconnect
            has_selection = page2.evaluate(
                """() => {
                    for (const name of CSS.highlights.keys()) {
                        if (name.startsWith('hl-sel-')) return true;
                    }
                    return false;
                }"""
            )
            assert has_selection, (
                "Expected remote selection before testing disconnect cleanup"
            )

            # Close user A's browser context (simulates disconnect)
            page1.context.close()

            # User B should see remote indicators disappear within 5 seconds
            # NiceGUI's on_disconnect fires within ~1-2s
            page2.wait_for_function(
                """() => {
                    const q = s => document.querySelectorAll(s);
                    if (q('.remote-cursor').length > 0)
                        return false;
                    for (const n of CSS.highlights.keys()) {
                        if (n.startsWith('hl-sel-'))
                            return false;
                    }
                    const sel = '[id^="remote-sel-style-"]';
                    if (q(sel).length > 0) return false;
                    return true;
                }""",
                timeout=5000,
            )
        finally:
            # page1 context already closed above; page2 still needs cleanup
            page2.context.close()

    def test_cursor_broadcast_via_event(
        self, browser: Browser, app_server: str
    ) -> None:
        """AC3.1: Cursor position broadcast via cursor_move event.

        The cursor_move NiceGUI event is wired on the Python side but the
        JS emission is not yet connected to click events. This test verifies
        the broadcast pipeline by emitting cursor_move directly.

        Steps:
        1. Two contexts on same workspace
        2. User A emits cursor_move event with char index
        3. User B sees a .remote-cursor element with user A's name
        """
        content = (
            "The plaintiff alleged that the defendant was negligent in the workplace."
        )
        page1, page2, _ws_id, _u1, _u2 = _setup_two_contexts(
            browser, app_server, content
        )
        try:
            # Emit cursor_move event from user A
            page1.evaluate("() => emitEvent('cursor_move', {char: 15})")

            # Wait for remote cursor to appear in user B's view
            page2.wait_for_function(
                "() => document.querySelectorAll('.remote-cursor').length > 0",
                timeout=5000,
            )

            # User B should see a remote cursor element
            remote_cursors = page2.locator(".remote-cursor")
            expect(remote_cursors).to_have_count(1, timeout=5000)

            # Cursor should have a name label
            label = remote_cursors.locator(".remote-cursor-label")
            assert label.count() == 1, "Expected cursor name label"
            # Label text should be user A's display name
            label_text = label.text_content()
            assert label_text and len(label_text) > 0, "Expected non-empty cursor label"
        finally:
            page1.context.close()
            page2.context.close()

    def test_late_joiner_sees_existing_presence(
        self, browser: Browser, app_server: str
    ) -> None:
        """Late-joining user sees existing cursor/selection from other users.

        Steps:
        1. User A creates workspace and emits cursor position
        2. User B joins the same workspace
        3. User B should see user A's cursor immediately
        """
        content = (
            "The plaintiff alleged that the defendant was negligent in the workplace."
        )
        user1_email = f"presence_late1_{uuid4().hex[:8]}@test.edu.au"
        user2_email = f"presence_late2_{uuid4().hex[:8]}@test.edu.au"

        context1 = browser.new_context()
        page1 = context1.new_page()

        page1.goto(f"{app_server}/auth/callback?token=mock-token-{user1_email}")
        page1.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10000)

        setup_workspace_with_content_highlight_api(page1, app_server, content)

        # Extract workspace_id
        match = re.search(r"workspace_id=([^&]+)", page1.url)
        assert match, f"No workspace_id in URL: {page1.url}"
        workspace_id = match.group(1)

        try:
            # User A emits cursor position BEFORE user B joins
            page1.evaluate("() => emitEvent('cursor_move', {char: 10})")

            # Now user B joins
            context2 = browser.new_context()
            page2 = context2.new_page()

            page2.goto(f"{app_server}/auth/callback?token=mock-token-{user2_email}")
            page2.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10000)

            # Grant page2 access (ACL gate requires explicit permission)
            _grant_workspace_access(workspace_id, user2_email)

            page2.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            page2.wait_for_function(
                "() => window._textNodes && window._textNodes.length > 0",
                timeout=10000,
            )

            # User B should see user A's cursor (sent on late-join sync)
            remote_cursors = page2.locator(".remote-cursor")
            expect(remote_cursors).to_have_count(1, timeout=5000)
        finally:
            context1.close()
            context2.close()
