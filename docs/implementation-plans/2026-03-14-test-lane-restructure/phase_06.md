# Test Lane Restructure Implementation Plan

**Goal:** Restructure the test suite around a formal lane model with a `smoke` marker for toolchain-dependent tests.

**Architecture:** Define `smoke` pytest marker, propagate through decorator factories, exclude from default test runs. Each new lane is a `_run_pytest()` call producing a `LaneResult`.

**Tech Stack:** pytest, pytest-xdist, typer CLI

**Scope:** 6 phases from original design (phases 1-6)

**Codebase verified:** 2026-03-14

---

## Acceptance Criteria Coverage

This phase implements and tests:

### test-lane-restructure.AC6: Documentation updated
- **test-lane-restructure.AC6.1 Verify:** `docs/testing.md` contains command-to-lane matrix
- **test-lane-restructure.AC6.2 Verify:** No references to `all-fixtures` in `docs/testing.md` or `CLAUDE.md`

---

## Phase 6: Update Documentation

<!-- START_TASK_1 -->
### Task 1: Add lane/verb matrix to docs/testing.md and remove all-fixtures

**Verifies:** test-lane-restructure.AC6.1, test-lane-restructure.AC6.2

**Files:**
- Modify: `docs/testing.md` (around line 234, after Test Markers table; line 236 remove all-fixtures reference)

**Implementation:**

1. Remove the `all-fixtures` reference at line 236 (`To include BLNS and slow tests: \`uv run grimoire test all-fixtures\`.`)

2. Add a new subsection documenting the lane model and command-to-lane matrix. Place it after the Test Markers section. Include:
   - Lane definitions table (lane name, path filter, marker filter, workers, purpose)
   - Command-to-lane matrix showing which lanes each command runs
   - Brief explanation of the `smoke` marker and how it propagates through decorators
   - Note that `e2e all` summary output shows all lane results

Use the tables from the design plan's Architecture section as the reference format.

**Testing:**
- test-lane-restructure.AC6.1: docs/testing.md contains the command-to-lane matrix
- test-lane-restructure.AC6.2: No references to all-fixtures in docs/testing.md

## UAT Steps
1. Run: `grep -n "all-fixtures" docs/testing.md`
2. Verify: No results
3. Run: `grep -n "Lane" docs/testing.md`
4. Verify: Lane definitions table and command-to-lane matrix found

## Evidence Required
- [ ] Grep output showing no all-fixtures references
- [ ] docs/testing.md contains lane matrix

**Commit:** `docs: add lane/verb matrix and remove all-fixtures from testing.md`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Simplify CLAUDE.md Key Commands for test workflow

**Verifies:** test-lane-restructure.AC6.2

**Files:**
- Modify: `CLAUDE.md` (Key Commands section, lines 85-155)

**Implementation:**

Streamline the test-related commands in Key Commands to focus on the three essential commands:

1. `uv run grimoire test run <path>::<test>` — run any specific test anywhere (auto-detects type)
2. `uv run grimoire test all` — fast unit tests only (excludes smoke, E2E, integration)
3. `uv run grimoire e2e all` — full 6-lane suite (unit, integration, playwright, nicegui, smoke, blns+slow) with summary table at the end

Remove `test all-fixtures` if referenced (investigation found it's not currently in CLAUDE.md, but verify at implementation time). Keep other E2E commands (`e2e run`, `e2e slow`, etc.) that are still valid.

Update the `e2e all` description to note it runs 6 lanes and the last lines of output show the useful summary.

Ensure no `all-fixtures` references remain.

**Testing:**
- test-lane-restructure.AC6.2: No references to all-fixtures in CLAUDE.md

## UAT Steps
1. Run: `grep -n "all-fixtures" CLAUDE.md`
2. Verify: No results
3. Run: `grep -n "e2e all" CLAUDE.md`
4. Verify: Updated e2e all description found within Key Commands section (lines 85-155)
5. Run: `uv run grimoire docs build 2>&1 | tail -5`
6. Verify: Documentation builds successfully

## Evidence Required
- [ ] Grep output showing no all-fixtures references in CLAUDE.md
- [ ] e2e all description updated in Key Commands section
- [ ] docs build succeeds

**Commit:** `docs: update CLAUDE.md Key Commands for new test lane structure`
<!-- END_TASK_2 -->
