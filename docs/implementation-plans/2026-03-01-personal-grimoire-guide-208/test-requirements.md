# Test Requirements: Personal Grimoire Guide (#208)

**Mapped from:** `docs/design-plans/2026-03-01-personal-grimoire-guide-208.md`

**Implementation phases:** Phase 1 (guide script), Phase 2 (pipeline integration)

---

## Testing Strategy

Phase 1 produces a Playwright-driven guide script (`personal_grimoire.py`) that runs inside `make_docs()` against a live NiceGUI server. This is integration code -- it drives a browser through real application UI, emitting markdown and screenshots as side effects. It cannot be unit tested in isolation. Its correctness is verified by:

1. **Unit tests of the pipeline** (Phase 2): `test_make_docs.py` mocks the guide functions and verifies call order, arguments, and pandoc PDF generation. These tests run in `test-all` via xdist.
2. **End-to-end verification** by running `uv run make-docs` and inspecting the output artifacts. This is a human-verified step because it requires a running database, server, and Playwright browser -- infrastructure that only exists in the `make-docs` pipeline, not in the test harness.

---

## Automated Tests

### personal-grimoire-guide-208.AC1: Guide produces structured output

| AC | Criterion | Test Type | Test File | Test Name / Assertion | Notes |
|----|-----------|-----------|-----------|----------------------|-------|
| AC1.1 | Guide produces `your-personal-grimoire.md` in `docs/guides/` | Unit | `tests/unit/test_make_docs.py` | `TestMakeDocsServerLifecycle::test_all_guides_called_with_page_and_base_url` -- verifies `mock_personal` called with correct `page` and `base_url` arguments, confirming the guide entry point is invoked with the context needed to produce output. | The guide function itself produces the file; the unit test verifies the pipeline invokes it correctly. Actual file creation is verified via human verification (HV1). |
| AC1.2 | Guide produces ~11 screenshots with prefix `your-personal-grimoire-` | Human | -- | See HV1 below. | Screenshot count depends on Playwright interactions against a live app. Cannot be verified without running the full pipeline. |
| AC1.3 | Markdown contains 5 section headings matching the pedagogical arc | Human | -- | See HV1 below. | Section headings are emitted by `Guide.step(heading)` calls in the script. Verifiable by inspecting the generated markdown. |
| AC1.4 | All screenshot image references resolve to files that exist on disk | Human | -- | See HV1 below. | Requires the full pipeline to have run, producing real files. |

### personal-grimoire-guide-208.AC5: Pipeline integration

| AC | Criterion | Test Type | Test File | Test Name / Assertion | Notes |
|----|-----------|-----------|-----------|----------------------|-------|
| AC5.1 | `make_docs()` calls the personal grimoire guide after the student guide | Unit | `tests/unit/test_make_docs.py` | `TestMakeDocsGuideOrder::test_guide_execution_order` -- records call order via `side_effect` callbacks on all three guide mocks, asserts `call_order == ["instructor", "student", "personal"]`. | Renames existing `test_instructor_runs_before_student` and extends to three guides. |
| AC5.1 | Guide receives correct `page` and `base_url` arguments | Unit | `tests/unit/test_make_docs.py` | `TestMakeDocsServerLifecycle::test_all_guides_called_with_page_and_base_url` -- asserts `mocks["personal"].assert_called_once()`, verifies `page_arg is mocks["page"]` and `base_url_arg.startswith("http://localhost:")`. | Renames existing `test_both_guides_called_with_page_and_base_url` and adds personal guide assertions. |
| AC5.2 | MkDocs nav includes the guide as a third entry | Unit (visual inspection) | -- | See HV2 below. | `mkdocs.yml` is a static config file. Correctness is verified by reading the file. No runtime test needed -- the existing `test_mkdocs_build_called_with_cwd` already verifies that `mkdocs build` runs, which would fail if the nav references a nonexistent file. |
| AC5.3 | Pandoc generates a PDF for `your-personal-grimoire.md` | Unit | `tests/unit/test_make_docs.py` | `TestMakeDocsPandocPdf::test_pandoc_called_for_each_guide` -- after glob refactor, asserts `len(pandoc_calls) == 3` and checks that input files include `your-personal-grimoire.md`. | Requires Phase 2 Task 3 fixture changes: guide mocks create placeholder `.md` files via `side_effect` so the glob in `make_docs()` discovers them. |
| AC5.3 | Pandoc runs after mkdocs build | Unit | `tests/unit/test_make_docs.py` | `TestMakeDocsPandocPdf::test_pandoc_runs_after_mkdocs` (existing, unchanged) | Already passes with the glob refactor -- no pandoc-specific ordering changes. |

### personal-grimoire-guide-208.AC5: Pipeline ordering with mkdocs

| AC | Criterion | Test Type | Test File | Test Name / Assertion | Notes |
|----|-----------|-----------|-----------|----------------------|-------|
| AC5.1 | Personal guide runs before mkdocs build | Unit | `tests/unit/test_make_docs.py` | `TestMakeDocsMkdocsBuild::test_mkdocs_build_runs_after_guides` -- extended to record `"personal"` in `call_order` and assert `call_order.index("personal") < mkdocs_idx`. | Extends existing test. |

---

## Acceptance Criteria Not Amenable to Automated Testing

### personal-grimoire-guide-208.AC2: Loose workspace created by enrolled student

| AC | Criterion | Justification for Human Verification | Verification Approach |
|----|-----------|--------------------------------------|----------------------|
| AC2.1 | Student is enrolled in UNIT1234 but navigates to `/annotation` and clicks `create-workspace-btn` | This criterion describes a UI interaction sequence performed by the guide script against a live application. The guide script IS the test -- it will fail (Playwright timeout) if the `create-workspace-btn` does not exist or is not clickable. The underlying workspace creation logic is already covered by existing E2E persona tests (`test_instructor_workflow.py`). | HV1: Run `uv run make-docs` and confirm the guide completes without Playwright errors. Inspect screenshot `your-personal-grimoire-03.png` showing the newly created workspace. |
| AC2.2 | Created workspace has `activity_id=NULL` and `course_id=NULL` | The guide script creates a workspace by clicking `create-workspace-btn` on the annotation page (not via an activity Start button). The application's workspace creation path from `/annotation` always produces a loose workspace (`activity_id=NULL`, `course_id=NULL`). This behaviour is tested by existing integration tests for workspace CRUD. The guide script verifies it indirectly: if the workspace were associated with an activity, the placement dialog in Section 5 would show it as already placed (not "Unsorted"). | HV1: After running `make-docs`, inspect the placement dialog screenshot (`your-personal-grimoire-09.png` or similar) -- the dialog should show the workspace as unplaced, confirming NULL associations. |
| AC2.3 | Navigator shows the workspace in the "Unsorted" section | The Navigator's grouping logic (loose workspaces in "Unsorted") is tested by existing navigator integration tests. The guide script captures a screenshot of the Navigator but does not return to verify placement post-creation (the flow is linear, moving forward through sections). | HV3: After running `make-docs` end-to-end, manually navigate to the Navigator as `loose-student@test.example.edu.au` and confirm the workspace appears in "Unsorted" before placement. Alternatively, inspect the Section 5 narrative which closes the arc by placing the workspace. |

### personal-grimoire-guide-208.AC3: Emergent folksonomy -- student creates own tags

| AC | Criterion | Justification for Human Verification | Verification Approach |
|----|-----------|--------------------------------------|----------------------|
| AC3.1 | Tag management dialog opens on a workspace with zero pre-existing tags | The guide script clicks `tag-settings-btn` and waits for `add-tag-group-btn` to be visible. If the dialog fails to open, Playwright times out and the guide fails. The "zero pre-existing tags" condition is guaranteed by the setup: the workspace is loose (no inherited tags from an activity). | HV1: Inspect screenshot `your-personal-grimoire-04.png` (tag management dialog) and confirm it shows an empty state with no existing tag groups. |
| AC3.2 | Student creates tag group "My Analysis" and three tags | The guide script creates the group and tags via direct UI interactions (fill, click). If any interaction fails, Playwright times out. | HV1: Inspect screenshot `your-personal-grimoire-05.png` showing tag group "My Analysis" with three tags ("AI Assumption", "Cultural Gap", "Useful Insight"). |
| AC3.3 | Created tags appear in the tag toolbar and can be applied to highlights | Section 4 (`_section_annotate_and_reflect`) selects text and clicks the first tag button in the toolbar. If tags are not in the toolbar, the locator `[data-testid='tag-toolbar'] button` finds nothing and times out. If the tag cannot be applied, the `annotation-card` never appears and the wait times out. | HV1: Inspect screenshots from Section 4 showing highlighted text with a tag applied and the annotation card visible. |

### personal-grimoire-guide-208.AC4: Placement dialog associates workspace with unit

| AC | Criterion | Justification for Human Verification | Verification Approach |
|----|-----------|--------------------------------------|----------------------|
| AC4.1 | Placement dialog opens from the placement chip | The guide script clicks `placement-chip` and waits for `placement-mode` to be visible. Playwright timeout on failure. | HV1: Inspect screenshot showing the placement dialog open. |
| AC4.2 | Cascading selects populate with UNIT1234 data | The guide script clicks the course select, then clicks the UNIT1234 option. If UNIT1234 is not in the dropdown, the `.q-menu .q-item:has-text("UNIT1234")` locator times out. | HV1: Inspect screenshot showing cascading selects with UNIT1234 selected. |
| AC4.3 | After confirming, workspace is associated with selected activity | The guide script clicks `placement-confirm-btn`. If placement fails, the application would show an error state. The guide captures a post-placement screenshot. | HV1: Inspect the final screenshot showing the workspace header updated to reflect the activity association. |
| AC4.4 | Enrolment in UNIT1234 causes it to appear in the placement dialog | The `_setup_loose_student()` helper enrols the student in UNIT1234 before the guide begins. If enrolment failed, UNIT1234 would not appear in the placement dialog's course select, and the guide would fail at AC4.2. This is a precondition, not a separately testable criterion. | HV1: Verified transitively -- if AC4.2 passes (UNIT1234 appears in the dropdown), then AC4.4 is satisfied. |

---

## Human Verification Procedures

### HV1: Full pipeline end-to-end run

**Verifies:** AC1.1, AC1.2, AC1.3, AC1.4, AC2.1, AC2.2, AC3.1, AC3.2, AC3.3, AC4.1, AC4.2, AC4.3, AC4.4

**Prerequisites:** PostgreSQL running with `DATABASE_URL` set, application dependencies installed (`uv sync`).

**Procedure:**

1. Run `uv run make-docs`
2. Confirm exit code 0 (no Playwright timeouts or application errors)
3. Verify output file exists:
   ```
   ls docs/guides/your-personal-grimoire.md
   ```
4. Verify screenshot count and naming:
   ```
   ls docs/guides/screenshots/your-personal-grimoire-*.png | wc -l
   ```
   Expected: ~11 files (exact count may vary by +/-1 as implementation stabilises)
5. Verify 5 section headings in the markdown:
   ```
   grep '^## ' docs/guides/your-personal-grimoire.md
   ```
   Expected headings (in order):
   - `## Enter the Grimoire`
   - `## Bring Your Conversation`
   - `## Make Meaning Through Tags`
   - `## Annotate and Reflect`
   - `## Connect to Your Unit`
6. Verify all image references resolve:
   ```
   grep -oP '!\[.*?\]\(\K[^)]+' docs/guides/your-personal-grimoire.md | while read img; do
     [ -f "docs/guides/$img" ] || echo "MISSING: $img"
   done
   ```
   Expected: no output (all images exist)
7. Visually inspect screenshots for content correctness:
   - Navigator showing enrolled unit (Section 1)
   - Create Workspace button highlighted (Section 1)
   - Loose workspace created (Section 1)
   - AI conversation pasted (Section 2)
   - Processed conversation (Section 2)
   - Empty tag management dialog (Section 3)
   - Tag group with three tags (Section 3)
   - Highlighted text with tag applied (Section 4)
   - Comment on annotation (Section 4)
   - Organise view (Section 4)
   - Placement dialog with cascading selects (Section 5)
8. Verify PDF generated:
   ```
   ls docs/guides/your-personal-grimoire.pdf
   ```

### HV2: MkDocs nav entry

**Verifies:** AC5.2

**Procedure:**

1. Inspect `mkdocs.yml` nav section:
   ```yaml
   nav:
     - Home: index.md
     - Instructor Setup: instructor-setup.md
     - Student Workflow: student-workflow.md
     - Your Personal Grimoire: your-personal-grimoire.md
   ```
2. Confirm fourth entry exists with correct title and filename.
3. After HV1, open `docs/site/index.html` in a browser and confirm the nav sidebar includes "Your Personal Grimoire" as the third guide entry.

### HV3: Navigator "Unsorted" section placement

**Verifies:** AC2.3

**Procedure:**

1. After HV1 (which creates the workspace), start the application: `uv run python -m promptgrimoire`
2. Authenticate as `loose-student@test.example.edu.au`
3. Confirm the Navigator shows the workspace in the "Unsorted" section (before Section 5 placement)

**Note:** This is partially verified by HV1 step 7 (screenshot inspection). HV3 is only needed if screenshot evidence is ambiguous. In practice, AC2.3 is verified by the guide completing successfully: if the workspace were misclassified, the Section 5 placement flow would behave differently.

---

## Traceability Matrix

| Acceptance Criterion | Automated Test | Human Verification |
|----------------------|---------------|--------------------|
| personal-grimoire-guide-208.AC1.1 | `test_all_guides_called_with_page_and_base_url` (invocation) | HV1 step 3 (file exists) |
| personal-grimoire-guide-208.AC1.2 | -- | HV1 step 4 (screenshot count) |
| personal-grimoire-guide-208.AC1.3 | -- | HV1 step 5 (section headings) |
| personal-grimoire-guide-208.AC1.4 | -- | HV1 step 6 (image references) |
| personal-grimoire-guide-208.AC2.1 | -- | HV1 step 2 + 7 (guide completes, screenshot inspection) |
| personal-grimoire-guide-208.AC2.2 | -- | HV1 step 7 (placement dialog shows unplaced) |
| personal-grimoire-guide-208.AC2.3 | -- | HV3 (Navigator inspection) |
| personal-grimoire-guide-208.AC3.1 | -- | HV1 step 7 (empty tag dialog screenshot) |
| personal-grimoire-guide-208.AC3.2 | -- | HV1 step 7 (tag group + tags screenshot) |
| personal-grimoire-guide-208.AC3.3 | -- | HV1 step 7 (tag applied to highlight) |
| personal-grimoire-guide-208.AC4.1 | -- | HV1 step 7 (placement dialog screenshot) |
| personal-grimoire-guide-208.AC4.2 | -- | HV1 step 7 (cascading selects screenshot) |
| personal-grimoire-guide-208.AC4.3 | -- | HV1 step 7 (post-placement screenshot) |
| personal-grimoire-guide-208.AC4.4 | -- | HV1 (transitive via AC4.2) |
| personal-grimoire-guide-208.AC5.1 | `test_guide_execution_order`, `test_all_guides_called_with_page_and_base_url`, `test_mkdocs_build_runs_after_guides` | -- |
| personal-grimoire-guide-208.AC5.2 | -- | HV2 (mkdocs.yml inspection) |
| personal-grimoire-guide-208.AC5.3 | `test_pandoc_called_for_each_guide` | HV1 step 8 (PDF exists) |

---

## Test Infrastructure Changes (Phase 2)

The following changes to `tests/unit/test_make_docs.py` are required to support these test requirements:

### Fixture: `_mock_happy_path`

1. Add `patch("promptgrimoire.docs.scripts.personal_grimoire.run_personal_grimoire_guide")` as `mock_personal`
2. All three guide mocks get `side_effect` functions that create placeholder `.md` files in `_guides_dir` (computed from `cli_module.__file__`) so the glob-based pandoc loop discovers them
3. Add `"personal": mock_personal` to the yielded dict
4. Add teardown to remove placeholder files after each test

### Renamed / extended tests

| Original Test | New Name | Change |
|--------------|----------|--------|
| `test_both_guides_called_with_page_and_base_url` | `test_all_guides_called_with_page_and_base_url` | Add `mocks["personal"]` assertions |
| `test_instructor_runs_before_student` | `test_guide_execution_order` | Add personal guide to `call_order`, assert `["instructor", "student", "personal"]` |
| `test_pandoc_called_for_each_guide` | (same name) | Assert `len(pandoc_calls) == 3`, add `your-personal-grimoire.md` check |
| `test_mkdocs_build_runs_after_guides` | (same name) | Add personal guide recording and ordering assertion |

### No new test files

All automated tests live in the existing `tests/unit/test_make_docs.py`. No new test files are created. The guide script itself (`personal_grimoire.py`) is not unit-testable -- it is verified by running the full `make_docs()` pipeline (HV1).
