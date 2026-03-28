# Annotation Deferred Load — Phase 4: Measurement and Verification

**Goal:** Run the full test suite and performance benchmarks to verify the deferred loading changes produce measurable improvement without regressions.

**Architecture:** Uses existing `grimoire e2e perf` infrastructure and `test_browser_perf_377.py` instrumentation. Captures before/after responseEnd timing and server-side phase durations.

**Tech Stack:** Playwright performance API, structlog timing events, pytest perf marker.

**Scope:** Phase 4 of 4 from original design.

**Codebase verified:** 2026-03-25

---

## Acceptance Criteria Coverage

This phase implements and tests:

### annotation-deferred-load-377.AC6: Tests pass + measurable improvement
- **annotation-deferred-load-377.AC6.1:** `uv run grimoire test all` passes (3,573+ tests)
- **annotation-deferred-load-377.AC6.2:** `grimoire e2e perf` shows responseEnd improvement (before/after comparison documented)

---

## Reference Files

The task-implementor should read these files for context:

- **Perf test:** `tests/e2e/test_browser_perf_377.py` (existing perf instrumentation)
- **Perf CLI:** `src/promptgrimoire/cli/e2e/__init__.py:555-589` (grimoire e2e perf command)
- **Testing patterns:** `docs/testing.md`, `CLAUDE.md`

---

<!-- START_TASK_1 -->
### Task 1: Capture baseline performance measurements

**Verifies:** None (infrastructure — establishes baseline for comparison)

**Files:**
- No files modified

**Implementation:**

Before any changes are deployed, capture baseline performance numbers using the existing instrumentation. This must be done on the `main` branch (or the state before Phase 1-3 changes).

**Step 1: Run baseline perf test**
```bash
# Switch to main branch baseline (or run before merging Phase 1-3)
uv run grimoire e2e perf -v -s
```

**Step 2: Record the following metrics from test output:**
- `responseEnd` (ms) — time from navigation start to server response complete
- `page_load_total` (ms) — server-side total from structlog
- `resolve_step` (ms) — server-side context resolution
- `render_phase` (ms) — server-side UI rendering
- Whether "Response not ready" warning appears in logs

**Step 3: Save baseline numbers** in a comment on issue #377 or in a local file for comparison.

**Verification:**
Perf test runs to completion and outputs timing numbers.

**Commit:** None (measurement only)

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Run full test suite

**Verifies:** annotation-deferred-load-377.AC6.1

**Files:**
- No files modified

**Implementation:**

Run the full test suite to verify no regressions from Phase 1-3 changes.

**Step 1: Run unit + integration tests**
```bash
uv run grimoire test all
```
Expected: All tests pass (3,573+ tests)

**Step 2: Run E2E tests**
```bash
uv run grimoire e2e run
```
Expected: All E2E tests pass

**Step 3: If any tests fail**, investigate and fix before proceeding. Do not skip failing tests.

**Verification:**
Run: `uv run grimoire test all && uv run grimoire e2e run`
Expected: All green

**Commit:** None (verification only) — or fix commits if regressions found

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Capture post-change performance measurements

**Verifies:** annotation-deferred-load-377.AC6.2

**Files:**
- No files modified

**Implementation:**

Run the perf tests again with all Phase 1-3 changes in place.

**Step 1: Run perf test**
```bash
uv run grimoire e2e perf -v -s
```

**Step 2: Record the same metrics as baseline:**
- `responseEnd` (ms)
- `page_load_total` (ms)
- `resolve_step` (ms)
- `render_phase` (ms)
- Whether "Response not ready" warning appears

**Step 3: Compare before/after**

Expected improvements:
- `responseEnd` should drop from 3000+ ms to <50ms (skeleton renders immediately)
- "Response not ready" warning should no longer appear
- `page_load_total` may not change much (same total DB work), but it now happens in the background
- `resolve_step` should decrease (JOINed query vs sequential)

**Step 4: Document results** in issue #377 comment with before/after table.

**Verification:**
Perf test shows measurable responseEnd improvement.

**Commit:** None (measurement only)

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update existing perf test for deferred load pattern

**Verifies:** annotation-deferred-load-377.AC6.2

**Files:**
- Modify: `tests/e2e/test_browser_perf_377.py`

**Implementation:**

The existing perf test may need to be updated to account for the deferred loading pattern:

1. **Wait for content, not page load:** After navigating to the annotation page, the test should wait for `window.__loadComplete` (set by the background task in Phase 2) rather than assuming content is available immediately after navigation.

2. **Measure two timings:**
   - `responseEnd` (skeleton delivered) — should be <50ms
   - Time until `__loadComplete` (full content rendered) — total wall-clock time

3. **Update assertions:** If the test asserts timing thresholds, update them to reflect the new skeleton-first pattern.

4. **Verify `resolve_step` timing** reflects the JOINed query (should be lower than baseline sequential queries).

Review the existing test structure and adapt minimally — the instrumentation framework is already in place.

**Verification:**
Run: `uv run grimoire e2e perf -v -s`
Expected: Test passes with updated timing expectations

**Commit:** `test(perf): update perf test for deferred load pattern`

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Update issue #377 with results

**Verifies:** annotation-deferred-load-377.AC6.2

**Files:**
- No files modified

**Implementation:**

Post a comment on GitHub issue #377 with the before/after comparison:

```markdown
## Performance Results

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| responseEnd | Xms | Yms | -Z% |
| page_load_total | Xms | Yms | -Z% |
| resolve_step | Xms | Yms | -Z% |
| "Response not ready" warning | Yes/No | Yes/No | |
| DB sessions per page load | 10 | 2-3 | -70% |

[Include test output or screenshots as evidence]
```

```bash
gh issue comment 377 --body "$(cat <<'EOF'
## Performance Results
[paste comparison table]
EOF
)"
```

**Verification:**
Comment visible on #377.

**Commit:** None (documentation only)

<!-- END_TASK_5 -->
