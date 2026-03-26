"""E2E regressions for ChatCraft fixture ingest."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import _authenticate_page
from tests.e2e.fixture_loaders import _load_fixture_via_paste

if TYPE_CHECKING:
    from playwright.sync_api import Browser

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "conversations"
CHATCRAFT_FIXTURE = FIXTURES_DIR / "chatcraft_sonnet-232.html.gz"


@pytest.mark.e2e
class TestChatCraftIngest232:
    """Regression coverage for issue 232's ChatCraft fixture."""

    def test_chatcraft_paste_preserves_all_turns_and_roles(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Clipboard paste keeps all ChatCraft turns and role labels intact."""
        context = browser.new_context()
        page = context.new_page()

        try:
            _authenticate_page(page, app_server)
            _load_fixture_via_paste(
                page,
                app_server,
                CHATCRAFT_FIXTURE,
                seed_tags=False,
            )

            doc = page.get_by_test_id("doc-container")
            expect(doc).to_contain_text("Hi Sonnet. Trying to repro a bug report.")
            expect(doc.locator("[data-speaker]")).to_have_count(10)
            expect(doc.locator('[data-speaker="system"]')).to_have_count(1)
            expect(doc.locator('[data-speaker="user"]')).to_have_count(4)
            expect(doc.locator('[data-speaker="assistant"]')).to_have_count(5)
            expect(doc).not_to_contain_text("<ChatCraft />")
            expect(doc).not_to_contain_text("Activity Denubis")
        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_chatcraft_paste_preserves_nested_blockquotes_and_code_blocks(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """The surviving final assistant card retains its nested rich content."""
        context = browser.new_context()
        page = context.new_page()

        try:
            _authenticate_page(page, app_server)
            _load_fixture_via_paste(
                page,
                app_server,
                CHATCRAFT_FIXTURE,
                seed_tags=False,
            )

            final_assistant = (
                page.get_by_test_id("doc-container")
                .locator('[data-speaker="assistant"]')
                .last
            )
            expect(final_assistant).to_contain_text("The above summary is nested:")
            expect(final_assistant.locator("blockquote")).to_have_count(2)
            expect(final_assistant.locator("blockquote blockquote")).to_have_count(1)
            expect(final_assistant.locator("pre")).to_have_count(2)
            expect(final_assistant).to_contain_text("def dedupe_speaker_markers")
            expect(final_assistant).to_contain_text("dedupeSpeakerMarkers")
        finally:
            page.goto("about:blank")
            page.close()
            context.close()
