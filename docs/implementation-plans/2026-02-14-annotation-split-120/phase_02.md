# Annotation Module Split — Phase 2: Split Monolith into Package

**Goal:** Replace `annotation.py` with `pages/annotation/` package containing 9 authored modules.

**Architecture:** Delete the 3,043-line monolith and create a Python package with focused modules. Uses definition-before-import ordering in `__init__.py` to resolve the circular dependency between core types and submodule functions. The split is atomic — all 9 modules must exist before any imports work.

**Tech Stack:** Python 3.14, NiceGUI

**Scope:** 4 phases from original design (phase 2 of 4)

**Codebase verified:** 2026-02-14

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 120-annotation-split.AC1: Package replaces monolith (partial — AC1.1 through AC1.3)
- **120-annotation-split.AC1.1 Success:** `src/promptgrimoire/pages/annotation/` is a Python package (directory with `__init__.py`)
- **120-annotation-split.AC1.2 Success:** `src/promptgrimoire/pages/annotation.py` does not exist as a file
- **120-annotation-split.AC1.3 Success:** Package contains 9 authored modules: `__init__`, `broadcast`, `cards`, `content_form`, `css`, `document`, `highlights`, `pdf_export`, `workspace`
- **120-annotation-split.AC1.6 Success:** Guard test fails if `annotation.py` is recreated as a file

### 120-annotation-split.AC3: Direct submodule imports
- **120-annotation-split.AC3.1 Success:** All inter-module imports use direct paths (e.g., `from promptgrimoire.pages.annotation.highlights import _add_highlight`)
- **120-annotation-split.AC3.2 Success:** `__init__.py` contains no late imports
- **120-annotation-split.AC3.3 Success:** No `PLC0415` per-file-ignores for the annotation package in `pyproject.toml`
- **120-annotation-split.AC3.4 Success:** Dependency graph is acyclic (no circular imports at module load time)

### 120-annotation-split.AC4: No logic changes
- **120-annotation-split.AC4.1 Success:** All existing tests pass (`uv run test-all`)
- **120-annotation-split.AC4.3 Edge:** Test import paths updated but test logic unchanged

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create package with all 9 modules — atomic split

**Verifies:** 120-annotation-split.AC1.1, 120-annotation-split.AC1.2, 120-annotation-split.AC1.3, 120-annotation-split.AC3.1, 120-annotation-split.AC3.2, 120-annotation-split.AC3.4

**Files:**
- Delete: `src/promptgrimoire/pages/annotation.py`
- Create: `src/promptgrimoire/pages/annotation/__init__.py`
- Create: `src/promptgrimoire/pages/annotation/broadcast.py`
- Create: `src/promptgrimoire/pages/annotation/cards.py`
- Create: `src/promptgrimoire/pages/annotation/content_form.py`
- Create: `src/promptgrimoire/pages/annotation/css.py`
- Create: `src/promptgrimoire/pages/annotation/document.py`
- Create: `src/promptgrimoire/pages/annotation/highlights.py`
- Create: `src/promptgrimoire/pages/annotation/pdf_export.py`
- Create: `src/promptgrimoire/pages/annotation/workspace.py`

**Implementation:**

This is a mechanical split — move functions from the monolith into their target modules with corrected imports. **No logic changes.**

**CRITICAL: `__init__.py` ordering.** Types must be defined BEFORE submodule imports. Python gives partially-loaded modules to circular importers, so `workspace.py` will find `PageState` already defined:

```python
# __init__.py — ORDER MATTERS
#
# 1. Stdlib/third-party imports
# 2. Define: PageState, _RemotePresence, _RawJS, _render_js()
#    Define: _workspace_registry, _workspace_presence, _background_tasks
# 3. Import from submodules (workspace.py etc.) — types already exist
# 4. Define: annotation_page() — uses imported functions
#
# WARNING: Do not reorder. Types must be defined before submodule imports
# to resolve circular dependency (workspace.py imports PageState from here).
```

**Function-to-module mapping (line numbers from annotation.py AFTER Phase 1 JS extraction):**

**`__init__.py`** — Core types, globals, route:

Third-party imports needed: `AnnotationDocumentRegistry` from `promptgrimoire.crdt.annotation_doc` (used to initialise `_workspace_registry`).

| Function/Class/Constant | Lines (approx) |
|--------------------------|-------|
| `_workspace_registry` | 76 |
| `_RemotePresence` dataclass | 80–109 |
| `_workspace_presence` | 113 |
| `_RawJS` class | 116–130 |
| `_render_js()` | 132–156 |
| `_background_tasks` | 160 |
| `PageState` dataclass | 364–412 |
| `annotation_page()` | 3013–3044 |

Submodule imports needed by `annotation_page()`:
- `from promptgrimoire.pages.annotation.workspace import _render_workspace_view, _get_current_username, _create_workspace_and_redirect`

**`css.py`** — CSS + tag toolbar:
| Function/Constant | Lines |
|--------------------|-------|
| `_PAGE_CSS` | 163–360 |
| `_get_tag_color()` | 490–497 |
| `_build_highlight_pseudo_css()` | 499–547 |
| `_setup_page_styles()` | 549–558 |
| `_build_tag_toolbar()` | 560–592 |

Imports from package: `PageState` from `__init__`.

**`highlights.py`** — Highlight CRUD, JSON, push-to-client:
| Function | Lines |
|----------|-------|
| `_warp_to_highlight()` | 425–468 |
| `_build_highlight_json()` | 594–623 |
| `_push_highlights_to_client()` | 625–656 |
| `_update_highlight_css()` | 658–678 |
| `_delete_highlight()` | 680–704 |
| `_add_highlight()` | 956–1057 |

Imports from package: `PageState`, `_RawJS`, `_render_js()` from `__init__`; `_get_tag_color()`, `_build_highlight_pseudo_css()` from `css`; `_refresh_annotation_cards` from `cards`.

**`cards.py`** — Annotation card UI:
| Function | Lines |
|----------|-------|
| `_build_expandable_text()` | 706–741 |
| `_build_comments_section()` | 743–799 |
| `_build_annotation_card()` | 801–919 |
| `_refresh_annotation_cards()` | 921–954 |

Imports from package: `PageState`, `_RawJS`, `_render_js()` from `__init__`; `_get_tag_color()` from `css`; `_warp_to_highlight()`, `_delete_highlight()`, `_push_highlights_to_client()` from `highlights`.

**`document.py`** — Document rendering + selection wiring:
| Function | Lines |
|----------|-------|
| `_setup_selection_handlers()` | 1059–1136 |
| `_render_document_with_highlights()` | 1138–1366 |

Imports from package: `PageState`, `_RawJS`, `_render_js()` from `__init__`; `_setup_page_styles()` from `css`; `_build_highlight_json()`, `_push_highlights_to_client()`, `_add_highlight()` from `highlights`; `_refresh_annotation_cards()` from `cards`.

**`broadcast.py`** — Multi-client sync, remote presence:
| Function | Lines |
|----------|-------|
| `_get_user_color()` | 1368–1384 |
| `_update_user_count()` | 1386–1400 |
| `_broadcast_js_to_others()` | 1402–1415 |
| `_notify_other_clients()` | 1417–1425 |
| `_setup_client_sync()` | 1427–1570 |
| `_broadcast_yjs_update()` | 2738–2760 |

Imports from package: `PageState`, `_RemotePresence`, `_RawJS`, `_render_js()`, `_workspace_presence`, `_background_tasks` from `__init__`; `_push_highlights_to_client()`, `_update_highlight_css()` from `highlights`; `_refresh_annotation_cards()` from `cards`.

**`content_form.py`** — Content paste/upload form:
| Function | Lines |
|----------|-------|
| `_detect_type_from_extension()` | 1654–1671 |
| `_get_file_preview()` | 1673–1683 |
| `_render_add_content_form()` | 1685–2280 |

Imports from package: `PageState`, `_RawJS`, `_render_js()` from `__init__`.

**`pdf_export.py`** — PDF export orchestration:
| Function | Lines |
|----------|-------|
| `_handle_pdf_export()` | 1572–1652 |

Imports from package: `PageState` from `__init__`.

**`workspace.py`** — Workspace view, header, copy protection, tab init:
| Function/Constant | Lines |
|--------------------|-------|
| `_get_current_username()` | 414–424 |
| `_create_workspace_and_redirect()` | 470–488 |
| `_get_placement_chip_style()` | 2282–2291 |
| `_get_current_user_id()` | 2293–2299 |
| `_load_enrolled_course_options()` | 2301–2312 |
| `_build_activity_cascade()` | 2314–2389 |
| `_build_course_only_select()` | 2391–2409 |
| `_apply_placement()` | 2411–2444 |
| `_show_placement_dialog()` | 2446–2514 |
| `_render_workspace_header()` | 2516–2602 |
| `_parse_sort_end_args()` | 2604–2647 |
| `_setup_organise_drag()` | 2649–2736 |
| `_initialise_respond_tab()` | 2762–2798 |
| `_COPY_PROTECTION_PRINT_CSS` | 2851–2857 |
| `_COPY_PROTECTION_PRINT_MESSAGE` | 2859–2863 |
| `_inject_copy_protection()` | 2866–2879 |
| `_render_workspace_view()` | 2881–3003 |

Imports from package: `PageState`, `_RawJS`, `_render_js()`, `_workspace_registry`, `_workspace_presence`, `_background_tasks` from `__init__`; `_setup_page_styles()` from `css`; `_push_highlights_to_client()`, `_update_highlight_css()` from `highlights`; `_refresh_annotation_cards()` from `cards`; `_render_document_with_highlights()` from `document`; `_setup_client_sync()`, `_broadcast_yjs_update()` from `broadcast`; `_render_add_content_form()` from `content_form`; `_handle_pdf_export()` from `pdf_export`.

**Each module gets its own `import` block** with only the stdlib/third-party imports it actually uses. Do NOT copy the monolith's full import block to every module. Let ruff autofix unused imports.

**Dependency graph (must be acyclic at module-load time):**

```
__init__.py  →  workspace.py  (annotation_page calls _render_workspace_view)
css.py       ←  highlights.py, cards.py, document.py
highlights.py ←  cards.py, document.py, workspace.py, broadcast.py
cards.py     ←  document.py, broadcast.py
broadcast.py ←  workspace.py
pdf_export.py ← workspace.py
content_form.py ← workspace.py
document.py  ←  workspace.py
```

All arrows go "down" (toward leaf modules) except `__init__.py → workspace.py`, which is safe due to definition-before-import ordering.

**Verification:**

```bash
# Quick import check — should not raise ImportError
uv run python -c "from promptgrimoire.pages.annotation import annotation_page, PageState; print('OK')"

# Full test suite
uv run test-all
# Expected: Tests fail with import errors (test paths not yet updated — fixed in Task 2)
```

**Commit:** `refactor: split annotation.py monolith into pages/annotation/ package`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update external import paths

**Verifies:** 120-annotation-split.AC3.1, 120-annotation-split.AC4.3

**Files:**
- Modify: `tests/unit/test_copy_protection_js.py` (line 26–30 — import path only; `_COPY_PROTECTION_JS` removal handled in Phase 1 Task 3 Step 5)
- Modify: `tests/unit/test_render_js.py` (line 22)
- Modify: `tests/unit/pages/test_annotation_organise.py` (line 18)
- Modify: `tests/unit/pages/test_annotation_warp.py` (line 16)
- Modify: `tests/unit/test_remote_presence_refactor.py` (line 15 — may need adjustment for package introspection)

**Implementation:**

Update import paths to use direct submodule imports per AC3.1. The changes are:

```python
# test_copy_protection_js.py — old (after Phase 1 Task 3 Step 5 removed _COPY_PROTECTION_JS):
from promptgrimoire.pages.annotation import (
    _inject_copy_protection,
    _render_workspace_header,
)
# new:
from promptgrimoire.pages.annotation.workspace import (
    _inject_copy_protection,
    _render_workspace_header,
)

# test_copy_protection_js.py — also update patch() targets in TestPrintSuppressionInjection._mock_ui (line 254):
# old:
patch("promptgrimoire.pages.annotation.ui.run_javascript")
patch("promptgrimoire.pages.annotation.ui.add_css")
patch("promptgrimoire.pages.annotation.ui.html")
# new:
patch("promptgrimoire.pages.annotation.workspace.ui.run_javascript")
patch("promptgrimoire.pages.annotation.workspace.ui.add_css")
patch("promptgrimoire.pages.annotation.workspace.ui.html")

# test_render_js.py — old:
from promptgrimoire.pages.annotation import _RawJS, _render_js
# new (same path — these ARE in __init__.py):
from promptgrimoire.pages.annotation import _RawJS, _render_js

# test_annotation_organise.py — old:
from promptgrimoire.pages.annotation import _parse_sort_end_args
# new:
from promptgrimoire.pages.annotation.workspace import _parse_sort_end_args

# test_annotation_warp.py — old:
from promptgrimoire.pages.annotation import _warp_to_highlight
# new:
from promptgrimoire.pages.annotation.highlights import _warp_to_highlight

# test_remote_presence_refactor.py — old:
from promptgrimoire.pages import annotation
# new (same — package import is transparent):
from promptgrimoire.pages import annotation
# NOTE: This test does AST introspection on the module. After split, it inspects
# __init__.py only. Check whether the test's assertions still make sense.
# If the test checks for functions that moved out, update assertions.
```

**No changes needed for:**
- `src/promptgrimoire/pages/__init__.py` — `from promptgrimoire.pages import annotation` works for packages
- `src/promptgrimoire/pages/annotation_organise.py` — imports from `annotation_tags`, not `annotation`
- `src/promptgrimoire/pages/annotation_respond.py` — imports from `crdt` and `annotation_tags`
- All E2E tests — use HTTP interface, no direct imports

**Verification:**

```bash
uv run test-all
# Expected: All tests pass (2471+)
```

**Commit:** `refactor: update test import paths for annotation package split`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Guard test — package structure invariants

**Verifies:** 120-annotation-split.AC1.1, 120-annotation-split.AC1.2, 120-annotation-split.AC1.3, 120-annotation-split.AC1.6, 120-annotation-split.AC3.3

**Files:**
- Create: `tests/unit/test_annotation_package_structure.py`
- Verify: `pyproject.toml` has no `PLC0415` ignores for annotation package

**Implementation:**

Write a guard test that verifies the package structure:

1. `src/promptgrimoire/pages/annotation/` is a directory (not a file)
2. `src/promptgrimoire/pages/annotation.py` does NOT exist as a file
3. `__init__.py` exists in the package directory
4. All 9 authored modules exist: `broadcast.py`, `cards.py`, `content_form.py`, `css.py`, `document.py`, `highlights.py`, `pdf_export.py`, `workspace.py`
5. No `PLC0415` per-file-ignores for the annotation package in `pyproject.toml` (AC3.3)
6. Importing the package succeeds: `from promptgrimoire.pages.annotation import annotation_page, PageState`

Follow the guard test pattern from `tests/unit/test_async_fixture_safety.py` and `tests/unit/export/test_no_fstring_latex.py`.

**Testing:**

Tests verify structural invariants (AC1.1–1.3, AC1.6, AC3.3). No mocking needed.

- 120-annotation-split.AC1.1: Assert `pages/annotation/` is a directory with `__init__.py`
- 120-annotation-split.AC1.2: Assert `pages/annotation.py` file does not exist
- 120-annotation-split.AC1.3: Assert all 9 module files exist
- 120-annotation-split.AC1.6: If `annotation.py` is recreated as a file, this test fails (AC1.2 check)
- 120-annotation-split.AC3.3: Assert no `PLC0415` ignores for annotation in pyproject.toml

**Verification:**

```bash
uv run pytest tests/unit/test_annotation_package_structure.py -v
# Expected: All guard tests pass

uv run test-all
# Expected: All tests pass including new guard tests
```

**Commit:** `test: add guard tests for annotation package structure`
<!-- END_TASK_3 -->
