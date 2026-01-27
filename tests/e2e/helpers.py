"""Shared helper functions for E2E tests.

These are plain functions, NOT pytest fixtures.
Only include functions that are truly identical across test files.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page


def click_tag(page: Page, index: int = 0) -> None:
    """Click a tag button to create a highlight from current selection."""
    tag_buttons = page.locator(".tag-toolbar-compact button")
    tag_button = tag_buttons.nth(index)
    tag_button.scroll_into_view_if_needed()
    expect(tag_button).to_be_visible(timeout=5000)
    tag_button.click()
