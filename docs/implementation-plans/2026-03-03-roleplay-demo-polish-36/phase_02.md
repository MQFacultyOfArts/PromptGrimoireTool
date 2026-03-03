# Roleplay Demo Polish — Phase 2: Roleplay Page Visual Integration

**Goal:** Apply background image, avatars, dark theme CSS, and auto-load Becky Bennett character card

**Architecture:** Modify `roleplay.py` to link the new CSS, pass avatar URLs to `ui.chat_message()`, apply background class to page container, and auto-load the bundled Becky Bennett JSON on page load (skipping the upload step for demo).

**Tech Stack:** NiceGUI (`ui.chat_message`, `ui.add_css`, `ui.add_head_html`), Quasar CSS overrides

**Scope:** 3 phases from original design (phase 2 of 3)

**Codebase verified:** 2026-03-03

**Testing reference:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/roleplay-36/docs/testing.md`

---

## Acceptance Criteria Coverage

This phase implements and tests:

### roleplay-demo-polish-36.AC1: Visual assets display correctly
- **roleplay-demo-polish-36.AC1.1 Success:** Background image covers the full roleplay page viewport with no tiling or distortion
- **roleplay-demo-polish-36.AC1.2 Success:** User messages display kangaroo lawyer avatar as 50px round image
- **roleplay-demo-polish-36.AC1.3 Success:** AI messages display Becky Bennett portrait as 50px round image

### roleplay-demo-polish-36.AC2: ST-inspired dark theme renders correctly
- **roleplay-demo-polish-36.AC2.1 Success:** Chat area has semi-transparent dark tint over the background image
- **roleplay-demo-polish-36.AC2.2 Success:** Message text renders in ivory/warm white, italics in grey, blockquotes with orange left border
- **roleplay-demo-polish-36.AC2.3 Edge:** Upload card (pre-session) remains readable against the dark background

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Write failing tests for avatar parameter (TDD: Red)

**Verifies:** roleplay-demo-polish-36.AC1.2, roleplay-demo-polish-36.AC1.3

**Files:**
- Create: `tests/unit/test_roleplay_visual.py`

**Testing:**

Write tests first (TDD). Tests should verify:
- roleplay-demo-polish-36.AC1.2: `_create_chat_message` passes user avatar URL when `sent=True`
- roleplay-demo-polish-36.AC1.3: `_create_chat_message` passes AI avatar URL when `sent=False`
- Avatar parameter defaults to None for backward compatibility

Since `_create_chat_message` calls NiceGUI UI components which require a running client context, the test approach should mock `ui.chat_message` and `ui.markdown` to verify the correct parameters are passed. Follow the existing mock patterns from `tests/unit/test_auth_client.py`.

**Verification:**

Run: `uv run pytest tests/unit/test_roleplay_visual.py -v`
Expected: Tests FAIL (avatar parameter does not exist yet — this is the Red step)

**Commit:** `test: add failing tests for roleplay avatar integration (TDD red)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement avatar parameter to pass tests (TDD: Green)

**Verifies:** roleplay-demo-polish-36.AC1.2, roleplay-demo-polish-36.AC1.3

**Files:**
- Modify: `src/promptgrimoire/pages/roleplay.py:54-58` (`_create_chat_message` function)

**Implementation:**

Add an `avatar` parameter to `_create_chat_message()` and pass it through to `ui.chat_message()`. NiceGUI's `ui.chat_message()` accepts `avatar` as a URL string.

Current signature:
```python
def _create_chat_message(content: str, name: str, sent: bool) -> None:
```

New signature:
```python
def _create_chat_message(content: str, name: str, sent: bool, *, avatar: str | None = None) -> None:
```

Pass `avatar=avatar` to `ui.chat_message()`.

Update all call sites:
- `_render_messages()` (line 65) — determine avatar from `turn.is_user`
- `_handle_send()` user message (line 90) — pass user avatar
- `_handle_send()` thinking indicator (line 95) — pass AI avatar
- `_handle_send()` final rendered message (line 123) — pass AI avatar

Avatar URLs (module-level constants):
- User: `_USER_AVATAR = "/static/roleplay/user-default.png"`
- AI: `_AI_AVATAR = "/static/roleplay/becky-bennett.png"`

Static files are already served at `/static` by `__init__.py:87`, so `/static/roleplay/*.png` resolves automatically.

**Verification:**

Run: `uv run pytest tests/unit/test_roleplay_visual.py -v`
Expected: All tests now PASS (TDD green)

**Commit:** `feat: add avatar support to roleplay chat messages`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Apply background and dark theme CSS to roleplay page

**Verifies:** roleplay-demo-polish-36.AC1.1, roleplay-demo-polish-36.AC2.1, roleplay-demo-polish-36.AC2.2, roleplay-demo-polish-36.AC2.3

**Files:**
- Modify: `src/promptgrimoire/pages/roleplay.py:170-293` (`roleplay_page()` function)

**Implementation:**

In `roleplay_page()`, after `with page_layout("Roleplay"):` (line 189):

1. Link the roleplay CSS stylesheet via `ui.add_head_html('<link rel="stylesheet" href="/static/roleplay.css">')` or `ui.add_css()` with the file content.

2. Apply background class to the page body/container. NiceGUI pages can add CSS classes to the page body using `ui.query('body').classes('roleplay-bg')` or wrapping content in a div with the background class.

3. Add `data-testid` attributes to key elements for E2E testability:
   - Upload card: `data-testid="roleplay-upload-card"`
   - Chat card: `data-testid="roleplay-chat-card"`
   - Chat scroll area: `data-testid="roleplay-chat-area"`
   - Send button: `data-testid="roleplay-send-btn"`
   - Message input: `data-testid="roleplay-message-input"`

4. Add `.roleplay-chat` class to the chat scroll area for the dark tint styling.

5. Add `.roleplay-upload` class to the upload card for readability on dark background.

**Verification:**

Run: `uv run python -m promptgrimoire` and navigate to `/roleplay`
Expected: Page shows office background, dark-themed chat area, upload card is readable

**Commit:** `feat: apply ST-inspired dark theme to roleplay page`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Auto-load Becky Bennett character card on page open

**Design deviation (justified):** The design's Phase 2 scopes visual integration only. Auto-loading the character card was requested by the project owner during brainstorming as a demo convenience — students should not have to manually upload a JSON file during a live tutorial. The upload card is preserved (collapsed in an expansion panel) so users can still load a different character card if needed. This does not break existing functionality.

**Files:**
- Modify: `src/promptgrimoire/pages/roleplay.py` (`roleplay_page()` function)

**Implementation:**

Auto-load the bundled character card on page open, preserving upload as a fallback:

1. At module level, define the path to the bundled card:
   ```python
   _BECKY_CARD_PATH = Path(__file__).parent.parent / "static" / "roleplay" / "becky-bennett.json"
   ```

2. In `roleplay_page()`, after the page layout setup, call `parse_character_card(_BECKY_CARD_PATH)` directly (same as the upload handler does).

3. Call `_setup_session()` with the parsed character, lorebook entries, and user name from `_get_default_user_name()`.

4. Set the chat card visible. Move the upload card into a collapsed `ui.expansion("Load Different Character")` panel so it remains accessible but does not occupy space.

5. Render initial messages (the character's `first_mes` if present).

6. The upload handler continues to work — if a user uploads a different card, it replaces the current session.

**Verification:**

Run: `uv run python -m promptgrimoire` and navigate to `/roleplay`
Expected: Becky Bennett loads automatically with first message displayed. "Load Different Character" expansion available for alternative cards.

**Commit:** `feat: auto-load Becky Bennett character card on roleplay page`
<!-- END_TASK_4 -->

## UAT Steps (Phase 2)

1. [ ] Start the app: `uv run python -m promptgrimoire`
2. [ ] Navigate to: `/roleplay`
3. [ ] Verify: Office background image covers full viewport
4. [ ] Verify: Becky Bennett loads automatically with first message displayed (no upload needed)
5. [ ] Verify: Chat area has dark semi-transparent tint over background
6. [ ] Verify: "Load Different Character" expansion panel is present for loading alternative cards
7. [ ] Send a test message and verify: user message shows kangaroo avatar, AI response shows Becky portrait
8. [ ] Verify: Message text is ivory/warm white, italics are grey

## Evidence Required
- [ ] Screenshot showing roleplay page with background, dark theme, avatars, and auto-loaded character
- [ ] Test output showing all unit tests green
