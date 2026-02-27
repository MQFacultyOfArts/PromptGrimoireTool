"""E2E test: law student AustLII annotation workflow.

Narrative persona test covering the law student journey:
authenticate -> paste AustLII HTML -> create highlights with legal tags ->
add comments -> change tags -> keyboard shortcuts -> organise tab ->
respond tab -> reload persistence -> PDF export verification.

Each step is a discrete subtest checkpoint using pytest-subtests.

Acceptance Criteria:
- 156-e2e-test-migration.AC3.2: Persona test covering AustLII annotation flow
- 156-e2e-test-migration.AC3.6: Uses pytest-subtests for checkpoints
- 156-e2e-test-migration.AC4.1: No CSS.highlights assertions
- 156-e2e-test-migration.AC4.2: No page.evaluate() for internal DOM state
- 156-e2e-test-migration.AC5.1: Creates own workspace (no shared state)
- 156-e2e-test-migration.AC5.2: Random auth email + UUID comments for isolation
- 156-e2e-test-migration.AC7.2: HTML paste via clipboard simulation (#106)
- tags-qa-95.AC4.1: Typing "1" in comment input inserts character (not shortcut)
- tags-qa-95.AC4.2: Typing "1" in comment input does NOT create highlight
- tags-qa-95.AC4.3: Pressing "a" with text selected does NOT create highlight
- tags-qa-95.AC4.4: Organise tab has no "Untagged" column header

Traceability:
- Issue: #156 (E2E test migration)
- Design: docs/design-plans/2026-02-14-156-e2e-test-migration.md Phase 4
- Issue: #95 (Annotation tags QA)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Browser
    from pytest_subtests import SubTests

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import (
    _load_fixture_via_paste,
    create_highlight_with_tag,
    scroll_to_char,
    select_chars,
    wait_for_text_walker,
)
from tests.e2e.conftest import _authenticate_page


@pytest.mark.e2e
class TestLawStudent:
    """Law student persona: annotating an AustLII case judgment."""

    def test_austlii_annotation_workflow(  # noqa: PLR0915
        self,
        browser: Browser,
        app_server: str,
        subtests: SubTests,
    ) -> None:
        """Complete law student annotation workflow with 21 checkpoints.

        Tests the full journey: auth, fixture paste, empty respond state,
        highlighting with legal tags, comments, tag changes, keyboard shortcuts,
        keyboard shortcut isolation (input fields, letter keys),
        organise tab (no untagged column, column placement, author/text,
        locate/warp, drag-retag), respond tab (reference panel, locate/warp),
        reload persistence, and PDF export with annotation verification.
        """
        # Store UUIDs for cross-subtest verification
        uuid1 = ""
        uuid2 = ""

        # Create browser context with clipboard permissions
        context = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()

        try:
            # Authenticate as law student
            _authenticate_page(page, app_server)

            # Define fixture path
            fixture_path = (
                Path(__file__).parent.parent
                / "fixtures"
                / "conversations"
                / "lawlis_v_r_austlii.html"
            )

            with subtests.test(msg="authenticate_and_paste_fixture"):
                # Load AustLII fixture via clipboard paste
                _load_fixture_via_paste(page, app_server, fixture_path)

                # Verify fixture content loaded
                expect(page.locator("#doc-container")).to_contain_text(
                    "Lawlis", timeout=15000
                )

            with subtests.test(msg="respond_tab_empty_state"):
                # Check what the Respond tab looks like before any annotations
                page.get_by_test_id("tab-respond").click()

                editor = page.locator("[data-testid='milkdown-editor-container']")
                expect(editor).to_be_visible(timeout=10000)

                # Reference panel should show empty state
                no_highlights = page.locator("[data-testid='respond-no-highlights']")
                expect(no_highlights).to_be_visible(timeout=5000)
                expect(no_highlights).to_contain_text("No highlights yet")

                # Return to Annotate tab to start highlighting
                page.get_by_test_id("tab-annotate").click()
                wait_for_text_walker(page, timeout=10000)

            with subtests.test(msg="highlight_with_legal_tag"):
                # Create first highlight with Jurisdiction tag (tag_index=0)
                create_highlight_with_tag(page, 10, 40, tag_index=0)

                # Verify annotation card appears
                expect(
                    page.locator("[data-testid='annotation-card']").first
                ).to_be_visible(timeout=10000)

            with subtests.test(msg="add_comment_with_uuid"):
                # Generate unique comment identifier
                uuid1 = uuid4().hex

                # Click annotation card to ensure comment input is visible
                page.locator("[data-testid='annotation-card']").first.click()

                # Find comment input and add comment
                comment_input = page.get_by_test_id("comment-input").first
                comment_input.fill(uuid1)

                # Post comment
                page.locator("[data-testid='annotation-card']").first.get_by_text(
                    "Post"
                ).click()

                # Verify comment appears
                expect(page.get_by_text(uuid1)).to_be_visible(timeout=10000)

            with subtests.test(msg="highlight_with_different_tag"):
                # Create second highlight with Legal Issues tag (tag_index=3)
                create_highlight_with_tag(page, 100, 150, tag_index=3)

                # Verify second annotation card appears
                expect(
                    page.locator("[data-testid='annotation-card']").nth(1)
                ).to_be_visible(timeout=10000)

            with subtests.test(msg="add_second_comment_with_uuid"):
                # Generate second unique comment identifier
                uuid2 = uuid4().hex

                # Click second card
                page.locator("[data-testid='annotation-card']").nth(1).click()

                # Find comment input on second card
                comment_input = page.get_by_test_id("comment-input").nth(1)
                comment_input.fill(uuid2)

                # Post second comment
                page.locator("[data-testid='annotation-card']").nth(1).get_by_text(
                    "Post"
                ).click()

                # Verify second comment appears
                expect(page.get_by_text(uuid2)).to_be_visible(timeout=10000)

            with subtests.test(msg="change_tag_via_dropdown"):
                # Scroll first highlight back into view so card positioning
                # makes the card visible (cards are hidden when their
                # highlight is off-screen).
                scroll_to_char(page, 10)

                # Select first card's tag dropdown
                first_card = page.locator("[data-testid='annotation-card']").first
                expect(first_card).to_be_visible(timeout=5000)
                tag_select = first_card.get_by_test_id("tag-select")

                # Click dropdown to open menu
                tag_select.click()

                # Wait for dropdown menu and select Procedural History
                page.locator(".q-menu .q-item").filter(
                    has_text="Procedural History"
                ).click()

                # Verify tag changed (dropdown displays new tag)
                expect(tag_select).to_contain_text("Procedural History", timeout=5000)

            with subtests.test(msg="keyboard_shortcut_tag"):
                # Select text range for keyboard shortcut highlight
                select_chars(page, 200, 250)

                # Press "5" for Reasons tag
                page.keyboard.press("5")

                # Wait briefly for highlight processing
                page.wait_for_timeout(500)

                # Verify third annotation card appears
                expect(
                    page.locator("[data-testid='annotation-card']").nth(2)
                ).to_be_visible(timeout=10000)

            with subtests.test(msg="keyboard_shortcut_in_input_field"):
                # AC4.1: Typing "1" in comment input inserts character
                # AC4.2: Typing "1" in comment input does NOT create highlight
                highlight_count = page.locator(
                    "[data-testid='annotation-card']"
                ).count()

                # Use the third card's comment input (from keyboard_shortcut_tag).
                # It is at the bottom of the stack and not overlapped by other
                # absolutely-positioned cards. The input is empty (no comment
                # posted on this card).
                # Scroll the third card's highlight range into view first
                # (card positioning hides cards whose highlights are off-screen).
                scroll_to_char(page, 200)

                third_card = page.locator("[data-testid='annotation-card']").nth(2)
                expect(third_card).to_be_visible(timeout=5000)
                comment_input = third_card.get_by_test_id("comment-input")
                comment_input.click()
                page.keyboard.press("1")

                # Character appears in input field
                expect(comment_input).to_have_value("1")

                # No new highlight created
                assert (
                    page.locator("[data-testid='annotation-card']").count()
                    == highlight_count
                )

                # Wait to catch any async highlight creation
                page.wait_for_timeout(500)
                assert (
                    page.locator("[data-testid='annotation-card']").count()
                    == highlight_count
                )

                # Clear the input for subsequent tests (re-scroll in case
                # card positioning hid the card during the wait above).
                scroll_to_char(page, 200)
                expect(third_card).to_be_visible(timeout=5000)
                comment_input.fill("")

            with subtests.test(msg="letter_key_no_highlight"):
                # AC4.3: Pressing "a" with text selected does NOT create highlight
                highlight_count = page.locator(
                    "[data-testid='annotation-card']"
                ).count()

                # Select text in document (different range from existing selections)
                select_chars(page, 300, 350)

                # Press letter key -- JS handler only responds to digits 1-0
                page.keyboard.press("a")

                # Wait for any async processing
                page.wait_for_timeout(500)

                # Highlight count unchanged
                assert (
                    page.locator("[data-testid='annotation-card']").count()
                    == highlight_count
                )

                # Click elsewhere to deselect
                page.locator("#doc-container").click(position={"x": 5, "y": 5})

            with subtests.test(msg="organise_tab"):
                # Click Organise tab
                page.get_by_test_id("tab-organise").click()

                # Wait for organise content to render
                page.wait_for_timeout(1000)

                # Verify organise cards appear
                expect(
                    page.locator("[data-testid='organise-card']").first
                ).to_be_visible(timeout=10000)

                # Verify a column heading matches a tag we used
                expect(page.get_by_text("Procedural History").first).to_be_visible()

            with subtests.test(msg="no_untagged_column_in_organise"):
                # AC4.4: All highlights have tags, so "Untagged" column absent
                # Organise tab is already visible from subtest above
                expect(
                    page.locator("[data-testid='organise-columns']").get_by_text(
                        "Untagged"
                    )
                ).not_to_be_visible()

            with subtests.test(msg="organise_highlight_in_correct_column"):
                # The first card's tag was changed to Procedural History
                # Verify it appears in the correct column
                proc_col = page.locator(
                    '[data-testid="tag-column"][data-tag-name="Procedural History"]'
                )
                expect(proc_col).to_be_visible(timeout=3000)
                cards_in_col = proc_col.locator('[data-testid="organise-card"]')
                expect(cards_in_col.first).to_be_visible(timeout=3000)

            with subtests.test(msg="organise_card_shows_author_and_text"):
                # Organise card should show author attribution and text snippet
                card = page.locator('[data-testid="organise-card"]').first
                expect(card).to_be_visible(timeout=3000)
                expect(card).to_contain_text("by ")
                expect(card.locator(".italic")).to_be_visible()

            with subtests.test(msg="organise_locate_warps_to_annotate"):
                # Click locate button — should warp to Tab 1
                card = page.locator('[data-testid="organise-card"]').first
                locate_btn = card.locator("button").first
                expect(locate_btn).to_be_visible(timeout=3000)
                locate_btn.click()
                page.wait_for_timeout(1000)

                # Verify Annotate tab is now active
                annotate_tab = page.get_by_test_id("tab-annotate")
                expect(annotate_tab).to_have_attribute(
                    "aria-selected", "true", timeout=3000
                )
                # Verify text walker is populated
                page.wait_for_function(
                    "() => window._textNodes && window._textNodes.length > 0",
                    timeout=3000,
                )

            with subtests.test(msg="organise_return_after_warp"):
                # Return to Organise tab — content should still be rendered
                page.get_by_test_id("tab-organise").click()
                page.wait_for_timeout(500)
                columns = page.locator('[data-testid="organise-columns"]')
                expect(columns).to_be_visible(timeout=3000)
                organise_tab = page.get_by_test_id("tab-organise")
                expect(organise_tab).to_have_attribute("aria-selected", "true")

            with subtests.test(msg="respond_tab"):
                # Click Respond tab
                page.get_by_test_id("tab-respond").click()

                # Verify Milkdown editor loads
                editor = page.locator("[data-testid='milkdown-editor-container']")
                expect(editor).to_be_visible(timeout=10000)

                # Type into the editor to exercise input capability
                editor.locator("[contenteditable]").first.click()
                page.keyboard.type("Case analysis notes")

            with subtests.test(msg="respond_reference_panel"):
                # Reference panel should show highlights grouped by tag
                ref_panel = page.locator("[data-testid='respond-reference-panel']")
                expect(ref_panel).to_be_visible(timeout=5000)
                expect(ref_panel).to_contain_text("Highlight Reference")

                # Should have tag group sections
                tag_groups = ref_panel.locator("[data-testid='respond-tag-group']")
                expect(tag_groups.first).to_be_visible(timeout=5000)

                # Should have 3 reference cards (one per highlight)
                ref_cards = ref_panel.locator("[data-testid='respond-reference-card']")
                expect(ref_cards).to_have_count(3, timeout=5000)

            with subtests.test(msg="respond_locate_warps_to_annotate"):
                # Click locate button on a reference card — warp to Tab 1
                ref_panel = page.locator("[data-testid='respond-reference-panel']")
                ref_card = ref_panel.locator(
                    "[data-testid='respond-reference-card']"
                ).first
                locate_btn = ref_card.locator("button").first
                expect(locate_btn).to_be_visible(timeout=3000)
                locate_btn.click()
                page.wait_for_timeout(1000)

                # Verify Annotate tab is now active
                annotate_tab = page.get_by_test_id("tab-annotate")
                expect(annotate_tab).to_have_attribute(
                    "aria-selected", "true", timeout=3000
                )

            with subtests.test(msg="reload_persistence"):
                # Return to Annotate tab
                page.get_by_test_id("tab-annotate").click()

                # Reload page
                page.reload()

                # Wait for text walker to initialize
                wait_for_text_walker(page, timeout=15000)

                # Verify annotations persist after reload
                expect(
                    page.locator("[data-testid='annotation-card']").first
                ).to_be_visible(timeout=10000)
                expect(page.get_by_text(uuid1)).to_be_visible(timeout=10000)
                expect(page.get_by_text(uuid2)).to_be_visible(timeout=10000)

            with subtests.test(msg="export_pdf_with_annotations"):
                # Attempt PDF export with annotations
                try:
                    # Start download listener before clicking export
                    with page.expect_download(timeout=120000) as download_info:
                        page.get_by_role("button", name="Export PDF").click()

                    download = download_info.value
                    dl_path = Path(download.path())
                    content_bytes = dl_path.read_bytes()

                    # E2E server may produce .tex (fast mode) or .pdf (slow mode)
                    is_pdf = content_bytes[:5] == b"%PDF-"

                    if is_pdf:
                        assert len(content_bytes) > 20_000, (
                            f"PDF too small: {len(content_bytes)} bytes"
                        )
                        import pymupdf

                        doc = pymupdf.open(dl_path)
                        text = "".join(p.get_text() for p in doc)
                        doc.close()

                        import re

                        text = re.sub(r"-\n", "", text)
                    else:
                        text = content_bytes.decode("utf-8")

                    # Verify comment UUIDs in exported content
                    assert uuid1 in text, "First comment UUID not found"
                    assert uuid2 in text, "Second comment UUID not found"

                except PlaywrightTimeoutError:
                    pytest.skip("PDF export timed out (TinyTeX not installed?)")
                except PlaywrightError as e:
                    if "Download" in str(e):
                        pytest.skip(f"PDF download failed: {e}")
                    raise

        finally:
            # Cleanup
            page.close()
            context.close()
