# WIP: E2E Test Migration (#156)

**Date:** 2026-02-17
**Branch:** `156-e2e-test-migration`

## Completed — ALL 8 PHASES

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

### Phase 4: Law Student Test
- `449da23` — Add `_load_fixture_via_paste()` helper to `annotation_helpers.py`
- `158a267` — Create `test_law_student.py` (11 subtests)
- `5cd4571` — Fix: remove stale confirm dialog wait (pasted HTML skips dialog)
- `237f8db` — Add `test-e2e-debug` command (--lf last-failed re-run)
- `367b059` — Fix: use pymupdf for PDF text extraction (FlateDecode compression)
- `997373e` — Phase 4 review fixes (wait_for_text_walker, specific exceptions, stronger assertions)
- Code review: APPROVED (post-fix)

### Phase 5: Translation Student Test
- `fd5c354` — Create `test_translation_student.py` (12 subtests across 4 methods)
- `86eb4c2` — Refactor: extract `_setup_and_highlight()`, `_post_comment_on_first_card()`
- Code review: APPROVED (zero issues)

### Phase 6: History Tutorial Group Test
- `ee028aa` — Create `test_history_tutorial.py` (11 subtests)
- Code review: APPROVED (zero issues)

### Phase 7: Naughty Student Test
- `cef41fb` — Create `test_naughty_student.py` with dead-end navigation (3 subtests)
- `4f0841a` — Add BLNS/XSS content injection tests (11 subtests)
- `0c8d9bd` — Add copy protection bypass tests (7 subtests)
- Code review: APPROVED (zero issues)

### Phase 8: Delete Obsolete Files
- `f2dbb51` — Delete 12 obsolete test files
- `c05aedb` — Fix: wait_for_text_walker consistency, copy protection setup reorder
- `83f5138` — Add E2E test commands to implementation-plan-guidance
- `1381335` — Fix: normalise LaTeX soft-hyphens in PDF UUID assertions
- `50f7439` — Update e2e-test-audit.md with migration completion status
- Code review: APPROVED (zero issues)

## Resume Point

**All 8 phases complete. All ACs verified. Ready for final review and PR.**

### Remaining Steps
1. ~~Final code review~~ (individual phase reviews all passed)
2. `finishing-a-development-branch` skill — PR creation
3. Update WIP.md with PR link

### Final AC Verification
- AC1.1: Zero data-char-index in active tests ✓
- AC2.1: All persona tests pass (11 methods, 82.28s) ✓
- AC3.1-3.5: All 5 persona test files exist ✓
- AC3.6: All use pytest-subtests ✓
- AC4.1: No CSS.highlights in persona tests ✓
- AC4.2: No page.evaluate() in persona tests ✓
- AC5.1-5.2: Each test creates own workspace, random auth emails ✓
- AC6.1-6.3: 12 obsolete files deleted ✓
- AC7.1: #156 scope complete ✓
- AC7.2: HTML paste works (#106 closable) ✓
- AC7.3: CJK/RTL/BLNS work (#101 closable) ✓

### Known Pre-existing Failures (NOT from this migration)
- `test_remote_presence_rendering.py` — CSS Highlight API test from different feature, intermittent
- Multiple tests skipped with "Flaky E2E infrastructure timeout — #120"

## Key Learnings (NiceGUI/Quasar/Playwright)

- **NiceGUI `ui.label()`** renders as `<div>`, NOT semantic `<h1>`-`<h6>`.
- **NiceGUI `ui.switch()`** renders as Quasar `q-toggle`.
- **Icon-only buttons** have no accessible name. Use filter with `i.q-icon`.
- **Mock auth roles**: `instructor@uni.edu` gets instructor role.
- **E2E compliance guard**: forbids `page.evaluate()` in test files.
- **`wait_for_text_walker()`**: from `annotation_helpers.py` for `_textNodes` readiness.
- **Strict mode**: Use `.first` or `exact=True` to avoid multi-element matches.
- **Playwright exceptions**: `PlaywrightTimeoutError` and `PlaywrightError`.
- **LaTeX hyphenation**: PDF text extraction needs `re.sub(r"-\n", "", pdf_text)` for UUID searches.
- **Copy protection setup order**: create week/activity before enabling copy protection.
