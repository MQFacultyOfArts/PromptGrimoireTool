"""Student workflow guide - produces markdown with annotated screenshots.

Drives a Playwright browser through the full student annotation workflow:
login, navigate, create workspace, highlight text, add comment, organise
tab, respond tab, and export PDF. Each step uses the Guide DSL to emit
narrative markdown with highlighted screenshots.

The student workspace is cloned from the instructor's template, so it
already contains content and tag configuration. No paste step is needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

from promptgrimoire.docs import Guide
from promptgrimoire.docs.helpers import select_chars, wait_for_text_walker

GUIDE_OUTPUT_DIR = Path("docs/guides")


def _authenticate(page: Page, base_url: str, email: str) -> None:
    """Authenticate via mock token and wait for redirect."""
    page.goto(f"{base_url}/auth/callback?token=mock-token-{email}")
    page.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10000)


# ---------------------------------------------------------------------------
# Per-step functions
# ---------------------------------------------------------------------------


def _step_login(page: Page, base_url: str, guide: Guide) -> None:
    """Step 1: Login and see the Navigator."""
    with guide.step("Step 1: Logging In") as g:
        _authenticate(page, base_url, "student-demo@test.example.edu.au")
        g.note(
            "After logging in, you see the Navigator - your home page. "
            "Activities assigned by your instructor appear here."
        )


def _step_navigate_to_activity(page: Page, guide: Guide) -> None:
    """Step 2: Find the activity on the Navigator."""
    with guide.step("Step 2: Finding Your Activity") as g:
        g.note(
            "The Navigator shows activities available to you. "
            "Find the activity your instructor created."
        )
        start_btn = page.locator('[data-testid^="start-activity-btn"]')
        start_btn.first.wait_for(state="visible", timeout=10000)
        g.screenshot(
            "Navigator showing the unit and activity",
            highlight=["start-activity-btn"],
        )
        g.note("You can see the unit and activity on your Navigator.")


def _step_create_workspace(page: Page, guide: Guide) -> None:
    """Step 3: Click Start to create a workspace.

    The cloned workspace inherits content and tags from the instructor's
    template, so the annotation page renders existing content immediately
    (no paste step needed).
    """
    with guide.step("Step 3: Creating a Workspace") as g:
        g.note(
            "Click Start on the activity to create your workspace. "
            "The workspace inherits the content and tag configuration "
            "set by your instructor."
        )
        start_btn = page.locator('[data-testid^="start-activity-btn"]')
        start_btn.first.click()

        wait_for_text_walker(page, timeout=15000)
        g.screenshot(
            "New workspace on the annotation page with inherited content",
        )
        g.note(
            "Your workspace is created with the instructor's content already loaded. "
            "You are now on the annotation page "
            "with three tabs: Annotate, Organise, and Respond."
        )


def _step_highlight_text(page: Page, guide: Guide) -> None:
    """Step 4: Select text and apply a tag to create a highlight."""
    with guide.step("Step 4: Annotating - Creating a Highlight") as g:
        g.note(
            "Select text in the conversation to highlight it. "
            "A tag menu appears so you can categorise the highlight."
        )

        # Select chars 0-50 (beginning of the first text content)
        select_chars(page, 0, 50)
        page.wait_for_timeout(500)

        # Click the first tag button in the toolbar
        tag_button = page.locator('[data-testid^="tag-btn-"]').first
        tag_button.wait_for(state="visible", timeout=5000)
        tag_button.click()
        page.locator("[data-testid='annotation-card']").first.wait_for(
            state="visible", timeout=5000
        )

        g.screenshot(
            "Text highlighted and tagged with colour coding",
            highlight=["tag-toolbar", "annotation-card"],
        )
        g.note(
            "Select text and click a tag in the popup menu to create a highlight. "
            "The text is colour-coded by tag."
        )


def _step_add_comment(page: Page, guide: Guide) -> None:
    """Step 5: Add a comment to the annotation card."""
    with guide.step("Step 5: Adding a Comment") as g:
        g.note(
            "Click on a highlighted section to select it, "
            "then type a comment in the sidebar."
        )

        card = page.locator("[data-testid='annotation-card']").first
        card.wait_for(state="visible", timeout=10000)

        # Click the expand chevron to open the detail section (collapsed
        # by default) which contains the comment input.
        card.get_by_test_id("card-expand-btn").click()
        card.get_by_test_id("card-detail").wait_for(state="visible", timeout=5000)

        comment_input = card.get_by_test_id("comment-input")
        comment_input.fill(
            "This passage highlights key structural differences "
            "between legal writing traditions."
        )
        card.get_by_test_id("post-comment-btn").click()
        page.wait_for_timeout(1000)

        g.screenshot(
            "Comment added to a highlight in the sidebar",
            highlight=["comment-input"],
        )
        g.note(
            "Comments appear below each highlight in the sidebar. "
            "Use comments to record your analysis."
        )


def _step_organise_tab(page: Page, guide: Guide) -> None:
    """Step 6: Switch to the Organise tab."""
    with guide.step("Step 6: Organising by Tag") as g:
        g.note("Switch to the Organise tab to view your annotations grouped by tag.")

        page.get_by_test_id("tab-organise").click()
        page.get_by_test_id("organise-columns").wait_for(state="visible", timeout=10000)
        page.wait_for_timeout(1000)

        g.screenshot(
            "Organise tab with highlights grouped by tag",
            highlight=["organise-columns"],
        )
        g.note(
            "The Organise tab shows your highlights in columns by tag. "
            "You can drag highlights between columns to reclassify them."
        )


def _step_respond_tab(page: Page, guide: Guide) -> None:
    """Step 7: Switch to the Respond tab and write a response."""
    with guide.step("Step 7: Writing Your Response") as g:
        g.note(
            "Switch to the Respond tab to write your analysis. "
            "Your highlights appear in the reference panel on the right."
        )

        page.get_by_test_id("tab-respond").click()
        page.get_by_test_id("milkdown-editor-container").wait_for(
            state="visible", timeout=10000
        )

        # Insert content into the Milkdown editor via JS.
        # Milkdown uses a contenteditable div - same exception as QEditor.
        # Security note: static hardcoded content, not user-supplied.
        # Use [contenteditable="true"] to avoid the ProseMirror virtual
        # cursor element (contenteditable="false") which causes strict
        # mode violations.
        page.locator(
            '[data-testid="milkdown-editor-container"] [contenteditable="true"]'
        ).wait_for(state="visible", timeout=5000)
        page.evaluate(
            """() => {
                const editor = document.querySelector(
                    '[data-testid="milkdown-editor-container"]'
                    + ' [contenteditable="true"]'
                );
                editor.focus();
                editor.innerHTML = '<p>This analysis examines the translation '
                    + 'challenges identified in the AI conversation. The key '
                    + 'structural differences between English and Japanese '
                    + 'legal writing highlight the importance of understanding '
                    + 'both legal systems.</p>';
                editor.dispatchEvent(new Event('input', {bubbles: true}));
            }"""
        )
        page.wait_for_timeout(1000)

        g.screenshot(
            "Respond tab with markdown editor and highlight references",
            highlight=["milkdown-editor-container", "respond-reference-panel"],
        )
        g.note(
            "The Respond tab has a markdown editor on the left and your "
            "highlights as reference on the right. Write your analysis "
            "using the highlights as evidence."
        )


def _step_export_pdf(page: Page, guide: Guide) -> None:
    """Step 8: Export to PDF."""
    with guide.step("Step 8: Exporting to PDF") as g:
        g.note("Click Export PDF to generate a PDF of your complete annotation work.")

        # Switch back to source tab for the export button
        page.get_by_test_id("tab-source-1").click()
        page.get_by_test_id("export-pdf-btn").wait_for(state="visible", timeout=5000)

        g.screenshot(
            "Export PDF button on the annotation page",
            highlight=["export-pdf-btn"],
        )
        g.note(
            "The exported PDF includes your conversation with highlights, "
            "comments, organised notes, and your written response."
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_student_guide(page: Page, base_url: str) -> None:
    """Run the student workflow guide, producing markdown and screenshots."""
    with Guide("Student Workflow", GUIDE_OUTPUT_DIR, page) as guide:
        _step_login(page, base_url, guide)
        _step_navigate_to_activity(page, guide)
        _step_create_workspace(page, guide)
        _step_highlight_text(page, guide)
        _step_add_comment(page, guide)
        _step_organise_tab(page, guide)
        _step_respond_tab(page, guide)
        _step_export_pdf(page, guide)
