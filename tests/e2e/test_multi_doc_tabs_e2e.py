"""E2E tests for multi-document tabbed workspace (#186).

Verifies that workspaces with multiple documents render separate
source tabs, that switching tabs shows the correct document content,
and that annotations are isolated per document.

Requires DEV__TEST_DATABASE_URL and a running app server.

Traceability:
- Design: docs/implementation-plans/2026-03-14-multi-doc-tabs-186-plan-a/
- AC: multi-doc-tabs.AC1.1-AC1.6 (tab bar rendering)
- AC: multi-doc-tabs.AC2.1-AC2.5 (per-document isolation)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from promptgrimoire.config import get_settings
from promptgrimoire.docs.helpers import select_chars, wait_for_text_walker
from tests.e2e.conftest import _authenticate_page
from tests.e2e.db_fixtures import _create_multi_doc_workspace
from tests.e2e.export_tools import export_annotation_tex_text
from tests.e2e.highlight_tools import find_text_range

if TYPE_CHECKING:
    from playwright.sync_api import Browser
    from pytest_subtests import SubTests


pytestmark = [
    pytest.mark.skipif(
        not get_settings().dev.test_database_url,
        reason="DEV__TEST_DATABASE_URL not configured",
    ),
    pytest.mark.e2e,
]


class TestMultiDocTabRendering:
    """Verify tab bar renders one tab per document plus Organise and Respond."""

    def test_two_documents_show_two_source_tabs(
        self, browser: Browser, app_server: str
    ) -> None:
        """AC1.1: Each document gets its own source tab."""
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)
            ws_id = _create_multi_doc_workspace(
                email,
                [
                    ("Introduction", "<p>This is the introduction document.</p>"),
                    ("Analysis", "<p>This is the analysis document.</p>"),
                ],
            )

            page.goto(f"{app_server}/annotation?workspace_id={ws_id}")
            wait_for_text_walker(page, timeout=15000)

            # Should have 4 tabs: Source 1, Source 2, Organise, Respond
            tabs = page.locator("[data-testid^='tab-']")
            expect(tabs).to_have_count(4, timeout=5000)

            # Verify source tab labels include titles
            source_1 = page.get_by_test_id("tab-source-1")
            source_2 = page.get_by_test_id("tab-source-2")
            expect(source_1).to_contain_text("Source 1: Introduction")
            expect(source_2).to_contain_text("Source 2: Analysis")

            # Organise and Respond still present
            expect(page.get_by_test_id("tab-organise")).to_be_visible()
            expect(page.get_by_test_id("tab-respond")).to_be_visible()

            # Source 1 is selected by default
            expect(source_1).to_have_attribute("aria-selected", "true")

        finally:
            page.goto("about:blank")
            page.close()
            context.close()


class TestMultiDocTabSwitching:
    """Verify switching between source tabs shows correct document content."""

    def test_tab_switch_shows_different_content(
        self, browser: Browser, app_server: str
    ) -> None:
        """AC2.1: Switching tabs renders the correct document."""
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)
            ws_id = _create_multi_doc_workspace(
                email,
                [
                    ("Doc Alpha", "<p>Alpha content unique marker AAAA.</p>"),
                    ("Doc Beta", "<p>Beta content unique marker BBBB.</p>"),
                ],
            )

            page.goto(f"{app_server}/annotation?workspace_id={ws_id}")
            wait_for_text_walker(page, timeout=15000)

            # Source 1 is visible - verify its content
            expect(page.locator("text=Alpha content unique marker AAAA")).to_be_visible(
                timeout=5000
            )

            # Switch to Source 2
            page.get_by_test_id("tab-source-2").click()
            expect(page.locator("text=Beta content unique marker BBBB")).to_be_visible(
                timeout=10000
            )

            # Switch back to Source 1 - content should still be there
            page.get_by_test_id("tab-source-1").click()
            expect(page.locator("text=Alpha content unique marker AAAA")).to_be_visible(
                timeout=5000
            )

        finally:
            page.goto("about:blank")
            page.close()
            context.close()


class TestMultiDocAnnotationIsolation:
    """Verify annotation cards on one document don't appear on another."""

    def test_card_count_differs_between_tabs(
        self, browser: Browser, app_server: str
    ) -> None:
        """AC2.3: Annotation cards are filtered per document.

        Creates a 2-doc workspace, highlights text on Source 1 via the
        toolbar, then verifies Source 2 shows zero cards.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)
            ws_id = _create_multi_doc_workspace(
                email,
                [
                    ("First", "<p>First document content here.</p>"),
                    ("Second", "<p>Second document content here.</p>"),
                ],
            )

            page.goto(f"{app_server}/annotation?workspace_id={ws_id}")
            wait_for_text_walker(page, timeout=15000)

            # Select text via mouse drag on Source 1
            doc_text = page.locator("[data-testid='doc-container'] p").first
            doc_text.select_text()

            # Click the first tag button in the toolbar to apply highlight
            toolbar_btn = page.locator("[data-tag-id]").first
            toolbar_btn.wait_for(state="visible", timeout=5000)
            toolbar_btn.click()

            # Wait for annotation card to appear on Source 1
            cards = page.locator("[data-testid='annotation-card']")
            expect(cards.first).to_be_visible(timeout=5000)
            assert cards.count() > 0, "Expected at least one annotation card on Doc 1"

            # Switch to Source 2
            page.get_by_test_id("tab-source-2").click()
            wait_for_text_walker(page, timeout=10000)

            # Source 2 should have zero annotation cards
            cards_doc2 = page.locator("[data-testid='annotation-card']")
            expect(cards_doc2).to_have_count(0, timeout=5000)

        finally:
            page.goto("about:blank")
            page.close()
            context.close()


class TestMultiDocAnnotateSecondDocument:
    """Verify annotations work on non-default (second) document tab."""

    def test_annotate_second_document_with_select_chars(
        self, browser: Browser, app_server: str, subtests: SubTests
    ) -> None:
        """AC2.2: Text walker reinitialises correctly on tab switch.

        Switches to Source 2, uses char-offset selection (select_chars)
        to verify the text walker is correctly bound to the new document
        container, then creates a highlight and verifies the card appears.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)
            ws_id = _create_multi_doc_workspace(
                email,
                [
                    ("Intro", "<p>Introduction paragraph one.</p>"),
                    ("Detail", "<p>Detailed analysis paragraph two.</p>"),
                ],
            )

            page.goto(f"{app_server}/annotation?workspace_id={ws_id}")
            wait_for_text_walker(page, timeout=15000)

            # Switch to Source 2
            page.get_by_test_id("tab-source-2").click()

            with subtests.test(msg="text_walker_ready_on_doc2"):
                wait_for_text_walker(page, timeout=10000)

            with subtests.test(msg="find_text_range_on_doc2"):
                start, end = find_text_range(page, "Detailed analysis")
                assert start >= 0
                assert end > start

            with subtests.test(msg="select_and_highlight_on_doc2"):
                select_chars(page, start, end)
                toolbar_btn = page.locator("[data-testid='tag-toolbar'] button").first
                toolbar_btn.wait_for(state="visible", timeout=5000)
                toolbar_btn.click()

                cards = page.locator("[data-testid='annotation-card']")
                expect(cards.first).to_be_visible(timeout=5000)
                assert cards.count() > 0

        finally:
            page.goto("about:blank")
            page.close()
            context.close()


class TestMultiDocAnnotateBothDocuments:
    """Verify annotations on both documents survive tab switching."""

    def test_both_docs_retain_annotations_after_round_trip(
        self, browser: Browser, app_server: str, subtests: SubTests
    ) -> None:
        """AC2.4: Per-document annotation cards persist across tab switches.

        Annotates doc 1, switches to doc 2 and annotates it, then
        switches back — verifying each document retains its own cards.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)
            ws_id = _create_multi_doc_workspace(
                email,
                [
                    ("Alpha", "<p>Alpha paragraph for annotation.</p>"),
                    ("Beta", "<p>Beta paragraph for annotation.</p>"),
                ],
            )

            page.goto(f"{app_server}/annotation?workspace_id={ws_id}")
            wait_for_text_walker(page, timeout=15000)

            # --- Annotate on Source 1 ---
            with subtests.test(msg="doc1_highlight_created"):
                doc_text = page.locator("[data-testid='doc-container'] p").first
                doc_text.select_text()
                toolbar_btn = page.locator("[data-testid='tag-toolbar'] button").first
                toolbar_btn.wait_for(state="visible", timeout=5000)
                toolbar_btn.click()

                cards_doc1 = page.locator("[data-testid='annotation-card']")
                expect(cards_doc1.first).to_be_visible(timeout=5000)
                doc1_count = cards_doc1.count()
                assert doc1_count > 0, "Expected card on Doc 1"

            # --- Switch to Source 2 and annotate ---
            page.get_by_test_id("tab-source-2").click()
            wait_for_text_walker(page, timeout=10000)

            with subtests.test(msg="doc2_highlight_created"):
                # Wait for doc 2 content to be visible before selecting
                expect(
                    page.locator("text=Beta paragraph for annotation")
                ).to_be_visible(timeout=5000)
                doc_text = page.locator("[data-testid='doc-container'] p").first
                doc_text.select_text()
                toolbar_btn = page.locator("[data-testid='tag-toolbar'] button").first
                toolbar_btn.wait_for(state="visible", timeout=5000)
                toolbar_btn.click()

                cards_doc2 = page.locator("[data-testid='annotation-card']")
                expect(cards_doc2.first).to_be_visible(timeout=5000)
                doc2_count = cards_doc2.count()
                assert doc2_count > 0, "Expected card on Doc 2"

            # --- Switch back to Source 1 ---
            page.get_by_test_id("tab-source-1").click()
            wait_for_text_walker(page, timeout=10000)

            with subtests.test(msg="doc1_cards_survive_round_trip"):
                cards_back = page.locator("[data-testid='annotation-card']")
                expect(cards_back.first).to_be_visible(timeout=5000)
                assert cards_back.count() >= doc1_count, (
                    f"Doc 1 lost cards: {doc1_count} -> {cards_back.count()}"
                )

            # --- Switch to Source 2 again ---
            page.get_by_test_id("tab-source-2").click()
            wait_for_text_walker(page, timeout=10000)

            with subtests.test(msg="doc2_cards_survive_round_trip"):
                cards_back2 = page.locator("[data-testid='annotation-card']")
                expect(cards_back2.first).to_be_visible(timeout=5000)
                assert cards_back2.count() >= doc2_count, (
                    f"Doc 2 lost cards: {doc2_count} -> {cards_back2.count()}"
                )

        finally:
            page.goto("about:blank")
            page.close()
            context.close()


class TestMultiDocExport:
    """Verify PDF export includes all source documents."""

    def test_export_contains_all_documents(
        self, browser: Browser, app_server: str, subtests: SubTests
    ) -> None:
        """Export a 2-doc workspace and verify both appear in the output."""
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)
            ws_id = _create_multi_doc_workspace(
                email,
                [
                    ("Intro Doc", "<p>UNIQUEINTRO content for export test.</p>"),
                    ("Analysis Doc", "<p>UNIQUEANALYSIS content for export test.</p>"),
                ],
            )

            page.goto(f"{app_server}/annotation?workspace_id={ws_id}")
            wait_for_text_walker(page, timeout=15000)

            with subtests.test(msg="export_completes"):
                result = export_annotation_tex_text(page)
                assert result.size_bytes and result.size_bytes > 0

            with subtests.test(msg="export_contains_doc1"):
                assert "UNIQUEINTRO" in result

            with subtests.test(msg="export_contains_doc2"):
                assert "UNIQUEANALYSIS" in result

        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_export_with_annotation_and_reflection(
        self, browser: Browser, app_server: str, subtests: SubTests
    ) -> None:
        """Annotate active doc, write a reflection, export, save for inspection.

        Produces a .tex (fast) or .pdf (slow) at a known path so a human
        can visually verify the export layout.  The saved file path is
        printed to stdout for easy retrieval.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)
            ws_id = _create_multi_doc_workspace(
                email,
                [
                    (
                        "Case Summary",
                        "<p>The plaintiff, Ms Bennett, sustained a workplace injury "
                        "on 15 March 2025 when a ceiling tile dislodged and struck "
                        "her left shoulder. Medical evidence confirms a Grade II "
                        "rotator cuff tear requiring surgical intervention.</p>"
                        "<p>Liability is contested on the grounds that the building "
                        "inspection report dated 10 January 2025 found no defects "
                        "in the ceiling structure.</p>",
                    ),
                    (
                        "Statutory Framework",
                        "<p>Section 5B of the Civil Liability Act 2002 (NSW) "
                        "establishes the general principles for determining "
                        "negligence. The defendant owed a duty of care under "
                        "the Work Health and Safety Act 2011 (Cth) s 19.</p>",
                    ),
                ],
            )

            page.goto(f"{app_server}/annotation?workspace_id={ws_id}")
            wait_for_text_walker(page, timeout=15000)

            # Annotate on Source 1 (the active tab)
            with subtests.test(msg="annotate_case_summary"):
                doc_text = page.locator("[data-testid='doc-container'] p").first
                doc_text.select_text()
                toolbar_btn = page.locator("[data-testid='tag-toolbar'] button").first
                toolbar_btn.wait_for(state="visible", timeout=5000)
                toolbar_btn.click()
                cards = page.locator("[data-testid='annotation-card']")
                expect(cards.first).to_be_visible(timeout=5000)

            # Write a reflection on the Respond tab
            with subtests.test(msg="write_reflection"):
                page.get_by_test_id("tab-respond").click()
                editor = (
                    page.get_by_test_id("milkdown-editor-container")
                    .locator("[contenteditable]")
                    .first
                )
                editor.wait_for(state="visible", timeout=5000)
                editor.click()
                page.keyboard.type(
                    "The tension between the building inspection report "
                    "and the actual ceiling failure suggests either the "
                    "inspection methodology was inadequate or the defect "
                    "developed after the inspection date. Further discovery "
                    "should target the inspection protocol and any interim "
                    "maintenance records.",
                    delay=5,
                )

            # Export and save
            with subtests.test(msg="export_and_save"):
                result = export_annotation_tex_text(page)
                assert result.size_bytes and result.size_bytes > 0

                from pathlib import Path as _Path

                ext = ".pdf" if result.is_pdf else ".tex"
                save_dir = _Path("output/test_output/multi-doc-export")
                save_dir.mkdir(parents=True, exist_ok=True)
                save_path = save_dir / f"multi-doc-export{ext}"
                save_path.write_text(result.text, encoding="utf-8")
                print(f"\n  Multi-doc export saved to: {save_path}")

            with subtests.test(msg="export_has_case_summary"):
                assert "Ms Bennett" in result

            with subtests.test(msg="export_has_statutory_framework"):
                assert "Civil Liability Act" in result

            with subtests.test(msg="export_has_reflection"):
                assert "inspection methodology" in result

        finally:
            page.goto("about:blank")
            page.close()
            context.close()
