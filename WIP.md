# WIP: E2E Test Migration (#156)

**Date:** 2026-02-17
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

### Phase 4: Law Student Test
- `449da23` — Add `_load_fixture_via_paste()` helper to `annotation_helpers.py`
- `158a267` — Create `test_law_student.py` (11 subtests)
- `5cd4571` — Fix: remove stale confirm dialog wait (pasted HTML skips dialog)
- `237f8db` — Add `test-e2e-debug` command (--lf last-failed re-run)
- `367b059` — Fix: use pymupdf for PDF text extraction (FlateDecode compression)
- Code review (2026-02-17): 2 Important + 2 Minor issues found, all fixed:
  1. Fixed pymupdf `page` variable shadowing Playwright `page` (renamed to `pdf_page`)
  2. Extracted `wait_for_text_walker()` helper to keep AC4.2 compliance clean
  3. Replaced broad `except Exception` with specific `PlaywrightTimeoutError`/`PlaywrightError`
  4. Added organise tab column heading assertion + respond tab text input
- All 11 subtests pass after fixes
- Code review: APPROVED (post-fix)

## Resume Point

**Phase 4 complete. Ready for Phase 5.**

### Next Steps (in order)
1. Phase 5: Translation Student Test
2. Phase 6: History Tutorial Group Test
3. Phase 7: Naughty Student Test
4. Phase 8: Delete Obsolete Files

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
- **`_textNodes` readiness**: Use `wait_for_text_walker(page, timeout=N)` from `annotation_helpers.py` (wraps `window._textNodes` check).
- **Env var prefixes**: pydantic-settings uses double-underscore prefixes: `DEV__AUTH_MOCK`, `APP__STORAGE_SECRET`, `STYTCH__SSO_CONNECTION_ID`, `STYTCH__PUBLIC_TOKEN`. The `_E2E_SERVER_SCRIPT` in `cli.py` had wrong prefixes (fixed).
- **Student workspace cloning**: "Start Activity" button clones template workspace. Student must be enrolled in course to see the course page. Activities are visible once week is published.
- **Strict mode**: `get_by_text()` resolves to multiple elements when tag names appear in both column headers and cards. Use `.first` or scope to a specific container.
- **Playwright exception types**: Import `TimeoutError as PlaywrightTimeoutError` and `Error as PlaywrightError` from `playwright.sync_api` for specific exception handling.

## Constraints

- **Do NOT run `test-e2e`** without `--parallel` awareness. User was worried about forkbomb with 12+ concurrent E2E tests. Default is now serial fail-fast.
- **docs/database.md** was cherry-picked from `96-workspace-acl` with ACL tables. Keep as-is — those tables are landing soon.

## Task List State

Phases 1-4 code complete and reviewed. Ready for Phase 5.
