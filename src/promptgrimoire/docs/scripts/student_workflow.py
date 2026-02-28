"""Student workflow guide - produces markdown with annotated screenshots.

Drives a Playwright browser through the full student annotation workflow:
login, navigate, create workspace, paste content, highlight text, add
comment, organise tab, respond tab, and export PDF. Each step uses the
Guide DSL to emit narrative markdown with highlighted screenshots.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

from promptgrimoire.docs import Guide
from promptgrimoire.docs.helpers import select_chars, wait_for_text_walker

GUIDE_OUTPUT_DIR = Path("docs/guides")

_SAMPLE_HTML = (
    '<div class="conversation">'
    '<div class="user"><p><strong>Human:</strong> What are the key challenges'
    " in translating legal documents between English and Japanese?</p></div>"
    '<div class="assistant"><p><strong>Assistant:</strong> Legal translation'
    " between English and Japanese faces several key challenges:</p>"
    "<ol>"
    "<li><strong>Structural differences:</strong> Japanese legal writing uses"
    " longer sentences with nested clauses, while English prefers shorter,"
    " more direct constructions.</li>"
    "<li><strong>Terminology gaps:</strong> Some legal concepts exist in one"
    " system but not the other. For example, the Japanese concept of"
    " <em>good faith</em> has nuances that differ from common law"
    " interpretations.</li>"
    "<li><strong>Formality registers:</strong> Japanese legal language uses"
    " highly formal registers that have no direct English equivalent.</li>"
    "</ol></div></div>"
)


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
    """Step 3: Click Start to create a workspace."""
    with guide.step("Step 3: Creating a Workspace") as g:
        g.note(
            "Click Start on the activity to create your workspace. "
            "The workspace inherits the tag configuration set by your instructor."
        )
        start_btn = page.locator('[data-testid^="start-activity-btn"]')
        start_btn.first.click()

        page.get_by_test_id("content-editor").wait_for(state="visible", timeout=15000)
        g.screenshot(
            "New workspace on the annotation page",
            highlight=["content-editor"],
        )
        g.note(
            "Your workspace is created. You are now on the annotation page "
            "with three tabs: Annotate, Organise, and Respond."
        )


def _step_paste_content(page: Page, guide: Guide) -> None:
    """Step 4: Paste AI conversation content.

    Uses page.evaluate() to set innerHTML on the Quasar QEditor's
    contenteditable div. This is a known exception to the data-testid
    convention: Playwright's fill() does not work on contenteditable
    elements for HTML content. This matches the original bash script's
    approach and is acceptable in guide scripts.
    """
    with guide.step("Step 4: Pasting Your AI Conversation") as g:
        g.note(
            "Copy your AI conversation from ChatGPT, Claude, or another tool. "
            "Then paste it into the editor."
        )

        # Inject sample HTML into the QEditor contenteditable div.
        # Uses .q-editor__content - a known exception: Quasar renders this
        # div internally and our code cannot attach a data-testid to it.
        # Same pattern used in E2E tests and the instructor guide.
        #
        # Security note: innerHTML is used here with static, hardcoded content
        # (not user-supplied) to populate the contenteditable editor.
        # Playwright's fill() does not support HTML in contenteditable divs.
        page.evaluate(
            """(html) => {
                const el = document.querySelector(
                    '[data-testid="content-editor"] .q-editor__content'
                );
                el.focus();
                el.innerHTML = html;
                el.dispatchEvent(new Event('input', {bubbles: true}));
            }""",
            _SAMPLE_HTML,
        )
        g.screenshot(
            "AI conversation pasted into the editor",
            highlight=["content-editor"],
        )
        g.note(
            "Paste your AI conversation into the editor. "
            "PromptGrimoire accepts content from ChatGPT, Claude, and other tools."
        )

        page.get_by_test_id("add-document-btn").click()

        confirm_btn = page.get_by_test_id("confirm-content-type-btn")
        confirm_btn.wait_for(state="visible", timeout=5000)
        g.screenshot(
            "Content type confirmation dialog",
            highlight=["confirm-content-type-btn"],
        )
        g.note(
            "PromptGrimoire detects the content type. "
            "Confirm the detected type or change it, then click Confirm."
        )
        confirm_btn.click()

        wait_for_text_walker(page, timeout=15000)
        g.screenshot(
            "Processed conversation with formatted turns",
        )
        g.note("Your conversation is now processed and displayed with formatted turns.")


def _step_highlight_text(page: Page, guide: Guide) -> None:
    """Step 5: Select text and apply a tag to create a highlight."""
    with guide.step("Step 5: Annotating - Creating a Highlight") as g:
        g.note(
            "Select text in the conversation to highlight it. "
            "A tag menu appears so you can categorise the highlight."
        )

        # Select chars 0-50 (beginning of the first text content)
        select_chars(page, 0, 50)
        page.wait_for_timeout(500)

        # Click the first tag button in the toolbar
        tag_button = page.locator("[data-testid='tag-toolbar'] button").first
        tag_button.wait_for(state="visible", timeout=5000)
        tag_button.click()
        page.wait_for_timeout(1000)

        g.screenshot(
            "Text highlighted and tagged with colour coding",
            highlight=["tag-toolbar", "annotation-card"],
        )
        g.note(
            "Select text and click a tag in the popup menu to create a highlight. "
            "The text is colour-coded by tag."
        )


def _step_add_comment(page: Page, guide: Guide) -> None:
    """Step 6: Add a comment to the annotation card."""
    with guide.step("Step 6: Adding a Comment") as g:
        g.note(
            "Click on a highlighted section to select it, "
            "then type a comment in the sidebar."
        )

        card = page.locator("[data-testid='annotation-card']").first
        card.wait_for(state="visible", timeout=10000)

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
    """Step 7: Switch to the Organise tab."""
    with guide.step("Step 7: Organising by Tag") as g:
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
    """Step 8: Switch to the Respond tab and write a response."""
    with guide.step("Step 8: Writing Your Response") as g:
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
    """Step 9: Export to PDF."""
    with guide.step("Step 9: Exporting to PDF") as g:
        g.note("Click Export PDF to generate a PDF of your complete annotation work.")

        # Switch back to Annotate tab for the export button
        page.get_by_test_id("tab-annotate").click()
        page.wait_for_timeout(500)

        g.screenshot(
            "Export PDF button on the annotation page",
            highlight=["export-pdf-btn"],
        )
        g.note(
            "The exported PDF includes your pasted conversation with highlights, "
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
        _step_paste_content(page, guide)
        _step_highlight_text(page, guide)
        _step_add_comment(page, guide)
        _step_organise_tab(page, guide)
        _step_respond_tab(page, guide)
        _step_export_pdf(page, guide)
