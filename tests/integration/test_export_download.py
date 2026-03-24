"""Integration tests for the export download route.

Requires a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Acceptance Criteria:
- AC3.1: Valid token -> 200 with application/pdf
- AC3.2: Same token twice -> both return 200 (multi-use)
- AC3.3: Expired token -> 404
- AC3.4: Nonexistent token -> 404
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import httpx
import pytest

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


async def _create_user_and_workspace() -> tuple:
    """Create a test user and workspace, returning (user_id, workspace_id)."""
    from promptgrimoire.db.users import create_user
    from promptgrimoire.db.workspaces import create_workspace

    tag = uuid4().hex[:8]
    user = await create_user(
        email=f"download-{tag}@test.local",
        display_name=f"Download Test {tag}",
    )
    workspace = await create_workspace()
    return user.id, workspace.id


async def _create_completed_job(
    pdf_path: str,
    token: str | None = None,
    expired: bool = False,
) -> str:
    """Create a completed export job and return its download token."""
    from promptgrimoire.db.export_jobs import complete_job, create_export_job

    user_id, workspace_id = await _create_user_and_workspace()
    job = await create_export_job(user_id, workspace_id, {"format": "pdf"})

    download_token = token or uuid4().hex
    await complete_job(job.id, download_token, pdf_path)

    if expired:
        # Manually expire the token by updating token_expires_at
        from promptgrimoire.db.engine import get_session
        from promptgrimoire.db.models import ExportJob

        async with get_session() as session:
            db_job = await session.get(ExportJob, job.id)
            assert db_job is not None
            db_job.token_expires_at = datetime.now(UTC) - timedelta(hours=1)
            session.add(db_job)

    return download_token


def _get_test_client() -> httpx.AsyncClient:
    """Create an ASGI test client for the NiceGUI app."""
    from nicegui import app

    # Import the download module to register the route
    import promptgrimoire.export.download  # side-effect: registers route

    _ = promptgrimoire.export.download

    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


class TestDownloadRoute:
    """Tests for GET /export/{token}/download."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_pdf(self, tmp_path: Path) -> None:
        """AC3.1: Valid token returns 200 with application/pdf."""
        pdf_file = tmp_path / "output.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake pdf content")

        token = await _create_completed_job(str(pdf_file))

        async with _get_test_client() as client:
            response = await client.get(f"/export/{token}/download")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content == b"%PDF-1.4 fake pdf content"

    @pytest.mark.asyncio
    async def test_same_token_twice_returns_200(self, tmp_path: Path) -> None:
        """AC3.2: Same token used twice -> both return 200 (multi-use)."""
        pdf_file = tmp_path / "output.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 reusable")

        token = await _create_completed_job(str(pdf_file))

        async with _get_test_client() as client:
            r1 = await client.get(f"/export/{token}/download")
            r2 = await client.get(f"/export/{token}/download")

        assert r1.status_code == 200
        assert r2.status_code == 200

    @pytest.mark.asyncio
    async def test_expired_token_returns_404(self, tmp_path: Path) -> None:
        """AC3.3: Expired token returns 404."""
        pdf_file = tmp_path / "output.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 expired")

        token = await _create_completed_job(
            str(pdf_file),
            expired=True,
        )

        async with _get_test_client() as client:
            response = await client.get(f"/export/{token}/download")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_token_returns_404(self) -> None:
        """AC3.4: Nonexistent token returns 404."""
        async with _get_test_client() as client:
            response = await client.get("/export/totally-bogus-token/download")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_pdf_file_returns_404(self) -> None:
        """PDF path in DB but file deleted from disk -> 404."""
        token = await _create_completed_job("/tmp/nonexistent-pdf-file.pdf")

        async with _get_test_client() as client:
            response = await client.get(f"/export/{token}/download")

        assert response.status_code == 404
