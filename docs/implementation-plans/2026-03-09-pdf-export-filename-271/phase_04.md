# PDF Export Filename Convention Implementation Plan

**Goal:** Prove the browser-visible suggested download filename matches the new export policy at the Playwright boundary.

**Architecture:** Reuse the existing Playwright export-button/download helpers in `tests/e2e/annotation_helpers.py`, but extend them so the tests can assert `download.suggested_filename` directly. The canonical exact `.pdf` assertion belongs in the slow E2E lane because the default fast lane intentionally monkey-patches `compile_latex` and downloads `.tex` instead of `.pdf`.

**Tech Stack:** Python 3.14, Playwright, pytest

**Scope:** 4 phases from original design (phase 4 of 4)

**Codebase verified:** 2026-03-09

---

## Acceptance Criteria Coverage

This phase implements and tests:

### pdf-export-filename-271.AC5
- **pdf-export-filename-271.AC5.3 Success:** A download-facing test asserts the suggested exported filename matches the policy, not merely that a PDF download occurred.
- **pdf-export-filename-271.AC5.4 Success:** Regression coverage proves the old generic `workspace_{workspace_id}` basename is no longer used in annotation-page exports.

### pdf-export-filename-271.AC4
- **pdf-export-filename-271.AC4.3 Success:** Export from either the Annotate tab or the Respond tab yields the same filename for the same workspace on the same date.

---

<!-- START_TASK_1 -->
### Task 1: Extend E2E export helpers to expose `suggested_filename`

**Verifies:** pdf-export-filename-271.AC5.3

**Files:**
- Modify: `tests/e2e/annotation_helpers.py`

**Implementation:**

Extend the existing download helpers rather than inventing a second export path.

Recommended shape:

```python
class ExportResult:
    text: str
    is_pdf: bool
    suggested_filename: str
```

Required changes:

1. Capture `download.suggested_filename` inside the existing Playwright helper that clicks the export button.
2. Preserve the current fast-vs-slow behaviour:
   - fast lane (`E2E_SKIP_LATEXMK=1`) may download `.tex`
   - slow lane (`E2E_SKIP_LATEXMK=0`) downloads real `.pdf`
3. Keep existing text extraction behaviour intact:
   - `.pdf` -> PyMuPDF extracted text
   - `.tex` -> raw decoded source
4. Return the suggested filename alongside the extracted text so callers can make an assertion on the browser boundary.

Recommended adjustments:
- update `ExportResult.__init__` to accept `suggested_filename`
- update `export_annotation_tex_text(page)` to populate it
- if `export_pdf_text(page)` remains in use, either:
  - extend it similarly, or
  - document it as content-only and keep Phase 4 on `export_annotation_tex_text`

Do **not** change the production app for this task. This is test-helper work only.

**Verification:**

Run:
```bash
uv run pytest tests/e2e/test_law_student.py -k export_pdf_with_annotations -v
```

Expected: Existing export content checks still pass after the helper shape changes.

Run:
```bash
uvx ty check tests/e2e/annotation_helpers.py tests/e2e/test_law_student.py
```

Expected: No type errors after the helper return shape is updated.

## UAT Steps
1. [ ] Open `tests/e2e/annotation_helpers.py`.
2. [ ] Confirm `ExportResult` now includes `suggested_filename`.
3. [ ] Confirm the helper stores `download.suggested_filename` without changing the existing content extraction path.

## Evidence Required
- [ ] Green pytest output for one existing export-flow E2E test
- [ ] `ty check` output for the helper and one caller

**Commit:** `test: expose suggested filename in e2e export helper`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add deterministic E2E workspace setup for filename assertions

**Verifies:** pdf-export-filename-271.AC4.3, pdf-export-filename-271.AC5.3

**Files:**
- Modify: `tests/e2e/annotation_helpers.py`

**Implementation:**

Add a focused helper for filename-contract tests that creates deterministic export metadata via direct DB operations.

Required behaviour:

1. Create a real placed workspace with fixed, non-random metadata:
   - predictable owner identity
   - predictable course code
   - predictable activity title
   - predictable workspace title
2. Reuse the same direct-sync-DB setup style already used by:
   - `_create_workspace_via_db(...)`
   - `_create_workspace_with_word_limits(...)`
3. Ensure the workspace is activity-placed so the filename covers all slots.
4. Ensure the owner display name is explicitly set to a known value such as `Ada Lovelace`.
5. Return the `workspace_id` and the literal expected descriptive stem components needed by the E2E test.

Recommended helper shape:

```python
def _create_workspace_for_filename_export(
    user_email: str,
    *,
    owner_display_name: str = "Ada Lovelace",
    course_code: str = "LAWS5000",
    activity_title: str = "Final Essay",
    workspace_title: str = "Week 3 Response",
) -> str:
    ...
```

Notes:
- Keep the metadata values intentionally controlled so the E2E test can assert a literal `suggested_filename`.
- Do not introduce a name-parsing dependency for this phase. The goal is to validate the implemented heuristic contract, not replace it.
- Use a date source that will be stable in the test. If Phase 3 exposed a date seam only in page code, the E2E test should compute the expected date using the same server-local-day assumption on the test host. Because the E2E server and the test runner are on the same machine in this harness, that is acceptable here.
- Add a brief test comment documenting that this date assumption depends on co-location of the E2E server and the Playwright runner; if the harness ever becomes distributed, the test should freeze or inject the date explicitly instead of relying on host-local coincidence.

**Verification:**

Run:
```bash
uvx ty check tests/e2e/annotation_helpers.py
```

Expected: No type errors after the new helper is added.

## UAT Steps
1. [ ] Open `tests/e2e/annotation_helpers.py`.
2. [ ] Confirm the new helper creates controlled owner/course/activity/workspace metadata rather than random filename inputs.
3. [ ] Confirm the helper still uses direct DB setup instead of brittle UI creation steps.

## Evidence Required
- [ ] `ty check` output for the updated helper module
- [ ] Code review evidence that the metadata values are controlled and deterministic

**Commit:** `test: add deterministic e2e filename setup helper`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add browser-boundary filename assertions, with slow-lane exact `.pdf` coverage

**Verifies:** pdf-export-filename-271.AC5.3, pdf-export-filename-271.AC5.4, pdf-export-filename-271.AC4.3

**Files:**
- Create: `tests/e2e/test_pdf_export_filename.py`

**Implementation:**

Create a focused Playwright test file for the filename boundary.

Required test cases:

1. Fast-lane tolerance test: descriptive stem is preserved even when the download is `.tex`.
   - use the deterministic workspace helper from Task 2
   - authenticate and open the annotation workspace
   - export via the real `export-pdf-btn`
   - assert `result.suggested_filename` is descriptive and does **not** match `workspace_{workspace_id}`
   - allow either:
     - `<expected_stem>.tex` in default `e2e run`
     - `<expected_stem>.pdf` if the test happens to run in slow mode

2. Slow-lane canonical test: exact `.pdf` filename is suggested by the browser.
   - same workspace setup
   - if `E2E_SKIP_LATEXMK == "1"`, call `pytest.skip("run via `uv run grimoire e2e slow` for exact .pdf suggested filename")`
   - otherwise assert:
     - `result.is_pdf is True`
     - `result.suggested_filename == "<expected_stem>.pdf"`

3. Cross-tab consistency test.
   - export once from Annotate tab and once after switching to Respond tab
   - assert both `suggested_filename` values are identical for the same workspace/date

Expected-filename construction in the test:
- Build the expected value literally from the known metadata and the implemented heuristic contract:
  - `LAWS5000_Lovelace_Ada_Final_Essay_Week_3_Response_<YYYYMMDD>`
- Compute the date portion using the same server-local day assumption as the harness host
- Include a short code comment in the test acknowledging that this is stable only because the E2E server and runner share the same host-local day in the current harness
- Keep the assertion explicit rather than calling the production builder from the test

Testing constraints:
- Use `page.get_by_test_id("export-pdf-btn")` or the existing helper; do not select by visible text alone when a `data-testid` exists
- Keep the file marked `@pytest.mark.e2e`
- Do not depend on the NiceGUI lane for this phase
- Do not weaken the slow-lane exact `.pdf` assertion just to accommodate fast mode; the split is intentional

**Verification:**

Fast lane:
```bash
uv run grimoire e2e run -k pdf_export_filename
```

Expected: The fast-lane test passes with `.tex` tolerated, and the slow-only exact-PDF test is skipped with a clear message.

Slow lane:
```bash
uv run grimoire e2e slow -k pdf_export_filename
```

Expected: The exact `download.suggested_filename == "<expected>.pdf"` assertion passes.

Type check:
```bash
uvx ty check tests/e2e/annotation_helpers.py tests/e2e/test_pdf_export_filename.py
```

Expected: No type errors.

## UAT Steps
1. [ ] Run `uv run grimoire e2e run -k pdf_export_filename`.
2. [ ] Verify the fast lane tolerates a descriptive `.tex` download and still rejects `workspace_{workspace_id}`.
3. [ ] Run `uv run grimoire e2e slow -k pdf_export_filename`.
4. [ ] Verify the slow lane asserts the exact browser-suggested `.pdf` filename.

## Evidence Required
- [ ] Fast-lane test output showing descriptive filename coverage with `.tex` tolerated
- [ ] Slow-lane test output showing exact `.pdf` suggested filename assertion
- [ ] `ty check` output with zero issues

**Commit:** `test: assert browser suggested filename for pdf export`
<!-- END_TASK_3 -->

---

## Phase 4 Exit Criteria

Phase 4 is complete when:

1. Playwright export helpers expose `download.suggested_filename`.
2. There is a deterministic E2E setup path for filename-contract workspaces.
3. Default `e2e run` proves the descriptive basename survives the browser download boundary, even when the artifact is `.tex`.
4. `e2e slow` proves the browser suggests the exact descriptive `.pdf` filename.
5. Regression coverage explicitly rejects the old `workspace_{workspace_id}` naming pattern at the browser boundary.

## Risks To Watch

- If the E2E setup helper uses random course/activity/title/name values, the browser-boundary assertion becomes brittle or indirectly reimplements the builder.
- If the slow-lane test runs in default fast mode without an explicit skip, it will fail for the wrong reason (`.tex` vs `.pdf`) and muddy the contract.
- If the test computes the expected filename by calling the production builder, it stops being an independent browser-boundary regression test.
