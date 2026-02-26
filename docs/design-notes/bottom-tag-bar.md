# Design Notes: Bottom-Anchored Tag Bar

*Created: 2026-02-27*

## Summary

Move the annotation tag toolbar from fixed-top to fixed-bottom, and normalise the annotation page to use the standard page chrome (navigator title bar) instead of its own inline title.

## Current State

- Tag toolbar (`css.py:_build_tag_toolbar`) renders as `position: fixed; top: 0; left: 0; right: 0; z-index: 100;` with box-shadow.
- Annotation page builds its own `ui.label("Annotation Workspace")` title inline (`__init__.py:306`).
- Header row (save status, user count badge, export PDF, placement chip, copy protection, sharing controls) renders inline below the title (`workspace.py:531-540`).
- Tag toolbar only appears on the Annotate tab — Organise and Respond do not show it.

## Proposed Changes

### 1. Tag toolbar anchors to bottom

- `_build_tag_toolbar` CSS: `top: 0` → `bottom: 0`, box-shadow flips to top edge.
- Document scroll area and annotation sidebar need bottom padding/margin equal to toolbar height so content isn't hidden behind the bar.
- No change needed for Organise/Respond tabs (toolbar not rendered there).

### 2. Standard page chrome for title

- Remove inline `ui.label("Annotation Workspace")` from `annotation_page()`.
- The `@page_route` decorator already registers `title="Annotation Workspace"` — the navigator should display it in the top bar.
- The workspace UUID label (`ui.label(f"Workspace: {workspace_id}")`) can also be removed or moved into the header row as a subtle element.

### 3. Header row stays near the top

- Save status, user count, export, placement chip, sharing controls remain in a row near the top of the content area, below the standard navigator bar.
- No longer competing with the tag toolbar for top-of-viewport space.

## Interaction Benefit

Bottom-anchored tag bar matches the annotation workflow better: user selects text in the document (middle of screen), then eyes drop to the tag bar at the bottom to pick a tag. Current flow requires eyes to jump to the top and back down.

## Files to Touch

| File | Change |
|------|--------|
| `pages/annotation/css.py` | Toolbar CSS: `top: 0` → `bottom: 0`, flip box-shadow |
| `pages/annotation/css.py` | Add bottom padding to `.doc-container` and `.annotations-sidebar` |
| `pages/annotation/__init__.py` | Remove inline title label |
| `pages/annotation/workspace.py` | Remove workspace UUID label, adjust header row positioning |
| `pages/annotation/document.py` | Verify no top-padding hacks that compensate for the old toolbar position |

## Open Questions

- Exact toolbar height for bottom padding calc — currently dynamic based on tag count and wrapping. May need a CSS variable or a fixed min-height.
- Whether the workspace UUID should appear anywhere (useful for debugging/support, possibly a tooltip or footer element).
