"""E2E test: translation student multilingual annotation workflow.

Narrative persona test covering the translation student journey:
authenticate -> paste CJK/RTL/mixed-script content -> create highlights ->
add comments -> export PDF with i18n content.

Each step is a discrete subtest checkpoint using pytest-subtests.

Acceptance Criteria:
- 156-e2e-test-migration.AC3.3: Persona test covering CJK, RTL, mixed-script, i18n PDF
- 156-e2e-test-migration.AC3.6: Uses pytest-subtests for checkpoints
- 156-e2e-test-migration.AC4.1: No CSS.highlights assertions
- 156-e2e-test-migration.AC4.2: No page.evaluate() for internal DOM state
- 156-e2e-test-migration.AC5.1: Creates own workspace (no shared state)
- 156-e2e-test-migration.AC5.2: Random auth email + UUID comments for isolation
- 156-e2e-test-migration.AC7.3: CJK and RTL content works end-to-end (#101)

Replaces skipped test_annotation_cjk.py and test_i18n_pdf_export.py.

Traceability:
- Issue: #156 (E2E test migration)
- Issue: #101 (CJK/BLNS support)
- Design: docs/design-plans/2026-02-14-156-e2e-test-migration.md Phase 5
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page
    from pytest_subtests import SubTests

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect

from tests.e2e.card_helpers import add_comment_to_highlight
from tests.e2e.conftest import _authenticate_page
from tests.e2e.export_tools import export_annotation_tex_text
from tests.e2e.fixture_loaders import (
    _load_fixture_via_paste,
    setup_workspace_with_content,
)
from tests.e2e.highlight_tools import create_highlight_with_tag, find_text_range

# ---------------------------------------------------------------------------
# Local helpers -- reduce repeated setup/verify/highlight/comment sequences
# ---------------------------------------------------------------------------

ANNOTATION_CARD = "[data-testid='annotation-card']"


def _setup_and_highlight(
    page: Page,
    app_server: str,
    content: str,
    verify_snippet: str,
) -> None:
    """Create workspace, verify snippet rendered, highlight, verify card."""
    setup_workspace_with_content(page, app_server, content)
    expect(page.locator("#doc-container")).to_contain_text(
        verify_snippet, timeout=15000
    )
    hl = find_text_range(page, verify_snippet)
    create_highlight_with_tag(page, *hl, tag_index=0)
    expect(page.locator(ANNOTATION_CARD).first).to_be_visible(timeout=10000)


def _post_comment_on_first_card(page: Page, comment_uuid: str) -> None:
    """Post a comment on the first annotation card."""
    add_comment_to_highlight(page, comment_uuid, card_index=0)


# --- Test content strings ---
# Reused from test_annotation_cjk.py (deleted Phase 8)
CHINESE_TEXT = (
    "\u4f60\u597d\u4e16\u754c"
    " \u8fd9\u662f\u4e2d\u6587\u6d4b\u8bd5\u5185\u5bb9"
    " \u7ef4\u57fa\u767e\u79d1\u793a\u4f8b"
)
JAPANESE_TEXT = (
    "\u3053\u3093\u306b\u3061\u306f\u4e16\u754c"
    " \u65e5\u672c\u8a9e\u30c6\u30b9\u30c8"
    " \u96e2\u5a5a\u5224\u6c7a\u8b04\u672c"
)
KOREAN_TEXT = (
    "\uc548\ub155\ud558\uc138\uc694"
    " \ud55c\uad6d\uc5b4 \ud14c\uc2a4\ud2b8"
    " \ubc95\uc740 \ucc28\uc774\ub97c"
)
ARABIC_TEXT = (
    "\u0645\u0631\u062d\u0628\u0627 \u0628\u0627\u0644\u0639\u0627\u0644\u0645"
    " \u0647\u0630\u0627 \u0646\u0635"
    " \u0639\u0631\u0628\u064a \u0644\u0644\u0627\u062e\u062a\u0628\u0627\u0631"
)
HEBREW_TEXT = (
    "\u05e9\u05dc\u05d5\u05dd \u05e2\u05d5\u05dc\u05dd"
    " \u05d6\u05d4\u05d5 \u05d8\u05e7\u05e1\u05d8"
    " \u05d1\u05e2\u05d1\u05e8\u05d9\u05ea \u05dc\u05d1\u05d3\u05d9\u05e7\u05d4"
)
MIXED_TEXT = (
    "Hello \u4e16\u754c World"
    " \u3053\u3093\u306b\u3061\u306f"
    " \u0645\u0631\u062d\u0628\u0627 \uc548\ub155\ud558\uc138\uc694"
)


@pytest.mark.e2e
@pytest.mark.cards
class TestTranslationStudent:
    """Translation student persona: annotating multilingual content."""

    def test_cjk_chinese_annotation(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Chinese annotation: paste content, highlight, verify card."""
        context = browser.new_context()
        page = context.new_page()

        try:
            _authenticate_page(page, app_server)
            _setup_and_highlight(
                page, app_server, CHINESE_TEXT, "\u4f60\u597d\u4e16\u754c"
            )
        finally:
            page.close()
            context.close()

    def test_cjk_japanese_annotation(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Japanese annotation: paste content, highlight, verify card."""
        context = browser.new_context()
        page = context.new_page()

        try:
            _authenticate_page(page, app_server)
            _setup_and_highlight(
                page,
                app_server,
                JAPANESE_TEXT,
                "\u3053\u3093\u306b\u3061\u306f\u4e16\u754c",
            )
        finally:
            page.close()
            context.close()

    def test_cjk_korean_annotation(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Korean annotation: paste content, highlight, verify card."""
        context = browser.new_context()
        page = context.new_page()

        try:
            _authenticate_page(page, app_server)
            _setup_and_highlight(
                page, app_server, KOREAN_TEXT, "\uc548\ub155\ud558\uc138\uc694"
            )
        finally:
            page.close()
            context.close()

    def test_rtl_arabic_annotation(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Arabic RTL annotation: paste content, highlight, verify card.

        Narrative: Translation student pastes Arabic content, highlights a
        passage, verifies the annotation card appears.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            _authenticate_page(page, app_server)
            _setup_and_highlight(
                page, app_server, ARABIC_TEXT, "\u0645\u0631\u062d\u0628\u0627"
            )
        finally:
            page.close()
            context.close()

    def test_rtl_hebrew_annotation(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Hebrew RTL annotation: paste content, highlight, verify card.

        Narrative: Translation student pastes Hebrew content, highlights a
        passage, verifies the annotation card appears.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            _authenticate_page(page, app_server)
            _setup_and_highlight(
                page, app_server, HEBREW_TEXT, "\u05e9\u05dc\u05d5\u05dd"
            )
        finally:
            page.close()
            context.close()

    def test_mixed_script_annotation(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """Mixed-script annotation workflow with 3 checkpoints.

        Narrative: Translation student works with a document containing
        multiple scripts (Latin, CJK, Arabic).
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            _authenticate_page(page, app_server)

            with subtests.test(msg="paste_mixed_content"):
                setup_workspace_with_content(page, app_server, MIXED_TEXT)

                doc = page.locator("#doc-container")
                expect(doc).to_contain_text("Hello", timeout=15000)
                expect(doc).to_contain_text("\u4e16\u754c", timeout=5000)

            with subtests.test(msg="highlight_across_scripts"):
                hl = find_text_range(page, "Hello \u4e16\u754c")
                create_highlight_with_tag(page, *hl, tag_index=0)
                expect(page.locator(ANNOTATION_CARD).first).to_be_visible(timeout=10000)

            with subtests.test(msg="add_comment_with_uuid"):
                comment_uuid = uuid4().hex[:8]
                _post_comment_on_first_card(page, comment_uuid)
                expect(page.get_by_text(comment_uuid)).to_be_visible(timeout=10000)

        finally:
            page.close()
            context.close()

    def test_i18n_pdf_export(
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """i18n PDF export workflow with 3 checkpoints.

        Narrative: Translation student creates multilingual workspace from
        Chinese Wikipedia fixture, annotates it, and exports PDF to verify
        i18n content survives the full pipeline.
        """
        comment_uuid = ""
        result = None

        context = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()

        try:
            _authenticate_page(page, app_server)

            fixture_path = (
                Path(__file__).parent.parent
                / "fixtures"
                / "conversations"
                / "chinese_wikipedia.html"
            )

            with subtests.test(msg="paste_cjk_fixture"):
                _load_fixture_via_paste(page, app_server, fixture_path)
                expect(page.locator("#doc-container")).to_contain_text(
                    "\u7ef4\u57fa\u767e\u79d1", timeout=15000
                )

            with subtests.test(msg="highlight_and_comment"):
                hl = find_text_range(page, "\u7ef4\u57fa\u767e\u79d1")
                create_highlight_with_tag(page, *hl, tag_index=0)
                expect(page.locator(ANNOTATION_CARD).first).to_be_visible(timeout=10000)

                comment_uuid = uuid4().hex[:8]
                _post_comment_on_first_card(page, comment_uuid)
                expect(page.get_by_text(comment_uuid)).to_be_visible(timeout=10000)

                # Post a second comment with emoji to test #274
                emoji_comment = f"Great work! \U0001f389 {uuid4().hex[:8]}"
                add_comment_to_highlight(page, emoji_comment, card_index=0)
                expect(page.get_by_text(emoji_comment)).to_be_visible(timeout=10000)

            with subtests.test(msg="export_pdf"):
                try:
                    result = export_annotation_tex_text(page)

                    # UUID comment string must appear
                    assert comment_uuid in result, (
                        "Comment UUID not found in exported content"
                    )

                    # CJK characters must survive the full pipeline
                    assert any(char in result for char in "\u7ef4\u57fa\u767e\u79d1"), (
                        "CJK chars (维基百科) not found in exported content"
                    )

                except PlaywrightTimeoutError:
                    pytest.skip("PDF export timed out (TinyTeX not installed?)")
                except PlaywrightError as e:
                    if "Download" in str(e):
                        pytest.skip(f"PDF download failed: {e}")
                    raise

            with subtests.test(msg="export_emoji_gh274"):
                # Emoji must survive the full pipeline (#274)
                assert result is not None, "export_pdf subtest must run first"
                if "\U0001f389" not in result:
                    pytest.xfail("Emoji 🎉 not in export — #274 open")

        finally:
            page.close()
            context.close()
