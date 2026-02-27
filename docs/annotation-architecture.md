# Annotation Page Architecture

*Last updated: 2026-02-27*

The annotation page (`pages/annotation/`) is a 17-module package split from a monolith.

## Layout

The annotation page uses `page_layout(footer=True)` to get a Quasar `q-footer` element. The tag toolbar renders inside this footer. Quasar's layout system handles fixed positioning and `q-page` padding automatically -- no manual `position: fixed` or `padding-bottom` hacks.

**Key elements:**
- `#tag-toolbar-wrapper` -- The `q-footer` element containing the tag toolbar (fixed bottom, z-index managed by Quasar)
- `#highlight-menu` -- Popup menu for highlight creation (z-index 110, above toolbar; flips above selection if it would overlap toolbar)
- `.annotations-sidebar` -- Card sidebar uses `position: relative`; cards hide when their highlight scrolls off-screen

`page_layout()` yields the footer element (or `None`). Pages manage their own content padding -- the layout no longer wraps content in a `q-pa-lg` div.

## Import Ordering in `__init__.py`

Definition-before-import ordering is **critical** in `__init__.py`. The sequence is:

1. Stdlib/third-party imports
2. Define `PageState`, `_RemotePresence`, `_RawJS`, `_render_js()`, and module-level registries
3. Import from submodules (`workspace.py` etc.) -- types they need already exist
4. Define `annotation_page()` -- uses imported functions

Do not reorder. Types must be defined before submodule imports to resolve circular dependencies (e.g. `workspace.py` imports `PageState` from `__init__`). No `PLC0415` lint suppression is used; the ordering makes late imports unnecessary.

## Guard Tests

- `test_annotation_package_structure.py` -- Prevents regression: package directory exists, monolith `.py` file absent, all 17 modules present, no satellite files at `pages/` level, no imports from old paths
- `test_annotation_js_extraction.py` -- Prevents re-introduction of JS string constants: static JS files exist with expected functions, `_COPY_PROTECTION_JS` constant absent from Python source
- `test_css_audit.py` -- Quasar regression guard: asserts computed CSS properties on toolbar, buttons, highlight menu, and sidebar; verifies toolbar is at viewport bottom and content is not obscured
