"""E2E tests for BLNS edge cases in annotation system.

Verifies that the annotation system correctly handles edge cases from
the Big List of Naughty Strings (BLNS) including RTL text, special
whitespace characters, and CJK characters.

Traceability:
- Issue: #101 (CJK/BLNS support)
- Phase: 5 of character-based tokenization implementation

SKIPPED: Pending #106 HTML input redesign. Reimplement after #106.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from promptgrimoire.config import get_settings
from tests.e2e.annotation_helpers import select_chars, setup_workspace_with_content
from tests.unit.conftest import CJK_TEST_CHARS

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Skip all tests in this module pending #106 HTML input redesign
pytestmark = pytest.mark.skip(reason="Pending #106 HTML input redesign")

# Skip marker for tests requiring database
pytestmark_db = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


@pytest.mark.e2e
class TestBLNSEdgeCases:
    """Tests for BLNS edge cases in annotation system."""

    @pytestmark_db
    @pytest.mark.parametrize("cjk_char", CJK_TEST_CHARS[:10])  # Test first 10 CJK chars
    def test_individual_cjk_characters(
        self, authenticated_page: Page, app_server: str, cjk_char: str
    ) -> None:
        """Verify individual CJK characters from BLNS can be selected."""
        page = authenticated_page
        setup_workspace_with_content(page, app_server, cjk_char)
        page.wait_for_selector("[data-char-index]")

        char_span = page.locator("[data-char-index='0']")
        expect(char_span).to_be_visible()
        expect(char_span).to_have_text(cjk_char)

    @pytestmark_db
    def test_rtl_arabic_text(self, authenticated_page: Page, app_server: str) -> None:
        """Verify RTL Arabic text can be selected."""
        page = authenticated_page
        # Arabic "Hello" - characters still indexed left-to-right in DOM
        content = "مرحبا"
        setup_workspace_with_content(page, app_server, content)

        page.wait_for_selector("[data-char-index]")

        # Should have 5 character spans
        for i in range(5):
            char = page.locator(f"[data-char-index='{i}']")
            expect(char).to_be_visible()

    @pytestmark_db
    def test_rtl_hebrew_text(self, authenticated_page: Page, app_server: str) -> None:
        """Verify RTL Hebrew text can be selected."""
        page = authenticated_page
        content = "שלום"  # "Hello" in Hebrew (4 characters)
        setup_workspace_with_content(page, app_server, content)

        page.wait_for_selector("[data-char-index]")

        # Select all Hebrew characters
        select_chars(page, 0, 3)

    @pytestmark_db
    def test_hard_whitespace_nbsp(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Verify non-breaking spaces are individually selectable."""
        page = authenticated_page
        # Non-breaking space between words (U+00A0)
        content = "Hello\u00a0World"  # 11 characters, nbsp at index 5
        setup_workspace_with_content(page, app_server, content)

        page.wait_for_selector("[data-char-index]")

        # The nbsp should have its own index
        nbsp_span = page.locator("[data-char-index='5']")
        expect(nbsp_span).to_be_visible()

    @pytestmark_db
    def test_ideographic_space(self, authenticated_page: Page, app_server: str) -> None:
        """Verify ideographic space (U+3000) is selectable."""
        page = authenticated_page
        content = "你\u3000好"  # Chinese with ideographic space
        setup_workspace_with_content(page, app_server, content)

        page.wait_for_selector("[data-char-index]")

        # Should have 3 character spans: 你(0), space(1), 好(2)
        for i in range(3):
            char = page.locator(f"[data-char-index='{i}']")
            expect(char).to_be_visible()
