"""E2E CSS audit: guards against Quasar overrides and verifies bottom toolbar layout.

Verifies:
- AC5.1: Computed CSS for toolbar, layout wrapper, buttons, menu
- AC5.2: Fails if any property mismatches (Quasar overrides)
- AC1.1-AC1.3, AC2.1-AC2.3, AC4.1: Behavioural layout assertions
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import (
    _create_workspace_via_db,
    wait_for_text_walker,
)
from tests.e2e.conftest import _authenticate_page

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Browser, Page


@pytest.fixture
def annotation_page(browser: Browser, app_server: str) -> Generator[Page]:
    """Authenticated page navigated to an annotation workspace."""
    context = browser.new_context()
    page = context.new_page()
    email = _authenticate_page(page, app_server)

    workspace_id = _create_workspace_via_db(
        user_email=email,
        html_content=(
            "<p>CSS audit test content paragraph one.</p>"
            "<p>Second paragraph for layout verification.</p>"
        ),
    )
    page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
    wait_for_text_walker(page, timeout=15000)

    yield page

    with contextlib.suppress(Exception):
        page.goto("about:blank")
    page.close()
    context.close()


class TestStructuralCssProperties:
    """Quasar regression guard: assert computed CSS on key elements.

    Verifies: bottom-tag-bar.AC5.1, bottom-tag-bar.AC5.2
    """

    def test_toolbar_position_fixed_bottom(self, annotation_page: Page) -> None:
        """Toolbar wrapper is fixed to viewport bottom."""
        toolbar = annotation_page.locator("#tag-toolbar-wrapper")
        expect(toolbar).to_have_css("position", "fixed")
        expect(toolbar).to_have_css("bottom", "0px")

    def test_toolbar_box_shadow_upward(self, annotation_page: Page) -> None:
        """Toolbar shadow projects upward."""
        toolbar = annotation_page.locator("#tag-toolbar-wrapper")
        expect(toolbar).to_have_css("box-shadow", "rgba(0, 0, 0, 0.1) 0px -2px 4px 0px")

    def test_compact_button_padding(self, annotation_page: Page) -> None:
        """Compact buttons have tighter padding than Quasar default."""
        btn = annotation_page.locator(".q-btn.compact-btn").first
        expect(btn).to_have_css("padding", "0px 6px")

    def test_highlight_menu_z_index(self, annotation_page: Page) -> None:
        """Highlight menu z-index is above toolbar (110 > 100)."""
        menu = annotation_page.locator("#highlight-menu")
        expect(menu).to_have_css("z-index", "110")


class TestLayoutCorrectness:
    """Behavioural assertions: toolbar at bottom, content visible, no inline title.

    Verifies: bottom-tag-bar.AC1.1-AC1.3, AC2.1-AC2.3
    """

    def test_toolbar_at_viewport_bottom(self, annotation_page: Page) -> None:
        """Toolbar bottom edge aligns with viewport bottom."""
        toolbar = annotation_page.locator("#tag-toolbar-wrapper")
        box = toolbar.bounding_box()
        assert box is not None
        viewport = annotation_page.viewport_size
        assert viewport is not None
        # Toolbar bottom should be at viewport bottom (within 1px)
        assert abs((box["y"] + box["height"]) - viewport["height"]) <= 1

    def test_content_not_obscured_by_toolbar(self, annotation_page: Page) -> None:
        """Document content bottom is above toolbar top.

        Uses #doc-container (actual content) rather than the layout
        wrapper, because the wrapper's padding-bottom intentionally
        extends into the toolbar zone.
        """
        doc = annotation_page.locator("#doc-container")
        toolbar = annotation_page.locator("#tag-toolbar-wrapper")
        doc_box = doc.bounding_box()
        toolbar_box = toolbar.bounding_box()
        assert doc_box is not None
        assert toolbar_box is not None
        content_bottom = doc_box["y"] + doc_box["height"]
        toolbar_top = toolbar_box["y"]
        assert content_bottom <= toolbar_top + 1  # 1px tolerance

    def test_no_inline_title(self, annotation_page: Page) -> None:
        """No text-2xl font-bold heading in page content area (AC2.1)."""
        expect(annotation_page.locator(".text-2xl.font-bold")).to_have_count(0)

    def test_no_uuid_label(self, annotation_page: Page) -> None:
        """No 'Workspace: <uuid>' text visible on page (AC2.2)."""
        expect(annotation_page.locator("text=/Workspace: [0-9a-f-]+/")).to_have_count(0)

    def test_header_row_visible(self, annotation_page: Page) -> None:
        """Header row renders correctly after title removal (AC2.3)."""
        user_count = annotation_page.locator('[data-testid="user-count"]')
        expect(user_count).to_be_visible(timeout=5000)
