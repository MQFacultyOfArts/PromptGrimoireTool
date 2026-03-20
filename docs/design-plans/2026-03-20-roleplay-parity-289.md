# Roleplay Page Parity & UX Design

**GitHub Issue:** [#289](https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/289)

## Summary

This PR brings the roleplay page — used for simulated legal client interviews in tort law units — up to production quality across three areas. The page currently has a hardcoded `60vh` scroll area that breaks on small screens and zoom levels; a prompt construction pipeline that diverges from the SillyTavern reference implementation it is meant to replicate; and no mechanism to conclude an interview gracefully. All three are addressed together because they share the same page and prompt assembly code, and fixing the layout in isolation would leave the other two concerns unresolved.

The approach is a seven-phase incremental build. The first four phases work bottom-up through the data layer: extending the character card parser to extract fields SillyTavern uses but we currently ignore, restructuring prompt assembly to match SillyTavern's slot order exactly, adding an audit log mode so the two implementations can be compared request-by-request, and teaching the streaming client to detect an `<endofconversation>` marker in the AI's output. The last three phases are UI work: replacing the hardcoded scroll height with a CSS flexbox layout, adding a character info sidebar, and wiring the end-of-conversation detection into a completion flow that locks the input, exports the conversation to an annotation workspace, and presents the student with a link to review their work.

## Definition of Done

### A. Responsive Viewport Layout
The roleplay page chat card uses flexbox to fill available viewport height. The scroll area expands/contracts dynamically. The input row is always visible regardless of screen height. No hardcoded `vh` values. Works on small laptops (13" at default scaling) and zoomed browsers alike.

### B. Prompt Construction Parity with SillyTavern
Audit SillyTavern's Claude API prompt assembly for the Becky Bennett character card and compare with our implementation. Close gaps so that our one-turn API request is structurally identical to SillyTavern's (same system prompt construction, same message ordering, same metadata). The user will provide a SillyTavern API request log as the reference target. An audit logging mode must be added so our full API request payload can be dumped for comparison. AI response content is non-deterministic and excluded from comparison.

### C. End-of-Conversation Flow
The system prompt instructs the character to emit `<endofconversation>` when the interview concludes naturally. The streaming handler detects this marker, strips it from displayed output, locks the input (no further messages), auto-exports the conversation to an annotation workspace (`ai_conversation` document type), and presents "The activity is complete" with a clickable link to the annotation workspace. A "Finish Interview" button (with confirmation dialog) lets students end the interview early, triggering the same lock + export flow.

## Acceptance Criteria

### roleplay-parity-289.AC1: Responsive viewport layout
- **roleplay-parity-289.AC1.1 Success:** Chat scroll area and input row are both visible on a 600px-tall viewport without page-level scrolling
- **roleplay-parity-289.AC1.2 Success:** Scroll area dynamically resizes when browser window height changes (no hardcoded `vh` values)
- **roleplay-parity-289.AC1.3 Success:** Management panel (upload/export/settings) opens from a right drawer with zero vertical footprint when closed
- **roleplay-parity-289.AC1.4 Success:** Character info panel (portrait, name) displays as a left sidebar on viewports wider than 1024px
- **roleplay-parity-289.AC1.5 Success:** Character info panel collapses or hides on viewports narrower than 1024px; avatar + name remain visible in header

### roleplay-parity-289.AC2: Prompt construction parity
- **roleplay-parity-289.AC2.1 Success:** Parser extracts `mes_example`, `post_history_instructions`, and lorebook entry `position` from chara_card_v3 JSON
- **roleplay-parity-289.AC2.2 Edge:** Missing or empty card fields produce empty strings (no errors); lorebook entries without `extensions.position` default to `before_char`
- **roleplay-parity-289.AC2.3 Success:** System prompt assembled in ST order: main → worldInfoBefore → charDescription → charPersonality → scenario → worldInfoAfter → dialogueExamples
- **roleplay-parity-289.AC2.4 Success:** Lorebook entries split by `position` field — `before_char` entries appear between main and charDescription; `after_char` entries appear after scenario
- **roleplay-parity-289.AC2.5 Success:** `post_history_instructions` (when non-empty) injected as final `user`-role message after chat history
- **roleplay-parity-289.AC2.6 Success:** Placeholder substitution (`{{char}}`, `{{user}}`) applied to all prompt slots including new fields
- **roleplay-parity-289.AC2.7 Success:** Audit log mode produces a JSON file containing the full API request payload (system, messages, model, max_tokens) matching Anthropic Messages API schema

### roleplay-parity-289.AC3: End-of-conversation flow
- **roleplay-parity-289.AC3.1 Success:** `<endofconversation>` marker detected in streamed response and stripped from displayed text
- **roleplay-parity-289.AC3.2 Edge:** Marker spanning two streaming chunks is correctly detected and stripped
- **roleplay-parity-289.AC3.3 Success:** `StreamChunk.ended` is `True` when marker present, `False` for normal responses
- **roleplay-parity-289.AC3.4 Success:** On AI-triggered end: input disabled, conversation auto-exported to annotation workspace, completion banner with link displayed
- **roleplay-parity-289.AC3.5 Success:** "Finish Interview" button triggers confirmation dialog; on confirm: input locked, conversation exported, completion banner shown
- **roleplay-parity-289.AC3.6 Success:** Navigating back to `/roleplay` after conversation end starts a fresh session (no resumption of locked session)
- **roleplay-parity-289.AC3.7 Failure:** Sending a message after conversation end is rejected (input disabled, no API call made)

## Glossary

- **SillyTavern**: An open-source chat frontend for large language models. PromptGrimoire imports SillyTavern character cards to drive its roleplay scenarios, and this design aligns the prompt construction pipeline to match SillyTavern's behaviour exactly.
- **chara_card_v3**: The JSON format SillyTavern uses to bundle a character's persona, dialogue examples, and lorebook into a single portable file. The Becky Bennett card is the concrete reference used for this work.
- **Lorebook**: A collection of keyword-triggered entries bundled inside a character card. When a keyword appears in conversation, the associated entry is injected into the prompt to provide context the character should know about.
- **Lorebook position (`before_char` / `after_char`)**: A field on each lorebook entry that controls where in the system prompt the entry is inserted — either before the character description block or after the scenario block.
- **Prompt slot / `prompt_order`**: SillyTavern's term for the named sections of a Claude API request (main system prompt, character description, personality, scenario, dialogue examples, etc.) and the order they are assembled. This design replicates that order.
- **`mes_example`**: A SillyTavern character card field containing example dialogue that demonstrates how the character speaks. Injected into the system prompt as the `dialogueExamples` slot.
- **`post_history_instructions`**: A SillyTavern character card field containing a reminder injected as the final `user`-role message after the chat history, used to reinforce character behaviour late in the context window.
- **Placeholder substitution**: Replacing template tokens `{{char}}` and `{{user}}` with the character's name and the student's name throughout all prompt slots.
- **`StreamChunk`**: A dataclass yielded by the streaming client. Carries a text fragment and a boolean `ended` flag set when the `<endofconversation>` marker was detected.
- **`<endofconversation>`**: A string marker the system prompt instructs the character to emit when the interview concludes naturally. The streaming layer detects and strips it; the UI reacts by locking the input and triggering export.
- **Annotation workspace / `ai_conversation` document type**: The destination for exported roleplay sessions. An annotation workspace is the platform's collaborative review space; `ai_conversation` is the document type that represents a complete AI chat transcript within it.
- **NiceGUI**: The Python web UI framework used throughout PromptGrimoire. UI elements like drawers, scroll areas, and cards are NiceGUI components built on Quasar/Vue.
- **`ui.right_drawer`**: A NiceGUI component that slides in from the right edge of the viewport. The management panel (upload, export, settings) moves here so it takes no vertical space when closed.
- **Functional core / imperative shell**: An architecture pattern used in this codebase where pure functions (no side effects, no I/O) hold all business logic, and thin shell functions handle I/O and call the pure core. `llm/prompt.py` is the functional core for prompt assembly.
- **Anthropic Messages API**: The HTTP API used to send requests to Claude. The audit log mode dumps the exact JSON payload sent to this API so it can be compared with SillyTavern's equivalent log.
- **`100vw` vs `100%`**: A CSS distinction. `100vw` is the full viewport width including the scrollbar, which can cause horizontal overflow. `100%` is the width of the containing element, which does not.

## Architecture

Three concerns, addressed as a single coherent redesign of the roleplay page.

### A. Two-Panel Layout with Flex Chat

The roleplay page becomes a two-panel layout:

**Left panel — Character info.** Displays character name (large), portrait image, and optionally the scenario blurb (visibility TBD per instructor preference). Fixed sidebar on wide screens (>1024px). On narrow viewports, collapses into a left drawer or hides entirely, with a compact avatar + name remaining in the header bar.

**Centre — Chat card.** Flex column filling remaining viewport height. Contains: character name label (natural height), scroll area (`flex: 1`, replaces current `height: 60vh`), input row (natural height, always visible at bottom). The "Finish Interview" button sits in the input row or header.

**Right drawer — Management panel.** The current expansion panel (upload, export, settings) moves into a `ui.right_drawer`, toggled by a header button. Zero vertical footprint when closed. This is a temporary arrangement until the roleplay page is wired into the activity system.

**Background.** `.roleplay-bg` width changes from `100vw` to `100%` to prevent horizontal scrollbar overflow.

### B. SillyTavern Prompt Slot System

`build_system_prompt()` is restructured to replicate SillyTavern's `prompt_order` for the Claude Messages API path:

**System parameter (in order):**

| Slot | Source | ST Identifier |
|------|--------|---------------|
| 1. Main prompt | `Character.system_prompt` (falls back to ST default: `"Write {{char}}'s next reply..."`) | `main` |
| 2. World Info (before) | Lorebook entries with `position: before_char` | `worldInfoBefore` |
| 3. Character Description | `Character.description` | `charDescription` |
| 4. Character Personality | `Character.personality` | `charPersonality` |
| 5. Scenario | `Character.scenario` | `scenario` |
| 6. World Info (after) | Lorebook entries with `position: after_char` | `worldInfoAfter` |
| 7. Dialogue Examples | `Character.mes_example` | `dialogueExamples` |

**Messages array:**

| Slot | Source | ST Identifier |
|------|--------|---------------|
| 8. Chat History | User/assistant turn alternation | `chatHistory` |
| 9. Post-history instructions | `Character.post_history_instructions` as final `user`-role message | `jailbreak` |

**End-of-conversation instruction** appended after all ST-parity slots as a platform-level addition (not part of the ST card).

**Placeholder substitution** (`{{char}}` → name, `{{user}}` → user name) applies to all slots.

**Audit logging.** A `ROLEPLAY_AUDIT_LOG` config flag dumps the complete API request payload (system parameter + messages array) as JSON to the session log directory, enabling 1:1 comparison with SillyTavern logs.

### C. End-of-Conversation Detection

**AI-triggered ending.** A platform-level instruction appended to the system prompt tells the character to emit `<endofconversation>` when the interview concludes naturally. The marker is invisible to the student.

**Detection in ClaudeClient.** `stream_message_only()` yields `StreamChunk` dataclasses instead of bare strings:

```python
@dataclass(frozen=True)
class StreamChunk:
    text: str
    ended: bool = False
```

Normal chunks have `ended=False`. When the marker is detected, it is stripped and the final chunk carries `ended=True`. The UI checks each chunk's `ended` flag. This preserves true streaming (no waiting for full response).

**Matching strategy.** Case-sensitive exact match only. If the model drifts to `<EndOfConversation>` or a variant, the marker is not detected and the conversation continues (fail-open). The student can always use the "Finish Interview" button. No fuzzy matching — false positives are worse than false negatives.

**UI flow on detection:**
1. Final AI response renders (marker stripped)
2. Input field and send button disabled
3. Auto-export fires via existing `_handle_export()` path
4. Banner: "The activity is complete." with link to annotation workspace
5. Student clicks through at their own pace

**Early exit.** "Finish Interview" button (always visible) triggers confirmation dialog. On confirm: locks input, exports current conversation (no final AI response), shows same completion banner.

**Session lock.** `Session.ended: bool` flag. Navigating back to `/roleplay` starts fresh.

## Existing Patterns

**Page layout.** The roleplay page follows the same `page_route` + `create_page_layout()` pattern as other pages (`pages/layout.py:203-262`). The existing `ui.left_drawer` for navigation is the template for the new right drawer.

**Export flow.** `roleplay_export.py:session_to_html()` and `roleplay.py:_handle_export()` already implement the full export-to-annotation-workspace pipeline. The end-of-conversation flow reuses this path without modification.

**Prompt assembly.** Current `llm/prompt.py:build_system_prompt()` and `build_messages()` are pure functions with no side effects. The restructuring maintains this pattern — slot ordering changes, but the functional core / imperative shell separation is preserved.

**Streaming.** `llm/client.py:stream_message_only()` is the existing streaming method. The `StreamChunk` return type is a new pattern, but the streaming mechanism (async iterator with `yield`) is unchanged.

**Character card parsing.** `parsers/sillytavern.py` already extracts most v3 fields. Adding `mes_example`, `post_history_instructions`, and lorebook `position` follows the existing extraction pattern.

**Divergence: Lorebook position.** Current code treats all lorebook entries identically (no position awareness). The new code splits entries by their `position` field into `before_char` and `after_char` buckets. This is additive — entries without a position default to `before_char` (matching current behaviour).

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Model and Parser Updates
**Goal:** Extend Character and LorebookEntry models to support all ST-parity fields; update the parser to extract them.

**Components:**
- `Character` dataclass in `src/promptgrimoire/models/scenario.py` — add `mes_example: str`, `post_history_instructions: str` fields
- `LorebookEntry` dataclass in `src/promptgrimoire/models/scenario.py` — add `position: str` field (default `"before_char"`)
- `parse_character_card()` in `src/promptgrimoire/parsers/sillytavern.py` — extract `mes_example`, `post_history_instructions` from `data` block; extract `position` from lorebook entry `extensions.position` (0 → `"before_char"`, 1 → `"after_char"`)

**Dependencies:** None (first phase)

**Done when:** Parser extracts all new fields from the Becky Bennett card; existing tests still pass; new unit tests verify extraction of `mes_example`, `post_history_instructions`, and lorebook `position` from a test fixture card that has non-empty values for these fields.

**Covers:** roleplay-parity-289.AC2.1, roleplay-parity-289.AC2.2
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Prompt Assembly Parity
**Goal:** Restructure system prompt and message assembly to match SillyTavern's slot ordering 1:1.

**Components:**
- `build_system_prompt()` in `src/promptgrimoire/llm/prompt.py` — reorder to: main (system_prompt or fallback) → worldInfoBefore → description → personality → scenario → worldInfoAfter → dialogueExamples
- `build_messages()` in `src/promptgrimoire/llm/prompt.py` — append `post_history_instructions` as final `user`-role message when non-empty
- Lorebook splitting logic — partition activated entries by `position` into before/after buckets
- `activate_entries()` in `src/promptgrimoire/llm/lorebook.py` — no change to activation logic, but return value or caller must handle position-based splitting

**Dependencies:** Phase 1 (model fields must exist)

**Done when:** Unit tests verify: (a) system prompt assembled in ST order with all slots; (b) lorebook entries correctly split by position; (c) post_history_instructions appears as final user message; (d) empty slots produce no gap in output; (e) placeholder substitution applies to all slots.

**Covers:** roleplay-parity-289.AC2.3, roleplay-parity-289.AC2.4, roleplay-parity-289.AC2.5, roleplay-parity-289.AC2.6
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Audit Logging
**Goal:** Add debug mode that dumps the complete API request payload for 1:1 comparison with SillyTavern logs.

**Components:**
- `ClaudeClient` in `src/promptgrimoire/llm/client.py` — when audit flag is set, serialise the full `system` + `messages` payload as JSON and write to the session log directory alongside the JSONL chat log
- `Settings` in `src/promptgrimoire/config.py` — add `roleplay_audit_log: bool` config flag (env var `ROLEPLAY__AUDIT_LOG`, default `False`)
- Log format: JSON file with `{"system": [...], "messages": [...], "model": "...", "max_tokens": ...}` matching the Anthropic API request shape

**Dependencies:** Phase 2 (prompt assembly must be in final form)

**Done when:** With audit flag enabled, a one-turn conversation produces a JSON file containing the complete API request; JSON structure matches Anthropic Messages API schema.

**Covers:** roleplay-parity-289.AC2.7
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: End-of-Conversation Detection
**Goal:** Detect `<endofconversation>` marker in streaming response and signal the UI.

**Components:**
- `StreamChunk` dataclass in `src/promptgrimoire/llm/client.py` — `text: str`, `ended: bool`, `thinking: str | None`
- `stream_message_only()` in `src/promptgrimoire/llm/client.py` — buffer streamed text, detect marker, strip from output, set `ended=True` on result
- End-of-conversation system prompt instruction — appended after all ST-parity slots in `build_system_prompt()` as a platform-level addition
- `Session` in `src/promptgrimoire/models/scenario.py` — add `ended: bool` field (default `False`)

**Dependencies:** Phase 2 (system prompt assembly must support appending platform instructions)

**Done when:** Unit tests verify: (a) marker detected mid-stream and stripped; (b) marker detected at end of response; (c) `StreamChunk.ended` is `True` when marker present, `False` otherwise; (d) partial marker spanning chunk boundaries handled correctly; (e) system prompt includes end-of-conversation instruction.

**Covers:** roleplay-parity-289.AC3.1, roleplay-parity-289.AC3.2, roleplay-parity-289.AC3.3
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Responsive Layout — Flex Chat Card
**Goal:** Replace hardcoded `60vh` scroll area with flexbox layout; move management panel to right drawer.

**Components:**
- `roleplay.py` page builder in `src/promptgrimoire/pages/roleplay.py` — restructure chat card as flex column; move expansion panel into `ui.right_drawer` with header toggle button
- `roleplay.css` in `src/promptgrimoire/static/roleplay.css` — remove `height: 60vh` from `.roleplay-chat`; add flex properties to `.roleplay-card`; fix `.roleplay-bg` width from `100vw` to `100%`
- Scroll area — `flex: 1` with `min-height: 0`; input row at natural height

**Dependencies:** None (layout is independent of prompt changes)

**Done when:** Roleplay page renders with no hardcoded viewport heights; input row is visible on a 600px-tall viewport; management panel opens from right drawer; existing E2E roleplay tests pass (if any).

**Covers:** roleplay-parity-289.AC1.1, roleplay-parity-289.AC1.2, roleplay-parity-289.AC1.3
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Character Info Panel
**Goal:** Add left-side character info panel with portrait, name, and optional scenario.

**Components:**
- Character panel in `src/promptgrimoire/pages/roleplay.py` — left sidebar with character portrait (large), name, optional scenario blurb; collapses on narrow viewports (<1024px)
- `roleplay.css` — styles for character panel, responsive collapse behaviour
- Avatar handling — extract avatar from character card data (or use placeholder); `parsers/sillytavern.py` may need to extract avatar data if not already handled

**Dependencies:** Phase 5 (layout must be flex-based first)

**Done when:** Character panel displays on wide viewports; collapses or hides on narrow viewports; avatar and name are visible; chat card retains full height behaviour.

**Covers:** roleplay-parity-289.AC1.4, roleplay-parity-289.AC1.5
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: End-of-Conversation UI Flow
**Goal:** Wire marker detection to UI: lock input, auto-export, completion banner, early finish button.

**Components:**
- Roleplay page handler in `src/promptgrimoire/pages/roleplay.py` — react to `StreamChunk.ended`: disable input/send button, trigger `_handle_export()`, show completion banner with link to annotation workspace
- "Finish Interview" button — visible throughout conversation; on click shows confirmation dialog; on confirm: sets `Session.ended`, disables input, exports, shows banner
- Banner UI — "The activity is complete." with clickable link to the exported annotation workspace

**Dependencies:** Phase 4 (detection must work), Phase 5 (layout must support button placement)

**Done when:** AI-triggered end locks the conversation and auto-exports; early finish button triggers same flow with confirmation; completion banner links to annotation workspace; re-navigating to `/roleplay` starts fresh session.

**Covers:** roleplay-parity-289.AC3.4, roleplay-parity-289.AC3.5, roleplay-parity-289.AC3.6, roleplay-parity-289.AC3.7
<!-- END_PHASE_7 -->

## Additional Considerations

**Scenario visibility.** Whether the scenario blurb is shown to students in the character panel is an instructor decision. The panel should have a slot for it, controlled by a flag. This can be a character card extension field (`extensions.promptgrimoire.show_scenario`) or deferred to when roleplay is wired into the activity system. For now, default to hidden.

**Marker robustness.** The `<endofconversation>` marker could theoretically span two streaming chunks (e.g. `<endofconv` in one, `ersation>` in the next). The detection must buffer sufficiently to handle this. A sliding window of the marker's length over chunk boundaries is sufficient.

**Parity verification is manual UAT.** The audit log (AC2.7) is a delivery mechanism. Actual 1:1 comparison with a SillyTavern reference log is a manual step performed by the user — not an automated test. The reference log does not exist yet; the user will generate it by running a one-turn conversation in the local ST installation.

**ST fields we intentionally skip.** ST's `nsfw` (auxiliary prompt) and `enhanceDefinitions` slots are not relevant to educational use and are omitted. The `personaDescription` slot (user persona) is also omitted — our system uses the character card's `user_persona_name` for placeholder substitution but doesn't inject a separate persona description block.
