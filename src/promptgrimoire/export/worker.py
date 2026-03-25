"""Background worker for processing PDF export jobs.

Polls for queued ExportJob rows, runs the export pipeline, and
manages job lifecycle (claim, complete, fail). Follows the same
polling-loop pattern as deadline_worker.py and search_worker.py.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from promptgrimoire.db.export_jobs import (
    claim_next_job,
    cleanup_expired_jobs,
    complete_job,
    fail_job,
    fail_orphaned_jobs,
)
from promptgrimoire.export.pdf_export import export_annotation_pdf

if TYPE_CHECKING:
    from promptgrimoire.db.models import ExportJob

logger = structlog.get_logger()
logging.getLogger(__name__).setLevel(logging.INFO)


async def _process_job(job: ExportJob) -> None:
    """Run the export pipeline for a claimed job.

    On success, generates a download token and marks the job completed.
    On failure, marks the job failed with the error message.

    Args:
        job: A claimed ExportJob with status='running'.
    """
    log = logger.bind(
        job_id=str(job.id), workspace_id=str(job.workspace_id), user_id=str(job.user_id)
    )
    log.info("export_worker_processing_job")

    # Create the output dir here so we can clean it up on failure.
    # export_annotation_pdf creates a random tmpdir internally if not
    # given one, and we'd have no reference to it on failure.
    ws_prefix = str(job.workspace_id)[:8]
    output_dir = Path(tempfile.mkdtemp(prefix=f"promptgrimoire_export_{ws_prefix}_"))

    try:
        payload = job.payload or {}
        pdf_path = await export_annotation_pdf(
            html_content=payload.get("html_content", ""),
            highlights=payload.get("highlights", []),
            tag_colours=payload.get("tag_colours", {}),
            general_notes=payload.get("general_notes", ""),
            notes_latex=payload.get("notes_latex", ""),
            filename=payload.get("filename", "annotated_document"),
            output_dir=output_dir,
            workspace_id=str(job.workspace_id),
            word_to_legal_para=payload.get("word_to_legal_para"),
            word_count=payload.get("word_count"),
            word_minimum=payload.get("word_minimum"),
            word_limit=payload.get("word_limit"),
            documents=payload.get("documents"),
        )

        download_token = secrets.token_urlsafe(48)
        await complete_job(job.id, download_token, str(pdf_path))
        log.info("export_worker_job_completed", pdf_path=str(pdf_path))

    except Exception as exc:
        # CancelledError is not a subclass of Exception, so it propagates
        # to the outer loop for clean worker shutdown.
        log.exception("export_worker_job_failed")
        await fail_job(job.id, str(exc))
        # Clean up the temp dir — failed jobs have no pdf_path,
        # so cleanup_expired_jobs would never delete it.
        shutil.rmtree(output_dir, ignore_errors=True)


async def _run_cleanup() -> None:
    """Delete expired jobs older than 24 hours."""
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    count = await cleanup_expired_jobs(cutoff)
    if count:
        logger.info("export_worker_cleanup", deleted_count=count)


async def start_export_worker(
    poll_interval: float = 5.0,
    cleanup_interval: int = 60,
) -> None:
    """Start the background export polling worker.

    Claims queued jobs and processes them in a loop. Runs cleanup
    every ``cleanup_interval`` iterations.

    Args:
        poll_interval: Sleep duration between polling cycles (seconds).
        cleanup_interval: Run cleanup every N iterations.
    """
    # Fail any jobs orphaned by a previous server shutdown.
    orphaned = await fail_orphaned_jobs()
    if orphaned:
        logger.warning("export_worker_orphaned_jobs_failed", count=orphaned)

    logger.info(
        "export_worker_started",
        poll_interval=poll_interval,
        cleanup_interval=cleanup_interval,
    )
    iteration = 0
    while True:
        try:
            iteration += 1

            job = await claim_next_job()
            if job is not None:
                await _process_job(job)

            if iteration % cleanup_interval == 0:
                try:
                    await _run_cleanup()
                except Exception:
                    logger.exception("export_worker_cleanup_failed")

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("export_worker_iteration_failed")

        await asyncio.sleep(poll_interval)
