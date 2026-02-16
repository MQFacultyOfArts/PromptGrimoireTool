# WIP: E2E Test Migration (#156)

**Date:** 2026-02-16
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
- `b66781e` through `384e595` — Six fix commits from review cycles
- Code review: APPROVED (zero issues)
- Proleptic challenge raised 3 items, all addressed:
  1. Fixed `_E2E_SERVER_SCRIPT` env var prefixes (`AUTH_MOCK` → `DEV__AUTH_MOCK`, etc.)
  2. Added bridge subtests: `enrol_student` + `student_clones_and_sees_content` (9 subtests total)
  3. Ran fixture analysis on AustLII fixtures (structure documented below)

### Cherry-picks from 96-workspace-acl
- Rebased onto main (2026-02-16): annotation split refactor, workspace ACL docs merged cleanly

## Resume Point

**Ready for Phase 4.** All prior phases reviewed and approved. Bridge test confirms instructor→student handoff works.

### Next Steps (in order)
1. Phase 4: Law Student Test (`test_law_student.py`) — plan at `docs/implementation-plans/.../phase_04.md`
2. Phase 5: Translation Student Test
3. Phase 6: History Tutorial Group Test
4. Phase 7: Naughty Student Test
5. Phase 8: Delete Obsolete Files

### AustLII Fixture Analysis (for Phase 4)

Two AustLII fixtures available:
- **`austlii`** — 113K chars, 151 spans, 109 list items, 103 links. Full page with chrome (header, search, nav).
- **`lawlis_v_r_austlii`** — 39K chars, cleaner structure. Has `<article>`, `<h1>`, `<footer>`. Better for law student narrative (smaller, real case judgment).

Recommend `lawlis_v_r_austlii` for Phase 4 — smaller, semantic HTML, represents a real case.

## Key Learnings (NiceGUI/Quasar/Playwright)

These patterns were discovered through review cycles and are critical for remaining phases:

- **NiceGUI `ui.label()`** renders as `<div>`, NOT semantic `<h1>`-`<h6>`. Don't use `get_by_role("heading")`.
- **NiceGUI `ui.switch()`** renders as Quasar `q-toggle`. `aria-checked` lives on the **root** `.q-toggle` element, NOT on `div.q-toggle__inner` (which is `aria-hidden="true"`).
- **Icon-only buttons** have no accessible name. Use: `page.locator("button").filter(has=page.locator("i.q-icon", has_text="settings"))`.
- **Mock auth roles**: `instructor@uni.edu` gets `["stytch_member", "instructor"]` via `MOCK_INSTRUCTOR_EMAILS`.
- **Course creation**: Navigate directly to `/courses/new` (not via `/courses` page, which requires DB enrollment for "New Course" button).
- **E2E compliance guard**: `tests/unit/test_e2e_compliance.py::test_no_js_injection_in_e2e_tests` forbids `page.evaluate()` in test files not listed in `ALLOWED_JS_FILES`.
- **`_textNodes` readiness**: Use `page.wait_for_function("() => window._textNodes && window._textNodes.length > 0", timeout=N)` instead of `data-char-index` selectors.
- **Env var prefixes**: pydantic-settings uses double-underscore prefixes: `DEV__AUTH_MOCK`, `APP__STORAGE_SECRET`, `STYTCH__SSO_CONNECTION_ID`, `STYTCH__PUBLIC_TOKEN`. The `_E2E_SERVER_SCRIPT` in `cli.py` had wrong prefixes (fixed).
- **Student workspace cloning**: "Start Activity" button clones template workspace. Student must be enrolled in course to see the course page. Activities are visible once week is published.

## Constraints

- **Do NOT run `test-e2e`** without `--parallel` awareness. User was worried about forkbomb with 12+ concurrent E2E tests. Default is now serial fail-fast.
- **docs/database.md** was cherry-picked from `96-workspace-acl` with ACL tables. Keep as-is — those tables are landing soon.

## Task List State

Phases 1-3 tasks are completed. Pending tasks start at Phase 4.
