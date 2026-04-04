# Annotation Page Architecture

*Last updated: 2026-04-04*

The annotation page (`pages/annotation/`) is a 31-module package split from a monolith.

## Deferred Background Loading (#377)

The annotation page uses a skeleton+spinner pattern. The page handler returns immediately with a loading spinner; all DB work and UI rendering happens in a `background_tasks.create()` coroutine.

**Load sequence:**
1. `annotation_page()` in `__init__.py` renders a skeleton container with `ui.spinner("dots")` and injects the Milkdown bundle `<script>` tag
2. `_load_workspace_content()` in `workspace.py` runs as a background task:
   - Calls `resolve_annotation_context()` (single DB session for workspace, ACL, placement, tags)
   - Clears the spinner container and renders full workspace UI via `with client:`
   - Calls `_update_page_title()` to set browser tab title and visible header via JS
3. Error states (not found, no access) render inside the same container

**Key functions:**
- `resolve_annotation_context(workspace_id, user_id)` in `db/workspaces.py` -- consolidates 5+ DB calls (workspace fetch, ACL resolution, placement context, privileged user IDs, tags/tag groups) into a single `AsyncSession`. Returns `AnnotationContext` frozen dataclass.
- `_load_workspace_content(workspace_id, client, container, footer)` -- replaces the former `_render_workspace_view()`. Runs inside `background_tasks.create()`.
- `_update_page_title(title)` -- sets `document.title` and updates `[data-testid="page-header-title"]` via `ui.run_javascript()`.

**Invariant:** The Milkdown `<script>` tag must be in the page skeleton (`__init__.py`), not in the background task. The Respond tab's `_createMilkdownEditor` call needs it in the DOM before the deferred content renders.

## Layout

The annotation page uses `page_layout(footer=True)` to get a Quasar `q-footer` element. The tag toolbar renders inside this footer. Quasar's layout system handles fixed positioning and `q-page` padding automatically -- no manual `position: fixed` or `padding-bottom` hacks.

**Key elements:**
- `#tag-toolbar-wrapper` -- The `q-footer` element containing the tag toolbar (fixed bottom, z-index managed by Quasar)
- `#highlight-menu` -- Popup menu for highlight creation (z-index 110, above toolbar; flips above selection if it would overlap toolbar)
- `.annotations-sidebar` -- Vue annotation sidebar (`AnnotationSidebar` in `sidebar.py`, rendered by `annotationsidebar.js`). Cards use `position: absolute` with scroll-synced positioning driven by the Vue component's `positionCards()`. Compact by default, expandable on click. Card heights are cached in `data-cached-height` for stable layout when cards are collapsed

`page_layout()` yields the footer element (or `None`). Pages manage their own content padding -- the layout no longer wraps content in a `q-pa-lg` div.

## Toolbar Button Rendering

Toolbar action buttons (Create, Manage) switch between expanded and compact styles based on tag count. The threshold is `_COMPACT_THRESHOLD = 5` in `css.py`.

- **Below 5 tags:** Buttons show text labels ("Create New Tag", "Manage Tags") alongside icons.
- **5+ tags:** Buttons revert to compact icon-only style to save toolbar space.
- Both modes always have tooltips (hover text describing the action).
- `_render_action_buttons()` in `css.py` implements the rendering via a data-driven loop.

The toolbar rebuilds dynamically when tags are created or deleted (via `_refresh_tag_state()`), so the compact/expanded transition is live. Tag state is sourced from the CRDT `tags` Map during live sessions; DB tag rows are the source of truth at page load and for operations that predate CRDT hydration.

### Tag Modules

Tag management is split across four modules:

- `tags.py` -- Tag state helpers and exports shared by other annotation submodules
- `tag_management.py` -- Tag management dialog (create, edit, delete, reorder, Done button with save spinner)
- `tag_management_save.py` -- Debounced save logic for tag/group edits (dual-write to DB + CRDT)
- `tag_import.py` -- Import tags from other accessible workspaces (available to all users)
- `tag_quick_create.py` -- Inline tag creation from the highlight menu

## Floating Highlight Menu

The floating highlight menu (`#highlight-menu`) appears on text selection. It adapts to the workspace's tag state:

- **Tags exist + creation permitted:** Tag buttons plus a "+ New" button appended after all tag groups.
- **No tags + creation permitted:** Only a "+ New" button (no "No tags available" message).
- **No tags + creation NOT permitted:** "No tags available" label with tooltip "Ask your instructor".

The `on_add_click` callback is threaded through `_build_highlight_menu()` -> `_populate_highlight_menu()` and stored on `PageState._highlight_menu_on_add_click` so `_refresh_tag_state()` can pass it when rebuilding the menu after tag creation.

## Import Ordering in `__init__.py`

Definition-before-import ordering is **critical** in `__init__.py`. The sequence is:

1. Stdlib/third-party imports
2. Define `PageState`, `_RemotePresence`, `_RawJS`, `_render_js()`, and module-level registries
3. Import from submodules (`workspace.py` etc.) -- types they need already exist
4. Define `annotation_page()` -- uses imported functions

Do not reorder. Types must be defined before submodule imports to resolve circular dependencies (e.g. `workspace.py` imports `PageState` from `__init__`). No `PLC0415` lint suppression is used; the ordering makes late imports unnecessary.

## Tab System (`tab_bar.py`, `tab_state.py`, `workspace.py`)

Multi-document workspaces use a three-tab bar (Source, Respond, Organise) with deferred rendering per document.

- `tab_bar.py` -- Tab creation (`build_tabs`), tab change handler factory (`_make_tab_change_handler`), deferred tab panel rendering (`_build_tab_panels`), and SortableJS drag-and-drop wiring for the Organise tab (`_setup_organise_drag`). Extracted from `workspace.py` in Phase 6 to separate tab mechanics from workspace assembly.
- `tab_state.py` -- `DocumentTabState` dataclass holding per-document UI state: `document_id`, `tab`/`panel` element references, `document_container`/`cards_container`, `rendered` flag. Created for Phase 7 multi-document support so each source tab tracks its own rendering state independently.
- `workspace.py` -- Top-level workspace entry point (`_load_workspace_content`, formerly `_render_workspace_view`). Runs as a background task for deferred loading. Receives pre-resolved `AnnotationContext` from `db/workspaces.py`, renders document containers, and wires tag management callbacks. Tab management was extracted to `tab_bar.py`; workspace now imports `build_tabs`, `_make_tab_change_handler`, `_setup_organise_drag`, and `_build_tab_panels` from there.

## Broadcast & Presence (`broadcast.py`)

`_RemotePresence` (defined in `__init__.py`) carries two separate callbacks for broadcast events:

- **`callback`** -- Full annotation refresh. Called when a remote peer changes CRDT state (highlights, comments, tags). Triggers `refresh_annotations()` which updates the Vue sidebar's `items` prop via `sidebar.refresh_from_state()`. The Vue component's `watch` on `items` increments `window.__annotationCardsEpoch`.
- **`on_peer_left`** -- Lightweight user-count update. Called on CLIENT_DELETE (peer disconnection). Does NOT rebuild the DOM. CLIENT_DELETE changes zero CRDT state; a full rebuild would race with in-flight user interactions (fill + click), destroying input values and button handlers mid-action.

**Invariant:** `_handle_client_delete` in `broadcast.py` must call `invoke_peer_left()`, never `invoke_callback()`. Only CRDT-mutating events may trigger full rebuilds.

## Word Count Integration

Two new modules support word count limits in the annotation page:

- `word_count_badge.py` -- Pure functions. `format_word_count_badge(count, word_minimum, word_limit)` returns a `BadgeState` (text + CSS classes) for the header badge. Colour logic: red (over limit or below minimum), amber (approaching limit at 90%), neutral (within range).
- `word_count_enforcement.py` -- Re-export shim. The canonical implementation lives at `src/promptgrimoire/word_count_enforcement.py` (package root). This shim keeps annotation-package imports working. Only export-related code may import enforcement symbols (AC7 guard tests enforce this).

`PageState` carries four word count fields populated from `PlacementContext` during workspace content loading: `word_minimum`, `word_limit`, `word_limit_enforcement`, and `word_count_badge` (the live `ui.label` element). The badge updates on every keystroke in the respond tab via `word_count()` from `src/promptgrimoire/word_count.py`.

## Vue Annotation Sidebar (Compact/Expandable)

The annotation sidebar is a Vue component (`annotationsidebar.js`) wrapped by `AnnotationSidebar` in `sidebar.py`. All card rendering, positioning, expand/collapse, hover highlights, and scroll sync are handled client-side in Vue — no server round-trips for UI interactions.

**Two-tier card layout:**

- **Compact header** (always visible, ~20px) -- colour dot, tag name, author initials, paragraph reference, comment count badge (Quasar `bg-blue-1` pill), locate/expand/delete `q-btn` buttons. The entire header row is clickable to toggle expansion.
- **Detail section** (hidden by default, lazy-built on first expand via `v-if`/`v-show`) -- Quasar `q-select` for tag picker (annotators only), full author name, editable paragraph reference, text preview, comments with `bg-grey-2` rounded styling, and comment input.

**Server-side state:** `PageState.expanded_cards: set[str]` tracks which highlight IDs are currently expanded. This set is passed to the Vue component as the `expanded_ids` prop and survives annotation refreshes so expansion state is preserved across CRDT updates and broadcast refreshes.

**Event flow:** Vue emits events (`toggle_expand`, `change_tag`, `submit_comment`, `delete_comment`, `delete_highlight`, `edit_para_ref`, `locate_highlight`) which are handled by module-level functions in `document.py` (`_on_toggle_expand`, `_on_change_tag`, etc.). These functions receive the current `PageState` and the event payload, perform CRDT mutations, and trigger persist+broadcast.

**Positioning:** The Vue component's `positionCards()` function (ported from `annotation-card-sync.js`) positions cards absolutely based on their highlight's character offset. Cards cache `offsetHeight` into `data-cached-height` so collapsed cards use their last-known height. Fallback height is 80px. Scroll listener with `requestAnimationFrame` throttling drives repositioning.

**Epoch synchronisation:** The Vue `watch` on `items` (with `flush: 'post'`) increments `window.__annotationCardsEpoch` and the per-document `window.__cardEpochs` map after each prop update. E2E tests use `wait_for_function` on the epoch to synchronise after CRDT mutations.

`annotation-card-sync.js` now contains only the toolbar height `ResizeObserver` — all card-related JS was removed.

## Content Form Architecture (File Upload / Paste)

The content form is split across four modules:

- `content_form.py` -- Orchestration: renders the upload/paste form, delegates to handlers
- `paste_handler.py` -- Paste submission processing: runs content through the input pipeline, persists as WorkspaceDocument
- `paste_script.py` -- Client-side JavaScript for paste interception (clipboard event handling, QEditor integration)
- `upload_handler.py` -- File upload detection and processing: content type inference from extension, DOCX/PDF conversion, paragraph numbering detection

`PageState` carries two fields added for this feature:
- `refresh_documents: Callable | None` -- callback to refresh the document container after edit-mode save
- `footer: Any | None` -- page-level Quasar footer for tag toolbar (hidden on non-Annotate tabs)

## Guard Tests

- `test_annotation_package_structure.py` -- Prevents regression: package directory exists, monolith `.py` file absent, all expected modules present, no satellite files at `pages/` level, no imports from old paths
- `test_annotation_js_extraction.py` -- Prevents re-introduction of JS string constants: static JS files exist with expected functions, `_COPY_PROTECTION_JS` constant absent from Python source
- `test_css_audit.py` -- Quasar regression guard: asserts computed CSS properties on toolbar, buttons, highlight menu, and sidebar; verifies toolbar is at viewport bottom and content is not obscured
