# Roleplay Parity Implementation Plan — Phase 6: Character Info Panel

**Goal:** Add left-side character info panel with portrait, name, and responsive collapse behaviour.

**Architecture:** NiceGUI `ui.column()` as a flex sibling of the chat card. On wide viewports (>1024px), displays as a fixed-width left sidebar. On narrow viewports, hides via CSS media query; avatar + name remain in the chat card header. Uses existing hardcoded avatar static asset (`/static/roleplay/becky-bennett.png`).

**Tech Stack:** NiceGUI, CSS flexbox + media queries

**Scope:** Phase 6 of 7 from original design

**Codebase verified:** 2026-03-20

---

## Acceptance Criteria Coverage

This phase implements and tests:

### roleplay-parity-289.AC1: Responsive viewport layout
- **roleplay-parity-289.AC1.4 Success:** Character info panel (portrait, name) displays as a left sidebar on viewports wider than 1024px
- **roleplay-parity-289.AC1.5 Success:** Character info panel collapses or hides on viewports narrower than 1024px; avatar + name remain visible in header

---

<!-- START_TASK_1 -->
### Task 1: Add character info panel as flex sibling sidebar

**Verifies:** roleplay-parity-289.AC1.4

**Files:**
- Modify: `src/promptgrimoire/pages/roleplay.py` — add character panel column before chat card
- Modify: `src/promptgrimoire/static/roleplay.css` — add character panel styles

**Implementation:**

In `roleplay.py`, restructure the page layout (after Phase 5's changes) so the main content area is a horizontal flex row containing two children:

1. **Character info panel** (left, fixed width ~280px):
```python
with ui.column().classes("roleplay-char-panel").props(
    'data-testid="roleplay-char-panel"'
):
    ui.image(_AI_AVATAR).classes("roleplay-char-portrait")
    ui.label(character.name).classes("text-h5 roleplay-char-name")
    # Scenario blurb hidden by default (design: "default to hidden")
    # Note: Hardcoded _AI_AVATAR is intentional for the Becky Bennett MVP.
    # Dynamic avatar extraction from chara_card_v3 is deferred until a card
    # with an embedded avatar is deployed.
```

2. **Chat card** (right, flex: 1) — the existing chat card structure from Phase 5.

The horizontal flex container wraps both:
```python
with ui.row().classes("roleplay-main-row w-full").style("flex: 1; min-height: 0;"):
    # character panel (left)
    # chat card (right, flex: 1)
```

In `roleplay.css`, add styles for the character panel:
```css
.roleplay-char-panel {
    width: 280px;
    min-width: 280px;
    padding: 24px 16px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
}

.roleplay-char-portrait {
    width: 200px;
    height: 200px;
    border-radius: 50%;
    object-fit: cover;
    border: 3px solid rgba(220, 220, 210, 0.3);
}

.roleplay-char-name {
    color: rgb(220, 220, 210);
    text-align: center;
}
```

Add `data-testid="roleplay-char-panel"` to the panel and `data-testid="roleplay-char-portrait"` to the image.

**Verification:**
Run: `uv run run.py` and view on a viewport wider than 1024px
Expected: Character panel with portrait and name visible as left sidebar

**Commit:** `feat: add character info panel sidebar for wide viewports`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Responsive collapse for narrow viewports

**Verifies:** roleplay-parity-289.AC1.5

**Files:**
- Modify: `src/promptgrimoire/static/roleplay.css` — add media query for narrow viewports
- Modify: `src/promptgrimoire/pages/roleplay.py` — ensure avatar + name visible in chat card header on narrow viewports

**Implementation:**

In `roleplay.css`, add a media query that hides the character panel on narrow viewports:
```css
@media (max-width: 1024px) {
    .roleplay-char-panel {
        display: none !important;
    }
}
```

In `roleplay.py`, the chat card header (character name label area) should always show a compact avatar + name. This is already partially in place — the `char_name_label` exists at the top of the chat card. Enhance it to include a small avatar that's visible on all viewports:

```python
# Inside chat card, at the top (before scroll area)
with ui.row().classes("items-center gap-3").props(
    'data-testid="roleplay-chat-header"'
):
    ui.avatar(
        _AI_AVATAR, size="40px"
    ).classes("roleplay-chat-header-avatar")
    ui.label(character.name).classes("text-h5").style(
        "color: rgb(220, 220, 210);"
    )
```

On wide viewports, the chat header avatar is redundant with the sidebar portrait. You can either hide it on wide viewports via CSS or keep it visible (simpler). Keeping it visible is the simpler approach and doesn't harm UX.

**Verification:**
Run: `uv run run.py` and resize browser below 1024px width
Expected: Character panel disappears; avatar and name remain visible in chat card header

**Complexity check:**
Run: `uv run complexipy src/promptgrimoire/pages/roleplay.py`
Expected: No functions exceed complexity 15

**Commit:** `feat: add responsive collapse for character panel on narrow viewports`
<!-- END_TASK_2 -->

---

## UAT Steps

1. [ ] Start the app: `uv run run.py`
2. [ ] Open `/roleplay` in a browser wider than 1024px
3. [ ] Verify character panel visible on left with Becky Bennett portrait and name
4. [ ] Narrow the browser below 1024px — verify character panel disappears
5. [ ] Verify avatar and name remain visible in the chat card header area
6. [ ] Widen the browser back above 1024px — verify character panel reappears
7. [ ] Send a message — verify conversation works normally

## Evidence Required

- [ ] `uvx ty check` output clean
- [ ] `uv run complexipy src/promptgrimoire/pages/roleplay.py` output — no functions > 15
- [ ] Screenshot at >1024px showing character panel sidebar
- [ ] Screenshot at <1024px showing panel hidden, header avatar visible
