# PDF Export Character Alignment — Phase 4: Delete Dead Code

**Goal:** Remove all code made redundant by the new DOM-based marker insertion approach. Single source of truth for marker constants.

**Architecture:** Delete the old string-based `_insert_markers_into_html` and its support functions (`_escape_html_text_content`, `_plain_text_to_html`, `is_structured_html` detection). Delete the private marker constant copies in `latex.py` (Phase 1 created the shared `marker_constants.py`). Delete test files that exercise only deleted functions. Verify with grep that no references remain.

**Tech Stack:** Python 3.14, pytest

**Scope:** Phase 4 of 4 from original design

**Codebase verified:** 2026-02-08

---

## Acceptance Criteria Coverage

This phase implements and tests:

### pdf-export-char-alignment.AC4: Dead code removal
- **pdf-export-char-alignment.AC4.1 Success:** No references to `_insert_markers_into_html`, `_plain_text_to_html`, `_escape_html_text_content`, or `general_notes` (as export parameter) remain in source code
- **pdf-export-char-alignment.AC4.2 Success:** `ruff check` and `ty check` clean after removal
- **pdf-export-char-alignment.AC4.3 Success:** Full test suite passes

---

<!-- START_TASK_1 -->
### Task 1: Delete `_escape_html_text_content` from `latex.py`

**Verifies:** pdf-export-char-alignment.AC4.1, AC4.2

**Files:**
- Modify: `src/promptgrimoire/export/latex.py:57-97` (delete function)

**Implementation:**

Delete the entire `_escape_html_text_content` function (lines 57-97). This function escapes HTML special characters in text content while preserving structural `<p>` tags. It was only used by `convert_html_with_annotations` at line 1307, which was rewritten in Phase 2 to no longer call it.

Also check for and remove the import of `html` module at the top of the file if it was only used by this function (it's used as `html.escape()` inside `_escape_html_text_content`).

**Verification:**

Run: `uv run ruff check src/promptgrimoire/export/latex.py`
Expected: Clean

Run: `uvx ty check`
Expected: Clean

**Commit:** `refactor: delete unused _escape_html_text_content from latex.py`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Delete `_insert_markers_into_html` and private marker constants from `latex.py`

**Verifies:** pdf-export-char-alignment.AC4.1, AC4.2

**Files:**
- Modify: `src/promptgrimoire/export/latex.py:527-532` (delete marker constants)
- Modify: `src/promptgrimoire/export/latex.py:780-873` (delete function)

**Implementation:**

1. **Delete private marker constants** at lines 527-532. All six are dead once `_insert_markers_into_html` is deleted:
   - `_MARKER_TEMPLATE` (line 527)
   - `_MARKER_PATTERN` (line 528)
   - `_HLSTART_TEMPLATE` (line 529)
   - `_HLEND_TEMPLATE` (line 530)
   - `_HLSTART_PATTERN` (line 531)
   - `_HLEND_PATTERN` (line 532)

   Also delete the comment block at lines 523-526 that documents these constants.

   The shared equivalents already exist in `src/promptgrimoire/export/marker_constants.py` (created in Phase 1). The Lark grammar at lines 453-462 defines its own inline marker patterns for parsing — it does not use these compiled regexes.

   Update the comment at line 454 (`matching the production templates _HLSTART_TEMPLATE, _HLEND_TEMPLATE, etc.`) to reference the shared module instead:
   ```python
   # matching the marker format from export.marker_constants
   ```

2. **Delete `_insert_markers_into_html`** (lines 780-873 entirely). This is the old string-based marker insertion function. Its only caller was `convert_html_with_annotations` at line 1300, which was rewritten in Phase 2 to call `insert_markers_into_dom` instead.

**Verification:**

Run: `uv run ruff check src/promptgrimoire/export/latex.py`
Expected: Clean

Run: `uvx ty check`
Expected: Clean

**Commit:** `refactor: delete _insert_markers_into_html and private marker constants`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Delete `_plain_text_to_html` from `pdf_export.py`

**Verifies:** pdf-export-char-alignment.AC4.1, AC4.2

**Files:**
- Modify: `src/promptgrimoire/export/pdf_export.py:52-94` (delete `_plain_text_to_html`)

**Implementation:**

Delete the `_plain_text_to_html` function definition (lines 52-94 entirely). This function converts plain text to HTML with paragraph structure. Its only caller was `export_annotation_pdf` at line 313, within the `is_structured_html` branch. That call site was already removed in Phase 2 Task 3 (which deleted the `is_structured_html` detection and plain-text path). This task removes the now-orphaned function definition.

Verify no other callers exist — grep for `_plain_text_to_html` in `src/`. The only remaining references should be in test files (handled in Task 4).

**Verification:**

Run: `uv run ruff check src/promptgrimoire/export/pdf_export.py`
Expected: Clean

Run: `uvx ty check`
Expected: Clean

**Commit:** `refactor: delete unused _plain_text_to_html from pdf_export.py`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Delete obsolete test files

**Verifies:** pdf-export-char-alignment.AC4.1, AC4.3

**Files:**
- Delete: `tests/unit/export/test_plain_text_conversion.py`
- Delete: `tests/unit/export/test_crlf_char_index_bug.py`
- Delete: `tests/unit/export/test_marker_insertion.py`

**Implementation:**

1. **Delete `test_plain_text_conversion.py`** — Tests `_plain_text_to_html` and `_escape_html_text_content` exclusively. Both functions are deleted in Tasks 1 and 3.

2. **Delete `test_crlf_char_index_bug.py`** — Tests the plain-text CRLF flow with `_insert_markers_into_html`. This entire bug class (character index mismatch between string counting and DOM counting) is structurally eliminated by the DOM-based approach in Phase 1.

3. **Delete `test_marker_insertion.py`** — All 8 tests call `_insert_markers_into_html` directly. The same test scenarios (simple, multi-block, CJK, entities, cross-tag, backward compat) are covered by the 17 test cases in `tests/unit/input_pipeline/test_insert_markers.py` (created in Phase 1 Task 3). The Issue #113 regression tests (lines 89-161) test the `_plain_text_to_html` + `_escape_html_text_content` flow specifically — this bug is structurally impossible with the new approach.

**Verification:**

Run: `uv run test-debug`
Expected: All tests pass, no import errors

**Commit:** `test: delete obsolete marker insertion test files`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Grep verification and full test suite

**Verifies:** pdf-export-char-alignment.AC4.1, AC4.2, AC4.3

**Files:**
- None (verification only)

**Implementation:**

Run a comprehensive grep to confirm no references to deleted symbols remain in source or test code:

```bash
grep -rn "_insert_markers_into_html\|_plain_text_to_html\|_escape_html_text_content" src/ tests/
```

Expected: Zero results.

Also verify that `general_notes` does not appear as an export parameter (may still appear as a CRDT field name, which is expected for backward compatibility):

```bash
grep -rn "general_notes" src/promptgrimoire/export/ src/promptgrimoire/pages/
```

Expected: Zero results (Phase 3 removed all export pipeline references).

**Verification:**

Run: `uv run ruff check .`
Expected: Clean

Run: `uvx ty check`
Expected: Clean

Run: `uv run test-debug`
Expected: All tests pass, no regressions

**Commit:** No commit needed (verification only). If grep finds remaining references, fix them and commit as `fix: remove remaining references to deleted export functions`.
<!-- END_TASK_5 -->

---

## UAT Steps

After all tasks in this phase are complete and tests pass:

### Automated verification (pdf-export-char-alignment.AC4.1, AC4.2, AC4.3)

1. `uv run test-debug` — all tests pass, no import errors from deleted modules
2. `uv run ruff check .` — clean
3. `uvx ty check` — clean
4. Grep for deleted symbols returns zero results (Task 5)

### Manual verification (pdf-export-char-alignment.AC4.3 — full regression)

1. [ ] Start the app: `uv run python -m promptgrimoire`
2. [ ] Navigate to: `/annotation`
3. [ ] Paste a document, add highlights, type response draft content in Tab 3
4. [ ] Click Export PDF
5. [ ] Verify: PDF export still works identically to Phase 3 — highlights correct, Response Draft section present

**Evidence Required:**
- [ ] Test output showing all green for `test-debug`
- [ ] Grep output confirming zero references to deleted symbols
- [ ] PDF export still produces correct output (quick visual check)
