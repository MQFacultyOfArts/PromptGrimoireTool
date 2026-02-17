# E2E Test Migration: Persona-Based Narrative Tests

**GitHub Issue:** #156

## Summary

PromptGrimoire's E2E test suite was written for a character-index-based rendering architecture (`data-char-index` attributes on DOM spans). The application has since migrated to the CSS Custom Highlight API, which uses a JavaScript text walker and `StaticRange` objects instead of explicit span elements. The old tests now time out waiting for selectors that no longer exist.

Rather than patching tests feature-by-feature, this migration adopts a persona-based narrative testing approach. Instead of testing highlights, sync, and PDF export in isolation, the new suite follows realistic user workflows derived from PRDs: an instructor setting up a course, a solo student annotating content, two students collaborating in real-time, and an adversarial student testing internationalisation edge cases. Mechanism verification (CSS.highlights entries, DOM structure, CRDT operations) remains in unit and integration tests; E2E tests verify only user-visible outcomes. The migration fixes `data-char-index` locators in active tests, creates 4 persona-based test files, deletes 10 obsolete files, and provides evidence to close issues #106, #101, and #156.

## Definition of Done

1. Zero `data-char-index` references in any non-deprecated test file
2. All active E2E tests pass against the current annotation page (CSS Highlight API architecture)
3. Persona-based narrative tests replace feature-silo tests: instructor, solo student, two students collaborating, naughty student
4. `pytest-subtests` for discrete checkpoints within each narrative
5. E2E tests only verify user-visible outcomes; mechanism verification (CSS.highlights entries, DOM structure) stays in integration tests
6. All tests parallelisable under xdist (workspace-isolated, no shared mutable state beyond the single server instance)
7. `conftest.py` fixtures use `_textNodes` readiness instead of `[data-char-index]` selectors
8. Issues #106 (HTML paste), #101 (CJK/BLNS), #156 (E2E migration) closable after completion

## Acceptance Criteria

### 156-e2e-test-migration.AC1: No data-char-index references (DoD 1, 7)
- **156-e2e-test-migration.AC1.1 Success:** `grep -r "data-char-index" tests/e2e/ tests/benchmark/` returns zero matches excluding `deprecated/` and comment-only references in `test_no_char_span_queries.py`
- **156-e2e-test-migration.AC1.2 Success:** `conftest.py` fixtures `two_annotation_contexts` and `two_authenticated_contexts` use `_textNodes` readiness check
- **156-e2e-test-migration.AC1.3 Success:** `test_annotation_tabs.py` contains zero `data-char-index` locators

### 156-e2e-test-migration.AC2: All active E2E tests pass (DoD 2)
- **156-e2e-test-migration.AC2.1 Success:** `uv run test-e2e` completes with zero failures and zero timeouts
- **156-e2e-test-migration.AC2.2 Success:** No test is skipped with reason "Pending #106"

### 156-e2e-test-migration.AC3: Persona-based narrative tests (DoD 3, 4)
- **156-e2e-test-migration.AC3.1 Success:** `test_instructor_workflow.py` exists and passes, covering course creation through template editing and copy protection configuration
- **156-e2e-test-migration.AC3.2 Success:** `test_law_student.py` exists and passes, covering AustLII paste through PDF export with subtests for highlight CRUD, tab navigation, reload persistence, keyboard shortcuts
- **156-e2e-test-migration.AC3.3 Success:** `test_translation_student.py` exists and passes, covering CJK, RTL, mixed-script content through annotation and i18n PDF export with subtests
- **156-e2e-test-migration.AC3.4 Success:** `test_history_tutorial.py` exists and passes, covering bidirectional sync, comments, tag changes, concurrent edits, user count through user-leaves with subtests
- **156-e2e-test-migration.AC3.5 Success:** `test_naughty_student.py` exists and passes, covering BLNS/XSS content injection, copy protection bypass attempts, and dead-end navigation with subtests
- **156-e2e-test-migration.AC3.6 Success:** Each persona test uses `pytest-subtests` for discrete checkpoints

### 156-e2e-test-migration.AC4: E2E tests only verify user-visible outcomes (DoD 5)
- **156-e2e-test-migration.AC4.1 Success:** No persona test file contains `CSS.highlights` assertions (mechanism verification)
- **156-e2e-test-migration.AC4.2 Success:** No persona test file contains `page.evaluate()` calls that inspect internal DOM state (as opposed to user-visible text content)

### 156-e2e-test-migration.AC5: Parallelisable under xdist (DoD 6)
- **156-e2e-test-migration.AC5.1 Success:** Each test function creates its own workspace (no shared workspace state between tests)
- **156-e2e-test-migration.AC5.2 Success:** No test depends on database state created by another test

### 156-e2e-test-migration.AC6: Obsolete files deleted (DoD 3)
- **156-e2e-test-migration.AC6.1 Success:** `test_annotation_basics.py`, `test_annotation_cards.py`, `test_annotation_workflows.py`, `test_subtests_validation.py` are deleted
- **156-e2e-test-migration.AC6.2 Success:** `test_annotation_highlights.py`, `test_annotation_sync.py`, `test_annotation_collab.py` are deleted
- **156-e2e-test-migration.AC6.3 Success:** `test_annotation_blns.py`, `test_annotation_cjk.py`, `test_i18n_pdf_export.py` are deleted

### 156-e2e-test-migration.AC7: Issues closable (DoD 8)
- **156-e2e-test-migration.AC7.1 Success:** #156 scope complete (all data-char-index references removed)
- **156-e2e-test-migration.AC7.2 Success:** #106 evidence exists (HTML paste works end-to-end in persona tests)
- **156-e2e-test-migration.AC7.3 Success:** #101 evidence exists (CJK, RTL content works in translation student test; BLNS edge cases handled in naughty student test)

## Glossary

- **CSS Custom Highlight API**: Browser API (`CSS.highlights`) that renders highlights without modifying DOM structure; uses `StaticRange` objects to define highlighted regions
- **Text walker**: JavaScript function (`walkTextNodes()`) that traverses DOM text nodes to build a character-to-node coordinate mapping; replaces `data-char-index` attributes
- **Character offset**: Zero-indexed position in the document's text content, ignoring HTML markup; used to identify highlight boundaries independent of DOM structure
- **`_textNodes` readiness**: Test wait condition (`window._textNodes && window._textNodes.length > 0`) indicating the text walker has initialised and the document is interactive
- **Persona-based testing**: E2E test strategy organising tests by user role and realistic workflow rather than by isolated feature
- **pytest-subtests**: Plugin enabling multiple discrete checkpoints within a single test function; failures in one subtest don't prevent later subtests from running
- **xdist**: pytest plugin for parallel test execution across multiple workers; requires tests to be isolated
- **BLNS (Big List of Naughty Strings)**: Curated test fixture of edge-case strings (XSS attempts, null bytes, emoji, RTL text) designed to break software
- **Mock auth**: Test authentication bypass (`mock-token-{email}`) that creates valid user sessions without Stytch API calls
- **PRD (Product Requirements Document)**: Documents specifying PromptGrimoire's use cases (case-brief, translation, ancient-history); source of persona test narratives

## Architecture

### Test Philosophy

E2E tests verify **user narratives**, not feature mechanics. Each test file represents a persona performing a realistic workflow derived from the PRDs (case-brief-tool, translation-annotation, ancient-history-annotation). The question each test answers is: "Can this person complete their work?" not "Does this CSS property have this value?"

**Layering principle:**
- **Unit/integration tests** verify mechanisms: CSS.highlights entries, text walker parity, DOM structure, CRDT operations, highlight span computation
- **E2E tests** verify narratives: a student can paste content, annotate it, collaborate with another student, and export a PDF

Anything already proven at integration level appears in E2E at most as a subtest confirming the user-visible outcome (e.g. "highlight is visible" not "CSS.highlights.has('hl-tag-jurisdiction')").

### Persona Test Files (New)

| File | Persona | Narrative Source |
|------|---------|-----------------|
| `test_instructor_workflow.py` | Instructor | PRD course setup: create course, add week, create activity, configure copy protection, edit template |
| `test_law_student.py` | Law student | Case-brief PRD: paste AustLII case, highlight with legal tags (Jurisdiction, Legal Issues, etc.), organise by tag, write brief in Respond tab, export PDF |
| `test_translation_student.py` | Translation student | Translation PRD: paste CJK/RTL/multilingual source text, annotate translations, i18n PDF export. Owns all internationalisation test cases. |
| `test_history_tutorial.py` | History tutorial group (2 students) | Ancient-history PRD: paste Claude conversation, both annotate with tags, real-time collaboration, highlights/comments sync, concurrent edits, user count, one leaves |
| `test_naughty_student.py` | Adversarial student | BLNS edge cases, XSS via content injection, copy protection bypass attempts, dead-end navigation (bad workspace_id, unauthorised access) |

Each file contains one or a few `def test_*` functions with `pytest-subtests` for discrete checkpoints. Tests create their own workspaces for xdist isolation.

### Active Test Files (Fix Locators)

These files are active and working but contain `data-char-index` references that will time out:

| File | References | Fix Strategy |
|------|-----------|-------------|
| `conftest.py` | 2 (fixture setup) | Replace `wait_for_selector("[data-char-index]")` with `wait_for_function("() => window._textNodes && window._textNodes.length > 0")` |
| `test_annotation_tabs.py` | 5 (content visibility checks) | Replace char-index visibility checks with `#doc-container` text content or `_textNodes` readiness |
| `test_html_paste_whitespace.py` | 9 (content attachment/visibility) | Replace char-index waits and locators with `_textNodes` readiness + `page.evaluate()` for DOM structure checks |
| `test_fixture_screenshots.py` | 1 (content readiness) | Replace `[data-char-index]` wait with `_textNodes` readiness |
| `tests/benchmark/test_dom_performance.py` | 4 (DOM metrics) | Replace char-index selectors with `#doc-container` content queries |

### Files to Delete

| File | Reason |
|------|--------|
| `test_annotation_basics.py` | Workspace CRUD is implicit setup for every other test |
| `test_annotation_cards.py` | Card behaviour is implicit in highlight/sync tests |
| `test_annotation_workflows.py` | All duplicates per audit analysis |
| `test_subtests_validation.py` | Meta-test, no user value |
| `test_annotation_highlights.py` | 2 unique items (reload persistence, keyboard shortcut) folded into solo student narrative; rest implied by sync tests and integration tests |
| `test_annotation_sync.py` | Replaced by `test_student_collaboration.py` |
| `test_annotation_collab.py` | 3/6 duplicate of sync; 3 unique items folded into collaboration narrative |
| `test_annotation_blns.py` | Replaced by `test_naughty_student.py` |
| `test_annotation_cjk.py` | Replaced by `test_naughty_student.py` |
| `test_i18n_pdf_export.py` | PDF export folded into naughty student narrative |

### Files Unchanged

These are already written for the CSS Highlight API architecture and need no changes:

`test_highlight_rendering.py`, `test_text_selection.py`, `test_annotation_highlight_api.py`, `test_remote_presence_rendering.py`, `test_remote_presence_e2e.py`, `test_browser_gate.py`, `test_auth_pages.py`, `test_annotation_drag.py`, `test_organise_perf.py`

### Helpers

`annotation_helpers.py` already provides text-walker-based helpers (`select_chars()`, `create_highlight()`, `create_highlight_with_tag()`, `setup_workspace_with_content()`). New helpers may be needed for:

- `setup_workspace_with_html(page, app_server, html)` -- paste HTML content (for fixture-based tests)
- Course/activity setup helpers if the instructor narrative requires them

## Existing Patterns

Investigation found the annotation helpers (`tests/e2e/annotation_helpers.py`) already implement the text-walker-based approach:
- `select_chars()` uses `charOffsetToRect()` for coordinate lookup + Playwright mouse API
- `setup_workspace_with_content()` waits for `_textNodes` readiness, not char spans
- `create_highlight()` and `create_highlight_with_tag()` compose selection + tag click

The CSS Highlight API test files (`test_highlight_rendering.py`, `test_text_selection.py`, etc.) demonstrate the integration test pattern: `page.evaluate()` for mechanism verification, Playwright locators for user-visible outcomes.

The `conftest.py` fixtures (`two_annotation_contexts`, `two_authenticated_contexts`) show the multi-client pattern: separate browser contexts with independent authentication, sharing a workspace via URL.

This design follows all existing patterns. The new persona tests use the same helpers and fixtures.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Fix Infrastructure

**Goal:** Fix `conftest.py` fixtures and verify `setup_workspace_with_content()` works, unblocking all other tests.

**Components:**
- `tests/e2e/conftest.py` -- replace `[data-char-index]` waits in `two_annotation_contexts` and `two_authenticated_contexts` with `_textNodes` readiness check
- Verify `setup_workspace_with_content()` in `annotation_helpers.py` still works end-to-end (it already uses `_textNodes`, but the content type dialog flow may have changed during the annotation.py refactor)

**Dependencies:** None (first phase)

**Done when:** A minimal E2E test using `two_annotation_contexts` passes without timeout
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Fix Active Tests

**Goal:** Replace `data-char-index` locators in active test files with text-walker-based equivalents.

**Components:**
- `tests/e2e/test_annotation_tabs.py` -- 5 references: replace char-index visibility checks with `#doc-container` text content checks or `_textNodes` readiness
- `tests/e2e/test_html_paste_whitespace.py` -- 9 references: replace char-index waits with `_textNodes` readiness, replace DOM queries with `page.evaluate()` on `#doc-container`
- `tests/e2e/test_fixture_screenshots.py` -- 1 reference: replace char-index wait with `_textNodes` readiness
- `tests/benchmark/test_dom_performance.py` -- 4 references: replace char-index selectors with content-based queries

**Dependencies:** Phase 1 (conftest fixtures must work)

**Done when:** All currently-active E2E tests pass; zero `data-char-index` references remain in these files
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Instructor Workflow Test

**Goal:** Write persona-based E2E test for instructor course setup flow.

**Components:**
- `tests/e2e/test_instructor_workflow.py` -- new file. Narrative: instructor authenticates, creates course, adds week, creates activity (template workspace auto-created), configures copy protection, edits template workspace content, publishes week
- May need course setup helpers in `annotation_helpers.py` or a new `course_helpers.py`
- Uses `authenticated_page` fixture with mock auth

**Dependencies:** Phase 1 (infrastructure)

**Done when:** Instructor narrative test passes with subtests for each checkpoint
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Law Student Test

**Goal:** Write persona-based E2E test for a law student's annotation workflow, derived from the case-brief-tool PRD.

**Components:**
- `tests/e2e/test_law_student.py` -- new file. Narrative: law student authenticates, creates workspace, pastes AustLII case HTML (use existing fixture), highlights with legal tags (Jurisdiction, Procedural History, Legal Issues, etc.), adds comments on highlights, changes a tag, uses keyboard shortcut to apply tag, switches to Organise tab (cards in correct columns), switches to Respond tab (writes brief), reloads and verifies persistence, exports PDF
- Subtests for each checkpoint in the narrative
- Uses `authenticated_page` fixture, `setup_workspace_with_content()`, `select_chars()`, `create_highlight_with_tag()`

**Dependencies:** Phase 1 (infrastructure)

**Done when:** Law student narrative test passes with subtests; covers highlight CRUD, tab navigation, reload persistence, keyboard shortcuts, PDF export
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Translation Student Test

**Goal:** Write persona-based E2E test for a translation student working with multilingual content. Owns all internationalisation test cases.

**Components:**
- `tests/e2e/test_translation_student.py` -- new file. Narrative subtests covering:
  - Paste CJK source text (Chinese, Japanese, Korean) -- content renders, highlights work
  - Paste RTL text (Arabic, Hebrew) -- content renders, highlights work
  - Paste mixed scripts (CJK + Latin) -- content renders, highlights work
  - Annotate multilingual content with tags -- highlights on non-Latin text
  - Export i18n PDF -- paste multilingual content, create highlight, export PDF, verify PDF exists and is valid
- Uses `authenticated_page` fixture, `setup_workspace_with_content()`
- Provides evidence to close #101 (CJK/BLNS i18n subset)

**Dependencies:** Phase 1 (infrastructure)

**Done when:** Translation student test passes; CJK, RTL, and mixed-script content works end-to-end through annotation and PDF export
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: History Tutorial Group Test

**Goal:** Write persona-based E2E test for two history students collaborating in a tutorial, derived from the ancient-history PRD.

**Components:**
- `tests/e2e/test_history_tutorial.py` -- new file. Narrative: two students join same workspace with Claude conversation content, student A highlights text (syncs to B), student B highlights different text (syncs to A), student A adds comment (syncs to B), student B replies (syncs to A), student A changes tag (syncs to B), both create highlights concurrently (both preserved), user count badge shows 2, student B leaves, badge drops to 1
- Uses `two_authenticated_contexts` fixture
- Subtests for each sync checkpoint

**Dependencies:** Phase 1 (infrastructure, specifically the fixed `two_authenticated_contexts` fixture)

**Done when:** Tutorial collaboration narrative test passes with subtests; replaces `test_annotation_sync.py` and `test_annotation_collab.py`
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Naughty Student Test

**Goal:** Write persona-based E2E test for adversarial student behaviour -- security edge cases, copy protection enforcement, and dead-end navigation.

**Components:**
- `tests/e2e/test_naughty_student.py` -- new file. Narrative subtests covering:
  - Dead-end navigation: bad/nonexistent workspace_id shows appropriate error, not a crash
  - BLNS edge cases: paste XSS attempts (`<script>alert(1)</script>`), null bytes, special chars -- verify no injection, content sanitised
  - Copy protection bypass: student in a copy-protected activity attempts copy, cut, drag, print -- all blocked, toast notification shown
  - Content resilience: BLNS strings that survive paste can be highlighted and persisted
- Uses `authenticated_page` fixture, `setup_workspace_with_content()`
- For copy protection tests: requires instructor to set up activity with `copy_protection=True`, then student clones and attempts bypass

**Dependencies:** Phase 1 (infrastructure), Phase 3 (instructor workflow, for copy protection setup)

**Done when:** Naughty student test passes; BLNS content handling verified, copy protection enforced, dead-ends handled gracefully
<!-- END_PHASE_7 -->

<!-- START_PHASE_8 -->
### Phase 8: Delete Obsolete Files and Close Issues

**Goal:** Remove replaced test files, verify clean test suite, close issues.

**Components:**
- Delete 10 files: `test_annotation_basics.py`, `test_annotation_cards.py`, `test_annotation_workflows.py`, `test_subtests_validation.py`, `test_annotation_highlights.py`, `test_annotation_sync.py`, `test_annotation_collab.py`, `test_annotation_blns.py`, `test_annotation_cjk.py`, `test_i18n_pdf_export.py`
- Verify zero `data-char-index` references remain in non-deprecated test files
- Run full `test-e2e` suite and confirm all tests pass
- Update `docs/implementation-plans/2026-02-04-html-input-pipeline-106/e2e-test-audit.md` status

**Dependencies:** Phases 2-7 (all new tests must exist before deleting old ones)

**Done when:** Full E2E suite passes, zero `data-char-index` in active tests, issues #106/#101/#156 have evidence to close
<!-- END_PHASE_8 -->

## Additional Considerations

**Single-server architecture:** `test-e2e` runs one NiceGUI server shared by all xdist workers. All persona tests must be workspace-isolated (each test creates its own workspace via unique authenticated users). No test may depend on global server state beyond what's set up during `test-e2e` bootstrap (Alembic migrations, seed data).

**PDF export in E2E:** The law student and translation student narratives include PDF export. This requires TinyTeX to be installed (`scripts/setup_latex.py`). Tests should skip gracefully if LaTeX is not available, matching the pattern in the existing `test_i18n_pdf_export.py`.

**Instructor test scope:** The instructor workflow test is new coverage, not a migration of existing tests. It's included because the courses page is fully wired up but has zero E2E coverage. The naughty student test depends on it for copy protection setup. If this phase proves too large, it can be deferred to a separate issue without blocking #156 closure (the naughty student's copy protection subtests would also defer).

**Naughty student and copy protection:** The naughty student test requires an instructor to have set up a copy-protected activity. This can either be done inline (the test sets up its own course/activity) or by depending on a shared fixture. Given xdist isolation, inline setup is safer.

**Deprecated directory:** The `tests/e2e/deprecated/` directory (4 files, all module-level skipped) is not touched by this migration. Those files serve as historical reference for the audit's coverage gap analysis and can be deleted in a separate cleanup.
