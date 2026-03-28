"""E2E tests for document edit mode in Manage Documents dialog.

Verifies that documents with zero annotations show an edit button,
the WYSIWYG editor opens with pre-populated content, and save persists
changes. Also verifies that annotated documents do NOT show an edit button.

Also verifies paragraph_map consistency after a Quill editor save:
the Quasar QEditor normalises HTML (adds wrapper <p> tags, <br> for
empty paragraphs). The resulting paragraph_map must be consistent with
the actual saved HTML content — every char-offset key must correspond
to the start of a real paragraph in the stored document.

Run with: uv run grimoire e2e run -k test_edit_mode

Traceability:
- Issue: #109 (File Upload Support)
- AC: file-upload-109.AC3.1, AC3.2, AC3.3
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from promptgrimoire.docs.helpers import (
    wait_for_annotation_ready,
    wait_for_text_walker,
)
from tests.e2e.conftest import _authenticate_page
from tests.e2e.paste_helpers import simulate_paste

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Browser, Page
    from pytest_subtests import SubTests


def _fetch_document_db_state(workspace_id: str) -> dict[str, object]:
    """Query the DB for the first document in a workspace.

    Returns a dict with ``content`` (str), ``paragraph_map`` (dict[str, int]),
    and ``doc_id`` (str).  Used to verify DB state after an E2E save operation.

    Follows the sync DB pattern from ``conftest._grant_workspace_access``.

    Args:
        workspace_id: UUID string of the workspace.

    Returns:
        Dict with keys ``doc_id``, ``content``, and ``paragraph_map``.

    Raises:
        RuntimeError: If DATABASE__URL is not configured or no document found.
    """
    from sqlalchemy import create_engine, text

    from promptgrimoire.config import get_settings

    db_url = str(get_settings().database.url)
    if not db_url:
        msg = "DATABASE__URL not configured"
        raise RuntimeError(msg)
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    engine = create_engine(sync_url)

    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT id, content, paragraph_map"
                " FROM workspace_document"
                " WHERE workspace_id = CAST(:ws AS uuid)"
                " ORDER BY order_index, created_at"
                " LIMIT 1"
            ),
            {"ws": workspace_id},
        ).first()
    engine.dispose()

    if row is None:
        msg = f"No documents found in workspace {workspace_id}"
        raise RuntimeError(msg)

    raw_map = row[2]
    # psycopg returns jsonb as a dict; guard for str in case of driver variance
    if isinstance(raw_map, str):
        raw_map = json.loads(raw_map)
    return {
        "doc_id": str(row[0]),
        "content": row[1] or "",
        "paragraph_map": raw_map or {},
    }


@pytest.fixture
def edit_ready_page(browser: Browser, app_server: str) -> Generator[Page]:
    """Authenticated page with clipboard permissions at a fresh workspace.

    Creates a workspace and pastes a document so the Manage Documents
    dialog has content to show.
    """
    from uuid import uuid4

    context = browser.new_context()
    page = context.new_page()

    unique_id = uuid4().hex[:8]
    email = f"edit-test-{unique_id}@test.example.edu.au"
    _authenticate_page(page, app_server, email=email)

    # Navigate to annotation and create workspace
    page.goto(f"{app_server}/annotation")
    page.get_by_test_id("create-workspace-btn").click()
    page.wait_for_url(re.compile(r"workspace_id="))
    wait_for_annotation_ready(page)

    # Paste HTML content to create a document via synthetic paste event
    html_content = "<p>Editable document content for testing.</p>"
    editor = page.get_by_test_id("content-editor")
    expect(editor).to_be_visible(timeout=5000)
    editor.click()

    simulate_paste(page, html_content)
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
        url_before = page.url

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

        with subtests.test(msg="url_unchanged_after_edit_save"):
            # AC4.2: edit-save must not change the URL
            assert page.url == url_before, (
                f"URL changed after edit-save: {url_before!r} -> {page.url!r}"
            )

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
        from tests.e2e.highlight_tools import select_text_range, wait_for_css_highlight

        page = edit_ready_page

        with subtests.test(msg="create_highlight"):
            # Select text to trigger the highlight menu
            select_text_range(page, "Editable document")

            # No tags exist yet — use quick-create to make one and apply it
            highlight_menu = page.get_by_test_id("highlight-menu")
            expect(highlight_menu).to_be_visible(timeout=5000)
            highlight_menu.get_by_test_id("highlight-menu-new-tag").click()

            dialog = page.locator("[data-testid='tag-quick-create-dialog']")
            expect(dialog).to_be_visible(timeout=5000)
            dialog.get_by_test_id("tag-quick-create-name-input").fill("TestTag")
            dialog.get_by_test_id("quick-create-save-btn").click()
            expect(dialog).to_be_hidden(timeout=5000)

            # Wait for highlight to be created
            wait_for_css_highlight(page)
            page.keyboard.press("Escape")
            expect(highlight_menu).not_to_be_visible(timeout=5000)

        with subtests.test(msg="no_edit_button"):
            manage_btn = page.get_by_test_id("manage-documents-btn")
            manage_btn.click()

            # The edit button should NOT be visible
            edit_btn = page.locator('[data-testid^="edit-document-btn-"]')
            expect(edit_btn).to_have_count(0, timeout=3000)

            # But delete button should still be visible
            delete_btn = page.locator('[data-testid^="delete-doc-btn-"]')
            expect(delete_btn.first).to_be_visible(timeout=3000)

    def test_paragraph_map_consistency_after_quill_save(
        self,
        edit_ready_page: Page,
        subtests: SubTests,
    ) -> None:
        """paragraph_map is consistent with saved HTML after Quill editor save (AC3.3).

        The Quasar QEditor normalises HTML — adding wrapper <p> tags, converting
        newlines to <br>, and potentially altering attributes.  This test verifies
        that after a save via the editor UI, the ``paragraph_map`` stored in the DB
        is consistent with the actual saved ``content``:

        - Every char-offset key in paragraph_map corresponds to the start of a
          real paragraph in the extracted plain text.
        - Paragraph numbers are sequential positive integers starting at 1.
        - The stored paragraph_map matches a fresh recomputation from the
          saved content (no stale offsets from the pre-edit content remain).

        Steps:
        1. Open Manage Documents → click edit
        2. Type multi-paragraph content and save
        3. Query DB for stored content and paragraph_map
        4. Recompute paragraph_map from the stored content
        5. Assert stored map equals recomputed map
        """
        from promptgrimoire.input_pipeline import build_paragraph_map_for_json

        page = edit_ready_page

        # Extract workspace_id from the URL so we can query the DB
        workspace_id_match = re.search(r"workspace_id=([^&]+)", page.url)
        assert workspace_id_match, f"No workspace_id in URL: {page.url}"
        workspace_id = workspace_id_match.group(1)

        with subtests.test(msg="open_and_save_via_editor"):
            page.get_by_test_id("manage-documents-btn").click()
            edit_btn = page.locator('[data-testid^="edit-document-btn-"]')
            expect(edit_btn.first).to_be_visible(timeout=5000)
            edit_btn.first.click()

            expect(page.get_by_test_id("document-editor")).to_be_visible(timeout=5000)

            # Type two distinct paragraphs so the paragraph_map has multiple entries.
            # Quill wraps each paragraph in <p>…</p>, so pressing Enter creates a
            # new <p> element — meaning build_paragraph_map produces 2 entries.
            content_div = page.get_by_test_id("document-editor").locator(
                ".q-editor__content"
            )
            content_div.click()
            page.keyboard.press("Control+a")
            page.keyboard.type("First paragraph text")
            page.keyboard.press("Enter")
            page.keyboard.type("Second paragraph text")

            save_btn = page.get_by_test_id("edit-save-btn")
            expect(save_btn).to_be_visible(timeout=3000)
            save_btn.click()
            # Wait for dialog to close before querying DB
            expect(save_btn).not_to_be_visible(timeout=5000)

        with subtests.test(msg="paragraph_map_matches_saved_content"):
            from promptgrimoire.input_pipeline import build_paragraph_map_for_json

            # Wait for document view to refresh — proves the DB write is flushed
            wait_for_text_walker(page, timeout=15000)
            doc = page.get_by_test_id("doc-container")
            expect(doc).to_contain_text("Second paragraph text", timeout=10000)

            db_state = _fetch_document_db_state(workspace_id)
            saved_content: str = db_state["content"]  # type: ignore[assignment]
            stored_map: dict[str, int] = db_state["paragraph_map"]  # type: ignore[assignment]

            # Recompute from saved HTML — same function used by update_document_content
            expected_map = build_paragraph_map_for_json(saved_content, auto_number=True)

            # The stored map must exactly match a fresh recomputation —
            # no stale char offsets from before the edit should remain
            assert stored_map == expected_map, (
                f"paragraph_map mismatch after Quill save.\n"
                f"stored:   {stored_map}\n"
                f"expected: {expected_map}\n"
                f"content:  {saved_content!r}"
            )

        with subtests.test(msg="paragraph_map_has_sequential_numbers"):
            stored_map = db_state["paragraph_map"]  # type: ignore[assignment]
            para_numbers = sorted(stored_map.values())
            assert para_numbers, "paragraph_map should not be empty after save"
            assert para_numbers[0] == 1, (
                f"paragraph numbers should start at 1, got {para_numbers[0]}"
            )
            assert para_numbers == list(range(1, len(para_numbers) + 1)), (
                f"paragraph numbers should be sequential: {para_numbers}"
            )
