# Annotation Page Architecture

*Last updated: 2026-03-01*

The annotation page (`pages/annotation/`) is a 20-module package split from a monolith.

## Layout

The annotation page uses `page_layout(footer=True)` to get a Quasar `q-footer` element. The tag toolbar renders inside this footer. Quasar's layout system handles fixed positioning and `q-page` padding automatically -- no manual `position: fixed` or `padding-bottom` hacks.

**Key elements:**
- `#tag-toolbar-wrapper` -- The `q-footer` element containing the tag toolbar (fixed bottom, z-index managed by Quasar)
- `#highlight-menu` -- Popup menu for highlight creation (z-index 110, above toolbar; flips above selection if it would overlap toolbar)
- `.annotations-sidebar` -- Card sidebar uses `position: relative`; cards hide when their highlight scrolls off-screen

`page_layout()` yields the footer element (or `None`). Pages manage their own content padding -- the layout no longer wraps content in a `q-pa-lg` div.

## Toolbar Button Rendering

Toolbar action buttons (Create, Manage) switch between expanded and compact styles based on tag count. The threshold is `_COMPACT_THRESHOLD = 5` in `css.py`.

- **Below 5 tags:** Buttons show text labels ("Create New Tag", "Manage Tags") alongside icons.
- **5+ tags:** Buttons revert to compact icon-only style to save toolbar space.
- Both modes always have tooltips (hover text describing the action).
- `_render_action_buttons()` in `css.py` implements the rendering via a data-driven loop.

The toolbar rebuilds dynamically when tags are created or deleted (via `_refresh_tag_state()`), so the compact/expanded transition is live.

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

## Guard Tests

- `test_annotation_package_structure.py` -- Prevents regression: package directory exists, monolith `.py` file absent, all 20 modules present, no satellite files at `pages/` level, no imports from old paths
- `test_annotation_js_extraction.py` -- Prevents re-introduction of JS string constants: static JS files exist with expected functions, `_COPY_PROTECTION_JS` constant absent from Python source
- `test_css_audit.py` -- Quasar regression guard: asserts computed CSS properties on toolbar, buttons, highlight menu, and sidebar; verifies toolbar is at viewport bottom and content is not obscured
