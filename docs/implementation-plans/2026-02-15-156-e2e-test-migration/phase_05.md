# E2E Test Migration Implementation Plan — Phase 5

**Goal:** Create persona-based E2E test for a translation student working with multilingual content. Owns all internationalisation test cases.

**Architecture:** New `test_translation_student.py` with narrative subtests covering CJK, RTL, and mixed-script content through annotation and PDF export. Short content strings (Chinese, Japanese, Korean, Arabic, Hebrew) are pasted directly via `setup_workspace_with_content()`. PDF export verified by checking that UUID-based comment strings and script-specific characters appear in the downloaded PDF bytes. Replaces skipped `test_annotation_cjk.py` and `test_i18n_pdf_export.py`.

**Tech Stack:** Playwright, pytest, pytest-subtests

**Scope:** Phase 5 of 8 from design plan

**Codebase verified:** 2026-02-15

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 156-e2e-test-migration.AC3: Persona-based narrative tests (DoD 3, 4)
- **156-e2e-test-migration.AC3.3 Success:** `test_translation_student.py` exists and passes, covering CJK, RTL, mixed-script content through annotation and i18n PDF export with subtests
- **156-e2e-test-migration.AC3.6 Success:** Each persona test uses `pytest-subtests` for discrete checkpoints

### 156-e2e-test-migration.AC4: E2E tests only verify user-visible outcomes (DoD 5)
- **156-e2e-test-migration.AC4.1 Success:** No persona test file contains `CSS.highlights` assertions (mechanism verification)
- **156-e2e-test-migration.AC4.2 Success:** No persona test file contains `page.evaluate()` calls that inspect internal DOM state (as opposed to user-visible text content)

### 156-e2e-test-migration.AC5: Parallelisable under xdist (DoD 6)
- **156-e2e-test-migration.AC5.1 Success:** Each test function creates its own workspace (no shared workspace state between tests)
- **156-e2e-test-migration.AC5.2 Success:** No test depends on database state created by another test

### 156-e2e-test-migration.AC7: Issues closable (DoD 8)
- **156-e2e-test-migration.AC7.3 Success:** #101 evidence exists (CJK, RTL content works in translation student test; BLNS edge cases handled in naughty student test)

---

<!-- START_TASK_1 -->
### Task 1: Create test_translation_student.py

**Verifies:** 156-e2e-test-migration.AC3.3, 156-e2e-test-migration.AC3.6, 156-e2e-test-migration.AC4.1, 156-e2e-test-migration.AC4.2, 156-e2e-test-migration.AC5.1, 156-e2e-test-migration.AC5.2, 156-e2e-test-migration.AC7.3

**Files:**
- Create: `tests/e2e/test_translation_student.py`

**Implementation:**

Create a test file with multiple test methods, each using `pytest-subtests` for discrete checkpoints. Each test authenticates as a student (default random email via `_authenticate_page()`), creates its own workspace, and works with multilingual content.

**Authentication:** Use `_authenticate_page(page, app_server)` from `conftest.py`. Every test creates a fresh browser context and authenticates.

**Test content strings** (reused from existing `test_annotation_cjk.py` which will be deleted in Phase 8):
- Chinese: `"你好世界 这是中文测试内容 维基百科示例"`
- Japanese: `"こんにちは世界 日本語テスト 離婚判決謄本"`
- Korean: `"안녕하세요 한국어 테스트 법은 차이를"`
- Arabic (RTL): `"مرحبا بالعالم هذا نص عربي للاختبار"`
- Hebrew (RTL): `"שלום עולם זהו טקסט בעברית לבדיקה"`
- Mixed: `"Hello 世界 World こんにちは مرحبا 안녕하세요"`

---

**`test_cjk_annotation_workflow(self, browser, app_server, subtests)`:**

Narrative: Translation student pastes Chinese source text, highlights passages, verifies content renders correctly.

1. **`subtest: authenticate_and_create_workspace`** — Create browser context, authenticate, use `setup_workspace_with_content()` with the Chinese test string. Verify `#doc-container` contains `"你好世界"`.

2. **`subtest: highlight_chinese_text`** — Use `select_chars()` to select a range within the Chinese text. Create a highlight with `create_highlight_with_tag(page, start, end, tag_index=0)`. Verify annotation card appears.

3. **`subtest: add_japanese_content`** — Create a new workspace with the Japanese test string. Verify `#doc-container` contains `"こんにちは世界"`. Highlight a range. Verify annotation card appears.

4. **`subtest: add_korean_content`** — Create a new workspace with the Korean test string. Verify `#doc-container` contains `"안녕하세요"`. Highlight a range. Verify annotation card appears.

---

**`test_rtl_annotation_workflow(self, browser, app_server, subtests)`:**

Narrative: Translation student pastes RTL content (Arabic, Hebrew), highlights, verifies content renders.

1. **`subtest: arabic_content`** — Create browser context, authenticate, use `setup_workspace_with_content()` with Arabic test string. Verify `#doc-container` contains `"مرحبا"`. Highlight a range. Verify annotation card appears.

2. **`subtest: hebrew_content`** — Create new workspace with Hebrew test string. Verify `#doc-container` contains `"שלום"`. Highlight a range. Verify annotation card appears.

---

**`test_mixed_script_annotation(self, browser, app_server, subtests)`:**

Narrative: Translation student works with mixed-script document.

1. **`subtest: paste_mixed_content`** — Create browser context, authenticate, use `setup_workspace_with_content()` with the mixed test string. Verify `#doc-container` contains both `"Hello"` and `"世界"`.

2. **`subtest: highlight_across_scripts`** — Use `select_chars()` to select a range spanning Latin and CJK characters. Create highlight. Verify annotation card appears.

3. **`subtest: add_comment_with_uuid`** — Generate UUID string. Add as comment on the annotation. Store for later verification.

---

**`test_i18n_pdf_export(self, browser, app_server, subtests)`:**

Narrative: Translation student creates multilingual workspace, annotates, and exports PDF with i18n content.

Browser context created with `permissions=["clipboard-read", "clipboard-write"]` for paste simulation.

1. **`subtest: paste_cjk_fixture`** — Authenticate. Use `_load_fixture_via_paste()` (from Phase 4 Task 1) with the `chinese_wikipedia.html` fixture (`tests/fixtures/conversations/chinese_wikipedia.html`). Verify `#doc-container` contains `"维基百科"`.

2. **`subtest: highlight_and_comment`** — Use `create_highlight_with_tag()` to highlight a text range. Generate UUID string, add as comment on the highlight. Store UUID.

3. **`subtest: export_pdf`** — Click "Export PDF" button. Use `page.expect_download()` to capture the download. Wait for completion. Read PDF bytes. Verify:
   - File size > 20KB (real PDF with LaTeX-compiled content)
   - UUID comment string appears in PDF bytes (proves annotation pipeline works)
   - At least one CJK character from the fixture appears in the PDF bytes (e.g. encoded form of `"维基百科"`) — but note: CJK in PDF content streams may be encoded differently. **If CJK byte search is unreliable, rely on UUID string verification as the primary assertion** (UUID is ASCII, always findable in PDF bytes).

**Isolation:** Each test method creates its own browser context, authenticates with a random email, and creates its own workspace. No shared state between tests.

**Constraints from AC4:** No `CSS.highlights` assertions. All assertions use Playwright locators checking user-visible text, element visibility, and downloaded file content.

**AC4.2 `page.evaluate()` guidance:** Calls that read user-visible content are permitted (e.g. `textContent`, `innerText`, clipboard API). Prohibited: inspecting `CSS.highlights`, `getComputedStyle()` for highlight colours, `window._textNodes`, `window._crdt*`, or other internal framework state.

**Testing:**
- 156-e2e-test-migration.AC3.3: `test_translation_student.py` exists and all subtests pass for CJK, RTL, mixed-script content and i18n PDF export
- 156-e2e-test-migration.AC3.6: Each test uses `subtests.test(msg=...)` for checkpoints
- 156-e2e-test-migration.AC4.1: `grep "CSS.highlights" tests/e2e/test_translation_student.py` returns no matches
- 156-e2e-test-migration.AC4.2: `grep "page.evaluate" tests/e2e/test_translation_student.py` returns no matches
- 156-e2e-test-migration.AC5.1: Each test creates its own workspace
- 156-e2e-test-migration.AC5.2: Random auth emails, UUID comments, no cross-test DB dependency
- 156-e2e-test-migration.AC7.3: CJK and RTL content works end-to-end (evidence for #101)

**Verification:**
Run: `uv run pytest tests/e2e/test_translation_student.py -v -x --timeout=180 -m e2e`
Expected: All tests pass; CJK, RTL, and mixed-script content renders, can be highlighted, and exports to valid PDF

**Commit:** `feat(e2e): add test_translation_student.py persona test (AC3.3)`
<!-- END_TASK_1 -->
