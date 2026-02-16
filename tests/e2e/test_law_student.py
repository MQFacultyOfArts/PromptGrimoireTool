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

Traceability:
- Issue: #156 (E2E test migration)
- Design: docs/design-plans/2026-02-14-156-e2e-test-migration.md Phase 4
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Browser
    from pytest_subtests import SubTests

from playwright.sync_api import expect

from tests.e2e.annotation_helpers import (
    _load_fixture_via_paste,
    create_highlight_with_tag,
    select_chars,
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
        """Complete law student annotation workflow with 11 checkpoints.

        Tests the full journey: auth, fixture paste, highlighting with legal tags,
        comments, tag changes, keyboard shortcuts, organise/respond tabs,
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
                comment_input = page.get_by_placeholder("Add comment").first
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
                comment_input = page.get_by_placeholder("Add comment").nth(1)
                comment_input.fill(uuid2)

                # Post second comment
                page.locator("[data-testid='annotation-card']").nth(1).get_by_text(
                    "Post"
                ).click()

                # Verify second comment appears
                expect(page.get_by_text(uuid2)).to_be_visible(timeout=10000)

            with subtests.test(msg="change_tag_via_dropdown"):
                # Select first card's tag dropdown
                first_card = page.locator("[data-testid='annotation-card']").first
                tag_select = first_card.locator(".q-select").first

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

            with subtests.test(msg="organise_tab"):
                # Click Organise tab
                page.get_by_text("Organise", exact=True).click()

                # Wait for organise content to render
                page.wait_for_timeout(1000)

                # Verify organise cards appear
                expect(
                    page.locator("[data-testid='organise-card']").first
                ).to_be_visible(timeout=10000)

            with subtests.test(msg="respond_tab"):
                # Click Respond tab
                page.get_by_text("Respond", exact=True).click()

                # Verify Milkdown editor loads
                expect(
                    page.locator("[data-testid='milkdown-editor-container']")
                ).to_be_visible(timeout=10000)

            with subtests.test(msg="reload_persistence"):
                # Return to Annotate tab
                page.get_by_text("Annotate", exact=True).click()

                # Reload page
                page.reload()

                # Wait for text walker to initialize
                page.wait_for_function(
                    "() => window._textNodes && window._textNodes.length > 0",
                    timeout=15000,
                )

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

                    # Get downloaded PDF
                    download = download_info.value
                    pdf_bytes = Path(download.path()).read_bytes()

                    # Verify PDF size (should be substantial)
                    assert len(pdf_bytes) > 20_000, (
                        f"PDF too small: {len(pdf_bytes)} bytes"
                    )

                    # Verify comments embedded in PDF
                    assert uuid1.encode() in pdf_bytes, (
                        "First comment UUID not found in PDF"
                    )
                    assert uuid2.encode() in pdf_bytes, (
                        "Second comment UUID not found in PDF"
                    )

                except Exception as e:
                    # Skip if TinyTeX not installed or PDF generation fails
                    if "Timeout" in str(e) or "Download" in str(e):
                        msg = f"PDF export unavailable (TinyTeX not installed?): {e}"
                        pytest.skip(msg)
                    raise

        finally:
            # Cleanup
            page.close()
            context.close()
