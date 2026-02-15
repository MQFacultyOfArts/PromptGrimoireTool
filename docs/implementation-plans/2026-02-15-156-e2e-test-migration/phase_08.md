# E2E Test Migration Implementation Plan — Phase 8

**Goal:** Delete obsolete test files, verify clean test suite, update audit document.

**Architecture:** Delete 12 files (10 from design plan + `test_dom_performance.py` benchmark + `test_pdf_export.py` stub), verify zero `data-char-index` references remain in active test files, run full E2E suite, update `e2e-test-audit.md` status. The deprecated/ directory (4 files) is NOT touched — those serve as historical reference per design plan.

**Tech Stack:** git, grep, pytest

**Scope:** Phase 8 of 8 from design plan

**Codebase verified:** 2026-02-15

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 156-e2e-test-migration.AC1: No data-char-index references (DoD 1, 7)
- **156-e2e-test-migration.AC1.1 Success:** `grep -r "data-char-index" tests/e2e/ tests/benchmark/` returns zero matches excluding `deprecated/` and comment-only references in `test_no_char_span_queries.py`

### 156-e2e-test-migration.AC2: All active E2E tests pass (DoD 2)
- **156-e2e-test-migration.AC2.1 Success:** `uv run test-e2e` completes with zero failures and zero timeouts
- **156-e2e-test-migration.AC2.2 Success:** No test is skipped with reason "Pending #106"

### 156-e2e-test-migration.AC6: Obsolete files deleted (DoD 3)
- **156-e2e-test-migration.AC6.1 Success:** `test_annotation_basics.py`, `test_annotation_cards.py`, `test_annotation_workflows.py`, `test_subtests_validation.py` are deleted
- **156-e2e-test-migration.AC6.2 Success:** `test_annotation_highlights.py`, `test_annotation_sync.py`, `test_annotation_collab.py` are deleted
- **156-e2e-test-migration.AC6.3 Success:** `test_annotation_blns.py`, `test_annotation_cjk.py`, `test_i18n_pdf_export.py` are deleted

### 156-e2e-test-migration.AC7: Issues closable (DoD 8)
- **156-e2e-test-migration.AC7.1 Success:** #156 scope complete (all data-char-index references removed)

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Delete obsolete test files

**Verifies:** 156-e2e-test-migration.AC6.1, 156-e2e-test-migration.AC6.2, 156-e2e-test-migration.AC6.3

**Files:**
- Delete: `tests/e2e/test_annotation_basics.py`
- Delete: `tests/e2e/test_annotation_cards.py`
- Delete: `tests/e2e/test_annotation_workflows.py`
- Delete: `tests/e2e/test_subtests_validation.py`
- Delete: `tests/e2e/test_annotation_highlights.py`
- Delete: `tests/e2e/test_annotation_sync.py`
- Delete: `tests/e2e/test_annotation_collab.py`
- Delete: `tests/e2e/test_annotation_blns.py`
- Delete: `tests/e2e/test_annotation_cjk.py`
- Delete: `tests/e2e/test_i18n_pdf_export.py`
- Delete: `tests/benchmark/test_dom_performance.py`
- Delete: `tests/e2e/test_pdf_export.py`

**Implementation:**

Delete all 12 files listed above. These files are fully replaced by the persona-based tests created in Phases 3-7:

- `test_annotation_basics.py`, `test_annotation_cards.py`, `test_annotation_workflows.py`, `test_annotation_highlights.py` — replaced by `test_law_student.py` (Phase 4)
- `test_subtests_validation.py` — infrastructure file, no longer needed (pytest-subtests validated by all persona tests)
- `test_annotation_sync.py`, `test_annotation_collab.py` — replaced by `test_history_tutorial.py` (Phase 6)
- `test_annotation_blns.py` — replaced by `test_naughty_student.py` (Phase 7)
- `test_annotation_cjk.py`, `test_i18n_pdf_export.py` — replaced by `test_translation_student.py` (Phase 5)
- `test_dom_performance.py` — benchmark designed for old char-span architecture (data-char-index spans), not applicable to CSS Highlight API architecture
- `test_pdf_export.py` — module-level skipped stub (marked `pytestmark = pytest.mark.skip`), PDF export workflow replaced by `test_law_student.py` (Phase 4)

**DO NOT delete** anything in `tests/e2e/deprecated/` — those 4 files are historical reference per the design plan.

**Verification:**
Run: `ls tests/e2e/test_annotation_basics.py tests/e2e/test_annotation_cards.py tests/e2e/test_annotation_workflows.py tests/e2e/test_subtests_validation.py tests/e2e/test_annotation_highlights.py tests/e2e/test_annotation_sync.py tests/e2e/test_annotation_collab.py tests/e2e/test_annotation_blns.py tests/e2e/test_annotation_cjk.py tests/e2e/test_i18n_pdf_export.py tests/benchmark/test_dom_performance.py tests/e2e/test_pdf_export.py 2>&1`
Expected: All files report "No such file or directory"

**Commit:** `refactor(e2e): delete 12 obsolete test files replaced by persona tests`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Verify zero data-char-index references

**Verifies:** 156-e2e-test-migration.AC1.1, 156-e2e-test-migration.AC7.1

**Files:**
- No file changes — verification only

**Implementation:**

Run `grep -r "data-char-index" tests/e2e/ tests/benchmark/` and verify zero matches remain, excluding:
- `tests/e2e/deprecated/` directory (historical reference, not active tests)
- `tests/e2e/test_no_char_span_queries.py` — this file's purpose is to assert that `data-char-index` does NOT appear; its references are in assertion strings, not locator usage

If any unexpected references remain in active test files after Phases 1-2 fixes, they must be fixed before proceeding.

**Verification:**
Run: `grep -r "data-char-index" tests/e2e/ tests/benchmark/ --include="*.py" | grep -v "deprecated/" | grep -v "test_no_char_span_queries.py"`
Expected: Zero output (no matches)

Run: `grep -r "data-char-index" tests/e2e/test_no_char_span_queries.py`
Expected: Matches exist (this file asserts absence of data-char-index — that's correct)

No commit — verification only.
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Run full E2E suite and update audit document

**Verifies:** 156-e2e-test-migration.AC2.1, 156-e2e-test-migration.AC2.2

**Files:**
- Modify: `docs/implementation-plans/2026-02-04-html-input-pipeline/e2e-test-audit.md`

**Implementation:**

**Step 1: Run full E2E suite.**

Run: `uv run test-e2e`

Verify:
- Zero test failures
- Zero timeouts
- No test skipped with reason "Pending #106"
- All persona tests pass: `test_instructor_workflow.py`, `test_law_student.py`, `test_translation_student.py`, `test_history_tutorial.py`, `test_naughty_student.py`
- All fixed active tests pass: `test_annotation_tabs.py`, `test_html_paste_whitespace.py`, `test_fixture_screenshots.py`

If any tests fail, fix them before proceeding. Do NOT mark this task complete with failing tests.

**Step 2: Update e2e-test-audit.md.**

Open `docs/implementation-plans/2026-02-04-html-input-pipeline/e2e-test-audit.md` (660 lines). Add a status section at the top (after any existing header) documenting the migration outcome:

```markdown
## Migration Status: COMPLETE (2026-02-15)

**Issue:** #156
**Design:** docs/design-plans/2026-02-15-156-e2e-test-migration.md

### Files Deleted (12)
- test_annotation_basics.py
- test_annotation_cards.py
- test_annotation_workflows.py
- test_subtests_validation.py
- test_annotation_highlights.py
- test_annotation_sync.py
- test_annotation_collab.py
- test_annotation_blns.py
- test_annotation_cjk.py
- test_i18n_pdf_export.py
- test_dom_performance.py (benchmark)
- test_pdf_export.py (skipped stub)

### Files Created (5 persona tests)
- test_instructor_workflow.py — instructor course setup workflow
- test_law_student.py — AustLII paste, annotation, PDF export
- test_translation_student.py — CJK/RTL/mixed-script annotation, i18n PDF export
- test_history_tutorial.py — bidirectional real-time collaboration
- test_naughty_student.py — dead-end navigation, BLNS/XSS injection, copy protection bypass

### Files Fixed (4)
- conftest.py — _textNodes readiness in fixtures
- test_annotation_tabs.py — text walker helpers
- test_html_paste_whitespace.py — text walker helpers
- test_fixture_screenshots.py — _textNodes readiness wait

### Issues Closable
- #156: All data-char-index references removed, E2E suite migrated
- #106: HTML paste works end-to-end (test_law_student.py clipboard paste)
- #101: CJK/RTL content works (test_translation_student.py); BLNS edge cases handled (test_naughty_student.py)
```

**Verification:**
Run: `uv run test-e2e`
Expected: All tests pass, zero failures, zero timeouts

**Commit:** `docs: update e2e-test-audit.md with migration completion status`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
