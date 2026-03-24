# PDF Export Queue Implementation Plan — Phase 6

**Goal:** Update user-facing guide and developer docs to reflect the queue-based export flow.

**Architecture:** Update existing documentation files. No new code.

**Tech Stack:** Guide DSL (`guide.py`), mkdocs, pandoc

**Scope:** 6 of 6 phases from original design (Phase 6)

**Codebase verified:** 2026-03-21

---

## Acceptance Criteria Coverage

This phase implements and tests:

**Verifies: None** — documentation phase. Verified operationally by `uv run grimoire docs build` succeeding.

---

<!-- START_TASK_1 -->
### Task 1: Update user-facing guide for export flow

**Verifies:** None

**Files:**
- Modify: `src/promptgrimoire/docs/scripts/using_promptgrimoire.py` (lines 418-430, `_entry_export_pdf()` function)

**Implementation:**

Update the `_entry_export_pdf()` function's `.note()` text to describe the new queue-based UX. The current text says:

> "On the Annotate tab, click the **Export PDF** button. The export includes your conversation with highlights, comments, and written response."

Replace with text describing:
1. Click **Export PDF** button on the Annotate tab
2. A progress indicator shows the export status ("Export queued..." → "Compiling PDF...")
3. When compilation finishes, a **Download your PDF** button appears
4. Click the button to download your PDF
5. You can close or reload the page while the PDF is compiling — the download button will appear when you return
6. The download link is available for 24 hours

Keep `_entry_pdf_filename()` (lines 1160-1203) unchanged — the filename assembly logic is the same.

If the `_entry_export_pdf()` function uses `.screenshot()` calls, these will need updating to capture the new UI elements (progress spinner, download button). The docs build (`uv run grimoire docs build`) runs a live server and captures screenshots via Playwright, so the screenshots will reflect whatever UI is rendered at that point.

**Verification:**

Run: `uv run grimoire docs build`
Expected: Build succeeds without errors

**Commit:** `docs: update user guide for queue-based PDF export (#402)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update developer docs for export architecture

**Verifies:** None

**Files:**
- Modify: `docs/export.md`

**Implementation:**

Add a new section to `docs/export.md` titled "## Export Queue" covering:

1. **Overview** — PDF export decoupled from page handler via database-backed job queue
2. **ExportJob table** — schema summary (status lifecycle, payload JSON, download token, TTL)
3. **Data flow** — page handler gathers data → INSERT ExportJob → worker claims → pipeline runs → status updated → UI polls → download via token
4. **Worker** — async polling loop (5s interval), FOR UPDATE SKIP LOCKED claiming, fair scheduling, cleanup sweep
5. **Per-user concurrency** — partial unique index on `(user_id) WHERE status IN ('queued', 'running')`, application-level pre-check for friendly error message
6. **Download route** — `/export/{token}/download`, token-only auth, multi-use within 24h TTL, FileResponse
7. **response_timeout** — raised to 60s in `page_route` decorator (permanent fix for #377 Finding 6)

Update the existing "Concurrency and Process Safety" section to reflect:
- Remove mention of per-user asyncio.Lock (replaced by DB-level check)
- Add reference to the new per-user concurrency limit via partial unique index
- Semaphore(2) is unchanged

**Verification:**

Run: `uv run grimoire docs build`
Expected: Build succeeds without errors

**Commit:** `docs: add export queue architecture to developer docs (#402)`
<!-- END_TASK_2 -->

---

## UAT Steps

1. [ ] Run docs build: `uv run grimoire docs build`
2. [ ] Verify build completes without errors
3. [ ] Open generated documentation and verify export section reflects queue-based flow

## Evidence Required
- [ ] `uv run grimoire docs build` output showing success
- [ ] User guide text mentions progress spinner and download button
