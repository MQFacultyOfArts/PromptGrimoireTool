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
from tests.e2e.card_helpers import add_comment_to_highlight
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
    pytest.mark.noci,
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
            # Wait for doc 2 content to render before text walker check —
            # otherwise wait_for_text_walker sees stale doc 1 nodes.
            expect(page.locator("text=Detailed analysis")).to_be_visible(timeout=10000)

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

    def test_export_with_annotation_and_reflection(  # noqa: PLR0915
        self, browser: Browser, app_server: str, subtests: SubTests
    ) -> None:
        """Annotate BOTH documents, add comments, write reflection, export.

        Uses select_chars (not select_text()) after tab switch for reliable
        selection.  Verifies that the .tex output contains \\highLight and
        \\annot markup in BOTH \\section*{} blocks, that comments appear in
        the annotation bodies, and that the reflection section is present.

        Produces a .tex (fast) or .pdf (slow) at a known path for human
        visual inspection.
        """
        context = browser.new_context()
        page = context.new_page()

        # Short comment for doc 1 sidenote, long comment for doc 2 endnote.
        short_comment = "Key injury facts established here"
        long_comment = (
            "This statutory provision is critical because it establishes "
            "the standard of care that the defendant was required to meet. "
            "The interaction between the Civil Liability Act general "
            "negligence principles and the specific WHS duty creates a "
            "dual liability framework that strengthens the plaintiff case. "
            "Discovery should target compliance records under both statutes."
        )

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

            # --- Annotate Source 1 (Case Summary) ---
            with subtests.test(msg="annotate_case_summary"):
                start, end = find_text_range(page, "Ms Bennett, sustained")
                select_chars(page, start, end)
                toolbar_btn = page.locator("[data-testid='tag-toolbar'] button").first
                toolbar_btn.wait_for(state="visible", timeout=5000)
                toolbar_btn.click()
                cards = page.locator("[data-testid='annotation-card']")
                expect(cards.first).to_be_visible(timeout=5000)

            with subtests.test(msg="comment_on_case_summary"):
                add_comment_to_highlight(page, short_comment, card_index=0)

            # --- Switch to Source 2 and annotate ---
            with subtests.test(msg="annotate_statutory_framework"):
                page.get_by_test_id("tab-source-2").click()
                # Wait for doc 2 content to render before text walker check —
                # otherwise wait_for_text_walker sees stale doc 1 nodes.
                expect(
                    page.locator("text=general principles for determining")
                ).to_be_visible(timeout=10000)
                wait_for_text_walker(page, timeout=10000)

                start2, end2 = find_text_range(
                    page, "general principles for determining"
                )
                select_chars(page, start2, end2)
                toolbar_btn2 = page.locator("[data-testid='tag-toolbar'] button").first
                toolbar_btn2.wait_for(state="visible", timeout=5000)
                toolbar_btn2.click()
                cards2 = page.locator("[data-testid='annotation-card']")
                expect(cards2.first).to_be_visible(timeout=5000)

            with subtests.test(msg="comment_on_statutory_framework"):
                add_comment_to_highlight(page, long_comment, card_index=0)

            # --- Write reflection on Respond tab ---
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
                    "developed after the inspection date.",
                    delay=5,
                )

            # --- Export ---
            with subtests.test(msg="export_completes"):
                result = export_annotation_tex_text(page)
                assert result.size_bytes and result.size_bytes > 0

            # --- Save artifact for human visual inspection ---
            from pathlib import Path as _Path

            ext = ".pdf" if result.is_pdf else ".tex"
            save_dir = _Path("output/test_output/multi-doc-export")
            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = save_dir / f"multi-doc-export{ext}"
            save_path.write_text(result.text, encoding="utf-8")
            print(f"\n  Multi-doc export saved to: {save_path}")

            # --- Assert LaTeX structure (tex mode only) ---
            # In PDF mode we can only check text content, not markup.
            if not result.is_pdf:
                tex = result.text

                # Split into sections at \section* boundaries
                import re

                sections = re.split(r"\\section\*\{", tex)
                # sections[0] = preamble, sections[1:] = named sections
                case_section = next(
                    (s for s in sections if s.startswith("Case Summary")),
                    None,
                )
                stat_section = next(
                    (s for s in sections if s.startswith("Statutory Framework")),
                    None,
                )

                with subtests.test(msg="tex_case_summary_has_highlight"):
                    assert case_section is not None, (
                        "\\section*{Case Summary} not found in .tex"
                    )
                    assert "\\highLight" in case_section, (
                        "No \\highLight in Case Summary section"
                    )

                with subtests.test(msg="tex_case_summary_has_annot"):
                    assert "\\annot" in case_section, (
                        "No \\annot in Case Summary section"
                    )

                with subtests.test(msg="tex_case_summary_has_comment"):
                    assert "hrulefill" in case_section, (
                        "No comment separator in Case Summary annotation"
                    )
                    assert "Key injury facts" in case_section, (
                        "Short comment text missing from Case Summary"
                    )

                with subtests.test(msg="tex_statutory_has_highlight"):
                    assert stat_section is not None, (
                        "\\section*{Statutory Framework} not found in .tex"
                    )
                    assert "\\highLight" in stat_section, (
                        "No \\highLight in Statutory Framework section"
                    )

                with subtests.test(msg="tex_statutory_has_annot"):
                    assert "\\annot" in stat_section, (
                        "No \\annot in Statutory Framework section"
                    )

                with subtests.test(msg="tex_statutory_has_comment"):
                    assert "hrulefill" in stat_section, (
                        "No comment separator in Statutory Framework"
                    )
                    assert "dual liability framework" in stat_section, (
                        "Long comment text missing from Statutory Framework"
                    )

                with subtests.test(msg="tex_has_flushannotendnotes"):
                    assert "\\flushannotendnotes" in tex

                with subtests.test(msg="tex_annot_count"):
                    # Exactly 2 annotations: one per document
                    annot_count = len(re.findall(r"\\annot\{", tex))
                    assert annot_count == 2, (
                        f"Expected 2 \\annot commands, found {annot_count}"
                    )

            # --- Content assertions (work in both tex and pdf modes) ---
            with subtests.test(msg="export_has_case_summary"):
                # Use "plaintiff" not "Ms Bennett" — Pandoc line-wraps
                # "Ms\nBennett" across lines, breaking exact match.
                assert "plaintiff" in result

            with subtests.test(msg="export_has_statutory_framework"):
                assert "Civil Liability Act" in result

            with subtests.test(msg="export_has_reflection"):
                assert "inspection methodology" in result

        finally:
            page.goto("about:blank")
            page.close()
            context.close()
