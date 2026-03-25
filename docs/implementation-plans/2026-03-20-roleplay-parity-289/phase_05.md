# Roleplay Parity Implementation Plan — Phase 5: Responsive Layout — Flex Chat Card

**Goal:** Replace hardcoded `60vh` scroll area with flexbox layout; move management panel to right drawer.

**Architecture:** CSS flexbox chain from page body through roleplay-card to scroll area. Management panel migrates from inline `ui.expansion()` to `ui.right_drawer()` with header toggle button. Zero vertical footprint when closed.

**Tech Stack:** NiceGUI (Quasar/Vue), CSS flexbox

**Scope:** Phase 5 of 7 from original design

**Codebase verified:** 2026-03-20

---

## Acceptance Criteria Coverage

This phase implements and tests:

### roleplay-parity-289.AC1: Responsive viewport layout
- **roleplay-parity-289.AC1.1 Success:** Chat scroll area and input row are both visible on a 600px-tall viewport without page-level scrolling
- **roleplay-parity-289.AC1.2 Success:** Scroll area dynamically resizes when browser window height changes (no hardcoded `vh` values)
- **roleplay-parity-289.AC1.3 Success:** Management panel (upload/export/settings) opens from a right drawer with zero vertical footprint when closed

---

<!-- START_TASK_1 -->
### Task 1: Replace hardcoded 60vh with CSS flexbox layout

**Verifies:** roleplay-parity-289.AC1.1, roleplay-parity-289.AC1.2

**Files:**
- Modify: `src/promptgrimoire/static/roleplay.css:1-147`
- Modify: `src/promptgrimoire/pages/roleplay.py` (remove inline `height: 60vh` style, add flex classes)

**Implementation:**

In `roleplay.css`:

1. Change `.roleplay-bg` width from `100vw` to `100%` (line 8) to prevent horizontal scrollbar overflow.

2. Add flex properties to `.roleplay-card`:
```css
.roleplay-card {
    /* existing styles preserved */
    display: flex !important;
    flex-direction: column !important;
    flex: 1 !important;
    min-height: 0 !important;
    overflow: hidden !important;
}
```

3. Add flex properties to `.roleplay-chat` (the scroll area):
```css
.roleplay-chat {
    /* existing styles preserved */
    flex: 1 !important;
    min-height: 0 !important;
}
```

In `roleplay.py`:

1. Remove the inline `style("height: 60vh;")` from the scroll area (line 505).

2. The roleplay-column container needs to be a flex column filling available viewport height. Add flex styling to the outer column:
```python
# The main column should fill available height
ui.column().classes("roleplay-column").style(
    "max-width: 1000px; width: 100%; padding: 0 16px; "
    "flex: 1; min-height: 0; display: flex; flex-direction: column;"
)
```

3. Ensure the page content area fills viewport height. NiceGUI's `page_layout()` provides the header; the content area below needs to be a flex container. Add CSS for the main content area:
```css
.q-page {
    display: flex !important;
    flex-direction: column !important;
}
```

The full flex chain is: `.q-page` (flex column) → `.roleplay-column` (flex: 1) → `.roleplay-card` (flex: 1, flex column) → `.roleplay-chat` scroll area (flex: 1).

**Verification:**
Run: `uv run run.py` and resize browser to 600px height
Expected: Chat area and input row both visible without page scrolling; scroll area shrinks dynamically

**Commit:** `feat: replace hardcoded 60vh with flexbox layout for responsive chat`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Move management panel to right drawer

**Verifies:** roleplay-parity-289.AC1.3

**Files:**
- Modify: `src/promptgrimoire/pages/roleplay.py:434-477` (management panel) and header area
- Modify: `src/promptgrimoire/static/roleplay.css` (drawer-specific styles if needed)

**Implementation:**

In `roleplay.py`:

1. Create a `ui.right_drawer(value=False)` before the main column, following the left drawer pattern from `layout.py:116`. The drawer should be initially closed:

```python
with ui.right_drawer(value=False).props(
    'data-testid="roleplay-management-drawer"'
) as management_drawer:
    # Move all management panel content here (export button, user name input, upload, etc.)
    # Remove the ui.expansion() wrapper — drawer replaces it
    ...
```

2. Add a toggle button to the header. The roleplay page currently injects content after `page_layout()`. Add a settings button to the header bar that toggles the right drawer:

```python
# In header area or after page_layout setup
settings_btn = ui.button(icon="settings").props(
    'flat round data-testid="roleplay-settings-btn"'
)
settings_btn.on("click", management_drawer.toggle)
```

3. Remove the `ui.expansion("Management", icon="settings")` wrapper (lines 435-477). Move its children (export button, separator, user name input, file upload, info label) directly into the right drawer.

4. Keep all `data-testid` attributes on the moved elements. Add `data-testid="roleplay-management-drawer"` to the drawer itself and `data-testid="roleplay-settings-btn"` to the toggle button.

5. Update the `widgets` dict — replace `widgets["upload_expansion"]` with `widgets["management_drawer"]`. Check all consumers of `widgets["upload_expansion"]` (grep the file for `upload_expansion`) and update them to use the new key.

**Testing:**

This is a UI layout change. No unit tests needed (infrastructure task). Verify operationally:
- Management panel not visible on page load
- Settings button in header toggles the right drawer
- All management controls (export, upload, user name) present in drawer
- Closing drawer leaves zero vertical footprint

**Verification:**
Run: `uv run run.py` and verify drawer behaviour
Expected: Right drawer opens/closes with settings button; all management controls accessible

**Commit:** `feat: move management panel to right drawer for zero vertical footprint`

**Complexity check:**
Run: `uv run complexipy src/promptgrimoire/pages/roleplay.py`
Expected: No functions exceed complexity 15
<!-- END_TASK_2 -->

---

## UAT Steps

1. [ ] Start the app: `uv run run.py`
2. [ ] Navigate to `/roleplay`
3. [ ] Resize browser to 600px height — verify chat area and input row both visible without scrolling
4. [ ] Resize browser to full height — verify scroll area expands dynamically
5. [ ] Verify management panel is NOT visible inline on the page
6. [ ] Click the settings/gear button in the header — verify right drawer opens with upload, export, user name controls
7. [ ] Close the right drawer — verify zero vertical footprint
8. [ ] Send a message — verify conversation works normally with new layout

## Evidence Required

- [ ] `uvx ty check` output clean
- [ ] `uv run complexipy src/promptgrimoire/pages/roleplay.py` output — no functions > 15
- [ ] Screenshot at 600px viewport height showing chat + input visible
- [ ] Screenshot of right drawer open with management controls
