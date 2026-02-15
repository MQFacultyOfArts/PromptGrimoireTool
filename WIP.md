# WIP: E2E Test Migration (#156)

**Date:** 2026-02-15
**Branch:** `156-e2e-test-migration`

## Completed

### Phase 0: Commit implementation plans
- `cd92a47` — 8 phase files committed

### Phase 1: Fix Infrastructure
- `8f76371` — `--parallel` flag for `test-e2e` (default serial fail-fast)
- `387f24e` — Replace `data-char-index` waits in conftest fixtures with `_textNodes` readiness
- `77c2ed5` — Update CLAUDE.md for test-e2e serial default
- Code review: APPROVED

### Phase 2: Fix Active Tests
- `120ea15` — test_annotation_tabs.py: 5 `data-char-index` references replaced
- `9cc1194` — test_html_paste_whitespace.py: 11 references replaced
- `66749da` — test_fixture_screenshots.py: 1 reference replaced
- `e757df6` — Fix: replace `page.evaluate()` with native Playwright API (compliance guard)
- Code review: APPROVED

### Phase 3: Instructor Workflow Test
- `25bd896` — Add `email` param to `_authenticate_page()`
- `64640e9` — Create `course_helpers.py` (5 helpers)
- `d7eebe8` — Create `test_instructor_workflow.py` (7 subtests)
- `b66781e` through `384e595` — Six fix commits from review cycles:
  - Playwright strict mode violations
  - NiceGUI `ui.label()` renders `<div>` not heading
  - Auth mismatch (navigate to `/courses/new` directly)
  - Icon-only button locator pattern
  - Quasar `q-toggle` component scoping
  - `aria-checked` on root `.q-toggle`, not `div.q-toggle__inner`
- Code review: **NEEDS RE-REVIEW** (last fix `384e595` not yet reviewed)

### Cherry-picks from 96-workspace-acl
- `bf9ae95` — docs: extract subsystem documentation into dedicated docs files
- `4bd6609` — refactor: reduce CLAUDE.md from 555 to 172 lines

## Resume Point

**Phase 3 code review needs to run.** The aria-checked fix (`384e595`) hasn't been reviewed yet. After approval, continue with Phase 4.

### Next Steps (in order)
1. Run Phase 3 code review (all files: `conftest.py`, `course_helpers.py`, `test_instructor_workflow.py`)
2. Phase 4: Law Student Test (`test_law_student.py`) — plan at `docs/implementation-plans/.../phase_04.md`
3. Phase 5: Translation Student Test
4. Phase 6: History Tutorial Group Test
5. Phase 7: Naughty Student Test
6. Phase 8: Delete Obsolete Files

## Key Learnings (NiceGUI/Quasar/Playwright)

These patterns were discovered through review cycles and are critical for remaining phases:

- **NiceGUI `ui.label()`** renders as `<div>`, NOT semantic `<h1>`-`<h6>`. Don't use `get_by_role("heading")`.
- **NiceGUI `ui.switch()`** renders as Quasar `q-toggle`. `aria-checked` lives on the **root** `.q-toggle` element, NOT on `div.q-toggle__inner` (which is `aria-hidden="true"`).
- **Icon-only buttons** have no accessible name. Use: `page.locator("button").filter(has=page.locator("i.q-icon", has_text="settings"))`.
- **Mock auth roles**: `instructor@uni.edu` gets `["stytch_member", "instructor"]` via `MOCK_INSTRUCTOR_EMAILS`.
- **Course creation**: Navigate directly to `/courses/new` (not via `/courses` page, which requires DB enrollment for "New Course" button).
- **E2E compliance guard**: `tests/unit/test_e2e_compliance.py::test_no_js_injection_in_e2e_tests` forbids `page.evaluate()` in test files not listed in `ALLOWED_JS_FILES`.
- **`_textNodes` readiness**: Use `page.wait_for_function("() => window._textNodes && window._textNodes.length > 0", timeout=N)` instead of `data-char-index` selectors.

## Constraints

- **Do NOT run `test-e2e`** without `--parallel` awareness. User was worried about forkbomb with 12+ concurrent E2E tests. Default is now serial fail-fast.
- **docs/database.md** was cherry-picked from `96-workspace-acl` with ACL tables. Keep as-is — those tables are landing soon (Phase 4 of #96 is complete and tested).

## Task List State

Phases 1-3 tasks are completed. Pending tasks start at Phase 4 (#11, #12, #13) through Phase 8 (#23, #24, #25).
