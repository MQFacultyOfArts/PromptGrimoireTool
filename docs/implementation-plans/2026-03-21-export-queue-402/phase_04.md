# PDF Export Queue Implementation Plan — Phase 4

**Goal:** Raw FastAPI endpoint serving compiled PDFs via time-limited token.

**Architecture:** `@app.get()` route in `src/promptgrimoire/export/download.py`, registered at import time on the NiceGUI `app` singleton. Token-only authentication — no NiceGUI session dependency. `FileResponse` for PDF delivery.

**Tech Stack:** FastAPI/Starlette (`FileResponse`), NiceGUI `app` object, structlog

**Scope:** 4 of 6 phases from original design (Phase 4)

**Codebase verified:** 2026-03-21

---

## Acceptance Criteria Coverage

This phase implements and tests:

### export-queue-402.AC3: Download via FastAPI route
- **export-queue-402.AC3.1 Success:** Clicking download button triggers file download via `/export/{token}/download`
- **export-queue-402.AC3.2 Success:** Token is multi-use — repeat downloads within 24-hour TTL return the same PDF
- **export-queue-402.AC3.3 Failure:** Request with expired token (>24 hours) returns 404
- **export-queue-402.AC3.4 Failure:** Request with nonexistent token returns 404

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Download route handler

**Verifies:** export-queue-402.AC3.1, export-queue-402.AC3.2, export-queue-402.AC3.3, export-queue-402.AC3.4

**Files:**
- Create: `src/promptgrimoire/export/download.py`

**Implementation:**

```python
from __future__ import annotations

from pathlib import Path

import structlog
from nicegui import app
from starlette.responses import FileResponse, JSONResponse, Response

from promptgrimoire.db.export_jobs import get_job_by_token

logger = structlog.get_logger()


@app.get("/export/{token}/download")
async def download_export(token: str) -> Response:
    """Serve a compiled PDF via download token.

    Token-only authentication — no NiceGUI session dependency.
    Multi-use within 24-hour TTL. Returns 404 for expired or
    nonexistent tokens.
    """
    job = await get_job_by_token(token)

    if job is None:
        return JSONResponse(
            {"detail": "Export not found or expired"},
            status_code=404,
        )

    if job.pdf_path is None:
        logger.warning(
            "export_pdf_path_null",
            export_job_id=str(job.id),
        )
        return JSONResponse(
            {"detail": "Export file not available"},
            status_code=404,
        )

    pdf_path = Path(job.pdf_path)
    if not pdf_path.exists():
        logger.warning(
            "export_pdf_missing",
            export_job_id=str(job.id),
            pdf_path=str(pdf_path),
        )
        return JSONResponse(
            {"detail": "Export file no longer available"},
            status_code=404,
        )

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=pdf_path.name,
    )
```

Key points:
- `get_job_by_token()` (from Phase 2 CRUD) checks both token existence AND expiry
- Multi-use: no token invalidation on download — same token works for 24 hours
- If the PDF file was deleted from disk but the DB record still exists, return 404 with a warning log
- `filename=pdf_path.name` sets the Content-Disposition header for download

**Testing:**

Tests must verify each AC listed above:
- export-queue-402.AC3.1: Create a completed ExportJob with valid token and real PDF file, GET `/export/{token}/download`, verify 200 response with `application/pdf` content type
- export-queue-402.AC3.2: GET the same URL twice, verify both return 200 with identical content
- export-queue-402.AC3.3: Create a completed ExportJob with `token_expires_at` in the past, GET the URL, verify 404
- export-queue-402.AC3.4: GET `/export/nonexistent-token/download`, verify 404

These are integration tests requiring a database. For AC3.1 and AC3.2, create a real PDF file in a temp directory. Place in `tests/integration/test_export_download.py`. Include skip guard for `TEST_DATABASE_URL`.

Use `httpx.AsyncClient` with the Starlette/FastAPI test client pattern to test the route directly without starting a server.

**Verification:**

Run: `uv run grimoire test run tests/integration/test_export_download.py`
Expected: All tests pass

**Commit:** `feat: add download route for token-based PDF delivery (#402)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Register download route at app startup

**Verifies:** None (infrastructure — verified operationally)

**Files:**
- Modify: `src/promptgrimoire/__init__.py`

**Implementation:**

Import the download module in `main()` function so the `@app.get()` decorator registers the route. Add the import alongside existing page imports (around the `import promptgrimoire.pages` line):

```python
import promptgrimoire.export.download  # noqa: F401 — registers /export/{token}/download route
```

The `# noqa: F401` is needed because this is a side-effect import (the module isn't referenced, it just needs to be loaded to register the route decorator).

**Verification:**

Run: `uv run run.py` (start the app)
Expected: No startup errors. Navigating to `/export/test/download` returns 404 JSON (not a server error).

Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: register export download route at app startup (#402)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

---

## Phase Verification

Run: `uv run complexipy src/promptgrimoire/export/download.py --max-complexity-allowed 15`
Expected: No functions exceed threshold

## UAT Steps

1. [ ] Start the app: `uv run run.py`
2. [ ] Navigate to `/export/test/download` in browser — verify 404 JSON response (not a 500)
3. [ ] Run integration tests: `uv run grimoire test run tests/integration/test_export_download.py`

## Evidence Required
- [ ] Route responds with 404 JSON for invalid token
- [ ] All integration tests pass (valid download, multi-use, expired token, nonexistent token)
