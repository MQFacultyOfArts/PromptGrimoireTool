# Preregistered UAT Experiment — export-queue-402

**Date preregistered:** 2026-03-22
**Branch:** `402-pdf-export-fix`
**Worktree:** `.worktrees/402-pdf-export-fix`
**Issue:** `#402`
**Scope:** UAT for the queue-based export implementation once phases 3-5 are complete enough to exercise the full user flow.

## Purpose

This experiment is preregistered to answer one narrow question:

**Does the new queue-based export flow remove the user-visible failure mode where a long-running export finishes server-side but the original NiceGUI callback context is no longer usable for delivery?**

This experiment does **not** attempt to prove the original incident mechanism was specifically page `response_timeout`, stale slot weakref, websocket reconnect timing, or CPU pressure. The point is narrower and more practical:

- the old flow kept compile and delivery inside the original NiceGUI callback context
- the new flow should make compile and delivery independent of that original callback context

If the implementation passes this experiment, it has addressed the primary product concern even if the historical root-cause narrative remains partially disputed.

## Preregistered Hypotheses

### H1: Lifecycle decoupling

After export submission, the job can complete and remain downloadable even if the initiating browser tab reloads or disconnects before compilation finishes.

### H2: Same-user retry containment

While one export job is active for a user, a second export request from that same user is rejected before a second compile starts.

### H3: Download transport decoupling

The completed PDF is served by a token route independent of the original export callback, and repeat downloads within the token TTL succeed.

## Primary Endpoints

### Primary endpoint A: Reload/disconnect resilience

Pass if all of the following are true in one UAT run:

1. User submits export.
2. The page is reloaded or the tab is closed and reopened before compile finishes.
3. The export job reaches `completed`.
4. The user can later download the PDF from the reloaded/reconnected page.

### Primary endpoint B: No same-user double-spawn

Pass if all of the following are true in one UAT run:

1. User starts export A.
2. User attempts export B before A completes.
3. Export B is rejected with the expected user-facing message.
4. Evidence shows only one job was processed and only one compile started.

### Secondary endpoint C: Multi-use download

Pass if the same completed export can be downloaded twice within token TTL without re-export.

## Preconditions

This UAT experiment is **invalid** unless all of the following are already true in the candidate build:

1. The inline export path in `src/promptgrimoire/pages/annotation/pdf_export.py` no longer awaits `export_annotation_pdf(...)` directly from the button callback.
2. A worker exists and is started at app startup.
3. A token-based download route exists.
4. Reconnect/reload recovery exists in the annotation export UI.
5. The planned automated tests for queue, worker, download route, and page refactor are present and passing.

If any precondition is false, stop. Do not run UAT and do not claim the experiment failed. It is not ready.

## Required Evidence Bundle

The implementer must supply all of the following artifacts for evaluator review:

1. Git commit SHA.
2. `git diff --stat main...HEAD` from the `402-pdf-export-fix` worktree.
3. Output from the relevant automated tests:
   - `uv run grimoire test run tests/unit/pages/test_registry.py`
   - `uv run grimoire test run tests/integration/test_export_jobs.py`
   - `uv run grimoire test run tests/integration/test_export_worker.py`
   - `uv run grimoire test run tests/integration/test_export_download.py`
   - `uv run grimoire test run tests/unit/pages/test_pdf_export_refactor.py`
   - `uv run grimoire e2e run -k "export_queue"`
4. A screen recording or timestamped screenshots of the UAT run covering:
   - export submission
   - in-progress UI state
   - reload or reconnect
   - recovered UI state
   - download button
   - completed download
5. Relevant server log excerpt covering:
   - job enqueue
   - job claim/start
   - job completion or failure
   - any rejection of duplicate export attempts
6. One reproducible DB evidence snapshot showing job states for the tested user/workspace during the run.

If the evidence bundle is incomplete, evaluators must return **inconclusive**, not pass.

## Experimental Procedure

Use one authenticated user and one annotation workspace containing enough content that export takes at least 10 seconds locally. Runs shorter than 10 seconds are invalid for endpoint A because they do not meaningfully exercise lifecycle disruption.

### Run 1: Reload During Active Export

1. Start the app from the `402-pdf-export-fix` worktree.
2. Open the annotation workspace as user A.
3. Click **Export PDF**.
4. Confirm the UI shows the queued/running state expected by the implementation.
5. Before the export completes, hard-reload the page.
6. Return to the same workspace.
7. Wait for the export to finish.
8. Confirm the UI recovers to the correct state and exposes a download affordance.
9. Download the PDF.

**Prediction if H1 is true:**

- the export job completes without the original callback context
- the page recovers state after reload
- the PDF downloads successfully after reload

**Prediction if H1 is false:**

- the job is lost, stuck, or orphaned
- the UI does not recover the job state
- the PDF exists on disk or in DB state but is not recoverably downloadable from the reloaded page

### Run 2: Close/Reopen During Active Export

1. Start a fresh export as user A.
2. Close the tab entirely while the job is running.
3. Reopen the app and navigate back to the same workspace as the same user.
4. Wait for completion.
5. Download the finished PDF.

**Prediction if H1 is true:**

- the job remains tied to durable state, not tab-local callback state
- reopening the page recovers the running or completed job

### Run 3: Same-User Retry Containment

1. Start an export as user A.
2. Before it completes, attempt a second export as the same user.
3. This may be from the same tab, a reloaded tab, or a second browser tab.
4. Capture the user-facing result and the server evidence.

**Prediction if H2 is true:**

- the second request is rejected
- only one active job exists
- only one compile starts

**Prediction if H2 is false:**

- two jobs are created, or
- two compiles start, or
- the UI accepts the second request despite the active job

### Run 4: Multi-Use Download

1. After a completed export exists, click the download button twice.
2. If the implementation exposes the raw token URL via logs or UI, also confirm the same token is used for both downloads.

**Prediction if H3 is true:**

- both downloads succeed
- no second export is required

## Hard Failure Conditions

The experiment is an automatic **fail** if any of the following occur:

1. The export still depends on `ui.download(pdf_path)` inside the original long-running export callback.
2. A reload or reconnect during compile causes the job to disappear or become undownloadable.
3. The second export attempt from the same user starts a second compile.
4. The UI still emits the old stale-context failure pattern during the tested flow.
5. The completed PDF is only recoverable through manual filesystem retrieval rather than the intended product flow.

## Evaluator Rules

Claude and Codex should evaluate against this document, not against free-form prose from the implementer.

Evaluators should mark the result:

- **Pass** if all primary endpoints pass and the evidence bundle is complete.
- **Fail** if any hard failure condition is met.
- **Inconclusive** if artifacts are missing, timings are too short, or the implementation is not yet at the required phase boundary.

Evaluators must not award a pass based on:

- code review alone
- implementer claims without artifacts
- automated tests alone without the preregistered UAT evidence

## Interpretation Rules

If the experiment passes:

- conclude that the queue-based design has addressed the main product concern for `#402`
- do **not** conclude that the historical root-cause story was proven correct

If the experiment fails:

- conclude that the implementation has not yet decoupled delivery from lifecycle strongly enough
- do **not** patch the narrative first; fix the mechanism and rerun the preregistered experiment

## Fastest Follow-Up If It Fails

If endpoint A fails:

- inspect the reconnect recovery path first
- verify the job reached durable terminal state independently of the page
- check whether the UI is failing to rediscover an already-completed job

If endpoint B fails:

- inspect DB-level active-job enforcement before touching UI code
- verify the partial unique index and job-creation race handling

If endpoint C fails:

- inspect the token route and persistence path before touching the worker

## References

- Design plan: `docs/design-plans/2026-03-21-export-queue-402.md`
- Test requirements: `docs/implementation-plans/2026-03-21-export-queue-402/test-requirements.md`
- Current inline export path to be removed/refactored: `src/promptgrimoire/pages/annotation/pdf_export.py`
- Export button callback entrypoint: `src/promptgrimoire/pages/annotation/header.py`
