"""Integration tests for the export worker.

Requires a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Acceptance Criteria:
- AC1.1: Export initiated, client disconnects, PDF compiles successfully
- AC1.3: Worker encounters LaTeX error -- job fails with error_message

NOTE: All tests mock export_annotation_pdf to avoid requiring pandoc/latexmk.
Real-pipeline testing (with @requires_pandoc/@requires_latexmk markers) is
deferred to UAT and the smoke test lane (`uv run grimoire test smoke-export`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch
from uuid import uuid4

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
        email=f"worker-{tag}@test.local",
        display_name=f"Worker Test {tag}",
    )
    workspace = await create_workspace()
    return user.id, workspace.id


class TestProcessJob:
    """Tests for _process_job."""

    @pytest.mark.asyncio
    async def test_process_job_success(self, tmp_path: Path) -> None:
        """AC1.1: Successful export sets status to completed with download_token."""
        from promptgrimoire.db.export_jobs import (
            claim_next_job,
            create_export_job,
            get_job,
        )
        from promptgrimoire.export.worker import _process_job

        user_id, workspace_id = await _create_user_and_workspace()

        payload = {
            "html_content": "<p>Hello</p>",
            "highlights": [],
            "tag_colours": {},
            "general_notes": "",
            "notes_latex": "",
            "filename": "test_doc",
        }
        await create_export_job(user_id, workspace_id, payload)

        # Drain queue until we find our job
        job = None
        for _ in range(50):
            candidate = await claim_next_job()
            if candidate is None:
                break
            if candidate.workspace_id == workspace_id:
                job = candidate
                break

        assert job is not None

        fake_pdf = tmp_path / "output.pdf"
        fake_pdf.write_text("fake pdf content")

        with patch(
            "promptgrimoire.export.worker.export_annotation_pdf",
            new_callable=AsyncMock,
            return_value=fake_pdf,
        ):
            await _process_job(job)

        updated = await get_job(job.id)
        assert updated is not None
        assert updated.status == "completed"
        assert updated.download_token is not None
        assert len(updated.download_token) > 0
        assert updated.pdf_path == str(fake_pdf)

    @pytest.mark.asyncio
    async def test_process_job_failure(self) -> None:
        """AC1.3: LaTeX error sets status to failed with error_message."""
        from promptgrimoire.db.export_jobs import (
            claim_next_job,
            create_export_job,
            get_job,
        )
        from promptgrimoire.export.worker import _process_job

        user_id, workspace_id = await _create_user_and_workspace()

        payload = {
            "html_content": "<p>Bad doc</p>",
            "highlights": [],
            "tag_colours": {},
            "general_notes": "",
            "notes_latex": "",
            "filename": "bad_doc",
        }
        await create_export_job(user_id, workspace_id, payload)

        job = None
        for _ in range(50):
            candidate = await claim_next_job()
            if candidate is None:
                break
            if candidate.workspace_id == workspace_id:
                job = candidate
                break

        assert job is not None

        with patch(
            "promptgrimoire.export.worker.export_annotation_pdf",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LaTeX compilation failed: missing \\end"),
        ):
            await _process_job(job)

        updated = await get_job(job.id)
        assert updated is not None
        assert updated.status == "failed"
        assert updated.error_message is not None
        assert "LaTeX compilation failed" in updated.error_message


class TestRunCleanup:
    """Tests for _run_cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_sweep(self) -> None:
        """_run_cleanup calls cleanup_expired_jobs with correct cutoff."""
        from promptgrimoire.export.worker import _run_cleanup

        with patch(
            "promptgrimoire.export.worker.cleanup_expired_jobs",
            new_callable=AsyncMock,
            return_value=3,
        ) as mock_cleanup:
            await _run_cleanup()

        mock_cleanup.assert_called_once()
        cutoff_arg = mock_cleanup.call_args[0][0]
        expected = datetime.now(UTC) - timedelta(hours=24)
        assert abs((cutoff_arg - expected).total_seconds()) < 5


class TestWorkerLoop:
    """Tests for start_export_worker loop behaviour."""

    @pytest.mark.asyncio
    async def test_worker_loop_calls_cleanup(self) -> None:
        """Worker loop calls cleanup on the correct iteration."""
        import asyncio

        from promptgrimoire.export.worker import start_export_worker

        iteration_count = 0
        cleanup_calls = 0

        async def mock_cleanup_expired(_cutoff: datetime) -> int:
            nonlocal cleanup_calls
            cleanup_calls += 1
            return 0

        async def mock_claim() -> None:
            nonlocal iteration_count
            iteration_count += 1
            if iteration_count >= 15:
                raise asyncio.CancelledError

        with (
            patch(
                "promptgrimoire.export.worker.claim_next_job",
                side_effect=mock_claim,
            ),
            patch(
                "promptgrimoire.export.worker.cleanup_expired_jobs",
                side_effect=mock_cleanup_expired,
            ),
            patch(
                "promptgrimoire.export.worker.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            pytest.raises(asyncio.CancelledError),
        ):
            await start_export_worker(poll_interval=1.0, cleanup_interval=5)

        # With cleanup_interval=5, cleanup runs on iterations 5 and 10
        assert cleanup_calls >= 2
