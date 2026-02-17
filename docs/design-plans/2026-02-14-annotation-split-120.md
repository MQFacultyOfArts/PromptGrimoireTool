# Annotation Page Module Split Design

**GitHub Issue:** #120

## Summary

This design splits the 3,041-line `annotation.py` monolith into a 9-module `pages/annotation/` Python package to improve navigability and reduce merge conflicts. The split is mechanical — no logic changes, just code organization. Two large embedded JavaScript blocks (scroll-sync card positioning and copy protection) are extracted to static files following the pattern established by the CSS Highlight API migration. Three satellite modules (`annotation_organise.py`, `annotation_respond.py`, `annotation_tags.py`) are moved into the package via `git mv` to preserve rename detection. The result is a focused set of modules with clear responsibilities: `highlights.py` owns highlight CRUD, `cards.py` renders annotation cards, `broadcast.py` handles multi-client sync, etc.

The approach uses direct submodule imports (no re-exports from `__init__.py`) to avoid circular dependency risks. The dependency graph is acyclic by design: `__init__.py` defines core types (`PageState`, `_RemotePresence`), `css.py` provides styling infrastructure used by highlight and card modules, and higher-level modules like `workspace.py` orchestrate the UI. This follows the same package structure attempted in commit 3141eb5 but improves on the import pattern to eliminate the need for late imports and ruff ignore rules.

## Definition of Done

1. `annotation.py` replaced by `pages/annotation/` package — monolith split into focused modules, satellite modules (organise, respond, tags) `git mv`'d into the package
2. Embedded JS extracted to static files — substantial JS blocks moved from Python string constants to `.js` files in `static/`
3. `annotation-perf.md` Phase 1 updated — reflects actual module structure, current line counts, and post-CSS-Highlight-API function names
4. `CLAUDE.md` updated — project structure section reflects the package, not the monolith
5. All tests pass — pure mechanical refactor + JS extraction, no logic changes
6. No clobbering risk — future implementation plans reference package paths, not monolith

## Acceptance Criteria

### 120-annotation-split.AC1: Package replaces monolith
- **120-annotation-split.AC1.1 Success:** `src/promptgrimoire/pages/annotation/` is a Python package (directory with `__init__.py`)
- **120-annotation-split.AC1.2 Success:** `src/promptgrimoire/pages/annotation.py` does not exist as a file
- **120-annotation-split.AC1.3 Success:** Package contains 9 authored modules: `__init__`, `broadcast`, `cards`, `content_form`, `css`, `document`, `highlights`, `pdf_export`, `workspace`
- **120-annotation-split.AC1.4 Success:** Satellite modules exist inside package as `organise.py`, `respond.py`, `tags.py`
- **120-annotation-split.AC1.5 Success:** No `annotation_organise.py`, `annotation_respond.py`, or `annotation_tags.py` at the `pages/` level
- **120-annotation-split.AC1.6 Success:** Guard test fails if `annotation.py` is recreated as a file

### 120-annotation-split.AC2: JS extracted to static files
- **120-annotation-split.AC2.1 Success:** `static/annotation-card-sync.js` exists and exposes `setupCardPositioning()`
- **120-annotation-split.AC2.2 Success:** `static/annotation-copy-protection.js` exists and exposes `setupCopyProtection()`
- **120-annotation-split.AC2.3 Success:** Scroll-sync card positioning works in browser (cards track highlight positions on scroll)
- **120-annotation-split.AC2.4 Success:** Copy protection blocks copy/cut/drag/print when enabled
- **120-annotation-split.AC2.5 Success:** No `_COPY_PROTECTION_JS` Python string constant remains in the codebase

### 120-annotation-split.AC3: Direct submodule imports
- **120-annotation-split.AC3.1 Success:** All inter-module imports use direct paths (e.g., `from promptgrimoire.pages.annotation.highlights import _add_highlight`)
- **120-annotation-split.AC3.2 Success:** `__init__.py` contains no late imports
- **120-annotation-split.AC3.3 Success:** No `PLC0415` per-file-ignores for the annotation package in `pyproject.toml`
- **120-annotation-split.AC3.4 Success:** Dependency graph is acyclic (no circular imports at module load time)

### 120-annotation-split.AC4: No logic changes
- **120-annotation-split.AC4.1 Success:** All existing tests pass (`uv run test-all`)
- **120-annotation-split.AC4.2 Success:** E2E tests pass (`uv run test-e2e`)
- **120-annotation-split.AC4.3 Edge:** Test import paths updated but test logic unchanged

### 120-annotation-split.AC5: Documentation updated
- **120-annotation-split.AC5.1 Success:** `CLAUDE.md` project structure section lists the annotation package modules
- **120-annotation-split.AC5.2 Success:** `annotation-perf.md` Phase 1 references actual module names and post-CSS-Highlight-API functions
- **120-annotation-split.AC5.3 Success:** Follow-up issue filed for paste handler JS extraction

## Glossary

- **Annotation page**: The primary collaborative workspace page for highlighting and commenting on AI conversations. Located at `/annotation`.
- **CSS Highlight API**: Browser API for rendering text highlights without DOM manipulation. `CSS.highlights` registry uses `StaticRange` objects built from character offsets. Replaced char-span injection in #158.
- **CRDT (Conflict-free Replicated Data Type)**: Data structure that guarantees eventual consistency without coordination. Used via `pycrdt` for real-time collaborative editing of highlights, comments, and markdown notes.
- **Satellite modules**: Three smaller Python modules created alongside the annotation monolith during the three-tab UI work: `annotation_organise.py` (Tab 2), `annotation_respond.py` (Tab 3), `annotation_tags.py` (tag abstractions).
- **Scroll-sync card positioning**: JavaScript algorithm that moves annotation cards in the sidebar to track the vertical position of their associated highlights as the user scrolls the document.
- **Direct submodule imports**: Import pattern where external code references the specific module that owns a symbol (e.g., `from promptgrimoire.pages.annotation.highlights import _add_highlight`). Contrasts with re-exporting symbols from `__init__.py`.
- **Late imports**: `import` statements placed inside functions rather than at module top. Used to break circular dependencies. Avoided in this design via careful dependency ordering.
- **Copy protection**: Feature that blocks copy/cut/drag/print actions on student workspaces when enabled by instructors. Implemented via JavaScript event interception and CSS `@media print` rules.
- **NiceGUI**: Python web UI framework built on Vue and Quasar. Used for all PromptGrimoire UI.
- **Remote presence**: Feature showing cursor positions and text selections of other users in a shared workspace via WebSocket broadcast.
- **git mv**: Git command that moves/renames files while preserving history. Using `git mv` instead of `rm` + `add` ensures `git log --follow` shows the file's history across the rename.

## Architecture

Split the 3,041-line `src/promptgrimoire/pages/annotation.py` monolith into a `pages/annotation/` Python package with 9 authored modules plus 3 `git mv`'d satellite modules. Extract two self-contained JS blocks to static files. Use direct submodule imports (no re-exports from `__init__.py`).

### Module Structure

| Module | Responsibility | Key contents |
|--------|---------------|-------------|
| `__init__.py` | Core types, globals, route | `PageState`, `_RemotePresence`, `_RawJS`, `_render_js()`, `_workspace_presence`, `_background_tasks`, `annotation_page()` |
| `broadcast.py` | Multi-client sync, remote presence | `_setup_client_sync()`, `_get_user_color()`, `_update_user_count()`, remote cursor/selection push, disconnect cleanup, `_broadcast_yjs_update()` |
| `cards.py` | Annotation card UI | `_build_annotation_card()`, `_build_expandable_text()`, `_build_comments_section()`, `_refresh_annotation_cards()` |
| `content_form.py` | Content paste/upload form | `_render_add_content_form()`, `_detect_type_from_extension()`, `_get_file_preview()`, embedded paste handler JS |
| `css.py` | All CSS + tag toolbar | `_PAGE_CSS`, `_build_highlight_pseudo_css()`, `_setup_page_styles()`, `_get_tag_color()`, `_build_tag_toolbar()` |
| `document.py` | Document rendering + selection wiring | `_render_document_with_highlights()`, `_setup_selection_handlers()`, highlight init JS |
| `highlights.py` | Highlight CRUD, JSON, push-to-client | `_add_highlight()`, `_delete_highlight()`, `_warp_to_highlight()`, `_build_highlight_json()`, `_push_highlights_to_client()`, `_update_highlight_css()` |
| `pdf_export.py` | PDF export orchestration | `_handle_pdf_export()` |
| `workspace.py` | Workspace view, header, copy protection, tab init | `_render_workspace_view()`, `_render_workspace_header()`, `_setup_organise_drag()`, `_inject_copy_protection()`, `_parse_sort_end_args()`, `_initialise_respond_tab()`, copy protection CSS/HTML constants |
| `organise.py` | Tab 2 — git mv from `annotation_organise.py` | `render_organise_tab()`, `_build_highlight_card()`, `_build_tag_column()` |
| `respond.py` | Tab 3 — git mv from `annotation_respond.py` | `render_respond_tab()`, reference panel, CRDT markdown sync |
| `tags.py` | Tag abstractions — git mv from `annotation_tags.py` | `TagInfo`, `brief_tags_to_tag_info()` |

Two old modules consolidated into neighbours: `selection.py` (now thin after CSS Highlight API migration) merges into `document.py`; `tabs.py` (tab init, sort parsing) merges into `workspace.py`.

### JS Extraction

Two new static files for self-contained JS blocks with no Python-side data injection:

- `static/annotation-card-sync.js` (~120 lines) — scroll-sync card positioning engine. Exposes `setupCardPositioning(docContainer, sidebar, minGap)`. Depends on `charOffsetToRect()` and `walkTextNodes()` from `annotation-highlight.js`.
- `static/annotation-copy-protection.js` (~50 lines) — copy/cut/paste/drag/print blocking. Exposes `setupCopyProtection(protectedSelectors)`. Depends on Quasar.Notify (loaded by NiceGUI).

Small inline `_render_js()` calls (~20 instances, each 1–5 lines) that pass Python-side data to static functions stay in their respective Python modules.

The paste event handler (472 lines in `content_form.py`) stays inline — it requires restructuring to extract (tightly coupled to NiceGUI element IDs), which is deferred to a separate issue.

### Import Strategy

Direct submodule imports throughout. External code imports from the specific module that owns the symbol:

```python
from promptgrimoire.pages.annotation.highlights import _add_highlight
from promptgrimoire.pages.annotation.css import _get_tag_color
```

`__init__.py` exports only `annotation_page()` (for route registration) and `PageState` (for type hints). No re-exports, no late imports, no `PLC0415` ignores needed.

### Dependency Graph

```
__init__.py  (PageState, _RemotePresence, globals)
    ↑ imported by all modules

css.py  ← highlights.py, cards.py, document.py
highlights.py  ← cards.py, document.py, workspace.py
cards.py  ← document.py
broadcast.py  ← workspace.py
pdf_export.py  ← workspace.py
```

The graph is acyclic — no circular imports.

## Existing Patterns

### Prior Split (commit 3141eb5)

The 3141eb5 commit split `annotation.py` into an 11-module `pages/annotation/` package. It used late imports and `__init__.py` re-exports to break circular dependencies. This design follows the same package structure but improves on the import pattern (direct submodule imports eliminate circular dependency risk).

### Static JS Extraction (annotation-highlight.js)

The CSS Highlight API migration (#158) already extracted highlight rendering, text walking, selection detection, and remote presence JS to `static/annotation-highlight.js` (585 lines, 16 public functions). The two new static files follow the same pattern: self-contained JS modules loaded via `ui.add_head_html('<script src="...">')`.

### Satellite Module Pattern

Three satellite modules (`annotation_organise.py`, `annotation_respond.py`, `annotation_tags.py`) were created during the three-tab UI work as separate files alongside `annotation.py`. This design `git mv`s them into the package, preserving rename detection in git history.

### No Divergence

All patterns (package structure, static JS, satellite modules) already exist in the codebase. This design follows them without introducing new patterns.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Extract JS to Static Files

**Goal:** Move scroll-sync card positioning and copy protection JS from Python string constants to static JS files.

**Components:**
- `src/promptgrimoire/static/annotation-card-sync.js` — new file, extracted from scroll-sync block (annotation.py lines 1253–1365)
- `src/promptgrimoire/static/annotation-copy-protection.js` — new file, extracted from `_COPY_PROTECTION_JS` constant (annotation.py lines 2802–2848)
- `src/promptgrimoire/pages/annotation.py` — update call sites to load static files and invoke exposed functions

**Dependencies:** None (first phase)

**Done when:** `uv run test-all` passes. Manual smoke test confirms scroll-sync and copy protection work in browser. E2E tests (`uv run test-e2e`) pass.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Split Monolith into Package

**Goal:** Replace `annotation.py` with `pages/annotation/` package containing 9 modules.

**Components:**
- `src/promptgrimoire/pages/annotation/__init__.py` — core types, globals, route
- `src/promptgrimoire/pages/annotation/broadcast.py` — client sync, remote presence
- `src/promptgrimoire/pages/annotation/cards.py` — annotation card UI
- `src/promptgrimoire/pages/annotation/content_form.py` — paste/upload form
- `src/promptgrimoire/pages/annotation/css.py` — CSS constants, tag toolbar
- `src/promptgrimoire/pages/annotation/document.py` — document rendering, selection wiring
- `src/promptgrimoire/pages/annotation/highlights.py` — highlight CRUD, JSON, push-to-client
- `src/promptgrimoire/pages/annotation/pdf_export.py` — PDF export orchestration
- `src/promptgrimoire/pages/annotation/workspace.py` — workspace view, header, copy protection, tab init
- All test import paths updated to reference submodules directly

**Dependencies:** Phase 1 (JS extraction — changes the code being moved)

**Done when:** `annotation.py` no longer exists as a file. `uv run test-all` passes. Guard test verifies `annotation.py` is a directory, not a file.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: git mv Satellite Modules

**Goal:** Move satellite modules into the package, preserving git rename detection.

**Components:**
- `git mv src/promptgrimoire/pages/annotation_organise.py src/promptgrimoire/pages/annotation/organise.py`
- `git mv src/promptgrimoire/pages/annotation_respond.py src/promptgrimoire/pages/annotation/respond.py`
- `git mv src/promptgrimoire/pages/annotation_tags.py src/promptgrimoire/pages/annotation/tags.py`
- All import paths updated (`from promptgrimoire.pages.annotation_organise` → `from promptgrimoire.pages.annotation.organise`)

**Dependencies:** Phase 2 (package directory must exist)

**Done when:** `uv run test-all` passes. No `annotation_organise.py`, `annotation_respond.py`, or `annotation_tags.py` files remain at the `pages/` level.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Anti-Clobber Documentation Updates

**Goal:** Update project documentation so future sessions and implementation plans reference the package structure.

**Components:**
- `CLAUDE.md` — update project structure section to show `pages/annotation/` package with module listing
- `docs/design-plans/2026-02-10-annotation-perf-142.md` — update Phase 1 to reflect actual module structure (9 modules, current function names, post-CSS-Highlight-API); mark AC4 as addressed by this work
- File GitHub issue for paste handler JS extraction as follow-up

**Dependencies:** Phase 3 (all moves complete)

**Done when:** `CLAUDE.md` accurately reflects the package. `annotation-perf.md` Phase 1 reflects actual module names and current functions. Follow-up issue filed.
<!-- END_PHASE_4 -->

## Additional Considerations

**Paste handler JS extraction (follow-up issue):** The 472-line paste event handler in `content_form.py` is the largest remaining embedded JS block. Extracting it requires restructuring from a closure-based `<script>` tag to a parameterised function. This is deferred because (a) it changes runtime behaviour, requiring careful platform-specific testing across 6 chatbot exports, and (b) it can be done independently of the module split.

**`_PAGE_CSS` stays inline:** The 197-line CSS constant is tightly coupled to NiceGUI class names and would require a separate loading mechanism to extract. Not worth the complexity for this refactor.

**Implementation scoping:** This design has 4 phases. Well within the 8-phase limit.
