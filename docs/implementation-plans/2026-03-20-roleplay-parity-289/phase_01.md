# Roleplay Parity Implementation Plan — Phase 1: Model and Parser Updates

**Goal:** Extend Character and LorebookEntry models with ST-parity fields; update parser to extract them.

**Architecture:** Add `mes_example`, `post_history_instructions` to Character; add `position` to LorebookEntry. Update `parse_character_card()` and `_parse_lorebook_entries()` to extract these from chara_card_v3 JSON. Pure data model + parser changes, no side effects.

**Tech Stack:** Python 3.14 dataclasses, JSON parsing

**Scope:** Phase 1 of 7 from original design

**Codebase verified:** 2026-03-20

---

## Acceptance Criteria Coverage

This phase implements and tests:

### roleplay-parity-289.AC2: Prompt construction parity
- **roleplay-parity-289.AC2.1 Success:** Parser extracts `mes_example`, `post_history_instructions`, and lorebook entry `position` from chara_card_v3 JSON
- **roleplay-parity-289.AC2.2 Edge:** Missing or empty card fields produce empty strings (no errors); lorebook entries without `extensions.position` default to `before_char`

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add ST-parity fields to Character and LorebookEntry models

**Verifies:** roleplay-parity-289.AC2.1, roleplay-parity-289.AC2.2

**Files:**
- Modify: `src/promptgrimoire/models/scenario.py:28-58` (LorebookEntry) and `src/promptgrimoire/models/scenario.py:61-83` (Character)

**Implementation:**

Add `position` field to `LorebookEntry` after `match_whole_words` (line 58):

```python
position: str = "before_char"
```

Add `mes_example` and `post_history_instructions` fields to `Character` after `user_persona_name` (line 83):

```python
mes_example: str = ""
post_history_instructions: str = ""
```

Update the `LorebookEntry` docstring to include:
```
position: Prompt insertion position — "before_char" (before character description)
          or "after_char" (after scenario). Defaults to "before_char".
```

Update the `Character` docstring to include:
```
mes_example: Example dialogue demonstrating how the character speaks.
post_history_instructions: Reminder injected as final user message after chat history.
```

**Verification:**
Run: `uvx ty check`
Expected: No new type errors

**Commit:** `feat: add mes_example, post_history_instructions, and position fields to roleplay models`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update parser to extract new fields and add tests

**Verifies:** roleplay-parity-289.AC2.1, roleplay-parity-289.AC2.2

**Files:**
- Modify: `src/promptgrimoire/parsers/sillytavern.py:18-65` (parse_character_card) and `src/promptgrimoire/parsers/sillytavern.py:79-108` (_parse_lorebook_entries)
- Test: `tests/unit/test_sillytavern_parser.py` (unit)

**Implementation:**

In `parse_character_card()` at `sillytavern.py:52-60`, add extraction of `mes_example` and `post_history_instructions` from the `data` block (same pattern as `system_prompt`):

```python
character = Character(
    name=raw["name"],
    description=_clean_text(raw.get("description", "")),
    personality=_clean_text(raw.get("personality", "")),
    scenario=_clean_text(raw.get("scenario", "")),
    first_mes=_clean_text(raw.get("first_mes", "")),
    system_prompt=_clean_text(data.get("system_prompt", "")),
    user_persona_name=_extract_user_persona(),
    mes_example=_clean_text(data.get("mes_example", "")),
    post_history_instructions=_clean_text(data.get("post_history_instructions", "")),
)
```

In `_parse_lorebook_entries()` at `sillytavern.py:87-106`, add position extraction from `extensions.position` with numeric-to-string mapping. Add after the `match_whole_words` line:

```python
position=_map_lorebook_position(
    raw_entry.get("extensions", {}).get("position")
),
```

Add a new helper function after `_get_scan_depth()`:

```python
_POSITION_MAP: dict[int, str] = {0: "before_char", 1: "after_char"}


def _map_lorebook_position(value: int | None) -> str:
    """Map numeric lorebook position to string identifier.

    SillyTavern stores position as: 0 = before_char, 1 = after_char.
    Unknown or missing values default to "before_char".
    """
    if value is None:
        return "before_char"
    return _POSITION_MAP.get(value, "before_char")
```

**Testing:**

Tests must verify each AC listed above:
- roleplay-parity-289.AC2.1: Parser extracts `mes_example`, `post_history_instructions` from character card; parser extracts `position` from lorebook entries
- roleplay-parity-289.AC2.2: Empty/missing fields produce empty strings; missing `extensions.position` defaults to `"before_char"`

Specific test cases:
1. Becky Bennett fixture: `mes_example` and `post_history_instructions` are empty strings (verifies empty extraction works)
2. Becky Bennett fixture: all 5 lorebook entries have `position == "before_char"` (verifies numeric 0 → string mapping)
3. Synthetic card (via `tmp_path`): non-empty `mes_example` value is extracted correctly
4. Synthetic card (via `tmp_path`): non-empty `post_history_instructions` value is extracted correctly
5. Synthetic card (via `tmp_path`): lorebook entry with `extensions.position: 1` produces `position == "after_char"`
6. Synthetic card (via `tmp_path`): lorebook entry with no `extensions.position` defaults to `"before_char"`

Follow existing test patterns: class-based organisation (`TestParseCharacterCard`), real fixture for Becky Bennett cases, `tmp_path` JSON for synthetic cases (same pattern as `test_invalid_json_raises` and `test_missing_name_raises`).

**Verification:**
Run: `uv run grimoire test run tests/unit/test_sillytavern_parser.py`
Expected: All tests pass including new ones

**Commit:** `feat: extract mes_example, post_history_instructions, and lorebook position from character cards`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

---

## UAT Steps

1. [ ] Run tests: `uv run grimoire test run tests/unit/test_sillytavern_parser.py`
2. [ ] Verify all new tests pass (mes_example, post_history_instructions, position extraction)
3. [ ] Start the app: `uv run run.py`
4. [ ] Navigate to `/roleplay`
5. [ ] Verify the Becky Bennett character loads without errors (no regression)

## Evidence Required

- [ ] Test output showing all parser tests green
- [ ] `uvx ty check` output clean
- [ ] App starts and roleplay page loads without errors
