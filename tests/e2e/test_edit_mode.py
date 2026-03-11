"""E2E tests for document edit mode in Manage Documents dialog.

Verifies that documents with zero annotations show an edit button,
the WYSIWYG editor opens with pre-populated content, and save persists
changes. Also verifies that annotated documents do NOT show an edit button.

Run with: uv run grimoire e2e run -k test_edit_mode

Traceability:
- Issue: #109 (File Upload Support)
- AC: file-upload-109.AC3.1, AC3.2
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from tests.e2e.annotation_helpers import wait_for_text_walker
from tests.e2e.conftest import _authenticate_page

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Browser, Page
    from pytest_subtests import SubTests


@pytest.fixture
def edit_ready_page(browser: Browser, app_server: str) -> Generator[Page]:
    """Authenticated page with clipboard permissions at a fresh workspace.

    Creates a workspace and pastes a document so the Manage Documents
    dialog has content to show.
    """
    from uuid import uuid4

    context = browser.new_context(
        permissions=["clipboard-read", "clipboard-write"],
    )
    page = context.new_page()

    unique_id = uuid4().hex[:8]
    email = f"edit-test-{unique_id}@test.example.edu.au"
    _authenticate_page(page, app_server, email=email)

    # Navigate to annotation and create workspace
    page.goto(f"{app_server}/annotation")
    page.get_by_test_id("create-workspace-btn").click()
    page.wait_for_url(re.compile(r"workspace_id="))

    # Paste HTML content to create a document
    html_content = "<p>Editable document content for testing.</p>"
    editor = page.get_by_test_id("content-editor")
    expect(editor).to_be_visible(timeout=5000)
    editor.click()

    page.evaluate(
        """(html) => {
            const plainText = html.replace(/<[^>]*>/g, '');
            return navigator.clipboard.write([
                new ClipboardItem({
                    'text/html': new Blob([html], { type: 'text/html' }),
                    'text/plain': new Blob([plainText], { type: 'text/plain' })
                })
            ]);
        }""",
        html_content,
    )

    page.keyboard.press("Control+v")
    expect(editor).to_contain_text("Content pasted", timeout=5000)

    page.get_by_test_id("add-document-btn").click()
    wait_for_text_walker(page, timeout=15000)

    yield page

    page.goto("about:blank")
    page.close()
    context.close()


@pytest.mark.e2e
class TestEditMode:
    """Verify edit mode in Manage Documents dialog."""

    def test_edit_button_visible_and_editor_opens(
        self,
        edit_ready_page: Page,
        subtests: SubTests,
    ) -> None:
        """Edit button visible for unannotated doc; editor opens with content (AC3.1).

        Steps:
        1. Open Manage Documents dialog
        2. Verify edit button is visible
        3. Click edit button
        4. Verify editor dialog opens with document content
        5. Modify content and save
        6. Verify save notification and document refresh
        """
        page = edit_ready_page

        with subtests.test(msg="open_manage_dialog"):
            manage_btn = page.get_by_test_id("manage-documents-btn")
            expect(manage_btn).to_be_visible(timeout=5000)
            manage_btn.click()

        with subtests.test(msg="edit_button_visible"):
            # Find any edit button (we don't know the doc UUID)
            edit_btn = page.locator('[data-testid^="edit-document-btn-"]')
            expect(edit_btn.first).to_be_visible(timeout=5000)

        with subtests.test(msg="click_edit_opens_editor"):
            edit_btn.first.click()
            # Editor dialog should open with content
            editor = page.get_by_test_id("document-editor")
            expect(editor).to_be_visible(timeout=5000)

        with subtests.test(msg="editor_has_content"):
            # The Quasar QEditor renders content in a contenteditable div
            # Check the editor contains our pasted text
            editor_area = page.get_by_test_id("document-editor")
            expect(editor_area).to_contain_text(
                "Editable document content", timeout=5000
            )

        with subtests.test(msg="save_persists_changes"):
            # Modify content via the editor's contenteditable area
            # QEditor has a .q-editor__content div that is contenteditable
            content_div = page.get_by_test_id("document-editor").locator(
                ".q-editor__content"
            )
            content_div.click()
            # Select all and type new content
            page.keyboard.press("Control+a")
            page.keyboard.type("Modified content via edit mode")

            save_btn = page.get_by_test_id("edit-save-btn")
            expect(save_btn).to_be_visible(timeout=3000)
            save_btn.click()

            # Wait for the dialog to close (save button disappears)
            expect(save_btn).not_to_be_visible(timeout=5000)

        with subtests.test(msg="document_shows_updated_content"):
            # The document view should refresh and show the new content
            wait_for_text_walker(page, timeout=15000)
            doc = page.get_by_test_id("doc-container")
            expect(doc).to_contain_text("Modified content via edit mode", timeout=10000)

    def test_edit_cancel_preserves_content(
        self,
        edit_ready_page: Page,
        subtests: SubTests,
    ) -> None:
        """Cancel in editor returns without saving (AC3.1).

        Steps:
        1. Open Manage Documents → click edit
        2. Modify content in editor
        3. Click Cancel
        4. Verify original content is preserved
        """
        page = edit_ready_page

        with subtests.test(msg="open_edit_dialog"):
            page.get_by_test_id("manage-documents-btn").click()
            edit_btn = page.locator('[data-testid^="edit-document-btn-"]')
            expect(edit_btn.first).to_be_visible(timeout=5000)
            edit_btn.first.click()
            expect(page.get_by_test_id("document-editor")).to_be_visible(timeout=5000)

        with subtests.test(msg="modify_and_cancel"):
            content_div = page.get_by_test_id("document-editor").locator(
                ".q-editor__content"
            )
            content_div.click()
            page.keyboard.press("Control+a")
            page.keyboard.type("This should not be saved")

            cancel_btn = page.get_by_test_id("edit-cancel-btn")
            cancel_btn.click()
            expect(cancel_btn).not_to_be_visible(timeout=5000)

        with subtests.test(msg="original_content_preserved"):
            doc = page.get_by_test_id("doc-container")
            expect(doc).to_contain_text("Editable document content", timeout=5000)
            expect(doc).not_to_contain_text("This should not be saved")

    def test_no_edit_button_for_annotated_document(
        self,
        edit_ready_page: Page,
        subtests: SubTests,
    ) -> None:
        """Annotated document does not show edit button (AC3.2).

        Steps:
        1. Create a highlight on the document (adding an annotation)
        2. Open Manage Documents dialog
        3. Verify no edit button is visible
        """
        from tests.e2e.annotation_helpers import select_chars

        page = edit_ready_page

        with subtests.test(msg="create_highlight"):
            # Select some text to create a highlight
            select_chars(page, 0, 10)

            # The highlight menu should appear — click the first tag
            highlight_menu = page.get_by_test_id("highlight-menu")
            expect(highlight_menu).to_be_visible(timeout=5000)
            # Click the first tag button in the highlight menu
            tag_btn = highlight_menu.locator("button").first
            tag_btn.click()
            # Wait for highlight to be created and dismiss any overlays
            page.wait_for_timeout(1000)
            # Click elsewhere to dismiss any lingering menus/dialogs
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

        with subtests.test(msg="no_edit_button"):
            manage_btn = page.get_by_test_id("manage-documents-btn")
            manage_btn.click()

            # The edit button should NOT be visible
            edit_btn = page.locator('[data-testid^="edit-document-btn-"]')
            expect(edit_btn).to_have_count(0, timeout=3000)

            # But delete button should still be visible
            delete_btn = page.locator('[data-testid^="delete-doc-btn-"]')
            expect(delete_btn.first).to_be_visible(timeout=3000)
