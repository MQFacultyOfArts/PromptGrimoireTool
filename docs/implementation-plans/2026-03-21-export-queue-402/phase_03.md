# PDF Export Queue Implementation Plan — Phase 3

**Goal:** Background worker that polls for queued export jobs, runs the existing pandoc/LaTeX pipeline, and records results.

**Architecture:** Async polling loop following deadline_worker/search_worker pattern. Claims jobs via CRUD module (Phase 2), calls existing `export_annotation_pdf()`, updates job status. Cleanup sweep runs every ~5 minutes within the same loop.

**Tech Stack:** asyncio, existing export pipeline (`export/pdf.py`), structlog

**Scope:** 3 of 6 phases from original design (Phase 3)

**Codebase verified:** 2026-03-21

---

## Acceptance Criteria Coverage

This phase implements and tests:

### export-queue-402.AC1: Exports complete regardless of client lifecycle
- **export-queue-402.AC1.1 Success:** Export initiated, client disconnects during compilation, PDF compiles successfully and job reaches `completed` status
- **export-queue-402.AC1.2 Success:** Export initiated, client reconnects after compilation, download button appears on reconnected page
- **export-queue-402.AC1.3 Failure:** Worker encounters LaTeX compilation error — job status set to `failed`, error_message populated, user sees error notification

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Export worker polling loop

**Verifies:** export-queue-402.AC1.1, export-queue-402.AC1.3

**Files:**
- Create: `src/promptgrimoire/export/worker.py`

**Implementation:**

Create an async polling worker following the `deadline_worker.py` and `search_worker.py` pattern.

The worker function signature:

```python
async def start_export_worker(
    poll_interval: float = 5.0,
    cleanup_interval: int = 60,
) -> None:
```

**Core loop structure:**

```python
import asyncio
import secrets
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog

from promptgrimoire.db.export_jobs import (
    claim_next_job,
    cleanup_expired_jobs,
    complete_job,
    fail_job,
)
from promptgrimoire.export.pdf_export import export_annotation_pdf

logger = structlog.get_logger()

_CLEANUP_EVERY_N = 60  # Run cleanup every 60th iteration (~5 min at 5s interval)
_TOKEN_TTL_HOURS = 24

async def start_export_worker(
    poll_interval: float = 5.0,
    cleanup_interval: int = _CLEANUP_EVERY_N,
) -> None:
    """Poll for queued export jobs and process them."""
    logger.info("export_worker_started", poll_interval=poll_interval)
    iteration = 0

    while True:
        try:
            job = await claim_next_job()

            if job is not None:
                await _process_job(job)

            # Periodic cleanup
            iteration += 1
            if iteration % cleanup_interval == 0:
                await _run_cleanup()

        except asyncio.CancelledError:
            logger.info("export_worker_cancelled")
            raise
        except Exception:
            logger.exception("export_worker_error")

        await asyncio.sleep(poll_interval)
```

**Job processing function:**

```python
async def _process_job(job: "ExportJob") -> None:
    """Run the export pipeline for a claimed job."""
    log = logger.bind(export_job_id=str(job.id), user_id=str(job.user_id), workspace_id=str(job.workspace_id))
    log.info("export_job_processing")

    try:
        payload = job.payload
        pdf_path = await export_annotation_pdf(
            html_content=payload["html_content"],
            highlights=payload["highlights"],
            tag_colours=payload["tag_colours"],
            general_notes=payload.get("general_notes", ""),
            notes_latex=payload.get("notes_latex", ""),
            word_to_legal_para=payload.get("word_to_legal_para"),
            filename=payload.get("filename", "annotated_document"),
            workspace_id=str(job.workspace_id),
            word_count=payload.get("word_count"),
            word_minimum=payload.get("word_minimum"),
            word_limit=payload.get("word_limit"),
        )

        token = secrets.token_urlsafe(32)
        await complete_job(
            job_id=job.id,
            download_token=token,
            pdf_path=str(pdf_path),
        )
        log.info("export_job_completed", pdf_path=str(pdf_path))

    except Exception as exc:
        error_msg = str(exc)
        log.exception("export_job_failed", error=error_msg)
        await fail_job(job_id=job.id, error_message=error_msg)
```

**Important:** Pass `workspace_id` (not `user_id`) to `export_annotation_pdf()` so it uses `tempfile.mkdtemp(prefix=...)` which creates a unique directory per export rather than the destructive `_get_export_dir(user_id)` which wipes previous exports.

**Cleanup function:**

```python
async def _run_cleanup() -> None:
    """Delete expired jobs and their PDF files."""
    cutoff = datetime.now(UTC) - timedelta(hours=_TOKEN_TTL_HOURS)
    try:
        deleted = await cleanup_expired_jobs(cutoff)
        if deleted > 0:
            logger.info("export_cleanup_completed", deleted_count=deleted)
    except Exception:
        logger.exception("export_cleanup_error")
```

**Testing:**

Tests must verify each AC listed above:
- export-queue-402.AC1.1: Create a queued job, call `_process_job()`, verify status becomes `completed` with `download_token` and `pdf_path` set
- export-queue-402.AC1.3: Create a queued job with invalid payload (e.g., empty `html_content` that causes LaTeX failure), call `_process_job()`, verify status becomes `failed` with `error_message` populated
- Cleanup sweep: Call `_run_cleanup()` directly with expired jobs, verify `cleanup_expired_jobs()` is called and returns correct count
- Loop counter mechanic: Mock `cleanup_expired_jobs`, run the worker loop for N iterations, verify cleanup is called on iteration N (the cleanup_interval-th iteration)

These are integration tests requiring a real database AND the export pipeline (pandoc + latexmk). Place in `tests/integration/test_export_worker.py`. Include skip guard for `TEST_DATABASE_URL`. Use the `requires_pandoc` and `requires_latexmk` decorators for tests that exercise the full pipeline.

For tests that only verify the worker's DB interaction (status transitions) or the cleanup mechanic, mock `export_annotation_pdf` to avoid requiring the LaTeX toolchain.

**Verification:**

Run: `uv run grimoire test run tests/integration/test_export_worker.py`
Expected: All tests pass

**Commit:** `feat: add export worker with polling loop and cleanup (#402)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Worker startup and shutdown registration

**Verifies:** None (infrastructure — verified operationally by app startup)

**Files:**
- Modify: `src/promptgrimoire/__init__.py`

**Implementation:**

Follow the existing pattern for `_search_worker_task` and `_deadline_worker_task`:

1. Add module-level variable:
   ```python
   _export_worker_task: asyncio.Task[None] | None = None
   ```

2. In `startup()` callback, after existing worker launches:
   ```python
   _export_worker_task = asyncio.create_task(
       start_export_worker(),
   )
   ```

3. In `shutdown()` callback, before DB teardown:
   ```python
   if _export_worker_task is not None:
       _export_worker_task.cancel()
       _export_worker_task = None
   ```

4. Add import at top of file:
   ```python
   from promptgrimoire.export.worker import start_export_worker
   ```

**Verification:**

Run: `uv run run.py` (start the app)
Expected: Log line `export_worker_started` appears in startup output. No errors.

Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: register export worker in app startup/shutdown (#402)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

---

## Phase Verification

Run: `uv run complexipy src/promptgrimoire/export/worker.py src/promptgrimoire/__init__.py --max-complexity-allowed 15`
Expected: No functions exceed threshold

## UAT Steps

1. [ ] Start the app: `uv run run.py`
2. [ ] Verify log line `export_worker_started` appears in startup output
3. [ ] Run integration tests: `uv run grimoire test run tests/integration/test_export_worker.py`

## Evidence Required
- [ ] Worker starts without errors (log line visible)
- [ ] All integration tests pass (job processing, failure handling, cleanup sweep)
