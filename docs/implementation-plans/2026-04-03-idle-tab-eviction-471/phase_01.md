# Idle Tab Eviction Implementation Plan

**Goal:** Add `IdleConfig` pydantic-settings sub-model with kill switch for idle tab eviction

**Architecture:** Single `IdleConfig(BaseModel)` class added to `src/promptgrimoire/config.py` following the existing sub-model pattern. Registered in root `Settings` class. Accessed via `get_settings().idle`.

**Tech Stack:** pydantic, pydantic-settings (already in use)

**Scope:** 7 phases from original design (phases 1-7). Design AC6 (Login page element reduction) is deliberately not implemented — replaced by the pre-auth `/welcome` landing page (Phase 5, AC7).

**Codebase verified:** 2026-04-03

---

## Acceptance Criteria Coverage

This phase implements and tests:

### idle-tab-eviction-471.AC5: Configurable via pydantic-settings
- **idle-tab-eviction-471.AC5.1 Success:** `IDLE__TIMEOUT_SECONDS=900` sets idle timeout to 15 minutes
- **idle-tab-eviction-471.AC5.2 Success:** `IDLE__WARNING_SECONDS=120` sets warning countdown to 2 minutes
- **idle-tab-eviction-471.AC5.3 Success:** `IDLE__ENABLED=false` disables idle eviction entirely (no script injected, no event listeners attached)
- **idle-tab-eviction-471.AC5.4 Success:** Defaults are 1800s timeout, 60s warning, enabled=true

---

**Note:** Task ordering is implementation-first because this is an infrastructure phase (config scaffolding, verified operationally). TDD applies to functionality tasks, not config registration. See writing-implementation-plans § Task Types.

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: IdleConfig sub-model and Settings registration

**Verifies:** idle-tab-eviction-471.AC5.4

**Files:**
- Modify: `src/promptgrimoire/config.py:199` (after `HelpConfig`, before `Settings`)
- Modify: `src/promptgrimoire/config.py:336` (add `idle` field to `Settings`)

**Implementation:**

Add `IdleConfig` class after `HelpConfig` (around line 199), following the `ExportConfig` minimal pattern:

```python
class IdleConfig(BaseModel):
    """Idle tab eviction configuration."""

    timeout_seconds: int = 1800
    warning_seconds: int = 60
    enabled: bool = True
```

Register in `Settings` class (around line 336, after `help` field):

```python
idle: IdleConfig = IdleConfig()
```

**Verification:**

Run: `uv run python -c "from promptgrimoire.config import Settings; s = Settings(_env_file=None); print(s.idle.timeout_seconds, s.idle.warning_seconds, s.idle.enabled)"`
Expected: `1800 60 True`

**Commit:** `feat(config): add IdleConfig pydantic-settings sub-model`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: IdleConfig unit tests

**Verifies:** idle-tab-eviction-471.AC5.1, idle-tab-eviction-471.AC5.2, idle-tab-eviction-471.AC5.3, idle-tab-eviction-471.AC5.4

**Files:**
- Create: `tests/unit/test_idle_config.py`

**Testing:**

Follow the existing pattern from `tests/unit/test_config.py`:

- idle-tab-eviction-471.AC5.4: Test that `IdleConfig()` has correct defaults (1800, 60, True) and that `Settings(_env_file=None).idle` is an `IdleConfig` instance with those defaults. Clear any `IDLE__*` env vars with monkeypatch first.
- idle-tab-eviction-471.AC5.1: Set `IDLE__TIMEOUT_SECONDS=900` via `monkeypatch.setenv`, instantiate `Settings(_env_file=None)`, assert `s.idle.timeout_seconds == 900`.
- idle-tab-eviction-471.AC5.2: Set `IDLE__WARNING_SECONDS=120` via `monkeypatch.setenv`, instantiate `Settings(_env_file=None)`, assert `s.idle.warning_seconds == 120`.
- idle-tab-eviction-471.AC5.3: Set `IDLE__ENABLED=false` via `monkeypatch.setenv`, instantiate `Settings(_env_file=None)`, assert `s.idle.enabled is False`.

Use the `Settings(_env_file=None)` pattern for test isolation (avoids loading `.env` files). Clear interfering `IDLE__*` env vars before testing defaults.

**Verification:**

Run: `uv run grimoire test run tests/unit/test_idle_config.py`
Expected: All tests pass

**Commit:** `test(config): add IdleConfig default and env var override tests`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
