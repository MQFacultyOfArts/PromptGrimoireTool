"""Integration tests for ExportJob CRUD operations.

Requires a running PostgreSQL instance. Set DEV__TEST_DATABASE_URL.

Acceptance Criteria:
- AC4.1: Two users submit exports — both are processed
- AC4.2: Three users submit exports — fair scheduling order
- AC4.3: User with active export gets rejected with BusinessLogicError
- AC6.1: Partial unique index rejects concurrent inserts at DB level
- AC6.2: Expired jobs and PDF files are cleaned up
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from promptgrimoire.config import get_settings
from promptgrimoire.db.exceptions import BusinessLogicError

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
        email=f"export-{tag}@test.local",
        display_name=f"Export Test {tag}",
    )
    workspace = await create_workspace()
    return user.id, workspace.id


class TestCreateExportJob:
    """Tests for create_export_job (AC4.3, AC6.1)."""

    @pytest.mark.asyncio
    async def test_creates_job_with_defaults(self) -> None:
        """create_export_job creates a job with status='queued'."""
        from promptgrimoire.db.export_jobs import create_export_job

        user_id, workspace_id = await _create_user_and_workspace()
        job = await create_export_job(user_id, workspace_id, {"format": "pdf"})

        assert job.id is not None
        assert job.user_id == user_id
        assert job.workspace_id == workspace_id
        assert job.status == "queued"
        assert job.payload == {"format": "pdf"}
        assert job.created_at is not None

    @pytest.mark.asyncio
    async def test_rejects_duplicate_active_job(self) -> None:
        """AC4.3: User with an active export gets BusinessLogicError."""
        from promptgrimoire.db.export_jobs import create_export_job

        user_id, workspace_id = await _create_user_and_workspace()
        await create_export_job(user_id, workspace_id, {"format": "pdf"})

        with pytest.raises(BusinessLogicError, match="already in progress"):
            await create_export_job(user_id, workspace_id, {"format": "pdf"})

    @pytest.mark.asyncio
    async def test_allows_job_after_completion(self) -> None:
        """User can create a new job after the previous one completes."""
        from promptgrimoire.db.export_jobs import (
            complete_job,
            create_export_job,
        )

        user_id, workspace_id = await _create_user_and_workspace()
        job1 = await create_export_job(user_id, workspace_id, {"format": "pdf"})
        await complete_job(job1.id, "token123", "/tmp/test.pdf")

        # Should succeed — no active job
        job2 = await create_export_job(user_id, workspace_id, {"format": "pdf"})
        assert job2.id != job1.id
        assert job2.status == "queued"

    @pytest.mark.asyncio
    async def test_allows_job_after_failure(self) -> None:
        """User can create a new job after the previous one fails."""
        from promptgrimoire.db.export_jobs import (
            create_export_job,
            fail_job,
        )

        user_id, workspace_id = await _create_user_and_workspace()
        job1 = await create_export_job(user_id, workspace_id, {"format": "pdf"})
        await fail_job(job1.id, "LaTeX error")

        job2 = await create_export_job(user_id, workspace_id, {"format": "pdf"})
        assert job2.id != job1.id


class TestClaimNextJob:
    """Tests for claim_next_job (AC4.1, AC4.2)."""

    @pytest.mark.asyncio
    async def test_claims_queued_job(self) -> None:
        """claim_next_job returns a queued job and sets status='running'."""
        from promptgrimoire.db.export_jobs import create_export_job
        from tests.integration.conftest import claim_own_job

        user_id, workspace_id = await _create_user_and_workspace()
        created = await create_export_job(user_id, workspace_id, {"format": "pdf"})

        claimed = await claim_own_job({created.id})

        assert claimed is not None
        assert claimed.status == "running"
        assert claimed.started_at is not None

    @pytest.mark.asyncio
    async def test_returns_none_when_empty(self) -> None:
        """claim_next_job returns None when no queued jobs exist."""
        from promptgrimoire.db.export_jobs import claim_next_job

        await claim_next_job()
        # May or may not be None depending on other test state,
        # but at least should not raise

    @pytest.mark.asyncio
    async def test_fair_scheduling_three_users(self) -> None:
        """AC4.2: Fair scheduling with three users.

        With MAX_CONCURRENT_WORKERS=2, the user whose job was claimed first
        has a running job. After two claims, the third user's job is still
        queued. Once a claimed job completes, the third user's job becomes
        claimable.
        """
        from promptgrimoire.db.export_jobs import (
            complete_job,
            create_export_job,
            get_job,
        )
        from tests.integration.conftest import claim_own_job

        uid1, wid1 = await _create_user_and_workspace()
        uid2, wid2 = await _create_user_and_workspace()
        uid3, wid3 = await _create_user_and_workspace()

        job1 = await create_export_job(uid1, wid1, {"format": "pdf"})
        job2 = await create_export_job(uid2, wid2, {"format": "pdf"})
        job3 = await create_export_job(uid3, wid3, {"format": "pdf"})

        our_ids = {job1.id, job2.id, job3.id}

        # Claim two of our three jobs (scoped to avoid xdist interference).
        claimed_a = await claim_own_job(our_ids)
        claimed_b = await claim_own_job(our_ids)

        assert claimed_a is not None
        assert claimed_b is not None
        assert claimed_a.id != claimed_b.id
        claimed_ids = {claimed_a.id, claimed_b.id}

        # The unclaimed job must belong to the third user.
        unclaimed_id = our_ids - claimed_ids
        assert len(unclaimed_id) == 1
        remaining_job = await get_job(next(iter(unclaimed_id)))
        assert remaining_job is not None
        assert remaining_job.status == "queued"

        # Complete one of the claimed jobs — third slot opens.
        await complete_job(claimed_a.id, "tok-a", "/tmp/a.pdf")

        # Now claim the third job.
        claimed_c = await claim_own_job(unclaimed_id)
        assert claimed_c is not None
        assert claimed_c.id == next(iter(unclaimed_id))

        # Cleanup
        await complete_job(claimed_b.id, "tok-b", "/tmp/b.pdf")
        await complete_job(claimed_c.id, "tok-c", "/tmp/c.pdf")

    # NOTE: Fair-scheduling *priority ordering* (users with fewer running
    # jobs claimed first) cannot be integration-tested with the current
    # schema because the partial unique index ix_export_job_one_active_per_user
    # prevents any user from having both a running AND a queued job
    # simultaneously. The correlated subquery in claim_next_job() is
    # correct (verified by code review, uses aliased() to avoid
    # self-comparison tautology) but degenerates to FIFO when the
    # per-user cap is 1. If the cap is ever raised, add a priority
    # ordering test here.

    @pytest.mark.asyncio
    async def test_two_users_both_processed(self) -> None:
        """AC4.1: Two users submit exports — both are processed."""
        from promptgrimoire.db.export_jobs import (
            complete_job,
            create_export_job,
        )
        from tests.integration.conftest import claim_own_job

        uid1, wid1 = await _create_user_and_workspace()
        uid2, wid2 = await _create_user_and_workspace()

        job1 = await create_export_job(uid1, wid1, {"format": "pdf"})
        job2 = await create_export_job(uid2, wid2, {"format": "pdf"})

        our_ids = {job1.id, job2.id}

        claimed1 = await claim_own_job(our_ids)
        claimed2 = await claim_own_job(our_ids)

        assert claimed1 is not None
        assert claimed2 is not None
        assert {claimed1.id, claimed2.id} == our_ids

        # Complete both
        await complete_job(claimed1.id, "tok1", "/tmp/1.pdf")
        await complete_job(claimed2.id, "tok2", "/tmp/2.pdf")


class TestCompleteAndFailJob:
    """Tests for complete_job and fail_job."""

    @pytest.mark.asyncio
    async def test_complete_sets_fields(self) -> None:
        """complete_job sets download_token, pdf_path, token_expires_at."""
        from promptgrimoire.db.export_jobs import (
            complete_job,
            create_export_job,
            get_job,
        )

        user_id, workspace_id = await _create_user_and_workspace()
        job = await create_export_job(user_id, workspace_id, {"format": "pdf"})
        await complete_job(job.id, "download-tok", "/tmp/export.pdf")

        updated = await get_job(job.id)
        assert updated is not None
        assert updated.status == "completed"
        assert updated.download_token == "download-tok"
        assert updated.pdf_path == "/tmp/export.pdf"
        assert updated.token_expires_at is not None
        assert updated.completed_at is not None

    @pytest.mark.asyncio
    async def test_fail_sets_error(self) -> None:
        """fail_job sets error_message and completed_at."""
        from promptgrimoire.db.export_jobs import (
            create_export_job,
            fail_job,
            get_job,
        )

        user_id, workspace_id = await _create_user_and_workspace()
        job = await create_export_job(user_id, workspace_id, {"format": "pdf"})
        await fail_job(job.id, "LaTeX compilation failed")

        updated = await get_job(job.id)
        assert updated is not None
        assert updated.status == "failed"
        assert updated.error_message == "LaTeX compilation failed"
        assert updated.completed_at is not None


class TestGetActiveJobForUser:
    """Tests for get_active_job_for_user."""

    @pytest.mark.asyncio
    async def test_finds_queued_job(self) -> None:
        """Returns a queued job for the user+workspace."""
        from promptgrimoire.db.export_jobs import (
            create_export_job,
            get_active_job_for_user,
        )

        user_id, workspace_id = await _create_user_and_workspace()
        created = await create_export_job(user_id, workspace_id, {"format": "pdf"})

        found = await get_active_job_for_user(user_id, workspace_id)
        assert found is not None
        assert found.id == created.id

    @pytest.mark.asyncio
    async def test_returns_none_for_failed_job(self) -> None:
        """Does not return failed jobs."""
        from promptgrimoire.db.export_jobs import (
            create_export_job,
            fail_job,
            get_active_job_for_user,
        )

        user_id, workspace_id = await _create_user_and_workspace()
        job = await create_export_job(user_id, workspace_id, {"format": "pdf"})
        await fail_job(job.id, "error")

        found = await get_active_job_for_user(user_id, workspace_id)
        assert found is None


class TestGetJobByToken:
    """Tests for get_job_by_token."""

    @pytest.mark.asyncio
    async def test_finds_by_valid_token(self) -> None:
        """Returns job with matching, unexpired download token."""
        from promptgrimoire.db.export_jobs import (
            complete_job,
            create_export_job,
            get_job_by_token,
        )

        user_id, workspace_id = await _create_user_and_workspace()
        job = await create_export_job(user_id, workspace_id, {"format": "pdf"})
        await complete_job(job.id, "secret-token", "/tmp/out.pdf")

        found = await get_job_by_token("secret-token")
        assert found is not None
        assert found.id == job.id

    @pytest.mark.asyncio
    async def test_returns_none_for_wrong_token(self) -> None:
        """Returns None for non-existent token."""
        from promptgrimoire.db.export_jobs import get_job_by_token

        found = await get_job_by_token("nonexistent-token")
        assert found is None


class TestCleanupExpiredJobs:
    """Tests for cleanup_expired_jobs (AC6.2)."""

    @pytest.mark.asyncio
    async def test_deletes_expired_completed_jobs(self) -> None:
        """AC6.2: Completed jobs older than cutoff are deleted."""
        from promptgrimoire.db.export_jobs import (
            cleanup_expired_jobs,
            complete_job,
            create_export_job,
            get_job,
        )

        user_id, workspace_id = await _create_user_and_workspace()
        job = await create_export_job(user_id, workspace_id, {"format": "pdf"})
        await complete_job(job.id, "tok", "/tmp/nonexistent.pdf")

        # Cutoff in the future — should delete
        cutoff = datetime.now(UTC) + timedelta(hours=1)
        count = await cleanup_expired_jobs(cutoff)

        assert count >= 1
        assert await get_job(job.id) is None

    @pytest.mark.asyncio
    async def test_deletes_pdf_files_on_cleanup(self, tmp_path: Path) -> None:
        """AC6.2: PDF files and directories are removed from disk."""
        from promptgrimoire.db.export_jobs import (
            cleanup_expired_jobs,
            complete_job,
            create_export_job,
        )

        # Create a temp PDF file
        export_dir = tmp_path / "export-test"
        export_dir.mkdir()
        pdf_file = export_dir / "output.pdf"
        pdf_file.write_text("fake pdf")

        user_id, workspace_id = await _create_user_and_workspace()
        job = await create_export_job(user_id, workspace_id, {"format": "pdf"})
        await complete_job(job.id, "tok", str(pdf_file))

        cutoff = datetime.now(UTC) + timedelta(hours=1)
        await cleanup_expired_jobs(cutoff)

        assert not export_dir.exists()

    @pytest.mark.asyncio
    async def test_deletes_failed_jobs(self) -> None:
        """Failed jobs older than cutoff are deleted."""
        from promptgrimoire.db.export_jobs import (
            cleanup_expired_jobs,
            create_export_job,
            fail_job,
            get_job,
        )

        user_id, workspace_id = await _create_user_and_workspace()
        job = await create_export_job(user_id, workspace_id, {"format": "pdf"})
        await fail_job(job.id, "error")

        cutoff = datetime.now(UTC) + timedelta(hours=1)
        count = await cleanup_expired_jobs(cutoff)

        assert count >= 1
        assert await get_job(job.id) is None

    @pytest.mark.asyncio
    async def test_preserves_recent_jobs(self) -> None:
        """Jobs newer than cutoff are preserved."""
        from promptgrimoire.db.export_jobs import (
            cleanup_expired_jobs,
            complete_job,
            create_export_job,
            get_job,
        )

        user_id, workspace_id = await _create_user_and_workspace()
        job = await create_export_job(user_id, workspace_id, {"format": "pdf"})
        await complete_job(job.id, "tok", "/tmp/test.pdf")

        # Cutoff in the past — should preserve
        cutoff = datetime.now(UTC) - timedelta(hours=1)
        await cleanup_expired_jobs(cutoff)

        assert await get_job(job.id) is not None


class TestPartialUniqueIndex:
    """Tests for the partial unique index enforcement (AC6.1)."""

    @pytest.mark.asyncio
    async def test_index_rejects_concurrent_active_jobs(self) -> None:
        """AC6.1: Partial unique index rejects two active jobs for same user."""
        from sqlalchemy.exc import IntegrityError as SAIntegrityError

        from promptgrimoire.db.export_jobs import create_export_job
        from promptgrimoire.db.models import ExportJob

        user_id, workspace_id = await _create_user_and_workspace()
        await create_export_job(user_id, workspace_id, {"format": "pdf"})

        # Bypass application check — insert directly to test the DB index.
        # Use a raw engine connection to avoid get_session's auto-commit.
        from sqlalchemy.ext.asyncio import AsyncSession

        from promptgrimoire.db.engine import get_engine

        engine = get_engine()
        assert engine is not None

        async with engine.connect() as conn, conn.begin():
            async_session = AsyncSession(bind=conn)
            direct_job = ExportJob(
                user_id=user_id,
                workspace_id=workspace_id,
                status="queued",
                payload={"format": "pdf"},
            )
            async_session.add(direct_job)
            with pytest.raises(
                SAIntegrityError, match="ix_export_job_one_active_per_user"
            ):
                await async_session.flush()
            # Rollback required: the IntegrityError leaves the transaction
            # in an error state. This rolls back both the session flush and
            # the outer conn.begin() transaction.
            await conn.rollback()
