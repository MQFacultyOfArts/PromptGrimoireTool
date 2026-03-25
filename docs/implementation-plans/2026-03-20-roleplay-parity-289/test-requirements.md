# Roleplay Parity — Test Requirements

**Design:** `docs/design-plans/2026-03-20-roleplay-parity-289.md`

Every acceptance criterion maps to either an automated test or documented human verification.

---

## roleplay-parity-289.AC1: Responsive viewport layout

### roleplay-parity-289.AC1.1

**AC text:** Chat scroll area and input row are both visible on a 600px-tall viewport without page-level scrolling.

**Test type:** e2e

**Test file:** `tests/e2e/test_roleplay_layout.py`

**Description:** Set Playwright viewport to 1280x600. Navigate to `/roleplay`. Assert the input row (`data-testid="roleplay-input"`) and scroll area (`data-testid="roleplay-chat"`) are both within the visible viewport (`bounding_box().y + height <= 600`). Assert no page-level vertical scrollbar exists (document scrollHeight equals clientHeight).

---

### roleplay-parity-289.AC1.2

**AC text:** Scroll area dynamically resizes when browser window height changes (no hardcoded `vh` values).

**Test type:** e2e + unit (CSS audit)

**Test file:** `tests/e2e/test_roleplay_layout.py`, `tests/unit/test_roleplay_css_no_vh.py`

**Description:**

1. *E2E:* Set viewport to 1280x900, capture the scroll area bounding box height. Resize viewport to 1280x600, capture again. Assert the scroll area height decreased proportionally (not fixed).
2. *Unit (CSS audit):* Read `src/promptgrimoire/static/roleplay.css` as text. Assert no occurrence of a `vh` value on any `height` or `min-height` property (regex: `(min-)?height\s*:\s*\d+vh`). This prevents regression to hardcoded viewport heights.

---

### roleplay-parity-289.AC1.3

**AC text:** Management panel (upload/export/settings) opens from a right drawer with zero vertical footprint when closed.

**Test type:** e2e

**Test file:** `tests/e2e/test_roleplay_layout.py`

**Description:** Navigate to `/roleplay`. Assert the management drawer (`data-testid="roleplay-management-drawer"`) is not visible on initial load. Click the settings button (`data-testid="roleplay-settings-btn"`). Assert the drawer becomes visible and contains the export button and file upload controls. Close the drawer. Assert the chat card height is unchanged (zero vertical footprint from the drawer).

---

### roleplay-parity-289.AC1.4

**AC text:** Character info panel (portrait, name) displays as a left sidebar on viewports wider than 1024px.

**Test type:** e2e

**Test file:** `tests/e2e/test_roleplay_layout.py`

**Description:** Set viewport to 1280x800. Navigate to `/roleplay`. Assert the character panel (`data-testid="roleplay-char-panel"`) is visible. Assert it contains an image element (`data-testid="roleplay-char-portrait"`) and a text element with the character name. Assert the panel's bounding box is to the left of the chat card.

---

### roleplay-parity-289.AC1.5

**AC text:** Character info panel collapses or hides on viewports narrower than 1024px; avatar + name remain visible in header.

**Test type:** e2e

**Test file:** `tests/e2e/test_roleplay_layout.py`

**Description:** Set viewport to 800x800. Navigate to `/roleplay`. Assert the character panel (`data-testid="roleplay-char-panel"`) is not visible. Assert the chat header (`data-testid="roleplay-chat-header"`) contains an avatar image and the character name text.

---

## roleplay-parity-289.AC2: Prompt construction parity

### roleplay-parity-289.AC2.1

**AC text:** Parser extracts `mes_example`, `post_history_instructions`, and lorebook entry `position` from chara_card_v3 JSON.

**Test type:** unit

**Test file:** `tests/unit/test_sillytavern_parser.py`

**Description:** Six test cases as specified in Phase 1:

1. Becky Bennett fixture: `mes_example` and `post_history_instructions` are empty strings (real card has empty values).
2. Becky Bennett fixture: all 5 lorebook entries have `position == "before_char"` (numeric 0 maps to string).
3. Synthetic card (`tmp_path`): non-empty `mes_example` value extracted correctly.
4. Synthetic card (`tmp_path`): non-empty `post_history_instructions` value extracted correctly.
5. Synthetic card (`tmp_path`): lorebook entry with `extensions.position: 1` produces `position == "after_char"`.
6. Synthetic card (`tmp_path`): lorebook entry with no `extensions.position` defaults to `"before_char"`.

---

### roleplay-parity-289.AC2.2

**AC text:** Missing or empty card fields produce empty strings (no errors); lorebook entries without `extensions.position` default to `before_char`.

**Test type:** unit

**Test file:** `tests/unit/test_sillytavern_parser.py`

**Description:** Covered by test cases 1, 2, and 6 from AC2.1 above. Becky Bennett fixture exercises the empty-field path (real card has empty `mes_example` and `post_history_instructions`). Synthetic card without `extensions.position` exercises the default path.

---

### roleplay-parity-289.AC2.3

**AC text:** System prompt assembled in ST order: main -> worldInfoBefore -> charDescription -> charPersonality -> scenario -> worldInfoAfter -> dialogueExamples.

**Test type:** unit

**Test file:** `tests/unit/test_prompt_assembly.py`

**Description:** Construct a Character with distinct, identifiable values for each slot (e.g. `system_prompt="SLOT_MAIN"`, `description="SLOT_DESC"`, `personality="SLOT_PERSONALITY"`, `scenario="SLOT_SCENARIO"`, `mes_example="SLOT_EXAMPLES"`). Provide lorebook entries with `position="before_char"` and `position="after_char"`. Call `build_system_prompt()`. Assert slot markers appear in the output in the exact ST order: SLOT_MAIN before SLOT_DESC, SLOT_DESC before SLOT_PERSONALITY, SLOT_PERSONALITY before SLOT_SCENARIO, SLOT_EXAMPLES last.

---

### roleplay-parity-289.AC2.4

**AC text:** Lorebook entries split by `position` field -- `before_char` entries appear between main and charDescription; `after_char` entries appear after scenario.

**Test type:** unit

**Test file:** `tests/unit/test_prompt_assembly.py`

**Description:** Three test cases:

1. Mixed positions: `before_char` entry content appears after system_prompt but before description. `after_char` entry content appears after scenario but before mes_example.
2. All `before_char` (no `after_char`): all lorebook content appears before description (matches current default behaviour).
3. Budget sharing: `before_char` entries consume the full lorebook token budget; `after_char` entries are excluded because the shared budget is exhausted.

---

### roleplay-parity-289.AC2.5

**AC text:** `post_history_instructions` (when non-empty) injected as final `user`-role message after chat history.

**Test type:** unit

**Test file:** `tests/unit/test_prompt_assembly.py`

**Description:** Two test cases:

1. Non-empty `post_history_instructions`: call `build_messages()` with a Character that has `post_history_instructions="Remember to stay in character"` and a list of turns. Assert the last element in the returned messages list has `role == "user"` and its content matches the instructions text.
2. Empty `post_history_instructions`: call `build_messages()` with an empty string. Assert no extra message is appended (message count equals the number of turns).

---

### roleplay-parity-289.AC2.6

**AC text:** Placeholder substitution (`{{char}}`, `{{user}}`) applied to all prompt slots including new fields.

**Test type:** unit

**Test file:** `tests/unit/test_prompt_assembly.py`

**Description:** Two test cases:

1. `build_system_prompt()`: Character has `mes_example="Hello {{char}} from {{user}}"`. Assert the output contains the substituted names, not the raw placeholders.
2. `build_messages()`: Character has `post_history_instructions="Stay as {{char}}"`. Assert the final user message content contains the substituted character name.

---

### roleplay-parity-289.AC2.7

**AC text:** Audit log mode produces a JSON file containing the full API request payload (system, messages, model, max_tokens) matching Anthropic Messages API schema.

**Test type:** unit

**Test file:** `tests/unit/test_claude_client.py`

**Description:** Three test cases:

1. `audit_log_path` set: mock the Anthropic client, call `stream_message_only()`, assert a JSON file is written at the specified `tmp_path` location containing keys `system`, `messages`, `model`, `max_tokens`.
2. `audit_log_path` is `None`: mock the Anthropic client, call `stream_message_only()`, assert no file is written.
3. Schema validation: read the written JSON, assert `system` is a string, `messages` is a list of dicts each with `role` and `content` keys, `model` is a string, `max_tokens` is an integer.

**Additional:** human verification

**Justification:** The actual 1:1 comparison with a SillyTavern reference log is manual UAT. The reference log does not exist yet -- the user will generate it by running a one-turn conversation in their local SillyTavern installation. Automated tests verify the audit log is written with the correct schema; the semantic comparison (do our slots match ST's slots for the Becky Bennett card?) requires human judgement against a reference that is produced outside this codebase.

---

## roleplay-parity-289.AC3: End-of-conversation flow

### roleplay-parity-289.AC3.1

**AC text:** `<endofconversation>` marker detected in streamed response and stripped from displayed text.

**Test type:** unit

**Test file:** `tests/unit/test_end_of_conversation.py`

**Description:** Three test cases for `detect_end_of_conversation()`:

1. Marker in a single chunk: input `["Hello world<endofconversation>"]`. Assert yielded chunks contain `"Hello world"` with `ended=True`.
2. Marker at end of response: input `["Hello ", "world<endofconversation>"]`. Assert all text before marker is yielded; final chunk has `ended=True`.
3. Marker in middle of chunk: input `["Before<endofconversation>After"]`. Assert `"Before"` is yielded with `ended=True`; `"After"` is discarded.

---

### roleplay-parity-289.AC3.2

**AC text:** Marker spanning two streaming chunks is correctly detected and stripped.

**Test type:** unit

**Test file:** `tests/unit/test_end_of_conversation.py`

**Description:** Two test cases:

1. Marker split across two chunks: input `["Hello <endofconv", "ersation> goodbye"]`. Assert text before marker is yielded; marker is stripped; `ended=True`.
2. Marker split across three chunks: input `["<endof", "conver", "sation>"]`. Assert `ended=True` and no marker text in output.

---

### roleplay-parity-289.AC3.3

**AC text:** `StreamChunk.ended` is `True` when marker present, `False` for normal responses.

**Test type:** unit

**Test file:** `tests/unit/test_end_of_conversation.py`

**Description:** Three test cases:

1. No marker in response: input `["Hello", " world"]`. Assert all yielded chunks have `ended=False`.
2. Text containing `<` but not the marker: input `["Use <html> tags"]`. Assert all chunks have `ended=False` (no false positive).
3. Empty stream: no chunks yielded at all.
4. Marker is entire response: input `["<endofconversation>"]`. Assert a single chunk with `text=""` and `ended=True`.

---

### roleplay-parity-289.AC3.4

**AC text:** On AI-triggered end: input disabled, conversation auto-exported to annotation workspace, completion banner with link displayed.

**Test type:** e2e

**Test file:** `tests/e2e/test_roleplay_end_of_conversation.py`

**Description:** Navigate to `/roleplay`. Send a message. Mock or arrange for the AI response to contain `<endofconversation>`. After the response renders:

1. Assert input field (`data-testid="roleplay-input"`) is disabled.
2. Assert completion banner (`data-testid="roleplay-completion-banner"`) is visible.
3. Assert banner contains a link (`data-testid="roleplay-workspace-link"`) with an href pointing to `/annotation?workspace_id=`.
4. Click the link and assert navigation to the annotation page succeeds.

**Additional:** human verification

**Justification:** The AI response content is non-deterministic. The E2E test requires a mock or fixture that injects `<endofconversation>` into the streaming response. If mocking the LLM at the E2E level proves fragile (it depends on the NiceGUI server's ability to accept a test-injected mock), fallback to human verification: the tester manually conducts a conversation long enough for the AI to emit the marker, then verifies the UI flow. The unit tests for detection (AC3.1-AC3.3) cover the core logic; the E2E test covers the wiring.

---

### roleplay-parity-289.AC3.5

**AC text:** "Finish Interview" button triggers confirmation dialog; on confirm: input locked, conversation exported, completion banner shown.

**Test type:** e2e

**Test file:** `tests/e2e/test_roleplay_end_of_conversation.py`

**Description:** Navigate to `/roleplay`. Send at least one message (to have an exportable conversation). Click "Finish Interview" (`data-testid="roleplay-finish-btn"`).

1. Assert confirmation dialog appears with "End Interview" and "Cancel" buttons.
2. Click "Cancel". Assert the dialog closes and the input remains enabled.
3. Click "Finish Interview" again, then "End Interview".
4. Assert input field is disabled.
5. Assert completion banner (`data-testid="roleplay-completion-banner"`) is visible with workspace link.

---

### roleplay-parity-289.AC3.6

**AC text:** Navigating back to `/roleplay` after conversation end starts a fresh session (no resumption of locked session).

**Test type:** e2e

**Test file:** `tests/e2e/test_roleplay_end_of_conversation.py`

**Description:** Complete the finish-interview flow from AC3.5. Navigate away from `/roleplay` (e.g. to `/`), then navigate back to `/roleplay`. Assert the input field is enabled (not disabled). Assert the completion banner is not present. Assert the chat area is empty or shows only the initial first_mes greeting.

---

### roleplay-parity-289.AC3.7

**AC text:** Sending a message after conversation end is rejected (input disabled, no API call made).

**Test type:** unit + e2e

**Test file:** `tests/unit/test_end_of_conversation.py`, `tests/e2e/test_roleplay_end_of_conversation.py`

**Description:**

1. *Unit:* Create a Session with `ended=True`. Call the send handler (or the guard logic extracted into a testable function). Assert it returns immediately without invoking `stream_message_only()`.
2. *E2E:* After triggering the finish-interview flow, attempt to interact with the input field. Assert it is disabled (Playwright's `is_disabled()` returns `True`). Assert no network request to the Anthropic API is made (if observable via request interception, otherwise rely on the disabled state preventing submission).

---

## Summary

| AC | Sub | Test Type | Test File | Phase |
|----|-----|-----------|-----------|-------|
| AC1 | 1.1 | e2e | `tests/e2e/test_roleplay_layout.py` | 5 |
| AC1 | 1.2 | e2e + unit | `tests/e2e/test_roleplay_layout.py`, `tests/unit/test_roleplay_css_no_vh.py` | 5 |
| AC1 | 1.3 | e2e | `tests/e2e/test_roleplay_layout.py` | 5 |
| AC1 | 1.4 | e2e | `tests/e2e/test_roleplay_layout.py` | 6 |
| AC1 | 1.5 | e2e | `tests/e2e/test_roleplay_layout.py` | 6 |
| AC2 | 2.1 | unit | `tests/unit/test_sillytavern_parser.py` | 1 |
| AC2 | 2.2 | unit | `tests/unit/test_sillytavern_parser.py` | 1 |
| AC2 | 2.3 | unit | `tests/unit/test_prompt_assembly.py` | 2 |
| AC2 | 2.4 | unit | `tests/unit/test_prompt_assembly.py` | 2 |
| AC2 | 2.5 | unit | `tests/unit/test_prompt_assembly.py` | 2 |
| AC2 | 2.6 | unit | `tests/unit/test_prompt_assembly.py` | 2 |
| AC2 | 2.7 | unit + human | `tests/unit/test_claude_client.py` | 3 |
| AC3 | 3.1 | unit | `tests/unit/test_end_of_conversation.py` | 4 |
| AC3 | 3.2 | unit | `tests/unit/test_end_of_conversation.py` | 4 |
| AC3 | 3.3 | unit | `tests/unit/test_end_of_conversation.py` | 4 |
| AC3 | 3.4 | e2e + human | `tests/e2e/test_roleplay_end_of_conversation.py` | 7 |
| AC3 | 3.5 | e2e | `tests/e2e/test_roleplay_end_of_conversation.py` | 7 |
| AC3 | 3.6 | e2e | `tests/e2e/test_roleplay_end_of_conversation.py` | 7 |
| AC3 | 3.7 | unit + e2e | `tests/unit/test_end_of_conversation.py`, `tests/e2e/test_roleplay_end_of_conversation.py` | 7 |

### Test file inventory

| File | Type | New/Existing | ACs covered |
|------|------|-------------|-------------|
| `tests/unit/test_sillytavern_parser.py` | unit | existing (extend) | AC2.1, AC2.2 |
| `tests/unit/test_prompt_assembly.py` | unit | existing (extend) | AC2.3, AC2.4, AC2.5, AC2.6 |
| `tests/unit/test_claude_client.py` | unit | existing (extend) | AC2.7 |
| `tests/unit/test_end_of_conversation.py` | unit | new | AC3.1, AC3.2, AC3.3, AC3.7 |
| `tests/unit/test_roleplay_css_no_vh.py` | unit | new | AC1.2 |
| `tests/e2e/test_roleplay_layout.py` | e2e | new | AC1.1, AC1.2, AC1.3, AC1.4, AC1.5 |
| `tests/e2e/test_roleplay_end_of_conversation.py` | e2e | new | AC3.4, AC3.5, AC3.6, AC3.7 |

### Human verification inventory

| AC | Reason |
|----|--------|
| AC2.7 (partial) | Semantic comparison of audit log against SillyTavern reference log requires human judgement. The reference log does not yet exist and is produced outside this codebase. Automated tests verify schema correctness only. |
| AC3.4 (fallback) | AI response content is non-deterministic. E2E test requires a mock injecting the marker. If mock injection proves fragile at the NiceGUI E2E level, human verification is the fallback. Unit tests for detection logic (AC3.1-AC3.3) provide the safety net. |
