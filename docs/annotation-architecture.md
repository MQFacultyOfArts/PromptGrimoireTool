# Annotation Page Architecture

*Last updated: 2026-02-15*

The annotation page (`pages/annotation/`) is a 12-module package split from a monolith.

## Import Ordering in `__init__.py`

Definition-before-import ordering is **critical** in `__init__.py`. The sequence is:

1. Stdlib/third-party imports
2. Define `PageState`, `_RemotePresence`, `_RawJS`, `_render_js()`, and module-level registries
3. Import from submodules (`workspace.py` etc.) -- types they need already exist
4. Define `annotation_page()` -- uses imported functions

Do not reorder. Types must be defined before submodule imports to resolve circular dependencies (e.g. `workspace.py` imports `PageState` from `__init__`). No `PLC0415` lint suppression is used; the ordering makes late imports unnecessary.

## Guard Tests

- `test_annotation_package_structure.py` -- Prevents regression: package directory exists, monolith `.py` file absent, all 12 modules present, no satellite files at `pages/` level, no imports from old paths
- `test_annotation_js_extraction.py` -- Prevents re-introduction of JS string constants: static JS files exist with expected functions, `_COPY_PROTECTION_JS` constant absent from Python source
