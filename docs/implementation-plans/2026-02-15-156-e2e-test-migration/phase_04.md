# E2E Test Migration Implementation Plan — Phase 4

**Goal:** Create persona-based E2E test for the law student annotation workflow.

**Architecture:** New `test_law_student.py` with narrative subtests covering AustLII HTML paste through PDF export. HTML fixture loaded from disk and pasted via clipboard simulation (same pattern as `test_html_paste_whitespace.py:simulate_html_paste()`). PDF export verified by checking that UUID-based comment strings appear in the downloaded PDF content. All interactions require authentication first. Browser context created with clipboard permissions for paste simulation.

**Tech Stack:** Playwright, pytest, pytest-subtests

**Scope:** Phase 4 of 8 from design plan

**Codebase verified:** 2026-02-15

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 156-e2e-test-migration.AC3: Persona-based narrative tests (DoD 3, 4)
- **156-e2e-test-migration.AC3.2 Success:** `test_law_student.py` exists and passes, covering AustLII paste through PDF export with subtests for highlight CRUD, tab navigation, reload persistence, keyboard shortcuts
- **156-e2e-test-migration.AC3.6 Success:** Each persona test uses `pytest-subtests` for discrete checkpoints

### 156-e2e-test-migration.AC4: E2E tests only verify user-visible outcomes (DoD 5)
- **156-e2e-test-migration.AC4.1 Success:** No persona test file contains `CSS.highlights` assertions (mechanism verification)
- **156-e2e-test-migration.AC4.2 Success:** No persona test file contains `page.evaluate()` calls that inspect internal DOM state (as opposed to user-visible text content)

### 156-e2e-test-migration.AC5: Parallelisable under xdist (DoD 6)
- **156-e2e-test-migration.AC5.1 Success:** Each test function creates its own workspace (no shared workspace state between tests)
- **156-e2e-test-migration.AC5.2 Success:** No test depends on database state created by another test

### 156-e2e-test-migration.AC7: Issues closable (DoD 8)
- **156-e2e-test-migration.AC7.2 Success:** #106 evidence exists (HTML paste works end-to-end in persona tests)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add _load_fixture_via_paste() to annotation_helpers.py

**Verifies:** None (infrastructure enabling Task 2)

**Files:**
- Modify: `tests/e2e/annotation_helpers.py`

**Implementation:**

Add a helper function that loads an HTML fixture from disk and pastes it via the clipboard simulation pattern. This reuses the same approach as `test_html_paste_whitespace.py:simulate_html_paste()` but wraps the full flow: load file, create workspace, paste HTML, confirm content type, wait for text walker.

**`_load_fixture_via_paste(page, app_server, fixture_path)`** — Expects an **already-authenticated** page. Steps:

1. Navigate to `/annotation`
2. Click "Create" workspace button, wait for `workspace_id=` URL
3. Read the HTML fixture from `fixture_path` (handle `.html.gz` with `gzip.open` and plain `.html` with `Path.read_text`)
4. Focus the editor (`.q-editor__content`), click it
5. Write HTML to clipboard via `navigator.clipboard.write()` (same JS as `simulate_html_paste()`)
6. Press `Control+v` to trigger paste
7. Wait for "Content pasted" to appear in editor
8. Click "Add" button
9. Handle content type confirmation dialog: wait for "Confirm" button visible, click it
10. Wait for `_textNodes` readiness: `page.wait_for_function("() => window._textNodes && window._textNodes.length > 0", timeout=15000)`

The browser context must be created with `permissions=["clipboard-read", "clipboard-write"]` — this is the caller's responsibility (documented in docstring).

The 15-second timeout is intentional — AustLII fixtures are large HTML files that take time to process through the input pipeline.

Follow the existing `annotation_helpers.py` pattern: `from __future__ import annotations`, `TYPE_CHECKING` guard for `Page`, type-hinted, docstring.

**Testing:**
- No standalone tests — helper is verified by its consumer (Task 2)

**Verification:**
Run: `uv run ruff check tests/e2e/annotation_helpers.py && uvx ty check`
Expected: No lint or type errors

**Commit:** `feat(e2e): add _load_fixture_via_paste helper for HTML fixture clipboard simulation`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create test_law_student.py

**Verifies:** 156-e2e-test-migration.AC3.2, 156-e2e-test-migration.AC3.6, 156-e2e-test-migration.AC4.1, 156-e2e-test-migration.AC4.2, 156-e2e-test-migration.AC5.1, 156-e2e-test-migration.AC5.2, 156-e2e-test-migration.AC7.2

**Files:**
- Create: `tests/e2e/test_law_student.py`

**Implementation:**

Create a single narrative test class with one test method using `pytest-subtests` for discrete checkpoints. The test authenticates as a law student and walks through the complete annotation workflow with an AustLII case.

**Browser context:** Must be created with `permissions=["clipboard-read", "clipboard-write"]` for the clipboard paste simulation. Use a fresh browser context (not the `authenticated_page` fixture, since that doesn't grant clipboard permissions). Authenticate via `_authenticate_page(page, app_server)` from `conftest.py` (default random email = student role).

**Fixture path:** `tests/fixtures/conversations/lawlis_v_r_austlii.html` (39KB, smallest AustLII fixture — sufficient for annotation testing without excessive load times).

**Narrative flow with subtests:**

1. **`subtest: authenticate_and_paste_fixture`** — Authenticate, use `_load_fixture_via_paste()` to load the AustLII fixture. Verify `#doc-container` contains text (e.g. check for case-specific text like "Lawlis" or "AustLII").

2. **`subtest: highlight_with_legal_tag`** — Use `create_highlight_with_tag(page, start_char, end_char, tag_index=0)` to highlight a text range with the Jurisdiction tag (index 0). Verify an annotation card appears: `expect(page.locator("[data-testid='annotation-card']").first).to_be_visible()`.

3. **`subtest: add_comment_with_uuid`** — Generate a UUID string. Click on the annotation card to expand it. Find the comment input and type the UUID string as a comment. Submit. Verify the comment text appears on the card. **Store this UUID for PDF verification later.**

4. **`subtest: highlight_with_different_tag`** — Use `create_highlight_with_tag()` with a different tag (e.g. tag_index=3 for Legal Issues). Verify a second annotation card appears.

5. **`subtest: add_second_comment_with_uuid`** — Generate a second UUID string. Add it as a comment on the second annotation card. Store for PDF verification.

6. **`subtest: change_tag_via_dropdown`** — On one of the annotation cards, find the tag dropdown/select and change it to a different tag. Verify the card updates to show the new tag name.

7. **`subtest: keyboard_shortcut_tag`** — Select another text range with `select_chars()`. Press a keyboard shortcut (e.g. `page.keyboard.press("1")` for Procedural History). Verify a new annotation card appears with the correct tag.

8. **`subtest: organise_tab`** — Click the "Organise" tab. Verify organise cards appear: `expect(page.locator("[data-testid='organise-card']").first).to_be_visible()`. Check that at least one column heading matches a legal tag name used above.

9. **`subtest: respond_tab`** — Click the "Respond" tab. Verify the Milkdown editor loads: `expect(page.locator("[data-testid='milkdown-editor-container']")).to_be_visible()`. Type some text into the editor.

10. **`subtest: reload_persistence`** — Save the current URL. Call `page.reload()`. Wait for `_textNodes` readiness. Verify annotations persist: check that annotation cards are still visible and the UUID comment text from subtests 3/5 is still present.

11. **`subtest: export_pdf_with_annotations`** — Click "Export PDF" button in the header. Use Playwright's download interception (`page.expect_download()`) to capture the download. Wait for the download to complete. Read the PDF content as bytes. Verify:
    - File size is substantial (> 20KB — a real PDF with LaTeX-compiled content, not an error page)
    - The first UUID comment string from subtest 3 appears in the PDF bytes (search as raw bytes — PDF text is embedded in the file even if not easily extractable without a parser; for a LaTeX-compiled PDF, the annotation text will be in the content stream)
    - The second UUID comment string from subtest 5 appears in the PDF bytes

    **Why UUID string verification:** UUIDs are random and unique. Finding them in the PDF output proves the entire annotation-to-export pipeline works end-to-end. This is the hardest assertion to fake — the only way it passes is if the comments actually flowed through the CRDT → LaTeX → PDF pipeline.

**Isolation:** The test creates its own workspace with a random email for auth. No shared database state. UUID in comment text ensures no collision.

**Constraints from AC4:** No `CSS.highlights` assertions. All assertions use Playwright locators checking user-visible text, button labels, element visibility, and downloaded file content.

**AC4.2 `page.evaluate()` guidance:** Calls that read user-visible content are permitted (e.g. `textContent`, `innerText`, clipboard API via `navigator.clipboard.write()`). Prohibited: inspecting `CSS.highlights`, `getComputedStyle()` for highlight colours, `window._textNodes`, `window._crdt*`, or other internal framework state. The `_load_fixture_via_paste()` helper uses `page.evaluate()` for clipboard write — this is permitted because it simulates a user action (paste), not internal DOM inspection.

**Testing:**
- 156-e2e-test-migration.AC3.2: `test_law_student.py` exists and all subtests pass
- 156-e2e-test-migration.AC3.6: Test uses `subtests.test(msg=...)` for each checkpoint
- 156-e2e-test-migration.AC4.1: `grep "CSS.highlights" tests/e2e/test_law_student.py` returns no matches
- 156-e2e-test-migration.AC4.2: `grep "page.evaluate" tests/e2e/test_law_student.py` returns no matches (or only for user-visible text content checks in helpers)
- 156-e2e-test-migration.AC5.1: Test creates its own workspace, no fixture sharing
- 156-e2e-test-migration.AC5.2: Random auth email + UUID comments, no cross-test DB dependency
- 156-e2e-test-migration.AC7.2: HTML paste via clipboard simulation proves #106 works end-to-end

**Verification:**
Run: `uv run pytest tests/e2e/test_law_student.py -v -x --timeout=180 -m e2e`
Expected: All subtests pass; law student can paste AustLII HTML, annotate with legal tags, add comments, change tags, use keyboard shortcuts, view organise/respond tabs, reload with persistence, and export PDF with annotation content verified

**Commit:** `feat(e2e): add test_law_student.py persona test (AC3.2)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
