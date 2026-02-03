"""E2E tests for CJK character selection in annotation system.

Verifies that Chinese, Japanese, and Korean characters can be selected
individually and highlighted correctly through the character-based
tokenization system.

Traceability:
- Issue: #101 (CJK/BLNS support)
- Phase: 5 of character-based tokenization implementation
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import (
    create_highlight,
    select_chars,
    setup_workspace_with_content,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Skip marker for tests requiring database
pytestmark_db = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)


@pytest.mark.e2e
class TestCJKCharacterSelection:
    """Tests for CJK character selection in annotation system."""

    @pytestmark_db
    def test_chinese_character_selection(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Verify Chinese characters can be selected individually."""
        page = authenticated_page
        # 你好世界 = "Hello world" in Chinese (4 characters)
        content = "你好世界"
        setup_workspace_with_content(page, app_server, content)

        # Wait for character spans
        page.wait_for_selector("[data-char-index]")

        # Select middle two characters: 好世 (indices 1-2)
        select_chars(page, 1, 2)

        # Verify selection spans correct characters
        char_1 = page.locator("[data-char-index='1']")
        char_2 = page.locator("[data-char-index='2']")
        expect(char_1).to_be_visible()
        expect(char_2).to_be_visible()

    @pytestmark_db
    def test_japanese_mixed_script(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Verify Japanese mixed script (hiragana + kanji) selection."""
        page = authenticated_page
        # こんにちは世界 = "Hello world" in Japanese (7 characters)
        content = "こんにちは世界"
        setup_workspace_with_content(page, app_server, content)

        page.wait_for_selector("[data-char-index]")

        # Each character should have its own index
        for i in range(7):
            char = page.locator(f"[data-char-index='{i}']")
            expect(char).to_be_visible()

    @pytestmark_db
    def test_korean_character_selection(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Verify Korean Hangul selection."""
        page = authenticated_page
        # 안녕하세요 = "Hello" in Korean (5 syllables/characters)
        content = "안녕하세요"
        setup_workspace_with_content(page, app_server, content)

        page.wait_for_selector("[data-char-index]")

        # Create highlight across first 3 characters
        create_highlight(page, 0, 2)

        # Verify highlight applied (background-color will be rgba(...) when highlighted)
        char_0 = page.locator("[data-char-index='0']")
        expect(char_0).to_have_css("background-color", re.compile(r"rgba\("))

    @pytestmark_db
    def test_cjk_mixed_with_ascii(
        self, authenticated_page: Page, app_server: str
    ) -> None:
        """Verify mixed CJK and ASCII text selection."""
        page = authenticated_page
        content = "Hello 世界 World"  # 16 characters total
        setup_workspace_with_content(page, app_server, content)

        page.wait_for_selector("[data-char-index]")

        # Select the CJK portion (indices 6-7: 世界)
        select_chars(page, 6, 7)

        char_6 = page.locator("[data-char-index='6']")
        char_7 = page.locator("[data-char-index='7']")
        expect(char_6).to_be_visible()
        expect(char_7).to_be_visible()
