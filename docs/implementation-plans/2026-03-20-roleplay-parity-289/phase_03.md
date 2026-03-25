# Roleplay Parity Implementation Plan — Phase 3: Audit Logging

**Goal:** Add debug mode that dumps the complete API request payload for 1:1 comparison with SillyTavern logs.

**Architecture:** New `RoleplayConfig` sub-model with `audit_log` flag. When enabled, `ClaudeClient` writes the full `_build_api_params()` output as JSON alongside the JSONL chat log. Thin config addition + client-level serialisation.

**Tech Stack:** Python 3.14, pydantic-settings, json module

**Scope:** Phase 3 of 7 from original design

**Codebase verified:** 2026-03-20

---

## Acceptance Criteria Coverage

This phase implements and tests:

### roleplay-parity-289.AC2: Prompt construction parity
- **roleplay-parity-289.AC2.7 Success:** Audit log mode produces a JSON file containing the full API request payload (system, messages, model, max_tokens) matching Anthropic Messages API schema

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add RoleplayConfig sub-model with audit_log flag

**Verifies:** roleplay-parity-289.AC2.7 (config prerequisite)

**Files:**
- Modify: `src/promptgrimoire/config.py` — add RoleplayConfig sub-model

**Implementation:**

Add a new `RoleplayConfig` sub-model (follow the pattern of `LlmConfig`, `AppConfig`, etc.):

```python
class RoleplayConfig(BaseModel):
    """Configuration for roleplay simulation features."""

    audit_log: bool = False
```

Add `roleplay: RoleplayConfig = RoleplayConfig()` to the root `Settings` class, following the pattern of other sub-models.

The env var `ROLEPLAY__AUDIT_LOG=true` will be automatically handled by pydantic-settings' nested model delimiter (`__`).

**Verification:**
Run: `uvx ty check`
Expected: No new type errors

**Commit:** `feat: add RoleplayConfig sub-model with audit_log flag`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add audit log writing to ClaudeClient and update roleplay page

**Verifies:** roleplay-parity-289.AC2.7

**Files:**
- Modify: `src/promptgrimoire/llm/client.py:23-255` (ClaudeClient)
- Modify: `src/promptgrimoire/pages/roleplay.py` (pass audit config to client)
- Test: `tests/unit/test_claude_client.py` (unit)

**Implementation:**

Add an `audit_log_path` parameter to `ClaudeClient.__init__()`:

```python
def __init__(
    self,
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
    thinking_budget: int = 1024,
    lorebook_budget: int = 0,
    audit_log_path: Path | None = None,
):
    ...
    self._audit_log_path = audit_log_path
```

Add a private method `_write_audit_log()` that serialises and writes the API params:

```python
def _write_audit_log(self, params: dict[str, Any]) -> None:
    """Write API request payload as JSON for audit comparison."""
    if self._audit_log_path is None:
        return
    self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    self._audit_log_path.write_text(
        json.dumps(params, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
```

Call `_write_audit_log(params)` in `stream_message_only()` right after `_build_api_params()` returns and before the API call is made.

In the roleplay page (`_setup_session()`), when `settings.roleplay.audit_log` is `True`, construct the audit log path from the JSONL log path (replace `.jsonl` with `_audit.json`) and pass it to `ClaudeClient`:

```python
audit_path = log_path.with_name(log_path.stem + "_audit.json") if settings.roleplay.audit_log else None
# Pass audit_log_path=audit_path to ClaudeClient constructor
```

**Testing:**

Tests must verify:
- roleplay-parity-289.AC2.7: When audit_log_path is set, a JSON file is written containing keys `system`, `messages`, `model`, `max_tokens`
- roleplay-parity-289.AC2.7: When audit_log_path is None, no file is written
- roleplay-parity-289.AC2.7: JSON structure matches Anthropic Messages API schema (system is string, messages is list of dicts with role/content)

Follow existing test patterns in `test_claude_client.py` — mock the Anthropic client with `@patch` and `AsyncMock`. Use `tmp_path` for audit file output.

**Verification:**
Run: `uv run grimoire test run tests/unit/test_claude_client.py`
Expected: All tests pass including new audit log tests

**Commit:** `feat: add API request audit logging for SillyTavern parity comparison`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

---

## UAT Steps

1. [ ] Run tests: `uv run grimoire test run tests/unit/test_claude_client.py`
2. [ ] Set `ROLEPLAY__AUDIT_LOG=true` in environment
3. [ ] Start the app: `uv run run.py`
4. [ ] Navigate to `/roleplay` and send one message
5. [ ] Check the `logs/` directory for a `*_audit.json` file
6. [ ] Open the JSON file and verify it contains `system`, `messages`, `model`, `max_tokens` keys

## Evidence Required

- [ ] Test output showing all client tests green
- [ ] `uvx ty check` output clean
- [ ] Screenshot or contents of audit JSON file showing correct structure
