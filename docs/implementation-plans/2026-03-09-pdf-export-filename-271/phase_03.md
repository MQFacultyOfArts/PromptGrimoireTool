# PDF Export Filename Convention Implementation Plan

**Goal:** Replace the hardcoded `workspace_{workspace_id}` basename in the annotation-page export flow with the new filename-policy output, without changing the lower PDF export seam.

**Architecture:** Keep the filename policy at the annotation-page orchestration boundary in `src/promptgrimoire/pages/annotation/pdf_export.py`. The page layer already owns the workspace-aware export path, while `src/promptgrimoire/export/pdf_export.py` is the correct lower seam that simply accepts a basename and writes `.tex` / `.pdf` files. This phase adds a small page-local helper seam for determinism and testability rather than pushing owner/date/placement logic down into the compiler layer.

**Tech Stack:** Python 3.14, NiceGUI, pytest, NiceGUI user-simulation integration tests

**Scope:** 4 phases from original design (phase 3 of 4)

**Codebase verified:** 2026-03-09

---

## Acceptance Criteria Coverage

This phase implements and tests:

### pdf-export-filename-271.AC4: Annotation-page export uses the new policy without changing the lower export seam
- **pdf-export-filename-271.AC4.1 Success:** `src/promptgrimoire/pages/annotation/pdf_export.py` computes the filename before calling `export_annotation_pdf(...)`.
- **pdf-export-filename-271.AC4.2 Success:** `src/promptgrimoire/export/pdf_export.py` continues to accept a `filename` basename and writes the `.tex` / `.pdf` using that basename without new route or header logic.
- **pdf-export-filename-271.AC4.3 Success:** Export from either the Annotate tab or the Respond tab yields the same filename for the same workspace on the same date.
- **pdf-export-filename-271.AC4.4 Failure:** Missing placement metadata does not silently fall back to `workspace_{uuid}` once this feature is implemented.

### pdf-export-filename-271.AC5
- **pdf-export-filename-271.AC5.4 Success:** Regression coverage proves the old generic `workspace_{workspace_id}` basename is no longer used in annotation-page exports.

---

<!-- START_TASK_1 -->
### Task 1: Add a small filename-resolution seam to the annotation export module

**Verifies:** pdf-export-filename-271.AC4.1, pdf-export-filename-271.AC4.2, pdf-export-filename-271.AC4.4

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/pdf_export.py`

**Implementation:**

Add the new imports required by the page layer:
- `date`, `datetime`
- `get_workspace_export_metadata` from `promptgrimoire.db.workspaces`
- `PdfExportFilenameContext`, `build_pdf_export_stem` from `promptgrimoire.export.filename`

Add a small date seam:

```python
def _server_local_export_date() -> date:
    """Return the application server's local date for export filenames."""
```

Required behaviour:
- return the host-local date using standard library local time
- do not hardcode `ZoneInfo("Australia/Sydney")` in page code
- keep the function tiny so tests can monkeypatch/freeze it directly

Add a page-local filename helper:

```python
async def _build_export_filename(workspace_id: UUID) -> str:
    """Return the PDF export basename for the workspace."""
```

Required behaviour:

1. Call `get_workspace_export_metadata(workspace_id)`.
2. Build `PdfExportFilenameContext` from the returned metadata plus `_server_local_export_date()`.
3. Call `build_pdf_export_stem(...)` and return the stem.
4. If metadata lookup returns `None`, still build through the Phase 1 fallback contract rather than reverting to `workspace_{workspace_id}`. Use an all-`None` metadata context so the builder emits fallback segments.

Then update `_handle_pdf_export(...)`:
- compute `filename = await _build_export_filename(workspace_id)` before calling `export_annotation_pdf(...)`
- pass `filename=filename`
- remove the old `filename=f"workspace_{workspace_id}"` hardcode

Implementation notes:
- Keep this phase page-local. Do not move filename-building logic into `src/promptgrimoire/export/pdf_export.py`.
- Do not change `export_annotation_pdf(...)` or `generate_tex_only(...)` signatures in this phase.
- Do not add a separate download route or `Content-Disposition` logic.
- Keep the filename resolution out of the header button callback. The header should continue calling `_handle_pdf_export(...)` only.

**Verification:**

Run:
```bash
uvx ty check src/promptgrimoire/pages/annotation/pdf_export.py
```

Expected: No type errors after the new helper seam is added.

Run:
```bash
rg -n "workspace_\\{" src/promptgrimoire/pages/annotation/pdf_export.py
```

Expected: No remaining hardcoded `workspace_{...}` basename in the annotation export path.

## UAT Steps
1. [ ] Open `src/promptgrimoire/pages/annotation/pdf_export.py`.
2. [ ] Confirm `_server_local_export_date()` exists as a tiny local seam.
3. [ ] Confirm `_build_export_filename(...)` uses `get_workspace_export_metadata(...)` plus `build_pdf_export_stem(...)`.
4. [ ] Confirm `_handle_pdf_export(...)` now passes a computed `filename=` value instead of `workspace_{workspace_id}`.

## Evidence Required
- [ ] `ty check` output for `src/promptgrimoire/pages/annotation/pdf_export.py`
- [ ] `rg` output showing the old hardcoded basename is gone from the page export path

**Commit:** `feat: wire descriptive pdf filenames into annotation export`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add NiceGUI user-harness integration coverage for the page wiring seam

**Verifies:** pdf-export-filename-271.AC4.1, pdf-export-filename-271.AC4.3, pdf-export-filename-271.AC4.4, pdf-export-filename-271.AC5.4

**Files:**
- Create: `tests/integration/test_annotation_pdf_export_filename_ui.py`

**Implementation:**

Use the NiceGUI user-simulation lane (`pytest.mark.nicegui_ui`) rather than Playwright for this phase. The goal here is to prove the annotation page wiring calls the lower export seam with the correct basename. Browser-visible `download.suggested_filename` stays in Phase 4.

Follow existing patterns from:
- `tests/integration/test_instructor_template_ui.py` for opening `/annotation?workspace_id=...` with `nicegui_user`
- `tests/integration/nicegui_helpers.py` for `data-testid` interaction
- existing service-layer tests for creating workspaces, documents, ACL ownership, and placement

Recommended setup helper inside the test module:
- create owner user and authenticate as that user with `nicegui_user`
- create course/week/activity/workspace
- add a document to the workspace
- grant owner ACL
- set a concrete workspace title
- open `/annotation?workspace_id=<id>`
- wait for `export-pdf-btn`

Monkeypatch strategy:
- patch `promptgrimoire.pages.annotation.pdf_export.export_annotation_pdf` with an async fake that captures `filename` and returns a fake `Path`
- patch `promptgrimoire.pages.annotation.pdf_export.ui.download` to a no-op recorder
- patch `_server_local_export_date()` to a fixed `date(2026, 3, 9)`

Do **not** patch:
- `get_workspace_export_metadata(...)`
- `build_pdf_export_stem(...)`

The point of this phase is to exercise the real Phase 1 + Phase 2 wiring through the page layer.

Required test cases:

1. Annotate-tab export passes policy filename to the export seam.
   - open annotation workspace
   - click `export-pdf-btn`
   - assert captured `filename` equals the expected policy output
   - assert `filename != f"workspace_{workspace_id}"`
   - assert the patched `ui.download(...)` was called with the fake returned path

2. Respond-tab export yields the same filename for the same workspace/date.
   - open same kind of workspace
   - click `tab-respond`
   - ensure the Respond tab is initialised
   - click `export-pdf-btn`
   - assert captured `filename` equals the same expected value as Annotate-tab export

3. Missing placement metadata still avoids the old generic basename.
   - create a fully loose workspace with owner ACL and document
   - click export
   - assert captured `filename` uses the fallback-based policy output
   - assert it is not `workspace_{workspace_id}`

Testing constraints:
- Mark the module with `pytest.mark.nicegui_ui`
- Use real DB rows and real annotation page loading
- Keep the lower export pipeline patched out so this phase stays fast and focused on page wiring
- Use `data-testid="export-pdf-btn"` and existing tab test ids, not visible-text selectors

Expected assertion style:
- Make exact assertions on the `filename` argument passed into the patched export seam
- Do not merely assert that the export button click completed
- Use a fixed date to make the expected filename deterministic

**Verification:**

Run:
```bash
uv run pytest tests/integration/test_annotation_pdf_export_filename_ui.py -m nicegui_ui -v
```

Expected: The NiceGUI page-wiring integration tests pass.

Run:
```bash
uvx ty check \
  src/promptgrimoire/pages/annotation/pdf_export.py \
  tests/integration/test_annotation_pdf_export_filename_ui.py
```

Expected: No type errors.

Optional confidence check:

```bash
uv run pytest \
  tests/integration/test_workspace_export_metadata.py \
  tests/integration/test_annotation_pdf_export_filename_ui.py -m nicegui_ui -v
```

Expected: Metadata and page wiring still agree on the same contract.

## UAT Steps
1. [ ] Run `uv run pytest tests/integration/test_annotation_pdf_export_filename_ui.py -m nicegui_ui -v`.
2. [ ] Inspect the captured `filename` assertion in the Annotate-tab test.
3. [ ] Inspect the Respond-tab test and verify it expects the same filename for the same workspace/date.
4. [ ] Inspect the loose-workspace test and verify it proves the old `workspace_{workspace_id}` pattern is gone.

## Evidence Required
- [ ] Green pytest output for `tests/integration/test_annotation_pdf_export_filename_ui.py`
- [ ] `ty check` output with zero issues
- [ ] Test code showing exact assertions on the captured `filename=` argument

**Commit:** `test: cover annotation export filename wiring`
<!-- END_TASK_2 -->

---

## Phase 3 Exit Criteria

Phase 3 is complete when:

1. The annotation page computes a descriptive basename before calling `export_annotation_pdf(...)`.
2. The lower export seam in `src/promptgrimoire/export/pdf_export.py` remains unchanged apart from consuming the new basename.
3. NiceGUI user-harness integration tests prove:
   - Annotate-tab export uses the policy filename
   - Respond-tab export uses the same filename for the same workspace/date
   - loose/missing placement metadata no longer falls back to `workspace_{workspace_id}`
4. The old generic basename is no longer present in the annotation export path.

## Risks To Watch

- If `_handle_pdf_export(...)` absorbs too much policy logic directly, complexity will creep up and the filename seam will be harder to test. Keep the new helpers small.
- If the page helper falls back to `workspace_{workspace_id}` when metadata lookup returns `None`, AC4.4 fails even though the lower pipeline still works technically.
- If the NiceGUI integration test patches Phase 1 or Phase 2 helpers, it stops proving the actual wiring and becomes too synthetic. Patch only the expensive lower export/download side for this phase.
