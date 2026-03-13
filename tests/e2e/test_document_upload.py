"""E2E tests for no-reload document addition.

Verifies that adding a document via paste or file upload renders
it in-place without URL change or full page rebuild (AC4.1).

Also provides partial E2E coverage for DOCX upload-to-annotate
(AC1.2) and PDF upload-to-annotate (AC2.2).

Run with: uv run grimoire e2e run -k test_document_upload

Traceability:
- Issue: #109 (File Upload Support)
- AC: file-upload-109.AC4.1, AC1.2, AC2.2
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from promptgrimoire.docs.helpers import wait_for_text_walker
from tests.e2e.conftest import _authenticate_page
from tests.e2e.paste_helpers import simulate_paste

if TYPE_CHECKING:
    from collections.abc import Generator

    from playwright.sync_api import Browser, Page
    from pytest_subtests import SubTests

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def upload_ready_page(browser: Browser, app_server: str) -> Generator[Page]:
    """Authenticated page at a fresh workspace."""
    from uuid import uuid4

    context = browser.new_context()
    page = context.new_page()

    unique_id = uuid4().hex[:8]
    email = f"upload-test-{unique_id}@test.example.edu.au"
    _authenticate_page(page, app_server, email=email)

    # Navigate to annotation and create workspace
    page.goto(f"{app_server}/annotation")
    page.get_by_test_id("create-workspace-btn").click()
    page.wait_for_url(re.compile(r"workspace_id="))

    yield page

    page.goto("about:blank")
    page.close()
    context.close()


def _paste_html_and_add(page: Page, html_content: str) -> None:
    """Paste HTML into the editor and click Add Document.

    For pasted HTML, the content type dialog is skipped (auto-detected
    as HTML by content_form.py).
    """
    editor = page.get_by_test_id("content-editor")
    expect(editor).to_be_visible(timeout=5000)
    editor.click()

    simulate_paste(page, html_content)
    expect(editor).to_contain_text("Content pasted", timeout=5000)

    page.get_by_test_id("add-document-btn").click()


@pytest.mark.e2e
class TestDocumentUploadNoReload:
    """Verify document addition renders in-place without page reload."""

    def test_paste_renders_without_url_change(
        self,
        upload_ready_page: Page,
        subtests: SubTests,
    ) -> None:
        """Paste HTML content and verify in-place render (AC4.1).

        Steps:
        1. Capture URL before paste
        2. Paste HTML and add document
        3. Verify document text appears
        4. Verify URL did not change
        5. Verify content form is still present
        """
        page = upload_ready_page
        url_before = page.url

        html_content = (
            "<p>The quick brown fox jumps over the lazy dog. "
            "This sentence verifies paste-to-annotate rendering.</p>"
        )

        with subtests.test(msg="paste_and_add"):
            _paste_html_and_add(page, html_content)
            wait_for_text_walker(page, timeout=15000)

        with subtests.test(msg="document_text_visible"):
            doc = page.get_by_test_id("doc-container")
            expect(doc).to_contain_text(
                "The quick brown fox jumps over the lazy dog",
                timeout=10000,
            )

        with subtests.test(msg="url_unchanged"):
            assert page.url == url_before, (
                f"URL changed after paste: {url_before!r} -> {page.url!r}"
            )

        with subtests.test(msg="content_form_hidden_after_add"):
            # With multi-document disabled (default), the content form
            # hides after the first document is added.
            add_btn = page.get_by_test_id("add-document-btn")
            expect(add_btn).not_to_be_visible(timeout=5000)

    def test_docx_upload_renders_without_url_change(
        self,
        upload_ready_page: Page,
        subtests: SubTests,
    ) -> None:
        """Upload a DOCX file and verify in-place render (AC1.2, AC4.1).

        Uses the test fixture DOCX to verify the full upload-to-annotate
        pipeline via the UI.
        """
        page = upload_ready_page
        url_before = page.url

        docx_path = FIXTURES_DIR / "2025FCA0796 - Summary.docx"
        if not docx_path.exists():
            pytest.skip(f"DOCX fixture not found: {docx_path}")

        with subtests.test(msg="upload_docx"):
            # NiceGUI ui.upload renders as a Quasar QUploader.
            # Use Playwright's set_input_files on the hidden <input type="file">.
            # Quasar QUploader hides the native input — no data-testid possible here
            file_input = page.locator('input[type="file"]')
            file_input.set_input_files(str(docx_path))

            # The upload triggers the content type confirmation dialog
            confirm_btn = page.get_by_test_id("confirm-content-type-btn")
            confirm_btn.wait_for(state="visible", timeout=10000)
            confirm_btn.click()

            # Wait for document to render
            wait_for_text_walker(page, timeout=30000)

        with subtests.test(msg="docx_text_visible"):
            doc = page.get_by_test_id("doc-container")
            # The DOCX contains a court case summary — check for text
            # that should survive mammoth conversion
            expect(doc).to_contain_text("2025", timeout=10000)

        with subtests.test(msg="url_unchanged_after_upload"):
            assert page.url == url_before, (
                f"URL changed after upload: {url_before!r} -> {page.url!r}"
            )

        with subtests.test(msg="content_form_hidden_after_upload"):
            # With multi-document disabled (default), the content form
            # hides after the first document is added.
            add_btn = page.get_by_test_id("add-document-btn")
            expect(add_btn).not_to_be_visible(timeout=5000)

    def test_pdf_upload_renders_without_url_change(
        self,
        upload_ready_page: Page,
        subtests: SubTests,
    ) -> None:
        """Upload a PDF file and verify in-place render (AC2.2, AC4.1).

        Uses the test fixture PDF to verify the full upload-to-annotate
        pipeline via the UI.
        """
        page = upload_ready_page
        url_before = page.url

        pdf_path = FIXTURES_DIR / "Lawlis v R [2025] NSWCCA 183 (3 November 2025).pdf"
        if not pdf_path.exists():
            pytest.skip(f"PDF fixture not found: {pdf_path}")

        with subtests.test(msg="upload_pdf"):
            # Quasar QUploader hides the native input — no data-testid possible here
            file_input = page.locator('input[type="file"]')
            file_input.set_input_files(str(pdf_path))

            # The upload triggers the content type confirmation dialog
            confirm_btn = page.get_by_test_id("confirm-content-type-btn")
            confirm_btn.wait_for(state="visible", timeout=10000)
            confirm_btn.click()

            # Wait for document to render (PDF extraction can be slow)
            wait_for_text_walker(page, timeout=30000)

        with subtests.test(msg="pdf_text_visible"):
            doc = page.get_by_test_id("doc-container")
            # The PDF is a court case — check for text that should
            # survive PDF extraction
            expect(doc).to_contain_text("Lawlis", timeout=10000)

        with subtests.test(msg="url_unchanged_after_pdf"):
            assert page.url == url_before, (
                f"URL changed after PDF upload: {url_before!r} -> {page.url!r}"
            )

        with subtests.test(msg="content_form_hidden_after_pdf"):
            # With multi-document disabled (default), the content form
            # hides after the first document is added.
            add_btn = page.get_by_test_id("add-document-btn")
            expect(add_btn).not_to_be_visible(timeout=5000)
