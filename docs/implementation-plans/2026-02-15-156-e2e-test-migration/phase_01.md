# E2E Test Migration Implementation Plan — Phase 1

**Goal:** Fix conftest.py fixtures that use `data-char-index` waits, unblocking all other E2E tests.

**Architecture:** Replace broken DOM selector waits with the `_textNodes` readiness function already used by `annotation_helpers.py`. Two lines in two fixtures.

**Tech Stack:** Playwright, pytest, pytest-xdist

**Scope:** Phase 1 of 8 from design plan

**Codebase verified:** 2026-02-15

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 156-e2e-test-migration.AC1: No data-char-index references (DoD 1, 7)
- **156-e2e-test-migration.AC1.2 Success:** `conftest.py` fixtures `two_annotation_contexts` and `two_authenticated_contexts` use `_textNodes` readiness check

---

<!-- START_TASK_1 -->
### Task 1: Replace data-char-index waits in conftest.py fixtures

**Verifies:** 156-e2e-test-migration.AC1.2

**Files:**
- Modify: `tests/e2e/conftest.py:163` (two_annotation_contexts fixture)
- Modify: `tests/e2e/conftest.py:217` (two_authenticated_contexts fixture)

**Implementation:**

In `two_annotation_contexts` (line 163), replace:
```python
page2.wait_for_selector("[data-char-index]", timeout=10000)
```
with:
```python
page2.wait_for_function(
    "() => window._textNodes && window._textNodes.length > 0",
    timeout=10000,
)
```

In `two_authenticated_contexts` (line 217), make the identical replacement.

Both fixtures have the same pattern: page1 creates a workspace via `setup_workspace_with_content()` (which already uses `_textNodes` readiness internally), then page2 navigates to the same workspace URL and needs to wait for the text walker to initialise. The `_textNodes` check is the canonical readiness condition — it confirms the text walker has processed the document, not just that HTML rendered.

**Testing:**

This is an infrastructure fix. Verification is operational — an existing E2E test that uses these fixtures should pass without timeout.

- 156-e2e-test-migration.AC1.2: Run any test that uses `two_annotation_contexts` or `two_authenticated_contexts` and confirm it does not timeout on the wait

**Verification:**

Run: `uv run pytest tests/e2e/test_remote_presence_e2e.py -v -x --timeout=30 -m e2e` (this test uses `two_authenticated_contexts`)
Expected: Test completes without 10-second timeout; passes or fails on its own assertions, not on fixture setup.

If no single-test runner is available, run: `uv run test-e2e -k "remote_presence"` to verify through the full E2E harness.

**Commit:** `fix(e2e): replace data-char-index waits with _textNodes readiness in conftest fixtures`
<!-- END_TASK_1 -->
