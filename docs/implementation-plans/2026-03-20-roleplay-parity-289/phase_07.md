# Roleplay Parity Implementation Plan — Phase 7: End-of-Conversation UI Flow

**Goal:** Wire marker detection to UI: lock input, auto-export, completion banner, early finish button.

**Architecture:** `_handle_send()` checks `StreamChunk.ended`, triggers completion flow (disable input, export conversation, show banner). "Finish Interview" button with confirmation dialog triggers the same flow. Refactored export logic returns workspace URL without navigating. `Session.ended` prevents further messages.

**Tech Stack:** NiceGUI (dialogs, banners), existing export pipeline

**Scope:** Phase 7 of 7 from original design

**Codebase verified:** 2026-03-20

---

## Acceptance Criteria Coverage

This phase implements and tests:

### roleplay-parity-289.AC3: End-of-conversation flow
- **roleplay-parity-289.AC3.4 Success:** On AI-triggered end: input disabled, conversation auto-exported to annotation workspace, completion banner with link displayed
- **roleplay-parity-289.AC3.5 Success:** "Finish Interview" button triggers confirmation dialog; on confirm: input locked, conversation exported, completion banner shown
- **roleplay-parity-289.AC3.6 Success:** Navigating back to `/roleplay` after conversation end starts a fresh session (no resumption of locked session)
- **roleplay-parity-289.AC3.7 Failure:** Sending a message after conversation end is rejected (input disabled, no API call made)

---

<!-- START_TASK_1 -->
### Task 1: Refactor export to return workspace URL without navigating

**Verifies:** roleplay-parity-289.AC3.4 (prerequisite)

**Files:**
- Modify: `src/promptgrimoire/pages/roleplay.py:211-250` (_handle_export and new helper)

**Implementation:**

Extract the workspace creation logic from `_handle_export()` into a new pure async function `_export_to_workspace()` that creates the workspace and returns its URL without navigating:

```python
async def _export_to_workspace(session: Session, user_id: UUID) -> str:
    """Export session to annotation workspace, return the URL path.

    Creates a loose workspace, adds the session HTML as an ai_conversation
    document, grants owner permission, and returns the annotation URL.
    """
    # ... workspace creation logic from _handle_export() ...
    return f"/annotation?workspace_id={workspace.id}"
```

Update `_handle_export()` to call `_export_to_workspace()` and then navigate (preserving existing behaviour for the explicit export button in the management drawer).

**Verification:**
Run: `uvx ty check`
Expected: No new type errors

**Commit:** `refactor: extract export-to-workspace helper for reuse in completion flow`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Wire StreamChunk.ended to completion flow in _handle_send()

**Verifies:** roleplay-parity-289.AC3.4, roleplay-parity-289.AC3.7

**Files:**
- Modify: `src/promptgrimoire/pages/roleplay.py:94-169` (_handle_send)

**Implementation:**

After Phase 4, `_handle_send()` iterates over `StreamChunk` objects. After the streaming loop completes, check if any chunk had `ended=True`:

```python
conversation_ended = False
async for chunk in client.stream_message_only(session):
    # ... existing streaming display logic using chunk.text ...
    if chunk.ended:
        conversation_ended = True

if conversation_ended:
    session.ended = True
    await _complete_conversation(state, input_field, send_button, finish_btn, chat_container)
```

The `_complete_conversation()` helper encapsulates the completion flow:
1. Disable `input_field` and `send_button` and `finish_btn`
2. Set `session.ended = True` in state
3. Call `_export_to_workspace()` to get the workspace URL
4. Show completion banner in `chat_container`:

```python
async def _complete_conversation(
    state: dict,
    input_field: Input,
    send_button,
    finish_btn,
    chat_container,
) -> None:
    input_field.disable()
    send_button.disable()
    finish_btn.disable()

    session = state["session"]
    # Get current user (guard against expired session)
    auth_user = app.storage.user.get("auth_user")
    if auth_user is None:
        ui.notify("Session expired. Please refresh the page.", type="negative")
        return
    workspace_url = await _export_to_workspace(session, auth_user.user_id)

    with chat_container:
        with ui.card().classes("w-full q-pa-md").props(
            'data-testid="roleplay-completion-banner"'
        ):
            ui.label("The activity is complete.").classes("text-h6")
            ui.link(
                "Review your conversation in the annotation workspace",
                workspace_url,
            ).props('data-testid="roleplay-workspace-link"')
```

Also add a guard at the top of `_handle_send()` to reject messages when `session.ended` is True:

```python
if state["session"] and state["session"].ended:
    return  # AC3.7: no messages after conversation end
```

**Testing:**

This is primarily UI wiring. The core detection logic is tested in Phase 4. Add minimal tests:
- roleplay-parity-289.AC3.7: When `session.ended` is True, `_handle_send()` returns immediately without making API calls

**Verification:**
Run: `uv run grimoire test run tests/unit/test_end_of_conversation.py`
Expected: All tests pass (including any new AC3.7 guard test)

**Complexity check:**
Run: `uv run complexipy src/promptgrimoire/pages/roleplay.py`
Expected: No functions exceed complexity 15

**Commit:** `feat: wire end-of-conversation detection to UI completion flow`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add "Finish Interview" button with confirmation dialog

**Verifies:** roleplay-parity-289.AC3.5, roleplay-parity-289.AC3.6

**Files:**
- Modify: `src/promptgrimoire/pages/roleplay.py` (input row area, add button and dialog)

**Implementation:**

Add a "Finish Interview" button in the input row, to the right of the send button:

```python
# In the input row (after send button)
finish_btn = ui.button(
    "Finish Interview", icon="stop"
).props(
    'outline data-testid="roleplay-finish-btn"'
).classes("ml-2")
```

Wire the button to an async handler that shows a confirmation dialog:

```python
async def _handle_finish(state, input_field, send_button, finish_btn, chat_container):
    # Show confirmation dialog using the established codebase pattern
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("End this interview?").classes("text-h6")
        ui.label(
            "This will lock the conversation and export it to your annotation workspace."
        )
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("flat")
            ui.button(
                "End Interview",
                on_click=lambda: dialog.submit(True),
            ).props('color=negative')

    dialog.open()
    confirmed = await dialog

    if confirmed:
        state["session"].ended = True
        await _complete_conversation(state, input_field, send_button, finish_btn, chat_container)
```

For AC3.6 (fresh session on re-navigate): This already works by design. Each page load calls `_auto_load_character()` which creates a fresh Session. The `ended` flag is on the in-memory Session object, which is discarded on page reload. No additional code needed.

Add `data-testid="roleplay-finish-btn"` to the button and `data-testid="roleplay-finish-dialog"` to the dialog card.

**Verification:**
Run: `uv run run.py` and test the finish button flow
Expected: Confirmation dialog appears; on confirm, input locks, export runs, banner shows

**Complexity check:**
Run: `uv run complexipy src/promptgrimoire/pages/roleplay.py`
Expected: No functions exceed complexity 15

**Commit:** `feat: add Finish Interview button with confirmation dialog and completion flow`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update user-facing documentation

**Verifies:** Documentation gate (implementation guidance requirement)

**Files:**
- Modify: `src/promptgrimoire/docs/scripts/using_promptgrimoire.py` — update roleplay section

**Implementation:**

Update the roleplay section of the user guide to document:
- Right drawer for management panel (how to access upload/export/settings)
- Character info panel (visible on wide viewports)
- "Finish Interview" button (how to end a conversation early)
- Completion flow (what happens when the activity ends)

**Verification:**
Run: `uv run grimoire docs build`
Expected: Documentation builds without errors

**Commit:** `docs: update user guide for roleplay page UI changes`
<!-- END_TASK_4 -->

---

## UAT Steps

1. [ ] Run tests: `uv run grimoire test run tests/unit/test_end_of_conversation.py`
2. [ ] Run: `uv run grimoire docs build` — verify docs build
3. [ ] Start the app: `uv run run.py`
4. [ ] Navigate to `/roleplay` and start a conversation
5. [ ] Verify "Finish Interview" button is visible in the input row
6. [ ] Click "Finish Interview" — verify confirmation dialog appears
7. [ ] Click "Cancel" — verify conversation continues normally
8. [ ] Click "Finish Interview" again, then "End Interview" — verify:
   - [ ] Input field becomes disabled
   - [ ] "The activity is complete" banner appears
   - [ ] Banner contains a clickable link to annotation workspace
9. [ ] Click the workspace link — verify it navigates to the annotation page
10. [ ] Navigate back to `/roleplay` — verify a fresh session starts (AC3.6)
11. [ ] Run: `uv run grimoire test all` — verify no regressions

## Evidence Required

- [ ] Test output showing all end-of-conversation tests green
- [ ] `uvx ty check` output clean
- [ ] `uv run complexipy src/promptgrimoire/pages/roleplay.py` output — no functions > 15
- [ ] `uv run grimoire docs build` succeeds
- [ ] Screenshot of completion banner with workspace link
- [ ] Screenshot of confirmation dialog
