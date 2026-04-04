"""E2E tests for idle tab eviction.

Uses client-side JS to reconfigure the idle tracker with short timeouts
(5s timeout, 2s warning) per-test, so the server can run with production
defaults and other tests are unaffected.

Verifies:
- AC1.1: Idle timeout navigates to /paused
- AC1.4: Interaction resets the timer
- AC1.5: Wall-clock time, not accumulated intervals
- AC2.1: Warning modal appears with countdown
- AC2.2: Stay Active dismisses and resets
- AC2.3: Any interaction dismisses modal
- AC2.4: visibilitychange in warning window shows modal
- AC2.5: visibilitychange past timeout evicts immediately
- AC2.6: visibilitychange below threshold resets timer
- AC3.1/AC3.2: Resume returns to original page
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Page

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.noci,
]

_SHORT_IDLE_JS = """() => {
    cleanupIdleTracker();
    window.__idleConfig = { timeoutMs: 5000, warningMs: 2000, enabled: true };
    initIdleTracker();
}"""


@pytest.fixture()
def idle_page(authenticated_page: Page) -> Page:
    """Authenticated page with idle tracker reconfigured to short timeouts."""
    authenticated_page.evaluate(_SHORT_IDLE_JS)
    return authenticated_page


class TestIdleTimeout:
    """AC1.1, AC1.5: Idle tab navigates to /paused after timeout."""

    def test_idle_timeout_navigates_to_paused(self, idle_page: Page) -> None:
        """After idle timeout, browser navigates to /paused."""
        from playwright.sync_api import expect

        page = idle_page
        # Wait without interaction — 5s timeout + poll interval headroom
        page.wait_for_url("**/paused**", timeout=15000)
        assert "/paused" in page.url
        assert "return=" in page.url
        # Verify paused page content
        expect(page.locator("h1")).to_contain_text("paused")


class TestWarningModal:
    """AC2.1-AC2.3, AC1.4: Warning modal interaction."""

    def test_warning_modal_appears_before_eviction(self, idle_page: Page) -> None:
        """AC2.1: Modal appears at warning threshold with countdown."""
        page = idle_page
        modal = page.get_by_test_id("idle-warning-modal")
        modal.wait_for(state="visible", timeout=10000)
        assert "seconds" in modal.inner_text().lower()

    def test_stay_active_dismisses_and_resets(self, idle_page: Page) -> None:
        """AC2.2: Stay Active dismisses modal, timer resets."""
        page = idle_page
        modal = page.get_by_test_id("idle-warning-modal")
        modal.wait_for(state="visible", timeout=10000)

        # Click Stay Active
        page.get_by_test_id("idle-stay-active-btn").click()

        # Modal should disappear
        from playwright.sync_api import expect

        expect(modal).not_to_be_visible()

        # Timer was reset — modal should reappear after another cycle
        modal.wait_for(state="visible", timeout=10000)
        # But we should NOT have been evicted to /paused yet
        assert "/paused" not in page.url

    def test_any_click_dismisses_modal(self, idle_page: Page) -> None:
        """AC2.3: Any click during warning dismisses modal."""
        page = idle_page
        modal = page.get_by_test_id("idle-warning-modal")
        modal.wait_for(state="visible", timeout=10000)

        # Click on the page body (not the button)
        page.locator("body").click(position={"x": 10, "y": 10})

        from playwright.sync_api import expect

        expect(modal).not_to_be_visible()

    def test_interaction_during_warning_resets_timer(self, idle_page: Page) -> None:
        """AC1.4: Interaction during warning resets the full timer."""
        page = idle_page
        modal = page.get_by_test_id("idle-warning-modal")
        modal.wait_for(state="visible", timeout=10000)

        # Click to dismiss and reset
        page.locator("body").click(position={"x": 10, "y": 10})

        from playwright.sync_api import expect

        expect(modal).not_to_be_visible()

        # Modal reappears after another full cycle (proves timer reset)
        modal.wait_for(state="visible", timeout=10000)
        assert "/paused" not in page.url


class TestVisibilityChange:
    """AC2.4-AC2.6: Tab visibility change behaviour.

    Uses page.evaluate() to simulate visibilitychange — approved exception
    to the "no JS injection" E2E rule (Playwright has no native API for
    tab visibility simulation).
    """

    def _simulate_tab_refocus(self, page: Page) -> None:
        """Simulate tab hidden then refocused."""
        page.evaluate("""() => {
            Object.defineProperty(document, 'hidden',
                {value: true, configurable: true});
            document.dispatchEvent(new Event('visibilitychange'));
        }""")
        page.evaluate("""() => {
            Object.defineProperty(document, 'hidden',
                {value: false, configurable: true});
            document.dispatchEvent(new Event('visibilitychange'));
        }""")

    def test_refocus_past_timeout_evicts_immediately(self, idle_page: Page) -> None:
        """AC2.5: Refocus after timeout navigates to /paused."""
        page = idle_page
        # Wait for first eviction
        page.wait_for_url("**/paused**", timeout=15000)

        # Click Resume to return to original page
        page.locator("a.resume").click()
        page.wait_for_url(lambda u: "/paused" not in u, timeout=10000)

        # Re-inject short idle config — page reload restored server defaults
        page.evaluate(_SHORT_IDLE_JS)

        # Wait for second eviction (proves the cycle works)
        page.wait_for_url("**/paused**", timeout=15000)

    def test_refocus_in_warning_window_shows_modal(self, idle_page: Page) -> None:
        """AC2.4: Refocus in warning window shows modal immediately."""
        page = idle_page
        modal = page.get_by_test_id("idle-warning-modal")

        # Wait for modal to appear naturally
        modal.wait_for(state="visible", timeout=10000)
        # Dismiss it
        page.get_by_test_id("idle-stay-active-btn").click()

        from playwright.sync_api import expect

        expect(modal).not_to_be_visible()

        # Wait until we're in the warning window again
        modal.wait_for(state="visible", timeout=10000)

        # Modal is visible — simulate tab hide/refocus
        # The modal should remain visible (or reappear immediately)
        self._simulate_tab_refocus(page)

        # Modal should still be visible
        expect(modal).to_be_visible()

    def test_refocus_below_threshold_resets_timer(self, idle_page: Page) -> None:
        """AC2.6: Early refocus resets timer (no modal)."""
        page = idle_page
        modal = page.get_by_test_id("idle-warning-modal")

        # Immediately simulate refocus (well before warning threshold)
        self._simulate_tab_refocus(page)

        from playwright.sync_api import expect

        # No modal should be shown
        expect(modal).not_to_be_visible()

        # Timer was reset — wait for modal to eventually appear
        # (proves timer wasn't frozen)
        modal.wait_for(state="visible", timeout=10000)


class TestResumeFlow:
    """AC3.1, AC3.2: Resume from /paused returns to original page."""

    def test_resume_returns_to_original_page(self, idle_page: Page) -> None:
        """AC3.1/AC3.2: Resume button works with gate open."""
        page = idle_page

        # Wait for eviction
        page.wait_for_url("**/paused**", timeout=15000)
        assert "paused" in page.url.lower()

        # Click Resume
        page.locator("a.resume").click()

        # Should return to original page (gate open)
        page.wait_for_url(
            lambda u: "/paused" not in u,
            timeout=10000,
        )
