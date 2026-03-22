"""CRUD operations for ExportJob.

Provides async database functions for the PDF export queue:
enqueue, claim (FOR UPDATE SKIP LOCKED), complete, fail, and cleanup.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import sqlalchemy as sa
import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased
from sqlmodel import col, select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.exceptions import BusinessLogicError
from promptgrimoire.db.models import ExportJob

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.get_logger()


async def create_export_job(
    user_id: UUID,
    workspace_id: UUID,
    payload: dict,
) -> ExportJob:
    """Enqueue a new PDF export job.

    Raises BusinessLogicError if the user already has an active job.
    The partial unique index ``ix_export_job_one_active_per_user``
    is the real guard; the application check provides a friendly error.
    """
    async with get_session() as session:
        # Application-level check (friendly error, not race-proof)
        existing = (
            await session.exec(
                select(ExportJob).where(
                    ExportJob.user_id == user_id,
                    ExportJob.status.in_(["queued", "running"]),  # type: ignore[union-attr]  -- Column has .in_()
                )
            )
        ).first()
        if existing:
            raise BusinessLogicError("A PDF export is already in progress")

        job = ExportJob(
            user_id=user_id,
            workspace_id=workspace_id,
            payload=payload,
        )
        session.add(job)
        try:
            await session.flush()
        except IntegrityError as exc:
            if "ix_export_job_one_active_per_user" in str(exc):
                raise BusinessLogicError("A PDF export is already in progress") from exc
            raise

    return job


async def claim_next_job() -> ExportJob | None:
    """Claim the next queued job using FOR UPDATE SKIP LOCKED.

    Fair scheduling: jobs from users with fewer running jobs are
    prioritised, then FIFO by created_at.
    """
    async with get_session() as session:
        # Subquery: count running jobs for the same user as the outer row.
        # aliased() is required so the inner ej2.user_id == ExportJob.user_id
        # is a cross-table correlation, not a self-comparison tautology.
        ej2 = aliased(ExportJob)
        running_count = (
            select(sa.func.count())
            .select_from(ej2)
            .where(
                ej2.user_id == ExportJob.user_id,
                ej2.status == "running",
            )
            .correlate(ExportJob)
            .scalar_subquery()
        )

        stmt = (
            select(ExportJob)
            .where(ExportJob.status == "queued")
            .order_by(running_count.asc(), col(ExportJob.created_at).asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )

        job = (await session.exec(stmt)).first()
        if job is None:
            return None

        job.status = "running"
        job.started_at = datetime.now(UTC)
        session.add(job)

    return job


async def complete_job(
    job_id: UUID,
    download_token: str,
    pdf_path: str,
) -> None:
    """Mark a job as completed with download token and PDF path."""
    async with get_session() as session:
        job = await session.get(ExportJob, job_id)
        if job is None:
            msg = f"ExportJob {job_id} not found"
            raise BusinessLogicError(msg)

        now = datetime.now(UTC)
        job.status = "completed"
        job.download_token = download_token
        job.pdf_path = pdf_path
        job.token_expires_at = now + timedelta(hours=24)
        job.completed_at = now
        session.add(job)


async def fail_job(job_id: UUID, error_message: str) -> None:
    """Mark a job as failed with an error message."""
    async with get_session() as session:
        job = await session.get(ExportJob, job_id)
        if job is None:
            msg = f"ExportJob {job_id} not found"
            raise BusinessLogicError(msg)

        job.status = "failed"
        job.error_message = error_message
        job.completed_at = datetime.now(UTC)
        session.add(job)


async def fail_orphaned_jobs() -> int:
    """Mark all queued/running jobs as failed on app startup.

    After a server restart, any jobs left in 'queued' or 'running' state
    are orphaned — no worker is processing them. Fail them with a clear
    message so users see an error instead of a perpetual spinner.

    Returns the count of failed jobs.
    """
    async with get_session() as session:
        stmt = (
            sa.update(ExportJob)
            .where(col(ExportJob.status).in_(["queued", "running"]))
            .values(
                status="failed",
                error_message="Export interrupted by server restart. Please try again.",
                completed_at=datetime.now(UTC),
            )
        )
        result = await session.exec(stmt)
        count = result.rowcount
    return count


async def get_job(job_id: UUID) -> ExportJob | None:
    """Fetch an export job by ID."""
    async with get_session() as session:
        return await session.get(ExportJob, job_id)


async def get_active_job_for_user(
    user_id: UUID,
    workspace_id: UUID,
) -> ExportJob | None:
    """Find the most recent active job for a user+workspace.

    Returns the most recent queued, running, or completed (with valid token)
    job for this user+workspace combination.
    """
    now = datetime.now(UTC)
    async with get_session() as session:
        # Build the OR condition: active status OR (completed + valid token)
        active_filter = sa.or_(
            col(ExportJob.status).in_(["queued", "running"]),
            sa.and_(
                col(ExportJob.status) == "completed",
                col(ExportJob.token_expires_at) > now,
            ),
        )
        stmt = (
            select(ExportJob)
            .where(
                ExportJob.user_id == user_id,
                ExportJob.workspace_id == workspace_id,
            )
            .where(active_filter)
            .order_by(col(ExportJob.created_at).desc())
            .limit(1)
        )
        return (await session.exec(stmt)).first()


async def get_job_by_token(token: str) -> ExportJob | None:
    """Find a job by its download token (if not expired)."""
    now = datetime.now(UTC)
    async with get_session() as session:
        stmt = select(ExportJob).where(
            ExportJob.download_token == token,
            col(ExportJob.token_expires_at) > now,
        )
        return (await session.exec(stmt)).first()


async def cleanup_expired_jobs(cutoff: datetime) -> int:
    """Delete expired jobs and their PDF files from disk.

    Deletes jobs where:
    - completed_at < cutoff, OR
    - status='failed' and created_at < cutoff

    Returns the count of deleted rows.
    """
    async with get_session() as session:
        expired_filter = sa.or_(
            sa.and_(
                col(ExportJob.completed_at).isnot(None),
                col(ExportJob.completed_at) < cutoff,
            ),
            sa.and_(
                col(ExportJob.status) == "failed",
                col(ExportJob.created_at) < cutoff,
            ),
        )
        stmt = select(ExportJob).where(expired_filter)
        jobs = (await session.exec(stmt)).all()

        for job in jobs:
            if job.pdf_path:
                parent = Path(job.pdf_path).parent
                try:
                    shutil.rmtree(parent)
                except OSError:
                    logger.warning(
                        "failed to delete export directory",
                        path=str(parent),
                        job_id=str(job.id),
                    )

        count = len(jobs)
        if count:
            job_ids = [job.id for job in jobs]
            delete_stmt = sa.delete(ExportJob).where(
                col(ExportJob.id).in_(job_ids),
            )
            await session.exec(delete_stmt)

    return count
