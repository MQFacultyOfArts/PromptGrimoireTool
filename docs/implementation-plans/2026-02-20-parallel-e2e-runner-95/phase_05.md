# Parallel E2E Test Runner - Phase 5: Cleanup and Documentation

**Goal:** Update documentation to reflect the new parallel mode, its database isolation model, log file locations, and debugging guidance.

**Architecture:** Infrastructure phase — documentation updates only. No code changes. The database cleanup and error reporting logic was already implemented in Phase 3 (orchestrator teardown). This phase documents the operational behaviour.

**Tech Stack:** Markdown documentation

**Scope:** 5 of 5 phases from original design (phase 5)

**Codebase verified:** 2026-02-20

---

## Acceptance Criteria Coverage

**Verifies: None** — This is an infrastructure/documentation phase. Database cleanup was implemented in Phase 3. This phase documents it.

---

## Reference Files

The executor and its subagents should read these files for context:

- `docs/testing.md` — E2E test guidelines, database test architecture. Add parallel mode section.
- `docs/e2e-debugging.md` — E2E debugging investigation. Add parallel mode debugging section.
- `CLAUDE.md` — project conventions. Update `--parallel` description.
- `docs/implementation-plans/2026-02-20-parallel-e2e-runner-95/phase_03.md` — orchestrator behaviour to document
- `docs/implementation-plans/2026-02-20-parallel-e2e-runner-95/phase_04.md` — CLI integration to document

---

## Codebase Verification Findings

- `docs/testing.md` has no mention of `--parallel` or parallel mode. E2E section covers test structure, helpers, pitfalls. Natural insertion point: after "Common E2E Pitfalls" (around line 48), as a new "Running E2E Tests" subsection.
- `docs/e2e-debugging.md` is a historical investigation narrative about serial mode failures. No parallel content. Natural insertion point: new section at end, after "Key Files" table.
- CLAUDE.md describes `--parallel` as "xdist" — needs updating to reflect the new orchestrator.

---

<!-- START_TASK_1 -->
### Task 1: Update docs/testing.md with parallel mode section

**Verifies:** None (documentation)

**Files:**
- Modify: `docs/testing.md` (add section after "Common E2E Pitfalls", around line 48)

**Implementation:**

Add a new subsection "Running E2E Tests" within the "E2E Test Guidelines" section. This should cover:

**Serial mode (default):**
- `uv run test-e2e` — single server, fail-fast (`-x`), all test files run sequentially
- `uv run test-e2e -k test_name` — run specific test(s)
- `uv run test-e2e-debug` — re-run last-failed tests with verbose output (`--lf -x --tb=long -v`)

**Parallel mode:**
- `uv run test-e2e --parallel` — one server+database per test file, all files run concurrently
- Each test file gets its own NiceGUI server on a distinct port
- Each test file gets its own PostgreSQL database, cloned from the branch test database via `CREATE DATABASE ... TEMPLATE`
- Wall-clock time approximately equals the slowest individual test file
- User args (e.g. `-k`, `-v`) are forwarded to each pytest subprocess
- `-k` filters that match nothing in a file produce exit code 5, treated as pass

**Database isolation model:**
- Branch test database (e.g. `pg_test_95_annotation_tags`) is the template
- Worker databases named `{branch_db}_w0`, `{branch_db}_w1`, etc.
- On success: worker databases are dropped automatically
- On failure: worker databases are preserved and connection strings logged for debugging

**Log files:**
- Each worker writes to `test-e2e-{test_file_stem}.log` in a temp directory
- On failure, log file paths are printed to console
- Server and pytest output are merged into the same log file

**Verification:**
Read the updated file and confirm it renders correctly as markdown.

**Commit:** `docs: add parallel E2E mode documentation to testing.md`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update docs/e2e-debugging.md with parallel mode section

**Verifies:** None (documentation)

**Files:**
- Modify: `docs/e2e-debugging.md` (add new section at end, after "Key Files" table)

**Implementation:**

Add a new top-level section "Parallel Mode Debugging" at the end of the file. This should cover:

**Differences from serial mode:**
- Each test file runs in its own pytest process with its own server
- Failures in one file do not affect other files (unless fail-fast mode)
- Log files are per-worker, not shared

**Debugging a parallel failure:**
1. Check the summary output for which file(s) failed
2. Read the worker's log file (path printed on failure)
3. Worker databases are preserved on failure — connect directly to inspect state
4. Re-run the failing file in serial mode for interactive debugging: `uv run test-e2e -k test_file_name` or `uv run test-e2e-debug -k test_file_name`

**Common parallel-specific issues:**
- Port conflicts: unlikely (ports allocated simultaneously) but if it happens, re-run
- Database connection limits: 16 workers x pool_size could exceed PostgreSQL's `max_connections=100`. If connection errors appear, check `SHOW max_connections;` and increase if needed.
- Template database locking: `CREATE DATABASE ... TEMPLATE` requires no active connections on the template. The orchestrator terminates lingering connections before cloning.

**Key files (additions):**
- `test-e2e-{stem}.log` — per-worker combined server+pytest output
- Worker databases `{branch_db}_wN` — preserved on failure for inspection

**Verification:**
Read the updated file and confirm it renders correctly as markdown.

**Commit:** `docs: add parallel mode debugging section to e2e-debugging.md`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update CLAUDE.md parallel mode description

**Verifies:** None (documentation)

**Files:**
- Modify: `CLAUDE.md` (update the `--parallel` line in Key Commands)

**Implementation:**

In the "Key Commands" section of CLAUDE.md, update the parallel E2E description from:

```
# Run E2E tests in parallel (xdist)
uv run test-e2e --parallel
```

to:

```
# Run E2E tests in parallel (isolated servers + databases per file)
uv run test-e2e --parallel
```

This reflects that parallel mode now uses the custom orchestrator with per-file isolation, not xdist.

Also update the "E2E Test Isolation" section if it mentions xdist for E2E parallel mode. The xdist reference should be removed for E2E specifically (xdist is still used by `test-all` and `test-debug`).

**Verification:**
Read CLAUDE.md and confirm the updates are accurate.

**Commit:** `docs: update CLAUDE.md parallel mode description`
<!-- END_TASK_3 -->
