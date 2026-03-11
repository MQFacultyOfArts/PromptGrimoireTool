# Annotation Page Architecture

*Last updated: 2026-03-11*

The annotation page (`pages/annotation/`) is a 25-module package split from a monolith.

## Layout

The annotation page uses `page_layout(footer=True)` to get a Quasar `q-footer` element. The tag toolbar renders inside this footer. Quasar's layout system handles fixed positioning and `q-page` padding automatically -- no manual `position: fixed` or `padding-bottom` hacks.

**Key elements:**
- `#tag-toolbar-wrapper` -- The `q-footer` element containing the tag toolbar (fixed bottom, z-index managed by Quasar)
- `#highlight-menu` -- Popup menu for highlight creation (z-index 110, above toolbar; flips above selection if it would overlap toolbar)
- `.annotations-sidebar` -- Card sidebar uses `position: relative`; cards are always visible (compact by default, expandable on click). `annotation-card-sync.js` caches card heights via `data-cached-height` so layout remains stable when cards are collapsed

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

## Broadcast & Presence (`broadcast.py`)

`_RemotePresence` (defined in `__init__.py`) carries two separate callbacks for broadcast events:

- **`callback`** -- Full annotation refresh. Called when a remote peer changes CRDT state (highlights, comments, tags). Triggers `refresh_annotations()` which calls `container.clear()` and rebuilds all annotation cards, incrementing the epoch counter.
- **`on_peer_left`** -- Lightweight user-count update. Called on CLIENT_DELETE (peer disconnection). Does NOT rebuild the DOM. CLIENT_DELETE changes zero CRDT state; a full rebuild would race with in-flight user interactions (fill + click), destroying input values and button handlers mid-action.

**Invariant:** `_handle_client_delete` in `broadcast.py` must call `invoke_peer_left()`, never `invoke_callback()`. Only CRDT-mutating events may trigger full rebuilds.

## Word Count Integration

Two new modules support word count limits in the annotation page:

- `word_count_badge.py` -- Pure functions. `format_word_count_badge(count, word_minimum, word_limit)` returns a `BadgeState` (text + CSS classes) for the header badge. Colour logic: red (over limit or below minimum), amber (approaching limit at 90%), neutral (within range).
- `word_count_enforcement.py` -- Re-export shim. The canonical implementation lives at `src/promptgrimoire/word_count_enforcement.py` (package root). This shim keeps annotation-package imports working. Only export-related code may import enforcement symbols (AC7 guard tests enforce this).

`PageState` carries four word count fields populated from `PlacementContext` during `_resolve_workspace_context()`: `word_minimum`, `word_limit`, `word_limit_enforcement`, and `word_count_badge` (the live `ui.label` element). The badge updates on every keystroke in the respond tab via `word_count()` from `src/promptgrimoire/word_count.py`.

## Card Layout (Compact/Expandable)

Annotation cards (`cards.py`) use a two-tier layout:

- **Compact header** (always visible, ~28px) -- colour dot, tag name, author initials (`_author_initials()`), paragraph reference, comment count badge, locate/delete buttons, and expand chevron. The entire header row is clickable to toggle expansion.
- **Detail section** (hidden by default) -- tag select dropdown (annotators only), full author name, editable paragraph reference, text preview, and comments with input.

`PageState.expanded_cards: set[str]` tracks which highlight IDs are currently expanded. This set survives annotation refreshes (card rebuilds) so expansion state is preserved across CRDT updates and broadcast refreshes.

`annotation-card-sync.js` positions cards absolutely based on their highlight's character offset in the document. It caches each card's `offsetHeight` into `data-cached-height` so that collapsed cards (which have `offsetHeight=0` when hidden) use their last-known height for layout calculations. Fallback height is 80px when no cache exists.

## Guard Tests

- `test_annotation_package_structure.py` -- Prevents regression: package directory exists, monolith `.py` file absent, all 20 modules present, no satellite files at `pages/` level, no imports from old paths
- `test_annotation_js_extraction.py` -- Prevents re-introduction of JS string constants: static JS files exist with expected functions, `_COPY_PROTECTION_JS` constant absent from Python source
- `test_css_audit.py` -- Quasar regression guard: asserts computed CSS properties on toolbar, buttons, highlight menu, and sidebar; verifies toolbar is at viewport bottom and content is not obscured
