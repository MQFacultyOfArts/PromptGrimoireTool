# Bottom-Anchored Tag Bar Design

**GitHub Issue:** Loosely related to #196

## Summary

The annotation page currently has a fixed tag toolbar pinned to the top of the viewport, a pattern inherited from an earlier layout that has since become visually crowded. This design moves that toolbar to the bottom of the viewport — `top: 0` becomes `bottom: 0`, the box-shadow flips direction, and layout padding dynamically tracks the toolbar's actual rendered height via a ResizeObserver (handling tag wrapping gracefully). Two pieces of inline page chrome that became redundant once the navigator title bar was introduced — an "Annotation Workspace" heading and a workspace UUID label — are removed in the same pass.

The third concern is the floating highlight menu, which appears when a user selects text and must avoid being obscured by the bottom toolbar. The menu already positions itself relative to the text selection; the change adds a boundary check so it flips from below-selection to above-selection when the bottom toolbar would cover it, and a z-index bump ensures it always renders on top if positions do overlap. A Playwright CSS audit test is added as a regression guard, verifying computed styles for key elements — to catch any future Quasar framework overrides silently undoing the changes.

## Definition of Done

1. **Tag toolbar anchored to bottom of viewport** — CSS flipped from `top: 0` to `bottom: 0`, box-shadow direction reversed, layout padding dynamically tracks actual toolbar height via ResizeObserver, JS boundaries updated to reflect new layout.
2. **Inline title and UUID label removed** — annotation page uses the standard navigator title bar instead of its own inline `ui.label("Annotation Workspace")`; workspace UUID label removed (already visible in the URL).
3. **Highlight menu positioned near text selection** — floating highlight menu appears adjacent to the selected text range (above or below the selection) rather than at a fixed viewport position, and stays clear of the bottom toolbar.

**Out of scope:** Moving header row controls to the nav drawer; changes to Organise/Respond tabs.

## Acceptance Criteria

### bottom-tag-bar.AC1: Tag toolbar anchored to bottom
- **bottom-tag-bar.AC1.1 Success:** Toolbar renders at `position: fixed; bottom: 0` with full viewport width
- **bottom-tag-bar.AC1.2 Success:** Box-shadow appears above the toolbar (upward shadow), not below
- **bottom-tag-bar.AC1.3 Success:** Document content below the fold is not hidden behind the toolbar (padding-bottom dynamically matches toolbar height)
- **bottom-tag-bar.AC1.4 Success:** Toolbar with many tags wrapping to multiple rows — padding-bottom adjusts automatically via ResizeObserver, no content obscured

### bottom-tag-bar.AC2: Inline title and UUID removed
- **bottom-tag-bar.AC2.1 Success:** No `text-2xl` "Annotation Workspace" label visible in page content area
- **bottom-tag-bar.AC2.2 Success:** No workspace UUID text visible on the page; navigator bar shows "Annotation Workspace" as page title
- **bottom-tag-bar.AC2.3 Edge:** Header row (save status, user count, export, sharing) still renders correctly without the title above it

### bottom-tag-bar.AC3: Highlight menu positioned near selection
- **bottom-tag-bar.AC3.1 Success:** Selecting text in upper/middle viewport shows highlight menu below the selection (default position)
- **bottom-tag-bar.AC3.2 Success:** Menu left edge aligns with the end of the selection
- **bottom-tag-bar.AC3.3 Success:** Selecting text near viewport bottom shows highlight menu above the selection (flipped), using actual toolbar height for threshold
- **bottom-tag-bar.AC3.4 Failure:** Menu never renders behind or overlapping the bottom toolbar, even when toolbar wraps to multiple rows
- **bottom-tag-bar.AC3.5 Success:** Highlight menu z-index (110) renders above toolbar (100) if positions ever overlap
- **bottom-tag-bar.AC3.6 Edge:** Selecting text at very top of viewport — menu stays below selection even if that's the overlap zone (z-index handles it)

### bottom-tag-bar.AC4: Compact button padding fix
- **bottom-tag-bar.AC4.1 Success:** Compact buttons render with `padding: 0px 6px` (not Quasar's `2px 8px`)

### bottom-tag-bar.AC5: E2E CSS audit
- **bottom-tag-bar.AC5.1 Success:** Playwright test verifies computed CSS for toolbar, layout wrapper, sidebar, compact buttons, and annotation cards
- **bottom-tag-bar.AC5.2 Failure:** Test fails if any checked property doesn't match expected value (catches future Quasar overrides)

## Glossary

- **Quasar**: The Vue component library that NiceGUI builds on. Ships its own CSS for components like buttons (`.q-btn`), which can override application-level styles unless higher-specificity selectors or `!important` are used.
- **Tailwind z-class (`z-[110]`)**: NiceGUI uses Tailwind CSS utility classes. `z-[110]` is an arbitrary-value variant setting `z-index: 110` directly.
- **`charOffsetToRect()`**: Function in `annotation-highlight.js` that converts a text selection's character offset to a viewport rectangle, used to place the highlight menu adjacent to selected text.
- **Highlight menu**: Floating action panel that appears when a user selects text in the annotation view, offering tag application options.
- **`window._toolbarHeight`**: Global variable set by ResizeObserver on the toolbar element. Replaces the previous hardcoded `hH = 60` constant. Read by card sync (bottom boundary) and highlight menu (flip threshold).
- **ResizeObserver**: Browser API that fires a callback when an element's size changes. Used here to track the toolbar's actual rendered height, which varies when tags wrap to multiple rows.
- **Page chrome**: UI elements that frame content but carry no page-specific information — here, the inline title and UUID label that duplicate information in the navigator bar and URL.
- **Navigator title bar**: NiceGUI's standard per-page title in the application shell header. The annotation page sets this to "Annotation Workspace" via the `@page_route` decorator.

## Architecture

Move the annotation tag toolbar from viewport-top to viewport-bottom, clean up redundant page chrome, and add bottom-bar avoidance to the highlight menu positioning. Fix a pre-existing Quasar specificity override on compact button padding.

All changes are CSS/JS repositioning within the existing annotation page. No new components, no data model changes, no new dependencies.

**Components affected:**

| Component | File | Change |
|-----------|------|--------|
| Tag toolbar wrapper | `pages/annotation/css.py` (`_build_tag_toolbar`, line 370) | `top: 0` → `bottom: 0`, box-shadow flipped |
| Layout wrapper padding | `pages/annotation/document.py` (line 225) | `padding-top: 60px` → dynamic `padding-bottom` set by ResizeObserver |
| Toolbar ResizeObserver | `static/annotation-card-sync.js` (new) | Observes toolbar height, updates layout padding + card sync boundary + exposes height for highlight menu |
| Card sync boundary | `static/annotation-card-sync.js` (line 63) | Top boundary `hH=0` (no top bar); bottom boundary `vB = window.innerHeight - toolbarHeight` (dynamic) |
| Inline title | `pages/annotation/__init__.py` (lines 305-306) | Remove `ui.label("Annotation Workspace")` |
| Workspace UUID label | `pages/annotation/workspace.py` (line 531) | Remove `ui.label(f"Workspace: {workspace_id}")` |
| Highlight menu positioning | `static/annotation-highlight.js` (lines 338-342) | Add above/below flip using dynamic toolbar height for threshold |
| Highlight menu z-index | `pages/annotation/document.py` (`_build_highlight_menu`, line 165) | `z-50` → `z-[110]` |
| Compact button specificity | `pages/annotation/css.py` (`.compact-btn`, line 178) | Selector becomes `.q-btn.compact-btn` to beat Quasar's `.q-btn` |

**Data flow:** No change. Tag selection, highlight creation, CRDT sync, and annotation card positioning all work the same — only viewport coordinates shift.

## Existing Patterns

Investigation confirmed all annotation page styles use a consistent pattern: Python-side `.style()` for inline CSS on raw `ui.element("div")` wrappers, and `ui.add_css()` for stylesheet rules in `css.py`. Quasar components (buttons, cards) require `!important` and higher-specificity selectors to override framework defaults.

The highlight menu already uses selection-relative positioning via `charOffsetToRect()` in `annotation-highlight.js` — it's not at a fixed viewport position as the design notes initially assumed. The fix is adding a boundary guard, not rewriting the positioning system.

The 60px toolbar height was previously hardcoded in two places (Python CSS and JS). Proleptic challenge identified that this breaks when tags wrap to multiple rows — content becomes permanently obscured at the bottom of the document. The design now uses a ResizeObserver on the toolbar element that dynamically updates the layout padding, card sync boundary, and highlight menu threshold. This replaces all hardcoded 60px constants with a single source of truth: the toolbar's actual rendered height.

**CSS audit findings (pre-existing, not introduced by this design):**
- `.remote-cursor` and `.remote-cursor-label` in `css.py` are dead code (Phase 5 remote presence, not yet implemented)
- `static/annotations.css` contains three unused rules (`.annotation-highlight`, `.selectable-content`)
- `[data-speaker]` and `[data-thinking]` selectors in `css.py` target attributes no HTML import pipeline adds

These are noted for awareness but cleaning them is out of scope for this design.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Toolbar CSS, ResizeObserver, and Layout Padding

**Goal:** Move the tag toolbar to the bottom of the viewport with dynamic height tracking.

**Components:**
- Toolbar wrapper CSS in `pages/annotation/css.py` — flip `top: 0` to `bottom: 0`, reverse box-shadow from `0 2px 4px` to `0 -2px 4px`
- Layout wrapper in `pages/annotation/document.py` — remove hardcoded `padding-top: 60px`, set initial `padding-bottom: 0` (ResizeObserver will set the real value)
- ResizeObserver in `static/annotation-card-sync.js` — observe the toolbar element, on resize: update layout wrapper `padding-bottom`, store current toolbar height in `window._toolbarHeight` for card sync and highlight menu to read
- Compact button specificity in `pages/annotation/css.py` — change `.compact-btn` selector to `.q-btn.compact-btn`

**Dependencies:** None

**Done when:** Tag toolbar renders at bottom of viewport with upward shadow. Layout padding dynamically matches toolbar height (including when tags wrap). Compact buttons render at correct `0px 6px` padding. Covers `bottom-tag-bar.AC1.1`, `bottom-tag-bar.AC1.2`, `bottom-tag-bar.AC1.3`, `bottom-tag-bar.AC1.4`, `bottom-tag-bar.AC4.1`.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Page Chrome Cleanup

**Goal:** Remove redundant inline title and UUID label.

**Components:**
- Inline title removal in `pages/annotation/__init__.py` — remove `ui.label("Annotation Workspace")` and its containing column wrapper
- UUID label removal in `pages/annotation/workspace.py` — remove `ui.label(f"Workspace: {workspace_id}")`

**Dependencies:** None (functionally independent of toolbar position; recommended to implement after Phase 1 for coherent review)

**Done when:** Annotation page has no inline title. Navigator bar displays "Annotation Workspace" as the page title. No workspace UUID visible on page. Covers `bottom-tag-bar.AC2.1`, `bottom-tag-bar.AC2.2`.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Card Sync Boundary Update

**Goal:** Update JavaScript annotation card visibility to use dynamic toolbar height from ResizeObserver.

**Components:**
- `static/annotation-card-sync.js` — change top boundary from `hH=60` to `hH=0` (no top obstruction), change bottom boundary `vB` from `window.innerHeight` to `window.innerHeight - window._toolbarHeight` (reads actual toolbar height set by ResizeObserver in Phase 1)

**Dependencies:** Phase 1 (ResizeObserver populates `window._toolbarHeight`)

**Done when:** Annotation cards near the bottom of the viewport hide behind the toolbar boundary, including when toolbar wraps to multiple rows. Cards at the top of the viewport are visible without a dead zone. Covers `bottom-tag-bar.AC3.1`, `bottom-tag-bar.AC3.2`.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Highlight Menu Bottom-Bar Avoidance

**Goal:** Add above/below flip logic to highlight menu positioning using dynamic toolbar height, and bump z-index.

**Components:**
- Positioning logic in `static/annotation-highlight.js` — after calculating `top = endRect.bottom + 8`, check if `top + menuHeight > window.innerHeight - (window._toolbarHeight || 60)`. If so, flip to `top = endRect.top - menuHeight - 8`. Reads actual toolbar height from ResizeObserver (Phase 1), falls back to 60px if not yet set.
- Z-index in `pages/annotation/document.py` (`_build_highlight_menu`) — change `z-50` to `z-[110]` so the menu renders above the toolbar (z-100) when they overlap.

**Dependencies:** Phase 1 (ResizeObserver populates `window._toolbarHeight`)

**Done when:** Highlight menu appears below selection by default. When selection is near viewport bottom, menu flips to above selection using actual toolbar height. Menu never overlaps the bottom toolbar even when toolbar wraps. Covers `bottom-tag-bar.AC3.3`, `bottom-tag-bar.AC3.4`, `bottom-tag-bar.AC3.5`.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: E2E CSS Audit Test

**Goal:** Playwright test combining structural CSS assertions (Quasar regression guard) with behavioural assertions (content not obscured).

**Components:**
- New E2E test in `tests/e2e/` with two test functions:
  - **Structural assertions** — `expect(locator).to_have_css()` for properties Quasar is known to override: toolbar `position: fixed`, `bottom: 0px`; compact button padding; sidebar `position: relative`; highlight menu z-index.
  - **Behavioural assertions** — verify toolbar is visible at bottom of viewport; document content's last element is not obscured by toolbar (bounding rect check); no inline title or UUID label present.

**Dependencies:** Phases 1-4 (all CSS changes in place)

**Done when:** E2E test passes. Structural checks catch Quasar overrides. Behavioural checks catch layout regressions without being coupled to specific pixel values. Covers `bottom-tag-bar.AC5.1`, `bottom-tag-bar.AC5.2`.
<!-- END_PHASE_5 -->

## Additional Considerations

**Highlight menu edge case — selection at very top of viewport:** If the user selects text near the very top and the menu would go above the viewport when flipped, it should fall back to below-selection positioning even if that overlaps the toolbar (the z-index bump ensures it renders on top). This is a rare edge case — the menu should prefer above-selection only when below-selection would overlap the toolbar.

**Organise and Respond tabs:** The tag toolbar does not render on these tabs. The layout padding change in `document.py` only affects the Annotate tab's document view. No changes needed for other tabs.

**Dead CSS noted during audit:** `.remote-cursor`, `.remote-cursor-label`, `annotations.css` rules, `[data-speaker]`/`[data-thinking]` selectors are pre-existing dead code. Not addressed in this design — could be a separate cleanup task.
