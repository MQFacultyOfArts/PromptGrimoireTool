# Refactor Annotation workspace.py Design

**GitHub Issue:** #185

## Summary

The annotation workspace module (`workspace.py`) has grown to 1,072 lines with 18 functions, including a single rendering function 233 lines long that requires a linter suppression comment (`# noqa: PLR0915`) to silence a "function too complex" warning. This refactor breaks that monolith into four focused modules — `placement.py`, `sharing.py`, `header.py`, and a reduced `workspace.py` orchestrator — without changing any observable behaviour. The split follows the pattern already established by the rest of the annotation package, where each module owns one rendering concern and imports shared types from the package `__init__.py`.

Alongside the structural work, three small defects are corrected: the tag toolbar is incorrectly rendered for read-only viewers (it should only appear for users who can annotate); the tri-state resolution logic that determines effective boolean settings by merging activity-level overrides with course defaults is duplicated across two modules and will be deduplicated into a single shared function; and `update_workspace_sharing` is missing from the database layer's public export list. All changes are validated by the existing test suite — no new behaviour is introduced beyond the toolbar visibility fix.

## Definition of Done

- `_render_workspace_view()` decomposed into functions ≤80 lines each; no `# noqa: PLR0915` suppressions remain
- Unnecessary lazy imports in `_rebuild_toolbar()` promoted to module-level imports
- Placement dialog flow and sharing dialog flow extracted into their own modules
- All annotation package files ≤300 lines (soft target)
- Tag toolbar not rendered for viewers (`can_annotate=False`)
- Tri-state resolution uses single shared utility (no inline duplication in `acl.py`)
- `update_workspace_sharing` added to `db/__init__.py` `__all__`
- All 2843 unit/integration tests pass; all 65 E2E tests pass
- No behaviour change beyond the toolbar bug fix

## Acceptance Criteria

### refactor-workspace-185.AC1: Orchestrator decomposition
- **refactor-workspace-185.AC1.1 Success:** `_render_workspace_view()` is ≤80 lines
- **refactor-workspace-185.AC1.2 Success:** All extracted helpers (`_resolve_workspace_context()`, `_create_tag_callbacks()`, and optionally `_make_tab_change_handler()`) each ≤80 lines
- **refactor-workspace-185.AC1.3 Success:** No `# noqa: PLR0915` suppression in any annotation package file
- **refactor-workspace-185.AC1.4 Success:** `ruff check` passes with no PLR0915 violations in annotation package

### refactor-workspace-185.AC2: Module extraction
- **refactor-workspace-185.AC2.1 Success:** `placement.py` exists and contains `show_placement_dialog` as its entry point
- **refactor-workspace-185.AC2.2 Success:** `sharing.py` exists and contains `render_sharing_controls` and `open_sharing_dialog`
- **refactor-workspace-185.AC2.3 Success:** `header.py` exists and contains `render_workspace_header`
- **refactor-workspace-185.AC2.4 Success:** No top-level function moved to a new module still exists in `workspace.py` (inner closures and `@ui.refreshable` decorators move with their containing function, not independently)
- **refactor-workspace-185.AC2.5 Success:** All imports are module-level (no lazy imports for cycle avoidance)

### refactor-workspace-185.AC3: File size
- **refactor-workspace-185.AC3.1 Success:** `workspace.py` ≤300 lines
- **refactor-workspace-185.AC3.2 Success:** `placement.py` ≤300 lines
- **refactor-workspace-185.AC3.3 Success:** `sharing.py` ≤300 lines
- **refactor-workspace-185.AC3.4 Success:** `header.py` ≤300 lines

### refactor-workspace-185.AC4: Tag toolbar viewer gating
- **refactor-workspace-185.AC4.1 Success:** Viewer (`can_annotate=False`) does not see the tag toolbar
- **refactor-workspace-185.AC4.2 Success:** Peer/editor/owner (`can_annotate=True`) sees the tag toolbar as before

### refactor-workspace-185.AC5: Tri-state DRY
- **refactor-workspace-185.AC5.1 Success:** `resolve_tristate()` is a public function in `db/workspaces.py`
- **refactor-workspace-185.AC5.2 Success:** `acl.py` calls `resolve_tristate()` instead of inline logic
- **refactor-workspace-185.AC5.3 Success:** Both call sites produce identical results (existing tests cover this)

### refactor-workspace-185.AC6: Missing export
- **refactor-workspace-185.AC6.1 Success:** `from promptgrimoire.db import update_workspace_sharing` works

### refactor-workspace-185.AC7: No behaviour change
- **refactor-workspace-185.AC7.1 Success:** All 2843 unit/integration tests pass
- **refactor-workspace-185.AC7.2 Success:** All 65 E2E tests pass
- **refactor-workspace-185.AC7.3 Success:** No new test failures introduced

## Glossary

- **`# noqa: PLR0915`**: A comment that tells the ruff linter to suppress its "too many statements" rule for a specific line. Its presence indicates a function that should be split up.
- **`PageState`**: A shared state dataclass (defined in `annotation/__init__.py`) accumulating per-request context — user, workspace, permissions, and UI handles — passed into rendering functions throughout the annotation package.
- **`PlacementContext`**: A dataclass resolved at page load that describes where a workspace sits in the course hierarchy and what settings are in effect (copy protection, sharing, anonymity, tag creation).
- **Placement**: Where a workspace has been assigned in the course structure — "loose" (unassigned), under a course, or under a specific activity within a week.
- **`@ui.refreshable`**: A NiceGUI decorator that marks a function as re-renderable in place. Calling `fn.refresh()` clears and re-renders only that function's DOM output without a full page reload.
- **Tri-state resolution**: A pattern where a setting can be `True`, `False`, or `None` at the activity level. `None` means "inherit the course default." The resolution function collapses this to a plain boolean.
- **ast-grep**: A structural code search and rewrite tool that matches syntax patterns (e.g., "all calls to this function") regardless of whitespace or formatting. Used here to verify no stale references remain after moving functions.
- **`can_annotate`**: A boolean on `PageState` derived from the resolved ACL permission. `True` for peer, editor, and owner roles; `False` for viewer-only access. Gates which UI controls are rendered.

## Architecture

Extract `workspace.py` (1072 lines, 18 functions) into 4 focused modules within `src/promptgrimoire/pages/annotation/`. The monolithic `_render_workspace_view()` (233 lines, `# noqa: PLR0915`) becomes a ~60-line orchestrator calling extracted helpers.

### Target module structure

```
annotation/
├── __init__.py       (~280 lines — unchanged: PageState, registries, route handler)
├── workspace.py      (~300 lines — orchestrator, tab setup, helpers)
├── placement.py      (~215 lines — placement dialog flow)  ← NEW
├── sharing.py        (~170 lines — sharing controls + dialog)  ← NEW
├── header.py         (~130 lines — workspace header rendering)  ← NEW
├── document.py       (1-line change — tag toolbar gating)
└── [all other files unchanged]
```

### Import flow

All imports are unidirectional. New modules import from `__init__.py` for types and from `db`/`auth` for data access. `workspace.py` imports from the new modules. No new module imports from `workspace.py`.

```
__init__.py  (PageState, _RemotePresence, registries)
     ↑
placement.py, sharing.py, header.py  (UI modules, import types from __init__)
     ↑
workspace.py  (orchestrator, imports from new modules + existing leaves)
     ↑
__init__.py  (imports _render_workspace_view at bottom — standard package init)
```

Two lazy imports inside `_rebuild_toolbar()` (`css._build_tag_toolbar`, `highlights._add_highlight`) are promoted to module-level imports in `workspace.py`. Both source modules are leaves that don't import from `workspace.py`, so no cycle exists.

### Module responsibilities

**`placement.py`** — self-contained placement dialog flow with one entry point (`show_placement_dialog`). Contains the course→week→activity cascade UI, course-only select, and placement application logic. Imports from `db.workspaces`, `db.courses`, NiceGUI.

**`sharing.py`** — sharing controls and per-user sharing dialog with two entry points (`render_sharing_controls`, `open_sharing_dialog`). Contains email validation, grant/revoke UI, and refreshable shares list. Imports from `db.acl`, `db.users`, NiceGUI.

**`header.py`** — workspace header row rendering with one entry point (`render_workspace_header`). Contains status badges, export button, placement chip (refreshable), copy protection injection, and delegates to `sharing.render_sharing_controls` and `placement.show_placement_dialog`. Imports from both new modules.

**`workspace.py`** — remains as the orchestrator. `_render_workspace_view()` becomes a ~60-line function calling:
1. `_resolve_workspace_context()` — auth, ACL, PlacementContext, PageState construction
2. `_create_tag_callbacks()` — factory for tag management closures
3. `_setup_client_sync()` (existing, in broadcast.py)
4. `header.render_workspace_header()`
5. Tab panel setup (inline — NiceGUI context managers require it)
6. `_inject_copy_protection()` (moved to header.py)

Small utility functions (`_get_current_username`, `_get_current_user_id`, `_parse_sort_end_args`, `_create_workspace_and_redirect`) stay in workspace.py — they're small, only called locally, and extracting them would add files without improving maintainability.

## Existing Patterns

Investigation found the annotation package follows a consistent pattern: `__init__.py` defines shared types and the route handler; leaf modules (`cards.py`, `organise.py`, `respond.py`, `document.py`) each own one rendering concern and import `PageState` from `__init__`.

This design follows the same pattern. The three new modules (`placement.py`, `sharing.py`, `header.py`) each own one rendering concern and import `PageState` from `__init__`. No new patterns introduced.

The existing `@ui.refreshable` pattern (used in `_render_workspace_header` for placement chip and in `_open_sharing_dialog` for shares list) moves with its containing function. These are inner closures that must remain inner — they capture local scope and are called via `.refresh()` from sibling closures. They are not extraction targets.

### Divergence

`_resolve_workspace_context()` is a new pattern: an async function that performs auth checks and returns a result tuple or `None`. Currently, auth/state construction is inline in the rendering function. This extraction improves testability (the function can be called without rendering UI) but is a minor pattern addition, not a divergence.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Extract placement dialog

**Goal:** Move placement dialog flow to its own module.

**Components:**
- New `src/promptgrimoire/pages/annotation/placement.py` containing:
  - `show_placement_dialog()` (from workspace.py `_show_placement_dialog`)
  - `_build_activity_cascade()` (from workspace.py)
  - `_build_course_only_select()` (from workspace.py)
  - `_apply_placement()` (from workspace.py)
  - `_load_enrolled_course_options()` (from workspace.py)
- Updated imports in `workspace.py` — remove moved functions, add `from .placement import show_placement_dialog`
- ast-grep verification: zero stale references to moved functions in workspace.py

**Dependencies:** None (first phase)

**Done when:** All tests pass, `show_placement_dialog` callable from workspace.py via import, workspace.py line count reduced by ~215 lines
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Extract sharing dialog

**Goal:** Move sharing controls and dialog to their own module.

**Components:**
- New `src/promptgrimoire/pages/annotation/sharing.py` containing:
  - `render_sharing_controls()` (from workspace.py `_render_sharing_controls`)
  - `open_sharing_dialog()` (from workspace.py `_open_sharing_dialog`)
  - `_is_plausible_email()` (from workspace.py)
- Updated imports in `workspace.py`
- ast-grep verification: zero stale references

**Dependencies:** Phase 1 (placement.py already extracted, confirms the extraction pattern works)

**Done when:** All tests pass, sharing controls render correctly, workspace.py line count reduced by ~170 lines
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Extract header rendering

**Goal:** Move workspace header to its own module.

**Components:**
- New `src/promptgrimoire/pages/annotation/header.py` containing:
  - `render_workspace_header()` (from workspace.py `_render_workspace_header`)
  - `_get_placement_chip_style()` (from workspace.py)
  - `_inject_copy_protection()` (from workspace.py)
  - Copy protection string constants (`_COPY_PROTECTION_PRINT_CSS`, `_COPY_PROTECTION_PRINT_MESSAGE`)
- header.py imports from `sharing.render_sharing_controls` and `placement.show_placement_dialog`
- Updated imports in `workspace.py`
- ast-grep verification: zero stale references

**Dependencies:** Phases 1-2 (header.py imports from both extracted modules)

**Done when:** All tests pass, header renders correctly with placement chip and sharing controls, workspace.py line count reduced by ~130 lines
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Decompose orchestrator

**Goal:** Break `_render_workspace_view()` into ≤80-line functions. Remove `# noqa: PLR0915`.

**Components:**
- New functions in `workspace.py`:
  - `_resolve_workspace_context(workspace_id)` — workspace fetch, ACL enforcement, PlacementContext, PageState construction. Returns result tuple or `None`.
  - `_create_tag_callbacks(state, can_create_tags)` — factory returning `(on_add_tag, on_manage_tags, rebuild_toolbar)` closures
- `_on_tab_change` remains as an inline nested `def` in the orchestrator (counts as 1 statement for PLR0915; extracting to a factory adds indirection without improving clarity)
- Promote lazy imports in `_rebuild_toolbar()` to module-level imports (`css._build_tag_toolbar`, `highlights._add_highlight`)
- `_render_workspace_view()` reduced to orchestrator calling the above
- Remove `# noqa: PLR0915` suppression
- If ruff still flags PLR0915 after these extractions, extract `_on_tab_change` via `_make_tab_change_handler(state, workspace_id)` factory as a fallback

**Dependencies:** Phases 1-3 (workspace.py is at ~560 lines, header/sharing/placement already extracted)

**Done when:** All tests pass, no `# noqa` suppressions in workspace.py, ruff check clean
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Bug fix and DRY

**Goal:** Fix tag toolbar viewer gating, DRY tri-state resolution, fix missing export.

**Components:**
- `src/promptgrimoire/pages/annotation/document.py` — wrap `_build_tag_toolbar()` call (~line 207) in `if state.can_annotate:` guard
- `src/promptgrimoire/db/workspaces.py` — make `_resolve_tristate()` public (rename to `resolve_tristate()`)
- `src/promptgrimoire/db/acl.py` — replace inline tri-state logic in `_derive_enrollment_permission()` (~line 274) with call to `workspaces.resolve_tristate()`
- `src/promptgrimoire/db/__init__.py` — add `update_workspace_sharing` to `__all__`

**Dependencies:** Phase 4 (all structural changes complete; this phase is isolated fixes)

**Done when:** Viewer cannot see tag toolbar (E2E test or manual verification), `resolve_tristate` used in both call sites, `update_workspace_sharing` importable from `promptgrimoire.db`, all tests pass

**ACs covered:** refactor-workspace-185.AC4.1, refactor-workspace-185.AC5.1, refactor-workspace-185.AC6.1, refactor-workspace-185.AC7.1
<!-- END_PHASE_5 -->

## Additional Considerations

**ast-grep for mechanical safety:** Each extraction phase uses ast-grep to verify zero stale references remain after moving functions. Pattern: `ast-grep run -p 'moved_function($$$ARGS)' -l py src/promptgrimoire/pages/annotation/workspace.py` should return no matches after extraction. Import rewrites can use `ast-grep scan` with YAML rules for structural find-and-replace.

**Closure parameter threading:** When extracting `_resolve_workspace_context()` and `_create_tag_callbacks()`, closures that currently capture variables from `_render_workspace_view()`'s scope must receive those values as parameters instead. The `state` object is the primary shared state — most closures capture it. Passing `state` explicitly to factories is straightforward.

**NiceGUI context managers:** Tab panel content (`with ui.tab_panel("Annotate"):`) must remain inline in the orchestrator. NiceGUI's context managers bind UI elements to their parent container — extracting them into separate functions requires passing the container reference, which adds complexity without improving clarity.
