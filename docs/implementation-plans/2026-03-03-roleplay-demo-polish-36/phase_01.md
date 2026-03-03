# Roleplay Demo Polish — Phase 1: Static Assets and CSS

**Goal:** Copy image assets from SillyTavern installation and create ST-inspired stylesheet

**Architecture:** Three images (background, AI avatar, user avatar) placed in `src/promptgrimoire/static/roleplay/`. One new CSS file for dark theme styling. Also bundle the Becky Bennett character card JSON for auto-loading.

**Tech Stack:** Static files (PNG, CSS, JSON), NiceGUI static file serving (already configured at `/static`)

**Scope:** 3 phases from original design (phase 1 of 3)

**Codebase verified:** 2026-03-03

---

## Acceptance Criteria Coverage

This phase is infrastructure — verified operationally (files exist, app loads without errors).

**Verifies:** None (infrastructure phase — DoD item verification happens in Phase 2)

---

<!-- START_TASK_1 -->
### Task 1: Copy image assets to static/roleplay/

**Files:**
- Create: `src/promptgrimoire/static/roleplay/background.png`
- Create: `src/promptgrimoire/static/roleplay/becky-bennett.png`
- Create: `src/promptgrimoire/static/roleplay/user-default.png`

**Step 1: Create directory and copy files**

```bash
mkdir -p src/promptgrimoire/static/roleplay

cp "/home/brian/people/Amanda/ST-2025-10-24-TORTS/SillyTavern/data/default-user/backgrounds/pjqhsrifzuynmcmq9cpn.png" \
   src/promptgrimoire/static/roleplay/background.png

cp "/home/brian/people/Amanda/ST-2025-10-24-TORTS/SillyTavern/data/default-user/characters/Becky Bennett.png" \
   src/promptgrimoire/static/roleplay/becky-bennett.png

cp "/home/brian/people/Amanda/ST-2025-10-24-TORTS/SillyTavern/data/default-user/User Avatars/user-default.png" \
   src/promptgrimoire/static/roleplay/user-default.png
```

**Step 2: Verify files exist**

```bash
ls -la src/promptgrimoire/static/roleplay/
```

Expected: Three PNG files (background ~1.1M, becky-bennett ~680K, user-default ~600K).

**Step 3: Commit**

```bash
git add src/promptgrimoire/static/roleplay/
git commit -m "chore: add roleplay page image assets (background, avatars)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Bundle Becky Bennett character card JSON

**Files:**
- Create: `src/promptgrimoire/static/roleplay/becky-bennett.json`

The character card at `Becky Bennett (2).json` in the project root needs to be copied into the static directory so it can be loaded programmatically without a file upload.

**Step 1: Copy the character card**

```bash
cp "Becky Bennett (2).json" src/promptgrimoire/static/roleplay/becky-bennett.json
```

**Step 2: Verify**

```bash
uv run python -c "
from promptgrimoire.parsers.sillytavern import parse_character_card
from pathlib import Path
char, lore = parse_character_card(Path('src/promptgrimoire/static/roleplay/becky-bennett.json'))
print(f'Character: {char.name}, Lorebook entries: {len(lore)}')
"
```

Expected: `Character: Becky Bennett, Lorebook entries: N` (where N > 0).

**Step 3: Commit**

```bash
git add src/promptgrimoire/static/roleplay/becky-bennett.json
git commit -m "chore: bundle Becky Bennett character card for auto-loading"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create ST-inspired roleplay stylesheet

**Files:**
- Create: `src/promptgrimoire/static/roleplay.css`

**Step 1: Create the CSS file**

Create `src/promptgrimoire/static/roleplay.css` with ST-inspired styling. The design specifies these colour values derived from SillyTavern's default theme:

| Property | Value |
|----------|-------|
| Text colour | `rgb(220, 220, 210)` |
| Italics/em | `rgb(145, 145, 145)` |
| Quote colour | `rgb(225, 138, 36)` |
| Chat tint | `rgba(23, 23, 23, 0.85)` |
| User msg tint | `rgba(0, 0, 0, 0.3)` |
| AI msg tint | `rgba(60, 60, 60, 0.3)` |
| Font | `"Noto Sans", sans-serif` at 15px |
| Avatar | 50px round with shadow |

The CSS must target:
- `.roleplay-bg` — page background (full viewport, cover, fixed)
- `.roleplay-chat` — chat scroll area (semi-transparent dark tint, backdrop blur)
- `.q-message` — Quasar chat message overrides (text colour, font)
- `.q-message-sent` vs `.q-message-received` — user vs AI bubble tinting
- `.q-message em, .q-message i` — italic colour override
- `.q-message blockquote` — orange left border, dark background
- `.q-avatar img` — round avatar sizing
- `.roleplay-upload` — upload card styling for readability on dark background

**Step 2: Verify CSS loads**

```bash
cat src/promptgrimoire/static/roleplay.css | head -5
```

Expected: CSS file exists with role play theme rules.

**Step 3: Commit**

```bash
git add src/promptgrimoire/static/roleplay.css
git commit -m "feat: add ST-inspired roleplay CSS theme"
```

## UAT Steps (Phase 1)

Phase 1 is infrastructure — all verification is operational:

1. [ ] Confirm all image assets exist: `ls -la src/promptgrimoire/static/roleplay/`
2. [ ] Confirm character card parses: `uv run python -c "from promptgrimoire.parsers.sillytavern import parse_character_card; from pathlib import Path; c, l = parse_character_card(Path('src/promptgrimoire/static/roleplay/becky-bennett.json')); print(f'{c.name}: {len(l)} lorebook entries')"`
3. [ ] Confirm CSS file exists and is non-empty: `wc -l src/promptgrimoire/static/roleplay.css`
4. [ ] Confirm app starts without errors: `uv run python -m promptgrimoire` (Ctrl+C after startup)

## Evidence Required
- [ ] All 4 verification commands succeed
<!-- END_TASK_3 -->
