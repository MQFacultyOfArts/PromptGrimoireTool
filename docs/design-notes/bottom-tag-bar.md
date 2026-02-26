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

## Highlight Menu and Selection Interaction

The floating highlight menu (`document.py:_build_highlight_menu`) is a `fixed z-50` card that appears when the user selects text and vanishes when selection is cleared. With the tag bar moving to `bottom: 0` at `z-index: 100`, these interact:

- **Overlap risk**: The highlight menu could render behind or overlap the bottom tag bar. May need to constrain the highlight menu's vertical position so it stays above the toolbar, or switch to positioning it near the selection rather than fixed.
- **Click guard**: `document.py:86-88` prevents selection-clearing on tag toolbar clicks via `e.target.closest('[data-testid="tag-toolbar"]')`. This is selector-based so it survives the move. No change needed.
- **Scroll-sync**: `setupCardPositioning('doc-container', 'annotations-container', 8)` positions annotation cards relative to their highlights. The available vertical space changes — the sidebar's effective bottom boundary is now `toolbar height` pixels higher. The JS function may need a bottom-offset parameter.

## Layout Wrapper Padding

`document.py:223-226` has an explicit `padding-top: 60px` on the two-column layout wrapper to compensate for the fixed top toolbar. This must become `padding-bottom` instead (and the value may change if toolbar height differs at the bottom).

## Files to Touch

| File | Change |
|------|--------|
| `pages/annotation/css.py` | Toolbar CSS: `top: 0` → `bottom: 0`, flip box-shadow |
| `pages/annotation/css.py` | Add bottom padding to `.doc-container` and `.annotations-sidebar` |
| `pages/annotation/__init__.py` | Remove inline title label |
| `pages/annotation/workspace.py` | Remove workspace UUID label, adjust header row positioning |
| `pages/annotation/document.py` | `padding-top: 60px` → `padding-bottom`; review highlight menu z-index interaction |
| `static/annotation-card-sync.js` | `setupCardPositioning` may need bottom-offset param for sidebar boundary |

## Open Questions

- Exact toolbar height for bottom padding calc — currently dynamic based on tag count and wrapping. May need a CSS variable or a fixed min-height.
- Whether the workspace UUID should appear anywhere (useful for debugging/support, possibly a tooltip or footer element).
- Highlight menu positioning strategy: keep it `fixed` but constrain to above the toolbar, or switch to positioning near the text selection (which is more conventional but harder to implement).
