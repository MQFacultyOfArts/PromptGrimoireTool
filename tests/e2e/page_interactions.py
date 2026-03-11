"""Page interaction helpers for annotation E2E tests.

Provides navigation, drag-and-drop, sharing, and workspace cloning helpers.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from promptgrimoire.docs.helpers import wait_for_text_walker

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page


def navigate_home_via_drawer(page: Page) -> None:
    """Navigate to ``/`` using the shared ``page_layout`` nav drawer.

    Opens the drawer via the header menu button if it isn't already
    visible, then clicks the "Home" nav item.  Pages that use
    ``page_layout()`` get this drawer automatically.

    Args:
        page: Playwright page with ``page_layout`` rendered.
    """
    home_link = page.get_by_test_id("nav-home")
    if not home_link.is_visible():
        page.locator(".q-header .q-btn").first.click()
    expect(home_link).to_be_visible(timeout=5000)
    home_link.click()


def drag_sortable_item(source: Locator, target: Locator) -> None:
    """Drag a SortableJS item by its drag handle to the target.

    Uses Playwright's ``drag_to`` between the source's
    ``.drag-handle`` child and the *target* locator.

    Args:
        source: Locator for the draggable element
            (must contain ``.drag-handle``).
        target: Locator for the drop target element.
    """
    source_handle = source.locator(".drag-handle").first
    source_handle.drag_to(target)


def toggle_share_with_class(page: Page) -> None:
    """Toggle the 'Share with class' switch on.

    Waits for the toggle to be visible and clicks it if not
    already enabled.  Expects the annotation workspace page.
    """
    toggle = page.locator('[data-testid="share-with-class-toggle"]')
    toggle.wait_for(state="visible", timeout=5000)
    if toggle.get_attribute("aria-checked") != "true":
        toggle.click()
    expect(toggle).to_have_attribute("aria-checked", "true", timeout=5000)


def clone_activity_workspace(
    page: Page,
    app_server: str,
    course_id: str,
    activity_title: str,
) -> str:
    """Navigate to course, clone activity workspace.

    Args:
        page: Authenticated Playwright page.
        app_server: Base URL of the test server.
        course_id: UUID string of the course.
        activity_title: Title of the activity to clone.

    Returns:
        workspace_id as string.
    """
    page.goto(f"{app_server}/courses/{course_id}")

    label = page.get_by_text(activity_title)
    label.wait_for(state="visible", timeout=10000)
    card = label.locator("xpath=ancestor::div[contains(@class, 'q-card')]")
    card.locator("[data-testid^='start-activity-btn-']").first.click()

    page.wait_for_url(
        re.compile(r"/annotation\?workspace_id="),
        timeout=15000,
    )
    wait_for_text_walker(page, timeout=15000)

    return page.url.split("workspace_id=")[1].split("&")[0]
