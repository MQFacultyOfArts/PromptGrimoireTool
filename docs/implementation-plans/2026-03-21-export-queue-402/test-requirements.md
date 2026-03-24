# Test Requirements — export-queue-402

Maps every acceptance criterion from the [design plan](../../design-plans/2026-03-21-export-queue-402.md) to specific automated tests or documented human verification.

AC identifiers use the slug format `export-queue-402.AC{N}.{M}`.

For final evaluator review, use the preregistered UAT protocol in
[`preregistered-uat-experiment.md`](./preregistered-uat-experiment.md).

---

## AC1: Exports complete regardless of client lifecycle

### export-queue-402.AC1.1 Success
Export initiated, client disconnects during compilation, PDF compiles successfully and job reaches `completed` status.

- **Test type:** integration
- **Test file:** `tests/integration/test_export_worker.py`
- **Description:** Create a queued ExportJob in the database, call `_process_job()` (with `export_annotation_pdf` mocked to return a PDF path), verify the job status transitions to `completed` with `download_token` and `pdf_path` populated. No NiceGUI client is involved — the worker processes the job independently, which is exactly the decoupling this AC requires.

### export-queue-402.AC1.2 Success
Export initiated, client reconnects after compilation, download button appears on reconnected page.

- **Test type:** e2e
- **Test file:** `tests/e2e/test_export_queue.py`
- **Description:** Log in, trigger an export, wait for compilation to complete, reload the page, verify the download button (`data-testid="export-download-btn"`) is visible on the reloaded page. This exercises the `check_existing_export()` recovery path with a completed job.

### export-queue-402.AC1.3 Failure
Worker encounters LaTeX compilation error — job status set to `failed`, error_message populated, user sees error notification.

- **Test type:** integration
- **Test file:** `tests/integration/test_export_worker.py`
- **Description:** Create a queued ExportJob, mock `export_annotation_pdf` to raise an exception, call `_process_job()`, verify the job status is `failed` and `error_message` is populated with the exception text.

---

## AC2: Progress feedback in UI

### export-queue-402.AC2.1 Success
After clicking export, spinner shows "Export queued..." then "Compiling PDF..." then download button appears.

- **Test type:** unit
- **Test file:** `tests/unit/pages/test_pdf_export_refactor.py`
- **Description:** Three sub-tests: (1) Verify `_handle_pdf_export()` calls `create_export_job()` with correct payload structure and starts polling. (2) Mock `get_job()` to return jobs with status `queued`, `running`, and `completed` in sequence; verify notification message text transitions from "Export queued..." to "Compiling PDF..." to download button via `_show_download_button()`. (3) Verify `ui.download()` is called with the correct `/export/{token}/download` URL format.

### export-queue-402.AC2.2 Success
Timer deactivates after job reaches terminal state (completed or failed).

- **Test type:** unit
- **Test file:** `tests/unit/pages/test_pdf_export_refactor.py`
- **Description:** Mock `get_job()` to return a completed job, invoke the polling callback, verify `timer.deactivate()` is called. Repeat with a failed job, verify the same deactivation.

### export-queue-402.AC2.3 Edge
Page reload during active export re-renders progress indicator for running job or download button for completed job.

- **Test type:** unit + e2e
- **Test file (unit):** `tests/unit/pages/test_pdf_export_refactor.py`
- **Test file (e2e):** `tests/e2e/test_export_queue.py`
- **Description (unit):** Call `check_existing_export()` with a mocked `get_active_job_for_user()` returning: (a) a running job — verify `_start_export_polling()` is called; (b) a completed job with valid token — verify `_show_download_button()` is called; (c) no job — verify neither function is called.
- **Description (e2e):** Trigger an export, reload the page while the job is in-flight or completed, verify the appropriate UI element (spinner or download button) is rendered.

---

## AC3: Download via FastAPI route

### export-queue-402.AC3.1 Success
Clicking download button triggers file download via `/export/{token}/download`.

- **Test type:** integration
- **Test file:** `tests/integration/test_export_download.py`
- **Description:** Insert a completed ExportJob with a valid download token, create a real PDF file at the recorded `pdf_path`, send a GET request to `/export/{token}/download` via `httpx.AsyncClient`, verify 200 response with `content-type: application/pdf`.

### export-queue-402.AC3.2 Success
Token is multi-use — repeat downloads within 24-hour TTL return the same PDF.

- **Test type:** integration
- **Test file:** `tests/integration/test_export_download.py`
- **Description:** Using the same completed ExportJob and token as AC3.1, send two consecutive GET requests, verify both return 200 with identical response content.

### export-queue-402.AC3.3 Failure
Request with expired token (>24 hours) returns 404.

- **Test type:** integration
- **Test file:** `tests/integration/test_export_download.py`
- **Description:** Insert a completed ExportJob with `token_expires_at` set to a datetime in the past, send a GET request to `/export/{token}/download`, verify 404 response with `"Export not found or expired"` in the body.

### export-queue-402.AC3.4 Failure
Request with nonexistent token returns 404.

- **Test type:** integration
- **Test file:** `tests/integration/test_export_download.py`
- **Description:** Send a GET request to `/export/nonexistent-token-value/download` with no matching DB record, verify 404 response.

---

## AC4: Queue with per-user concurrency limit

### export-queue-402.AC4.1 Success
Two users submit exports — both are processed (concurrency cap 2).

- **Test type:** integration
- **Test file:** `tests/integration/test_export_jobs.py`
- **Description:** Create queued ExportJobs for two different users, call `claim_next_job()` twice, verify both jobs are claimed (status transitions to `running`).

### export-queue-402.AC4.2 Success
Three users submit exports — first two run concurrently, third waits, gets processed when a slot frees.

- **Test type:** integration
- **Test file:** `tests/integration/test_export_jobs.py`
- **Description:** Create queued ExportJobs for three different users, call `claim_next_job()` three times. Verify that all three are eventually claimed in FIFO order (the fair scheduling subquery deprioritises users with running jobs, but with one job per user this is effectively FIFO by `created_at`).

### export-queue-402.AC4.3 Failure
User with an active export submits a second — rejected with "already in progress" notification.

- **Test type:** integration + unit
- **Test file (integration):** `tests/integration/test_export_jobs.py`
- **Test file (unit):** `tests/unit/test_export_job_model.py`, `tests/unit/pages/test_pdf_export_refactor.py`
- **Description (integration):** Create a queued ExportJob for user A, call `create_export_job()` for user A again, verify `BusinessLogicError` is raised with message "A PDF export is already in progress". Also test the race condition path: bypass the application-level check and INSERT directly, verify the partial unique index raises `IntegrityError`, and verify `create_export_job()` catches this and converts it to `BusinessLogicError`.
- **Description (unit model):** Verify ExportJob instantiates with correct defaults (status='queued', timestamps set).
- **Description (unit page handler):** Mock `create_export_job()` to raise `BusinessLogicError`, call the refactored `_handle_pdf_export()`, verify a "already in progress" notification is shown to the user.

---

## AC5: response_timeout fix (#377)

### export-queue-402.AC5.1 Success
`page_route` decorator passes `response_timeout=60` to `ui.page()`.

- **Test type:** unit
- **Test file:** `tests/unit/pages/test_registry.py`
- **Description:** Patch `nicegui.ui.page` to capture kwargs, call `page_route("/test-route")` with a dummy handler, assert `response_timeout=60` was passed to `ui.page()`.

### export-queue-402.AC5.2 Edge
Page handler taking >3s but <60s completes normally without client deletion.

- **Test type:** human verification
- **Justification:** This AC verifies runtime NiceGUI client lifecycle behaviour that cannot be meaningfully unit-tested — the client deletion mechanism is internal to NiceGUI's WebSocket management. The unit test for AC5.1 confirms the parameter is passed correctly (the necessary condition). The sufficient condition (that NiceGUI honours the parameter) is verified by manual UAT: load an annotation workspace with a large document that takes >3s, confirm the page loads without the client being deleted.
- **UAT procedure:** Start the app, navigate to an annotation workspace with a large document, verify the page loads successfully without client deletion errors in the log.

---

## AC6: No cascade from retry-spam

### export-queue-402.AC6.1 Success
User's concurrent export attempt is rejected at the database level — no LaTeX process spawned, no pool impact.

- **Test type:** integration + unit
- **Test file (integration):** `tests/integration/test_export_jobs.py`
- **Test file (unit):** `tests/unit/pages/test_pdf_export_refactor.py`
- **Description (integration):** Verify that when a user already has a queued or running job, `create_export_job()` raises `BusinessLogicError` before any process is spawned. Also verify the partial unique index constraint fires on direct INSERT bypass. (Overlaps with AC4.3 tests — same test functions cover both ACs.)
- **Description (unit):** Verify the old in-memory `_user_export_locks` mechanism is removed from `pdf_export.py` — grep the module for references and assert none exist.

### export-queue-402.AC6.2 Success
Expired jobs and PDF files are cleaned up within 24 hours.

- **Test type:** integration
- **Test file:** `tests/integration/test_export_jobs.py`
- **Description:** Create completed ExportJobs with `completed_at` older than 24 hours and associated PDF files on disk (in a temp directory). Call `cleanup_expired_jobs(cutoff)`, verify the DB rows are deleted and the PDF files and their parent directories are removed from disk. Also create a failed job with `created_at` older than 24 hours and verify it is cleaned up. Create a recent job and verify it is NOT cleaned up.

---

## Summary Matrix

| AC | Test Type | Test File | Phase |
|----|-----------|-----------|-------|
| AC1.1 | integration | `tests/integration/test_export_worker.py` | 3 |
| AC1.2 | e2e | `tests/e2e/test_export_queue.py` | 5 |
| AC1.3 | integration | `tests/integration/test_export_worker.py` | 3 |
| AC2.1 | unit | `tests/unit/pages/test_pdf_export_refactor.py` | 5 |
| AC2.2 | unit | `tests/unit/pages/test_pdf_export_refactor.py` | 5 |
| AC2.3 | unit + e2e | `tests/unit/pages/test_pdf_export_refactor.py`, `tests/e2e/test_export_queue.py` | 5 |
| AC3.1 | integration | `tests/integration/test_export_download.py` | 4 |
| AC3.2 | integration | `tests/integration/test_export_download.py` | 4 |
| AC3.3 | integration | `tests/integration/test_export_download.py` | 4 |
| AC3.4 | integration | `tests/integration/test_export_download.py` | 4 |
| AC4.1 | integration | `tests/integration/test_export_jobs.py` | 2 |
| AC4.2 | integration | `tests/integration/test_export_jobs.py` | 2 |
| AC4.3 | integration + unit | `tests/integration/test_export_jobs.py`, `tests/unit/test_export_job_model.py`, `tests/unit/pages/test_pdf_export_refactor.py` | 2, 5 |
| AC5.1 | unit | `tests/unit/pages/test_registry.py` | 1 |
| AC5.2 | human verification | UAT (Phase 1 steps 2-3) | 1 |
| AC6.1 | integration + unit | `tests/integration/test_export_jobs.py`, `tests/unit/pages/test_pdf_export_refactor.py` | 2, 5 |
| AC6.2 | integration | `tests/integration/test_export_jobs.py` | 2 |

### Test Files Created

| File | Lane | Phase | ACs Covered |
|------|------|-------|-------------|
| `tests/unit/pages/test_registry.py` (existing, add tests) | unit | 1 | AC5.1 |
| `tests/unit/test_export_job_model.py` | unit | 2 | AC4.3 |
| `tests/integration/test_export_jobs.py` | integration | 2 | AC4.1, AC4.2, AC4.3, AC6.1, AC6.2 |
| `tests/integration/test_export_worker.py` | integration | 3 | AC1.1, AC1.3 |
| `tests/integration/test_export_download.py` | integration | 4 | AC3.1, AC3.2, AC3.3, AC3.4 |
| `tests/unit/pages/test_pdf_export_refactor.py` | unit | 5 | AC2.1, AC2.2, AC2.3, AC4.3, AC6.1 |
| `tests/e2e/test_export_queue.py` | playwright | 5 | AC1.2, AC2.3 |

### Human Verification

| AC | Justification |
|----|---------------|
| AC5.2 | Verifies NiceGUI runtime behaviour (client lifecycle on slow loads). The parameter-passing is confirmed by AC5.1's unit test; the runtime effect can only be observed in a live NiceGUI server with real WebSocket connections. |
