# Roleplay Parity Implementation Plan — Phase 2: Prompt Assembly Parity

**Goal:** Restructure system prompt and message assembly to match SillyTavern's slot ordering 1:1.

**Architecture:** Reorder `build_system_prompt()` to ST slot order, split lorebook entries by position field, add `post_history_instructions` injection to `build_messages()`. Pure function changes maintaining functional core pattern.

**Tech Stack:** Python 3.14, Anthropic Messages API types

**Scope:** Phase 2 of 7 from original design

**Codebase verified:** 2026-03-20

---

## Acceptance Criteria Coverage

This phase implements and tests:

### roleplay-parity-289.AC2: Prompt construction parity
- **roleplay-parity-289.AC2.3 Success:** System prompt assembled in ST order: main → worldInfoBefore → charDescription → charPersonality → scenario → worldInfoAfter → dialogueExamples
- **roleplay-parity-289.AC2.4 Success:** Lorebook entries split by `position` field — `before_char` entries appear between main and charDescription; `after_char` entries appear after scenario
- **roleplay-parity-289.AC2.5 Success:** `post_history_instructions` (when non-empty) injected as final `user`-role message after chat history
- **roleplay-parity-289.AC2.6 Success:** Placeholder substitution (`{{char}}`, `{{user}}`) applied to all prompt slots including new fields

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Restructure build_system_prompt() to ST slot order with position-aware lorebook splitting

**Verifies:** roleplay-parity-289.AC2.3, roleplay-parity-289.AC2.4, roleplay-parity-289.AC2.6

**Files:**
- Modify: `src/promptgrimoire/llm/prompt.py:55-121` (build_system_prompt)

**Implementation:**

Restructure `build_system_prompt()` to assemble in this order:

1. **Main prompt** — `character.system_prompt` (ST slot: `main`)
2. **World Info Before** — lorebook entries with `position == "before_char"`, sorted by `insertion_order` descending, budget-enforced (ST slot: `worldInfoBefore`)
3. **Character Description** — `character.description` (ST slot: `charDescription`)
4. **Character Personality** — `character.personality` (ST slot: `charPersonality`)
5. **Scenario** — `character.scenario` (ST slot: `scenario`)
6. **World Info After** — lorebook entries with `position == "after_char"`, sorted by `insertion_order` descending, budget-enforced (ST slot: `worldInfoAfter`)
7. **Dialogue Examples** — `character.mes_example` (ST slot: `dialogueExamples`)

Split lorebook entries by position inside this function (not in `activate_entries()`):

```python
before_entries = [e for e in activated_entries if e.position == "before_char"]
after_entries = [e for e in activated_entries if e.position == "after_char"]
```

Both lists are sorted by `insertion_order` descending independently. Token budget is shared across both lists using a single `lorebook_tokens` counter: process `before_entries` first (consuming budget), then process `after_entries` with the remaining budget. Concrete approach — use the existing budget enforcement loop twice, with a shared `lorebook_tokens` accumulator:

```python
lorebook_tokens = 0
# Process before_char entries
for entry in sorted(before_entries, key=lambda e: e.insertion_order, reverse=True):
    content = entry.content.strip()
    if not content:
        continue
    if budget > 0:
        entry_tokens = estimate_tokens(content)
        if lorebook_tokens + entry_tokens > budget:
            break
        lorebook_tokens += entry_tokens
    parts.append(content)

# ... character description, personality, scenario ...

# Process after_char entries (same lorebook_tokens counter)
for entry in sorted(after_entries, key=lambda e: e.insertion_order, reverse=True):
    content = entry.content.strip()
    if not content:
        continue
    if budget > 0:
        entry_tokens = estimate_tokens(content)
        if lorebook_tokens + entry_tokens > budget:
            break
        lorebook_tokens += entry_tokens
    parts.append(content)
```

Add a test case: when `before_char` entries fill the budget, `after_char` entries are excluded.

Empty slots (empty string after strip) produce no gap — same pattern as current code.

Placeholder substitution via `substitute_placeholders()` remains as the final step on the joined string. This already covers all slots including the new `mes_example` content.

Update the docstring to document the new ST-parity slot ordering.

**Verification:**
Run: `uvx ty check`
Expected: No new type errors

**Commit:** `feat: restructure build_system_prompt to match SillyTavern slot ordering`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add post_history_instructions to build_messages() and update tests

**Verifies:** roleplay-parity-289.AC2.3, roleplay-parity-289.AC2.4, roleplay-parity-289.AC2.5, roleplay-parity-289.AC2.6

**Files:**
- Modify: `src/promptgrimoire/llm/prompt.py:124-141` (build_messages)
- Test: `tests/unit/test_prompt_assembly.py` (unit)

**Implementation:**

Change `build_messages()` signature to accept Character and user_name:

```python
def build_messages(
    turns: list[Turn],
    character: Character,
    *,
    user_name: str,
) -> list[MessageParam]:
```

After building messages from turns, if `character.post_history_instructions` is non-empty after stripping, append it as a final `user`-role message with placeholder substitution applied:

```python
phi = character.post_history_instructions.strip()
if phi:
    phi = substitute_placeholders(phi, char_name=character.name, user_name=user_name)
    messages.append({"role": "user", "content": phi})
```

**Callers to update:** Known callers of `build_messages()`:
- `src/promptgrimoire/llm/client.py:88` — `ClaudeClient.send_message()`
- `src/promptgrimoire/llm/client.py:142` — `ClaudeClient.stream_message()`
- `src/promptgrimoire/llm/client.py:220` — `ClaudeClient.stream_message_only()`
- `tests/unit/test_prompt_assembly.py` — `TestBuildMessages` class

All callers must be updated to pass `character` and `user_name` keyword arguments.

**Testing:**

Tests must verify each AC listed above. Update existing tests and add new ones:

**Existing test updates:**
- All existing `TestBuildMessages` tests need updated calls: `build_messages(turns)` → `build_messages(turns, character, user_name="User")` where `character` is a minimal `Character(name="Test")`

**New tests for `TestBuildSystemPrompt`:**
- roleplay-parity-289.AC2.3: System prompt has correct slot order — system_prompt text appears before description, description before personality, personality before scenario, mes_example after scenario
- roleplay-parity-289.AC2.4: before_char lorebook entries appear between system_prompt and description; after_char entries appear between scenario and mes_example
- roleplay-parity-289.AC2.4: All entries before_char by default (no after_char entries) — all lorebook content appears before description
- roleplay-parity-289.AC2.6: Placeholder substitution applied to mes_example content

**New tests for `TestBuildMessages`:**
- roleplay-parity-289.AC2.5: post_history_instructions appended as final user message when non-empty
- roleplay-parity-289.AC2.5: Empty post_history_instructions produces no extra message
- roleplay-parity-289.AC2.6: Placeholder substitution applied to post_history_instructions

**Updated existing tests:**
- `test_injects_lorebook_before_character` — update to verify lorebook appears between system_prompt and description (not just "before character")
- `test_lorebook_sorted_by_order` — should still pass (ordering within position group unchanged)

**Verification:**
Run: `uv run grimoire test run tests/unit/test_prompt_assembly.py`
Expected: All tests pass including new ones

**Commit:** `feat: add post_history_instructions injection and update prompt assembly tests for ST parity`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

---

## UAT Steps

1. [ ] Run tests: `uv run grimoire test run tests/unit/test_prompt_assembly.py`
2. [ ] Verify all prompt assembly tests pass (slot ordering, lorebook splitting, post_history_instructions)
3. [ ] Run: `uvx ty check` — verify no type errors from signature changes
4. [ ] Start the app: `uv run run.py`
5. [ ] Navigate to `/roleplay` and send a message
6. [ ] Verify the conversation works (no regression from prompt restructuring)

## Evidence Required

- [ ] Test output showing all prompt assembly tests green
- [ ] `uvx ty check` output clean
- [ ] Successful one-turn conversation in the app
