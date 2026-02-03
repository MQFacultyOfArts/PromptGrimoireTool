"""Shared helper functions for annotation E2E tests.

These helpers extract common patterns used across annotation test files,
reducing duplication and ensuring consistent test setup.

Traceability:
- Epic: #92 (Annotation Workspace Platform)
- Issue: #93 (Seam A: Workspace Model)
- Design: docs/design-plans/2026-01-30-workspace-model.md
- Test consolidation: docs/design-plans/2026-01-31-test-suite-consolidation.md
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page


def select_chars(page: Page, start_char: int, end_char: int) -> None:
    """Select a range of characters by clicking start and shift-clicking end.

    This is the reliable method for text selection in Playwright tests.
    Uses click + shift+click which works consistently across browsers.

    Args:
        page: Playwright page.
        start_char: Index of first character to select.
        end_char: Index of last character to select.
    """
    char_start = page.locator(f"[data-char-index='{start_char}']")
    char_end = page.locator(f"[data-char-index='{end_char}']")

    char_start.scroll_into_view_if_needed()
    expect(char_start).to_be_visible(timeout=5000)

    char_start.click()
    char_end.click(modifiers=["Shift"])


# Deprecated alias for backwards compatibility during migration
select_words = select_chars


def create_highlight(page: Page, start_char: int, end_char: int) -> None:
    """Select characters and click the first tag button to create a highlight.

    Args:
        page: Playwright page.
        start_char: Index of first character to select.
        end_char: Index of last character to select.
    """
    select_chars(page, start_char, end_char)
    tag_button = page.locator("[data-testid='tag-toolbar'] button").first
    tag_button.click()


def setup_workspace_with_content(page: Page, app_server: str, content: str) -> None:
    """Navigate to annotation page, create workspace, and add document content.

    This is the common 5-step setup pattern shared by all annotation tests:
    1. Navigate to /annotation
    2. Click create workspace
    3. Wait for workspace URL
    4. Fill content
    5. Submit and wait for word spans

    The helper is page-agnostic: it works with single-user tests, multi-user
    sync tests, or any other context that provides a Playwright page.

    Args:
        page: Playwright page (can be from any browser context).
        app_server: Base URL of the app server.
        content: Text content to add as document.

    Traceability:
        Extracted from repetitive setup code across 15+ test classes.
        See test_annotation_page.py commit history for original patterns.
    """
    page.goto(f"{app_server}/annotation")
    page.get_by_role("button", name=re.compile("create", re.IGNORECASE)).click()
    page.wait_for_url(re.compile(r"workspace_id="))

    content_input = page.get_by_placeholder(re.compile("paste|content", re.IGNORECASE))
    content_input.fill(content)
    page.get_by_role("button", name=re.compile("add|submit", re.IGNORECASE)).click()
    page.wait_for_selector("[data-char-index]")
    page.wait_for_timeout(200)
