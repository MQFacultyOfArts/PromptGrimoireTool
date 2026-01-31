# Test Suite Consolidation - Phase 6: Deprecate and remove demo tests

**Goal:** Clean removal of demo-dependent tests after coverage is verified

**Architecture:** Staged deprecation with skip markers before deletion

**Tech Stack:** pytest, git

**Scope:** Phase 6 of 6 from original design

**Codebase verified:** 2026-01-31

---

## Phase Overview

Move demo test files to a deprecated directory with skip markers, verify CI runs correctly, then delete after a verification period.

**Files to deprecate:**
- `tests/e2e/test_live_annotation.py`
- `tests/e2e/test_text_selection.py`
- `tests/e2e/test_two_tab_sync.py`
- `tests/e2e/test_user_isolation.py`

---

<!-- START_TASK_1 -->
### Task 1: Create deprecated directory and move files

**Files:**
- Create: `tests/e2e/deprecated/`
- Move: 4 demo test files

**Step 1: Create the deprecated directory**

```bash
mkdir -p tests/e2e/deprecated
```

**Step 2: Move the demo test files**

```bash
mv tests/e2e/test_live_annotation.py tests/e2e/deprecated/
mv tests/e2e/test_text_selection.py tests/e2e/deprecated/
mv tests/e2e/test_two_tab_sync.py tests/e2e/deprecated/
mv tests/e2e/test_user_isolation.py tests/e2e/deprecated/
```

**Step 3: Create __init__.py for the deprecated package**

Create `tests/e2e/deprecated/__init__.py`:

```python
"""Deprecated E2E tests pending deletion.

These tests depend on /demo/* routes that are being removed.
Coverage has been migrated to:
- tests/e2e/test_annotation_page.py
- tests/e2e/test_annotation_sync.py
- tests/e2e/test_annotation_collab.py
- tests/e2e/test_auth_and_isolation.py

See docs/implementation-plans/2026-01-31-test-suite-consolidation/coverage-mapping.md
for the full coverage analysis.

These files will be deleted after verification period.
"""
```

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add skip markers to deprecated tests

**Files:**
- Modify: `tests/e2e/deprecated/test_live_annotation.py`
- Modify: `tests/e2e/deprecated/test_text_selection.py`
- Modify: `tests/e2e/deprecated/test_two_tab_sync.py`
- Modify: `tests/e2e/deprecated/test_user_isolation.py`

**Step 1: Add skip marker to test_live_annotation.py**

Add at the top of the file after imports:

```python
pytestmark = [
    pytest.mark.skip(
        reason="Deprecated: coverage migrated to test_annotation_page.py, "
        "test_annotation_sync.py, test_annotation_collab.py. "
        "Paragraph tests blocked on Issue #99. "
        "See coverage-mapping.md for details."
    )
]
```

**Step 2: Add skip marker to test_text_selection.py**

```python
pytestmark = [
    pytest.mark.skip(
        reason="Deprecated: demo-specific tests not applicable to /annotation route. "
        "Text selection patterns differ (click+shift vs drag). "
        "See coverage-mapping.md for details."
    )
]
```

**Step 3: Add skip marker to test_two_tab_sync.py**

```python
pytestmark = [
    pytest.mark.skip(
        reason="Deprecated: coverage migrated to test_annotation_sync.py. "
        "Raw text CRDT tests not applicable to highlight CRDT. "
        "See coverage-mapping.md for details."
    )
]
```

**Step 4: Add skip marker to test_user_isolation.py**

```python
pytestmark = [
    pytest.mark.skip(
        reason="Deprecated: coverage migrated to test_auth_and_isolation.py. "
        "See coverage-mapping.md for details."
    )
]
```

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify CI runs only new tests

**Files:**
- None (verification only)

**Step 1: Run pytest to verify skips**

```bash
uv run pytest tests/e2e/ -v --tb=no 2>&1 | grep -E "(SKIP|PASS|FAIL|test_)"
```

Expected: Deprecated tests show as SKIPPED, new tests PASSED.

**Step 2: Verify test count**

```bash
uv run pytest tests/e2e/ --co -q 2>&1 | tail -5
```

Expected: Shows collected test count. Skipped tests are still collected but not run.

**Step 3: Run only non-deprecated tests to verify coverage**

```bash
uv run pytest tests/e2e/ --ignore=tests/e2e/deprecated/ -v --tb=short
```

Expected: All tests pass without the deprecated directory.

**Step 4: Commit the deprecation**

```bash
git add tests/e2e/deprecated/
git commit -m "$(cat <<'EOF'
refactor(tests): move demo tests to deprecated directory

Moves 4 demo-dependent test files to tests/e2e/deprecated/:
- test_live_annotation.py
- test_text_selection.py
- test_two_tab_sync.py
- test_user_isolation.py

All files marked with pytest.mark.skip explaining:
- Where coverage was migrated
- What's blocked (paragraph detection on Issue #99)
- Why tests aren't applicable

Tests will be deleted after verification period.
See coverage-mapping.md for full analysis.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update CI configuration (if needed)

**Files:**
- Review: `.github/workflows/` (if exists)

**Step 1: Check if CI excludes deprecated tests**

If CI runs `pytest tests/`, the deprecated tests will be skipped but still collected. This is fine for the verification period.

For faster CI, optionally update to:

```yaml
- run: uv run pytest tests/ --ignore=tests/e2e/deprecated/
```

**Step 2: Verify CI passes**

Push changes and verify CI workflow passes:

```bash
git push origin HEAD
```

Check GitHub Actions for pass/fail status.

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Delete deprecated tests (after verification period)

**Files:**
- Delete: `tests/e2e/deprecated/` directory

**Step 1: Wait for verification period**

Allow 1-2 sprints (2-4 weeks) to ensure no issues with the new test coverage.

**Step 2: Delete the deprecated directory**

```bash
rm -rf tests/e2e/deprecated/
```

**Step 3: Final verification**

```bash
uv run pytest tests/e2e/ -v --tb=short
```

Expected: All tests pass. No more deprecated tests.

**Step 4: Commit the deletion**

```bash
git add -A
git commit -m "$(cat <<'EOF'
chore(tests): remove deprecated demo E2E tests

Deletes tests/e2e/deprecated/ after verification period:
- test_live_annotation.py
- test_text_selection.py
- test_two_tab_sync.py
- test_user_isolation.py

Coverage confirmed in:
- test_annotation_page.py (core workflows)
- test_annotation_sync.py (real-time sync)
- test_annotation_collab.py (multi-user)
- test_auth_and_isolation.py (auth/isolation)

Paragraph tests remain blocked on Issue #99.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_5 -->

---

## Phase Completion Checklist

- [ ] `tests/e2e/deprecated/` directory created
- [ ] 4 demo test files moved to deprecated
- [ ] `__init__.py` created with migration documentation
- [ ] Skip markers added to all deprecated files
- [ ] `uv run pytest tests/e2e/` shows deprecated tests skipped
- [ ] `uv run pytest tests/e2e/ --ignore=tests/e2e/deprecated/` passes
- [ ] CI configuration reviewed/updated
- [ ] Deprecation commit pushed
- [ ] (After verification period) Deprecated directory deleted
- [ ] (After deletion) Final test run passes

---

## Post-Consolidation Metrics

After completing all phases, verify these metrics:

| Metric | Before | After | Target |
|--------|--------|-------|--------|
| E2E test files | 5 | 4 (+1 deprecated) | 4 |
| Total E2E tests | 94 | ~40 | <50 |
| test_annotation_page.py lines | 816 | ~600 | <700 |
| Demo route dependencies | 4 files | 0 | 0 |
| Setup overhead per test | High | Shared via subtests | Reduced |

Run final metrics check:

```bash
# Test count
uv run pytest tests/e2e/ --ignore=tests/e2e/deprecated/ --co -q | tail -1

# Line count
wc -l tests/e2e/test_annotation_page.py

# File count
ls tests/e2e/*.py | wc -l
```
