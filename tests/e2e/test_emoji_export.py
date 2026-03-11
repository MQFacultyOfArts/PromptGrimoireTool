"""E2E test: emoji survival through annotation and export pipeline.

Verifies that emoji characters in pasted HTML content survive the full
pipeline: paste → render → highlight → comment → export (.tex/.pdf).

Uses the chatgpt54-emoji.html.gz fixture which contains 5 distinct
emoji: 🛵 🎮 😄 👍 🔋.

The LaTeX export pipeline passes emoji through as raw Unicode to
LuaLaTeX, which renders them via Noto Color Emoji HarfBuzz fallback
(see unicode_latex.py FallbackFont chain).

Traceability:
- Issue: #274 (Emoji rendering in PDF export)
- Fix: 6d6cdb9d (pass emoji through raw instead of \\emoji{} command)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from tests.e2e.card_helpers import add_comment_to_highlight
from tests.e2e.conftest import _authenticate_page
from tests.e2e.export_tools import export_annotation_tex_text
from tests.e2e.fixture_loaders import _load_fixture_via_paste
from tests.e2e.highlight_tools import create_highlight_with_tag, find_text_range

if TYPE_CHECKING:
    from playwright.sync_api import Browser
    from pytest_subtests import SubTests

ANNOTATION_CARD = "[data-testid='annotation-card']"
FIXTURE_PATH = (
    Path(__file__).parent.parent
    / "fixtures"
    / "conversations"
    / "chatgpt54-emoji.html.gz"
)

# Emoji present in the fixture
FIXTURE_EMOJI = ["🛵", "🎮", "😄", "👍", "🔋"]


@pytest.mark.e2e
class TestEmojiExport:
    """Emoji survival through annotation and export pipeline."""

    def test_emoji_survives_export(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """Paste emoji fixture, highlight, comment with emoji, export.

        Subtests:
        1. paste_emoji_fixture — load fixture, verify emoji visible
        2. highlight_emoji_text — create highlight over emoji-containing text
        3. add_emoji_comment — post comment containing emoji
        4. export_contains_emoji — verify emoji in .tex/.pdf output
        """
        context = browser.new_context(
            permissions=["clipboard-read", "clipboard-write"],
        )
        page = context.new_page()

        try:
            _authenticate_page(page, app_server)

            with subtests.test(msg="paste_emoji_fixture"):
                _load_fixture_via_paste(page, app_server, FIXTURE_PATH)
                doc = page.locator("#doc-container")
                # Verify at least one emoji rendered in the document
                for emoji in FIXTURE_EMOJI:
                    expect(doc).to_contain_text(emoji, timeout=15000)

            with subtests.test(msg="highlight_emoji_text"):
                # Find text containing an emoji and highlight it
                hl = find_text_range(page, "😄")
                create_highlight_with_tag(page, *hl, tag_index=0)
                expect(
                    page.locator(ANNOTATION_CARD).first,
                ).to_be_visible(timeout=10000)

            with subtests.test(msg="add_emoji_comment"):
                emoji_comment = f"Test emoji comment 🎉 {uuid4().hex[:8]}"
                add_comment_to_highlight(page, emoji_comment, card_index=0)
                expect(
                    page.get_by_text(emoji_comment),
                ).to_be_visible(timeout=10000)

            with subtests.test(msg="export_contains_emoji"):
                result = export_annotation_tex_text(page)

                # Emoji from fixture must survive export
                assert "😄" in result, "Fixture emoji 😄 not found in export"

                # Emoji from comment must survive export
                assert "🎉" in result, "Comment emoji 🎉 not found in export"

                # Verify raw emoji, not \emoji{} commands
                assert r"\emoji{" not in result, (
                    "Export uses \\emoji{} command instead of raw emoji"
                )

        finally:
            page.close()
            context.close()
