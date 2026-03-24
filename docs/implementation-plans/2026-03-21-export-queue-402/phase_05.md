# PDF Export Queue Implementation Plan — Phase 5

**Goal:** Replace synchronous in-handler PDF export with job submission and progress polling.

**Architecture:** `_handle_pdf_export()` gathers all data from live client context (highlights, HTML, notes, tag colours) and inserts an ExportJob row. A `ui.timer(2s)` polls job status and transitions the UI (spinner → download button). On page load, existing jobs are checked for state recovery. In-memory per-user lock removed (replaced by DB-level check from Phase 2).

**Tech Stack:** NiceGUI (`ui.timer`, `ui.download`, `ui.notification`, `ui.button`), ExportJob CRUD (Phase 2)

**Scope:** 5 of 6 phases from original design (Phase 5)

**Codebase verified:** 2026-03-21

---

## Acceptance Criteria Coverage

This phase implements and tests:

### export-queue-402.AC2: Progress feedback in UI
- **export-queue-402.AC2.1 Success:** After clicking export, spinner shows "Export queued..." then "Compiling PDF..." then download button appears
- **export-queue-402.AC2.2 Success:** Timer deactivates after job reaches terminal state (completed or failed)
- **export-queue-402.AC2.3 Edge:** Page reload during active export re-renders progress indicator for running job or download button for completed job

---

<!-- START_TASK_1 -->
### Task 1: Refactor _handle_pdf_export() to submit job instead of running inline

**Verifies:** export-queue-402.AC2.1, export-queue-402.AC4.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/pdf_export.py`

**Implementation:**

Replace the current synchronous export flow (lines 279-411) with a job submission flow.

**What stays the same:**
- `_extract_response_markdown()` — still extracts markdown from Milkdown editor or CRDT fallback
- `_check_word_count_enforcement()` — still runs word count dialogs before export
- Highlight extraction from CRDT doc
- Document content fetch from DB
- Pandoc conversion of markdown notes to LaTeX

**What changes:**
- Remove `_user_export_locks` dict and `_get_user_export_lock()` (lines 48-58) — replaced by DB-level per-user check
- Remove `_run_pdf_export()` function (lines 327-411) — replaced by job submission
- Replace the export execution block (lines 321-324) with:
  1. Gather all payload data (highlights, html_content, notes_latex, tag_colours, filename, word count params)
  2. Call `create_export_job(user_id, workspace_id, payload)` from Phase 2 CRUD
  3. If `BusinessLogicError` (concurrent export), show "A PDF export is already in progress" notification
  4. On success, call `_start_export_polling(job_id, state)` to begin UI polling

**Payload assembly** — gather data that currently lives in `_run_pdf_export()`:

```python
# All of this happens before job insertion (live client context required)
highlights = state.crdt_doc.get_highlights_for_document(str(state.document_id))
# ... anonymisation, tag enrichment ...
document = await get_document(state.document_id)
html_content = document.content
notes_latex = await markdown_to_latex_notes(response_markdown)
tag_colours = state.tag_colours()

payload = {
    "html_content": html_content,
    "highlights": highlights,
    "tag_colours": tag_colours,
    "general_notes": "",
    "notes_latex": notes_latex,
    "word_to_legal_para": legal_para_map,
    "filename": filename,
    "word_count": export_word_count,
    "word_minimum": state.word_minimum,
    "word_limit": state.word_limit,
}
```

The data gathering is the fast part (~1-2s). The expensive LaTeX compilation (up to 85s) is handled by the worker (Phase 3).

**Testing:**

Tests must verify each AC listed above:
- export-queue-402.AC2.1: Mock CRUD, call refactored handler, verify `create_export_job()` is called with correct payload structure
- export-queue-402.AC4.3: Mock `create_export_job()` to raise `BusinessLogicError`, verify notification shown

These are unit tests mocking the CRUD layer and NiceGUI UI elements. Place in `tests/unit/pages/test_pdf_export_refactor.py`.

**Verification:**

Run: `uv run grimoire test run tests/unit/pages/test_pdf_export_refactor.py`
Expected: All tests pass

**Commit:** `refactor: replace inline PDF export with job submission (#402)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add ui.timer polling for export job status

**Verifies:** export-queue-402.AC2.1, export-queue-402.AC2.2

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/pdf_export.py`

**Implementation:**

Add a `_start_export_polling()` function that creates a `ui.timer(2)` to poll job status:

```python
def _start_export_polling(job_id: UUID, state: PageState) -> None:
    """Start polling for export job status with UI transitions."""
    notification = ui.notification(
        "Export queued...",
        spinner=True,
        timeout=None,
        type="ongoing",
    ).props('data-testid="export-status-spinner"')

    async def _poll_status() -> None:
        job = await get_job(job_id)
        if job is None:
            notification.dismiss()
            timer.deactivate()
            return

        if job.status == "running":
            notification.message = "Compiling PDF..."
        elif job.status == "completed":
            notification.dismiss()
            timer.deactivate()
            _show_download_button(job.download_token, state)
        elif job.status == "failed":
            notification.dismiss()
            timer.deactivate()
            ui.notification(
                f"Export failed: {job.error_message}",
                type="negative",
                timeout=10,
            )

    timer = ui.timer(2, _poll_status)
```

**Status transitions:**
- `queued` → notification shows "Export queued..."
- `running` → notification updates to "Compiling PDF..."
- `completed` → notification dismissed, download button appears
- `failed` → notification dismissed, error notification shown

Timer deactivates on terminal states (`completed` or `failed`).

**Testing:**

Tests must verify each AC listed above:
- export-queue-402.AC2.1: Create a job, simulate status transitions (queued → running → completed), verify notification text changes and download button appears
- export-queue-402.AC2.2: Verify timer.deactivate() is called on completed and failed states

Mock NiceGUI UI elements (`ui.timer`, `ui.notification`) and test the polling callback logic as unit tests. Place in `tests/unit/pages/test_pdf_export_refactor.py` alongside Tasks 1 and 3. Do NOT use `nicegui_ui` marker — these are pure unit tests with mocked UI.

**Verification:**

Run: `uv run grimoire test run tests/unit/pages/test_pdf_export_refactor.py`
Expected: All tests pass

**Commit:** `feat: add ui.timer polling for export job status (#402)`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add download button with token URL

**Verifies:** export-queue-402.AC2.1, export-queue-402.AC3.1

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/pdf_export.py`

**Implementation:**

Add a `_show_download_button()` function:

```python
def _show_download_button(download_token: str, state: PageState) -> None:
    """Show download button for a completed export."""
    download_url = f"/export/{download_token}/download"

    ui.notification(
        "Your PDF is ready!",
        type="positive",
        timeout=5,
    )

    # Add download button — visible only in the current client context
    with ui.row().classes("items-center gap-2"):
        ui.button(
            "Download your PDF",
            icon="download",
            on_click=lambda: ui.download(download_url),
        ).props('color=positive data-testid="export-download-btn"')
```

Key points:
- `ui.download(download_url)` triggers the browser to fetch `/export/{token}/download` (Phase 4 FastAPI route)
- Button has `data-testid="export-download-btn"` for E2E testing
- The button is created in the current NiceGUI client context — visible only to the user who initiated the export
- Multi-use: clicking the button multiple times re-downloads from the same token URL (AC3.2)

**Testing:**

- export-queue-402.AC2.1: Verify download button appears after completed status
- export-queue-402.AC3.1: Verify `ui.download()` is called with correct token URL format

Unit test with mocked NiceGUI elements. Add to existing `tests/unit/pages/test_pdf_export_refactor.py`.

**Verification:**

Run: `uv run grimoire test run tests/unit/pages/test_pdf_export_refactor.py`
Expected: All tests pass

**Commit:** `feat: add download button with token URL for completed exports (#402)`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Page load recovery for existing export jobs

**Verifies:** export-queue-402.AC2.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/pdf_export.py`

**Implementation:**

Add a function called on page load (from the annotation page initialisation) to check for existing export jobs:

```python
async def check_existing_export(state: PageState) -> None:
    """On page load, recover state for any active or completed export."""
    if state.user_id is None:
        return

    job = await get_active_job_for_user(
        user_id=UUID(state.user_id),
        workspace_id=state.workspace_id,
    )

    if job is None:
        return

    if job.status in ("queued", "running"):
        # Re-start polling for the active job
        _start_export_polling(job.id, state)
    elif job.status == "completed" and job.download_token:
        # Show download button for completed job
        _show_download_button(job.download_token, state)
```

This function must be called from the annotation page header setup. The export button is wired up in `src/promptgrimoire/pages/annotation/header.py:148-162`. Call `check_existing_export(state)` in the header builder function, after the export button is created (after line 162). This ensures PageState is fully initialised and the export UI context is available. The header is rendered during `_render_workspace_view()` in `workspace.py` (around line 865).

**Testing:**

Tests must verify:
- export-queue-402.AC2.3 (queued/running): Create a running export job for user+workspace, call `check_existing_export()`, verify polling timer starts
- export-queue-402.AC2.3 (completed): Create a completed export job with valid token, call `check_existing_export()`, verify download button shown
- export-queue-402.AC2.3 (no job): Call `check_existing_export()` with no existing jobs, verify nothing happens

Place in `tests/unit/pages/test_pdf_export_refactor.py` or `tests/integration/` if DB required.

**Verification:**

Run: `uv run grimoire test run tests/unit/pages/test_pdf_export_refactor.py`
Expected: All tests pass

**Commit:** `feat: add page-load recovery for existing export jobs (#402)`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Remove in-memory per-user export lock

**Verifies:** export-queue-402.AC6.1

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/pdf_export.py`

**Implementation:**

Remove the following code that is no longer needed:
- `_user_export_locks: dict[str, asyncio.Lock] = {}` (line ~48)
- `_get_user_export_lock()` function (lines ~54-58)
- Lock acquisition in `_handle_pdf_export()` (lines ~291-296, ~321-324)

The per-user concurrency check is now handled by `create_export_job()` (Phase 2 CRUD) which checks the database for existing queued/running jobs and raises `BusinessLogicError`. The partial unique index is the real guard.

**Testing:**

- export-queue-402.AC6.1: Verify no in-memory lock references remain in the module (grep for `_user_export_lock`)

Add to existing test file. This is a cleanup task — the behavioral tests from Task 1 already cover the new path.

**Verification:**

Run: `uv run grimoire test all`
Expected: All tests pass, no references to old lock mechanism

Run: `uvx ty check`
Expected: No type errors

**Commit:** `refactor: remove in-memory per-user export lock (#402)`
<!-- END_TASK_5 -->

---

## Phase Verification

Run: `uv run complexipy src/promptgrimoire/pages/annotation/pdf_export.py src/promptgrimoire/pages/annotation/header.py --max-complexity-allowed 15`
Expected: No functions exceed threshold. Flag any functions at complexity 10-15 as at-risk.

## UAT Steps

1. [ ] Start the app: `uv run run.py`
2. [ ] Navigate to an annotation workspace
3. [ ] Click "Export PDF" — verify spinner shows "Export queued..." then "Compiling PDF..."
4. [ ] Wait for compilation — verify "Download your PDF" button appears
5. [ ] Click download button — verify PDF downloads
6. [ ] Reload the page — verify download button reappears for the completed export
7. [ ] Click "Export PDF" while an export is already running — verify "already in progress" notification
8. [ ] Run tests: `uv run grimoire test run tests/unit/pages/test_pdf_export_refactor.py`

## Evidence Required
- [ ] Screenshot/recording of spinner → download button transition
- [ ] Screenshot of page reload showing recovered download button
- [ ] Test output showing all tests pass
