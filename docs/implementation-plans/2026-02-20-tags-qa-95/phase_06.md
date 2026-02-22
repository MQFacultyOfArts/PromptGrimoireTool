# Annotation Tags QA Pass — Phase 6: Refactor + Dead Code Cleanup

**Goal:** Split `tag_management.py` into 5 files, collapse duplicate confirm dialogs, remove vestigial `regionPriority()` JS, address `Any` types. Update module count.

**Architecture:** Pure move refactor — no logic changes. `tag_management.py` (1091 lines) split into 5 files by dialog type and responsibility. One-way import graph: orchestrator imports from rows, save, import; rows imports from save for blur handlers; quick-create imports palette from orchestrator. Existing tests serve as regression coverage. The refactor runs AFTER all E2E and integration tests are green (Phases 1-5) so regressions are immediately detectable.

**Tech Stack:** Python, NiceGUI, JavaScript

**Scope:** Phase 6 of 6 from original design

**Codebase verified:** 2026-02-20

**Status:** NOT STARTED (audited 2026-02-21). `tag_management.py` not split, no dead code cleanup done.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### tags-qa-95.AC7: Refactor complete
- **tags-qa-95.AC7.1 Success:** `tag_management.py` split into 5 files, no file exceeds ~400 lines
- **tags-qa-95.AC7.2 Success:** Import graph between tag management files is one-way
- **tags-qa-95.AC7.3 Success:** `regionPriority()` dead code removed from `annotation-highlight.js`
- **tags-qa-95.AC7.4 Success:** All existing tests pass after refactor
- **tags-qa-95.AC7.5 Success:** Module count in `__init__.py` and package structure test updated

---

## UAT

After this phase is complete, verify manually:

1. Run `uv run test-all && uv run test-e2e` — all tests pass after refactor (AC7.4)
2. Check file sizes: `wc -l src/promptgrimoire/pages/annotation/tag_management*.py src/promptgrimoire/pages/annotation/tag_import.py src/promptgrimoire/pages/annotation/tag_quick_create.py` — no file exceeds ~400 lines (AC7.1)
3. Verify import graph is one-way: `grep -r "from.*tag_management_save import\|from.*tag_management_rows import\|from.*tag_import import\|from.*tag_quick_create import\|from.*tag_management import" src/promptgrimoire/pages/annotation/tag_*.py` — verify no cycles (AC7.2)
4. Confirm `regionPriority` function is gone: `grep -r "regionPriority" src/promptgrimoire/static/` — no matches (AC7.3)
5. Run `uv run pytest tests/unit/test_annotation_package_structure.py -v` — module count test passes with 17 modules (AC7.5)

---

<!-- START_TASK_1 -->
### Task 1: Remove vestigial regionPriority from annotation-highlight.js

**Verifies:** tags-qa-95.AC7.3

**Files:**
- Modify: `src/promptgrimoire/static/annotation-highlight.js`

**Implementation:**

The `regionPriority()` function at line 166-172 is called at line 156 inside `applyHighlights`. Its hardcoded priority table (`jurisdiction`, `legal_issues`, `legislation`, `evidence`) contains legacy names that never match dynamic tag keys (UUIDs). Every call falls through to the fallback: `tagIdx !== undefined ? tagIdx : 0`.

1. Replace line 156 `hl.priority = regionPriority(tag, tagIdx);` with:
   ```javascript
   hl.priority = tagIdx !== undefined ? tagIdx : 0;
   ```

2. Delete the `regionPriority` function (lines 166-172).

**Verification:**

Run: `uv run test-e2e -k test_annotation_highlight_api`
Expected: Highlight rendering and stacking order unchanged

**Commit:** `refactor: remove vestigial regionPriority from annotation-highlight.js`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Split tag_management.py into 5 files

**Verifies:** tags-qa-95.AC7.1, tags-qa-95.AC7.2

**Files:**
- Create: `src/promptgrimoire/pages/annotation/tag_quick_create.py`
- Create: `src/promptgrimoire/pages/annotation/tag_import.py`
- Create: `src/promptgrimoire/pages/annotation/tag_management_rows.py`
- Create: `src/promptgrimoire/pages/annotation/tag_management_save.py`
- Modify: `src/promptgrimoire/pages/annotation/tag_management.py` (keep as orchestrator)

**Implementation:**

This is a pure move refactor — no logic changes. Move functions between files, update imports, verify all existing tests pass unchanged.

**File assignments:**

**`tag_quick_create.py` (~165 lines):**
- `_SWATCH_BASE` constant (from line 51)
- `_SWATCH_SELECTED` constant (from line 52)
- `_build_colour_picker()` (lines 102-151)
- `open_quick_create()` (lines 154-260)
- Imports: `_PRESET_PALETTE` from `tag_management` (shared palette)
- Imports: `_refresh_tag_state` from `tag_management_save`

**`tag_import.py` (~60 lines):**
- `_render_import_section()` (lines 664-719)
- Imports: `_refresh_tag_state` from `tag_management_save`

**`tag_management_rows.py` (~370 lines):**
- `_render_tag_row()` (lines 266-378)
- `_render_group_header()` (lines 384-429)
- `_open_confirm_delete()` — collapsed from `_open_confirm_delete_tag` (lines 435-470) and `_open_confirm_delete_group` (lines 473-499) into a single parameterised function
- `_render_group_tags()` (lines 532-563)
- `_render_tag_list_content()` (lines 566-658)
- Imports: `_save_single_tag`, `_save_single_group` from `tag_management_save` (for blur handlers wired in `_render_tag_row` and `_render_group_header`)

**`tag_management_save.py` (~130 lines):**
- `_refresh_tag_state()` (lines 55-99)
- `_save_single_tag()` (lines 722-773)
- `_save_single_group()` (lines 776-800)
- No imports from other tag_management files (leaf module)

**`tag_management.py` orchestrator (~335 lines):**
- `TagRowInputs` TypedDict (lines 20-36)
- `_PRESET_PALETTE` constant (lines 38-49)
- `_reorder_list()` (lines 505-513)
- `_extract_reorder_indices()` (lines 516-526)
- `open_tag_management()` (lines 806-938)
- `_build_group_callbacks()` (lines 944-985)
- `_build_management_callbacks()` (lines 988-1090)
- Imports from: `tag_management_rows` (render functions), `tag_management_save` (save/refresh), `tag_import` (import section)
- Exports: `open_tag_management` (public API, imported by workspace.py)

**Import graph (one-way, no cycles):**

```
tag_management.py (orchestrator)
├── imports from tag_management_rows.py
├── imports from tag_management_save.py
└── imports from tag_import.py

tag_management_rows.py
└── imports from tag_management_save.py

tag_import.py
└── imports from tag_management_save.py

tag_quick_create.py
├── imports _PRESET_PALETTE from tag_management.py
└── imports _refresh_tag_state from tag_management_save.py

tag_management_save.py
└── (no imports from tag_management files — leaf)
```

**workspace.py import update:**

Currently imports `open_quick_create` and `open_tag_management` from `tag_management`. After split:
- `open_tag_management` stays in `tag_management.py` — no change
- `open_quick_create` moves to `tag_quick_create.py` — update import

```python
from promptgrimoire.pages.annotation.tag_management import open_tag_management
from promptgrimoire.pages.annotation.tag_quick_create import open_quick_create
```

**Collapsing confirm delete dialogs:**

Replace `_open_confirm_delete_tag` and `_open_confirm_delete_group` with a single parameterised function in `tag_management_rows.py`:

```python
def _open_confirm_delete(
    entity_name: str,
    body_text: str,
    delete_fn: Callable[[], Awaitable[None]],
    on_confirmed: Callable[[str], Awaitable[None]],
) -> None:
```

Callers in `_build_management_callbacks` and `_build_group_callbacks` construct the appropriate closure for `delete_fn` (handling `bypass_lock`, `tag_id`/`group_id`) and `body_text` (handling `highlight_count` message).

**Verification:**

Run: `uv run test-all && uv run test-e2e`
Expected: All tests pass unchanged

**Commit:** `refactor: split tag_management.py into 5 files`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Address Any types in tag management files

**Verifies:** None (code quality improvement, part of AC7.1 intent)

**Files:**
- Modify: all 5 tag management files from Task 2

**Implementation:**

Replace `Any` typed parameters with proper types. Use `TYPE_CHECKING` blocks for imports that would cause circular dependencies.

Priority replacements:

| Current | Replacement | Location |
|---------|-------------|----------|
| `tag: Any` | `Tag` (under TYPE_CHECKING) | `_render_tag_row`, `_render_group_tags` |
| `group: Any` | `TagGroup` (under TYPE_CHECKING) | `_render_group_header`, `_render_tag_list_content` |
| `on_delete: Any` | `Callable[[UUID, str], Awaitable[None]]` | callback params |
| `on_lock_toggle: Any \| None` | `Callable[[UUID, bool], Awaitable[None]] \| None` | callback params |
| `on_field_save: Any \| None` | `Callable[[UUID], Awaitable[None]] \| None` | callback params |
| `on_confirmed: Any` | `Callable[[str], Awaitable[None]]` | confirm delete |
| `_e: Any` | `events.GenericEventArguments` | event handlers |
| `render_tag_list: Any` | `Callable[[], Awaitable[None]]` | builder params |

For NiceGUI event types, import from `nicegui.events` (already available in the runtime).

For `Callable` and `Awaitable`, import from `collections.abc`.

Keep `Any` for Sortable-specific events if the exact type is unclear from NiceGUI's API.

**Verification:**

Run: `uvx ty check`
Expected: No new type errors

Run: `uv run test-all`
Expected: All tests pass

**Commit:** `refactor: replace Any types with concrete types in tag management`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update module count and package structure test

**Verifies:** tags-qa-95.AC7.5

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/__init__.py` — update docstring module count 13 → 17, add 4 new module descriptions
- Modify: `tests/unit/test_annotation_package_structure.py` — update `_AUTHORED_MODULES` tuple and docstring count

**Implementation:**

**`__init__.py`** — update the module listing docstring:

Add 4 new entries to the package description:
```
tag_import       Tag import from other activities
tag_management   Tag/group management dialog orchestrator
tag_management_rows  Tag/group row rendering and deletion
tag_management_save  Tag/group save-on-blur handlers
tag_quick_create  Quick tag creation dialog and colour picker
```

Remove the old single `tag_management` description and replace with the 5 entries. The count goes from 13 to 17: the original `tag_management.py` stays as orchestrator (no net removal) plus 4 new files (`tag_import.py`, `tag_management_rows.py`, `tag_management_save.py`, `tag_quick_create.py`), so 13 + 4 = 17.

**`test_annotation_package_structure.py`** — update `_AUTHORED_MODULES`:

Add 4 new entries:
```python
_AUTHORED_MODULES = (
    "__init__.py",
    "broadcast.py",
    "cards.py",
    "content_form.py",
    "css.py",
    "document.py",
    "highlights.py",
    "organise.py",
    "pdf_export.py",
    "respond.py",
    "tag_import.py",           # NEW
    "tag_management.py",
    "tag_management_rows.py",  # NEW
    "tag_management_save.py",  # NEW
    "tag_quick_create.py",     # NEW
    "tags.py",
    "workspace.py",
)
```

Update docstring from "13 authored modules" to "17 authored modules".

**Verification:**

Run: `uv run pytest tests/unit/test_annotation_package_structure.py -v`
Expected: test_all_authored_modules_exist passes with 17 modules

Run: `uv run test-all`
Expected: All tests pass

**Commit:** `chore: update module count to 17 after tag_management split`
<!-- END_TASK_4 -->
