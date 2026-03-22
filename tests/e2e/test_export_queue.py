"""E2E tests: export queue page-load recovery (#402).

Validates that the annotation page recovers export state on page load:
- AC1.2: Client reconnects after compilation, download button appears.
- AC2.3: Page reload recovers export state (completed job -> download button).

These tests inject completed ExportJob rows directly into the DB rather
than running the full LaTeX pipeline.  This avoids pandoc/latexmk
dependencies and exercises the ``check_existing_export()`` recovery path
that runs on every annotation page load.

Traceability:
- Issue: #402 (Export queue decoupling)
- Design: docs/design-plans/2026-03-21-export-queue-402.md
"""

from __future__ import annotations

import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Browser

from promptgrimoire.docs.helpers import wait_for_text_walker
from tests.e2e.conftest import _authenticate_page
from tests.e2e.db_fixtures import _create_workspace_via_db


def _insert_completed_export_job(
    user_email: str,
    workspace_id: str,
    *,
    pdf_path: str,
    download_token: str | None = None,
) -> str:
    """Insert a completed ExportJob directly into the database.

    Creates a job in ``completed`` status with a valid download token
    and token_expires_at 24 hours in the future.  This simulates the
    state after the export worker has finished compilation.

    Args:
        user_email: Email of the user who owns the job.
        workspace_id: Workspace UUID (as string).
        pdf_path: Filesystem path to the PDF file.
        download_token: Optional explicit token; auto-generated if None.

    Returns:
        The download_token string.
    """
    from sqlalchemy import create_engine, text

    db_url = os.environ.get("DATABASE__URL", "")
    if not db_url:
        msg = "DATABASE__URL not configured"
        raise RuntimeError(msg)
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    engine = create_engine(sync_url)

    if download_token is None:
        download_token = uuid.uuid4().hex

    job_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    expires = now + timedelta(hours=24)

    with engine.begin() as conn:
        # Resolve user_id from email
        row = conn.execute(
            text('SELECT id FROM "user" WHERE email = :email'),
            {"email": user_email},
        ).first()
        if not row:
            msg = f"User not found in DB: {user_email}"
            raise RuntimeError(msg)
        user_id = row[0]

        conn.execute(
            text("""
                INSERT INTO export_job
                    (id, user_id, workspace_id, status, payload,
                     download_token, token_expires_at, pdf_path,
                     created_at, started_at, completed_at)
                VALUES
                    (CAST(:id AS uuid),
                     :user_id,
                     CAST(:ws AS uuid),
                     'completed',
                     :payload,
                     :token,
                     :expires,
                     :pdf_path,
                     :now,
                     :now,
                     :now)
            """),
            {
                "id": job_id,
                "user_id": user_id,
                "ws": workspace_id,
                "payload": "{}",
                "token": download_token,
                "expires": expires,
                "pdf_path": pdf_path,
                "now": now,
            },
        )

    engine.dispose()
    return download_token


def _create_dummy_pdf(directory: str | None = None) -> str:
    """Create a minimal valid PDF file in a temp directory.

    Returns the absolute path to the file.  The caller is responsible
    for cleanup (the temp directory is NOT auto-deleted).
    """
    # Minimal valid PDF (1 blank page)
    pdf_bytes = (
        b"%PDF-1.0\n"
        b"1 0 obj<</Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</MediaBox[0 0 612 792]>>endobj\n"
        b"trailer<</Root 1 0 R>>\n"
    )
    tmpdir = Path(tempfile.mkdtemp(prefix="e2e_export_", dir=directory))
    path = tmpdir / "export.pdf"
    path.write_bytes(pdf_bytes)
    return str(path)


@pytest.mark.e2e
class TestExportQueueRecovery:
    """Page-load recovery of export state (#402)."""

    def test_completed_export_shows_download_on_page_load(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """AC2.3: Page load with a completed export job shows download button.

        Inserts a completed ExportJob in the DB, navigates to the
        workspace, and verifies that ``check_existing_export()``
        renders the download button.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)
            workspace_id = _create_workspace_via_db(
                email,
                "<p>Export queue recovery test content word1 word2 word3.</p>",
                seed_tags=False,
            )

            # Create a dummy PDF and insert a completed job
            pdf_path = _create_dummy_pdf()
            _insert_completed_export_job(
                email,
                workspace_id,
                pdf_path=pdf_path,
            )

            # Navigate to the workspace -- check_existing_export() runs on load
            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            wait_for_text_walker(page, timeout=15000)

            # The download button should appear from page-load recovery
            download_btn = page.get_by_test_id("export-download-btn")
            download_btn.wait_for(state="visible", timeout=10000)
            assert download_btn.is_visible()

        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_download_button_persists_after_reload(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """AC1.2: Completed export download button reappears after page reload.

        Inserts a completed ExportJob, navigates to the workspace to
        see the download button, reloads the page, and verifies the
        button is still visible.  This exercises the reconnect-after-
        compilation recovery path.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)
            workspace_id = _create_workspace_via_db(
                email,
                "<p>Export reload test content word1 word2 word3.</p>",
                seed_tags=False,
            )

            pdf_path = _create_dummy_pdf()
            _insert_completed_export_job(
                email,
                workspace_id,
                pdf_path=pdf_path,
            )

            ws_url = f"{app_server}/annotation?workspace_id={workspace_id}"
            page.goto(ws_url)
            wait_for_text_walker(page, timeout=15000)

            # Verify download button on initial load
            download_btn = page.get_by_test_id("export-download-btn")
            download_btn.wait_for(state="visible", timeout=10000)
            assert download_btn.is_visible()

            # Reload the page
            page.reload()
            wait_for_text_walker(page, timeout=15000)

            # Download button should reappear after reload
            download_btn = page.get_by_test_id("export-download-btn")
            download_btn.wait_for(state="visible", timeout=10000)
            assert download_btn.is_visible()

        finally:
            page.goto("about:blank")
            page.close()
            context.close()

    def test_no_download_button_without_export_job(
        self,
        browser: Browser,
        app_server: str,
    ) -> None:
        """Negative case: no export job means no download button.

        Verifies that ``check_existing_export()`` correctly does
        nothing when no active export job exists for the user.
        """
        context = browser.new_context()
        page = context.new_page()

        try:
            email = _authenticate_page(page, app_server)
            workspace_id = _create_workspace_via_db(
                email,
                "<p>No export test content word1 word2 word3.</p>",
                seed_tags=False,
            )

            page.goto(f"{app_server}/annotation?workspace_id={workspace_id}")
            wait_for_text_walker(page, timeout=15000)

            # The export button should be visible (page fully loaded)
            export_btn = page.get_by_test_id("export-pdf-btn")
            export_btn.wait_for(state="visible", timeout=10000)

            # No download button should be present
            download_btn = page.get_by_test_id("export-download-btn")
            assert download_btn.count() == 0

        finally:
            page.goto("about:blank")
            page.close()
            context.close()
