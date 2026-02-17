# Test Requirements: Annotation Module Split (#120)

**Design Plan:** `docs/design-plans/2026-02-14-annotation-split-120.md`
**Implementation Phases:** `docs/implementation-plans/2026-02-14-annotation-split-120/phase_01.md` through `phase_04.md`

---

## Automated Test Coverage Required

These criteria MUST have automated tests that verify the specific behaviour described. The "Expected Test File" column shows where the test should live; the "Behaviour to Verify" column describes what the test must actually assert (not just that it imports without error).

| ID | Criterion | Expected Test File | Behaviour to Verify |
|----|-----------|-------------------|---------------------|
| AC1.1 | `pages/annotation/` is a Python package with `__init__.py` | `tests/unit/test_annotation_package_structure.py` | Assert `src/promptgrimoire/pages/annotation/` is a directory AND `__init__.py` exists inside it |
| AC1.2 | `pages/annotation.py` does not exist as a file | `tests/unit/test_annotation_package_structure.py` | Assert `src/promptgrimoire/pages/annotation.py` is NOT a file (the path resolves to a directory) |
| AC1.3 | Package contains 9 authored modules | `tests/unit/test_annotation_package_structure.py` | Assert all 9 `.py` files exist: `__init__.py`, `broadcast.py`, `cards.py`, `content_form.py`, `css.py`, `document.py`, `highlights.py`, `pdf_export.py`, `workspace.py` |
| AC1.4 | Satellite modules exist inside package | `tests/unit/test_annotation_package_structure.py` | Assert `organise.py`, `respond.py`, `tags.py` exist inside `pages/annotation/` |
| AC1.5 | No satellite files at `pages/` level | `tests/unit/test_annotation_package_structure.py` | Assert `annotation_organise.py`, `annotation_respond.py`, `annotation_tags.py` do NOT exist at `src/promptgrimoire/pages/` |
| AC1.6 | Guard test fails if `annotation.py` recreated as file | `tests/unit/test_annotation_package_structure.py` | The AC1.2 assertion inherently covers this: if someone recreates `annotation.py` as a file, the "is not a file" check fails |
| AC2.1 | `static/annotation-card-sync.js` exists and exposes `setupCardPositioning()` | `tests/unit/test_annotation_js_extraction.py` | Assert file exists AND contains the string `function setupCardPositioning` |
| AC2.2 | `static/annotation-copy-protection.js` exists and exposes `setupCopyProtection()` | `tests/unit/test_annotation_js_extraction.py` | Assert file exists AND contains the string `function setupCopyProtection` |
| AC2.5 | No `_COPY_PROTECTION_JS` Python string constant in codebase | `tests/unit/test_annotation_js_extraction.py` | Scan all `.py` files under `src/promptgrimoire/` for the pattern `_COPY_PROTECTION_JS =` and assert zero matches |
| AC3.3 | No `PLC0415` per-file-ignores for annotation package in `pyproject.toml` | `tests/unit/test_annotation_package_structure.py` | Read `pyproject.toml`, check per-file-ignores entries: none should match `pages/annotation/` with `PLC0415` |
| AC3.4 | Dependency graph is acyclic (no circular imports) | `tests/unit/test_annotation_package_structure.py` | `from promptgrimoire.pages.annotation import annotation_page, PageState` succeeds without `ImportError` |
| AC4.1 | All existing tests pass | Full test suite (`uv run test-all`) | All unit + integration tests pass. No individual test file needed -- this is verified by running the full suite. |
| AC4.3 | Test import paths updated, logic unchanged | `tests/unit/test_copy_protection_js.py`, `tests/unit/test_render_js.py`, `tests/unit/pages/test_annotation_organise.py`, `tests/unit/pages/test_annotation_warp.py`, `tests/unit/test_remote_presence_refactor.py`, `tests/unit/pages/test_annotation_respond.py`, `tests/unit/pages/test_annotation_tags.py` | Each existing test file has imports updated to new submodule paths. Test logic (assertions, mocks, fixtures) unchanged. Verified by all tests passing with new import paths. |

---

## Human Verification Required

These criteria require manual inspection or browser interaction that automated tests cannot fully cover.

| ID | Criterion | Why Manual | Verification Method |
|----|-----------|-----------|---------------------|
| AC2.3 | Scroll-sync card positioning works in browser | Requires visual inspection of card-to-highlight tracking during scroll. E2E tests verify DOM state but cannot confirm smooth visual tracking. | Start app, open annotation workspace with highlights, scroll document, verify cards track highlight positions. |
| AC2.4 | Copy protection blocks copy/cut/drag/print when enabled | Requires verifying browser event interception and Quasar toast display. E2E tests can check some clipboard behaviour but not all browser-native interactions (context menu, print dialog). | Enable copy protection on Activity, open student workspace, try Ctrl+C/Ctrl+P on selected text, verify toast and blocked action. |
| AC3.1 | All inter-module imports use direct paths | Requires inspection of all source files to confirm no re-exports or indirect imports. Guard test covers import success but not style. | Grep all `.py` files in `pages/annotation/` for import statements. Verify all cross-module imports are `from promptgrimoire.pages.annotation.<module> import ...` not `from promptgrimoire.pages.annotation import ...` (except for `__init__.py` exports). |
| AC3.2 | `__init__.py` contains no late imports | Requires source inspection -- no automated way to distinguish "late" from "early" imports reliably. | Read `pages/annotation/__init__.py`. Verify all `import` statements are at module top level (not inside functions or `if` blocks). |
| AC4.2 | E2E tests pass | E2E tests require running browser infrastructure (`uv run test-e2e`). Separated from `test-all` by design. | Run `uv run test-e2e` and verify all tests pass. |
| AC5.1 | `CLAUDE.md` project structure lists annotation package modules | Documentation correctness -- not testable by code. | Read `CLAUDE.md` project structure section. Verify it lists `pages/annotation/` as a directory with all 12 modules (9 authored + 3 satellite). Verify no stale `annotation.py` reference. |
| AC5.2 | `annotation-perf.md` Phase 1 references actual module names | Documentation correctness for a separate design doc. | Read `docs/design-plans/2026-02-10-annotation-perf-142.md`. Verify Phase 1 module list matches actual package contents and uses post-CSS-Highlight-API function names. |
| AC5.3 | Follow-up issue filed for paste handler JS extraction | GitHub issue existence check. | Run `gh issue list --search "paste handler JS"` and verify issue exists with correct title and acceptance criteria. |

---

## Test-to-Criterion Traceability

### Guard Test: `tests/unit/test_annotation_js_extraction.py`

**Created in:** Phase 1, Task 4
**Pattern:** Filesystem structural checks (like `test_async_fixture_safety.py`, `test_no_fstring_latex.py`)

| Test | Criterion |
|------|-----------|
| Assert `annotation-card-sync.js` exists and contains `setupCardPositioning` | AC2.1 |
| Assert `annotation-copy-protection.js` exists and contains `setupCopyProtection` | AC2.2 |
| Assert no `.py` file under `src/promptgrimoire/` defines `_COPY_PROTECTION_JS` | AC2.5 |

### Guard Test: `tests/unit/test_annotation_package_structure.py`

**Created in:** Phase 2, Task 3 (extended in Phase 3, Task 3)
**Pattern:** Filesystem structural checks + import validation

| Test | Criterion |
|------|-----------|
| Assert `pages/annotation/` is a directory with `__init__.py` | AC1.1 |
| Assert `pages/annotation.py` is not a file | AC1.2, AC1.6 |
| Assert 9 authored module files exist | AC1.3 |
| Assert `organise.py`, `respond.py`, `tags.py` inside package | AC1.4 |
| Assert no `annotation_organise.py`, `annotation_respond.py`, `annotation_tags.py` at `pages/` level | AC1.5 |
| Assert no `PLC0415` annotation-package ignores in `pyproject.toml` | AC3.3 |
| Assert `from promptgrimoire.pages.annotation import annotation_page, PageState` succeeds | AC3.4 |

### Existing Tests (Import Path Updates Only)

These tests exist today. The refactor updates their import paths but does not change test logic.

| Test File | Current Imports (pre-refactor) | New Imports (post-refactor) | Phase |
|-----------|-------------------------------|----------------------------|-------|
| `tests/unit/test_copy_protection_js.py` | `from promptgrimoire.pages.annotation import _COPY_PROTECTION_JS, _inject_copy_protection, _render_workspace_header` | Remove `_COPY_PROTECTION_JS` import and `TestCopyProtectionJsContent` class (Phase 1); change remaining to `from promptgrimoire.pages.annotation.workspace import _inject_copy_protection, _render_workspace_header`; update `patch()` targets to `promptgrimoire.pages.annotation.workspace.ui.*` (Phase 2) | Phase 1 + Phase 2 |
| `tests/unit/test_render_js.py` | `from promptgrimoire.pages.annotation import _RawJS, _render_js` | No change -- `_RawJS` and `_render_js` remain in `__init__.py` | Phase 2 |
| `tests/unit/pages/test_annotation_organise.py` | `from promptgrimoire.pages.annotation import _parse_sort_end_args`; `from promptgrimoire.pages.annotation_organise import _SNIPPET_MAX_CHARS`; `from promptgrimoire.pages.annotation_tags import brief_tags_to_tag_info` | `from promptgrimoire.pages.annotation.workspace import _parse_sort_end_args` (Phase 2); `from promptgrimoire.pages.annotation.organise import _SNIPPET_MAX_CHARS`; `from promptgrimoire.pages.annotation.tags import brief_tags_to_tag_info` (Phase 3) | Phase 2 + Phase 3 |
| `tests/unit/pages/test_annotation_warp.py` | `from promptgrimoire.pages.annotation import _warp_to_highlight`; `from promptgrimoire.pages.annotation_organise import ...`; `from promptgrimoire.pages.annotation_respond import ...` | `from promptgrimoire.pages.annotation.highlights import _warp_to_highlight` (Phase 2); satellite imports updated to `annotation.organise`/`annotation.respond` (Phase 3) | Phase 2 + Phase 3 |
| `tests/unit/test_remote_presence_refactor.py` | `from promptgrimoire.pages import annotation` | No path change -- package import is transparent. Test does AST introspection on `__init__.py` after split. Verify assertions still valid (inspects module for deleted symbols and `_RemotePresence`). | Phase 2 |
| `tests/unit/pages/test_annotation_respond.py` | `from promptgrimoire.pages.annotation_respond import ...`; `from promptgrimoire.pages.annotation_tags import brief_tags_to_tag_info` | `from promptgrimoire.pages.annotation.respond import ...`; `from promptgrimoire.pages.annotation.tags import brief_tags_to_tag_info` | Phase 3 |
| `tests/unit/pages/test_annotation_tags.py` | `from promptgrimoire.pages.annotation_tags import brief_tags_to_tag_info` | `from promptgrimoire.pages.annotation.tags import brief_tags_to_tag_info` | Phase 3 |

### Full Suite Validation

| Command | What It Proves | Criteria |
|---------|---------------|----------|
| `uv run test-all` | All unit + integration tests pass with new package structure | AC4.1 |
| `uv run test-e2e` | Browser-level behaviour unchanged (scroll-sync, copy protection, highlights, cards) | AC4.2, AC2.3, AC2.4 |
| `uv run pytest tests/unit/test_annotation_js_extraction.py -v` | JS extraction guard tests pass | AC2.1, AC2.2, AC2.5 |
| `uv run pytest tests/unit/test_annotation_package_structure.py -v` | Package structure guard tests pass | AC1.1-AC1.6, AC3.3, AC3.4 |

---

## Phase-by-Phase Test Execution Order

### Phase 1: Extract JS to Static Files

**New tests created:** `tests/unit/test_annotation_js_extraction.py`
**Existing tests modified:** `tests/unit/test_copy_protection_js.py` (remove `_COPY_PROTECTION_JS` import and `TestCopyProtectionJsContent` class)

Run after Phase 1:
```bash
uv run pytest tests/unit/test_annotation_js_extraction.py -v   # New guard tests
uv run test-all                                                  # Full regression
```

### Phase 2: Split Monolith into Package

**New tests created:** `tests/unit/test_annotation_package_structure.py`
**Existing tests modified:** `tests/unit/test_copy_protection_js.py`, `tests/unit/pages/test_annotation_organise.py`, `tests/unit/pages/test_annotation_warp.py` (import path updates)

Run after Phase 2:
```bash
uv run pytest tests/unit/test_annotation_package_structure.py -v  # New guard tests
uv run test-all                                                    # Full regression
```

### Phase 3: git mv Satellite Modules

**Existing tests modified:** `tests/unit/test_annotation_package_structure.py` (extended with satellite checks), `tests/unit/pages/test_annotation_organise.py`, `tests/unit/pages/test_annotation_warp.py`, `tests/unit/pages/test_annotation_respond.py`, `tests/unit/pages/test_annotation_tags.py` (import path updates)

Run after Phase 3:
```bash
uv run pytest tests/unit/test_annotation_package_structure.py -v  # Extended guard tests
uv run test-all                                                    # Full regression
```

### Phase 4: Documentation Updates

**No test changes.** Documentation-only phase.

Run after Phase 4:
```bash
uv run test-all     # Confirm no accidental breakage
uv run test-e2e     # Full browser-level validation
```

---

## Edge Cases and Risks

| Risk | Mitigation | Test Coverage |
|------|-----------|---------------|
| `test_remote_presence_refactor.py` does AST introspection on `annotation` module. After split, `inspect.getfile(annotation)` returns `__init__.py` path, and `ast.parse` only sees `__init__.py` contents, not the full package. | Review test assertions post-split. Symbols that moved to submodules (like `_build_remote_cursor_css`) should still not appear in `__init__.py`, so `hasattr(annotation, ...)` checks may still work via re-exports or fail correctly. The `_source_text()` method will only see `__init__.py`, which is correct -- deleted symbols should not be in `__init__.py`. | Manual review of test assertions during Phase 2, Task 2 |
| `_RawJS` and `_render_js` stay in `__init__.py`, so `test_render_js.py` imports do not change. | No action needed. | Verified by `uv run test-all` |
| Circular import between `__init__.py` and `workspace.py` (init imports `_render_workspace_view` from workspace, workspace imports `PageState` from init). | Resolved by definition-before-import ordering in `__init__.py`: types defined before submodule imports. | AC3.4 guard test (import success) |
| `git mv` rename detection breaks if file content changes too much in same commit. | Phase 3 Task 1 does `git mv` only; import path updates are separate. Content similarity stays above git's 50% threshold. | `git log --follow` verification (manual) |
