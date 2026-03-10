# Roleplay Privileged Access Implementation Plan - Phase 1: Navigation Filtering

**Goal:** Hide all roleplay-marked navigation entries from non-privileged users while preserving existing feature-flag behavior.

**Architecture:** Extend the existing registry-level page filter in `src/promptgrimoire/pages/registry.py` so privilege is evaluated in the same place as auth, admin, demo, and roleplay feature-flag checks. Apply the new rule to every page with `requires_roleplay=True`, which currently covers both `/roleplay` and `/logs`.

**Tech Stack:** Python 3.14, NiceGUI page registry, pytest unit tests

**Scope:** Phase 1 of 2 from original design

**Codebase verified:** 2026-03-04

**Testing documentation:** `/home/brian/people/Brian/PromptGrimoireTool/AGENTS.md`, `/home/brian/people/Brian/PromptGrimoireTool/docs/testing.md`

---

## Acceptance Criteria Coverage

This phase implements and tests:

### roleplay-privileged-access-258.AC2: Non-privileged users do not see roleplay in navigation
- **roleplay-privileged-access-258.AC2.1 Success:** Authenticated non-privileged user does not see `Roleplay` in navigation
- **roleplay-privileged-access-258.AC2.2 Success:** Authenticated privileged user still sees `Roleplay` in navigation when the roleplay feature flag is enabled
- **roleplay-privileged-access-258.AC2.3 Edge:** Existing roleplay feature-flag filtering still hides `Roleplay` for all users when the feature is disabled

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add navigation visibility tests for privileged roleplay pages

**Verifies:** roleplay-privileged-access-258.AC2.1, roleplay-privileged-access-258.AC2.2, roleplay-privileged-access-258.AC2.3

**Files:**
- Modify: `tests/unit/test_settings.py:210-246`

**Implementation:**

Expand `TestPageRegistryRoleplayFlag` in `tests/unit/test_settings.py` so it covers privilege-sensitive visibility, not just the roleplay feature flag.

Keep the existing feature-flag coverage but tighten the assertions to reflect all current `requires_roleplay=True` pages. The tests should assert on both `/roleplay` and `/logs`, because the registry currently marks both pages as roleplay-gated.

Add these test cases:

1. `test_roleplay_pages_hidden_for_non_privileged_user_when_enabled`
   - Call `get_visible_pages()` with `user={"email": "student@example.com", "is_admin": False, "roles": []}` and `roleplay_enabled=True`
   - Assert `/roleplay` and `/logs` are absent from the returned routes

2. `test_roleplay_pages_shown_for_privileged_user_when_enabled`
   - Call `get_visible_pages()` with a privileged auth payload such as `{"email": "staff@example.com", "is_admin": False, "roles": ["instructor"]}`
   - Assert `/roleplay` and `/logs` are present in the returned routes

3. Keep or rename the existing feature-flag test so it still proves `roleplay_enabled=False` hides all `requires_roleplay=True` pages even for a privileged user

Do not create a new test module. The current registry/feature-flag tests already live in `tests/unit/test_settings.py`, and this phase should extend that existing coverage point.

**Testing:**

Tests must verify each AC listed above:
- roleplay-privileged-access-258.AC2.1: Non-privileged authenticated user does not see either roleplay-marked page
- roleplay-privileged-access-258.AC2.2: Privileged authenticated user sees both roleplay-marked pages when the feature flag is enabled
- roleplay-privileged-access-258.AC2.3: Feature flag still overrides privilege and hides both pages when disabled

Follow existing project test style:
- plain pytest unit tests
- descriptive test names and docstrings
- no network or database usage

**Verification:**

Run: `uv run pytest tests/unit/test_settings.py -v`
Expected: The new privilege-sensitive tests fail before the registry implementation changes, and the existing non-roleplay settings tests continue to run.

**Commit:** `test: add privileged roleplay navigation coverage`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Filter roleplay-marked pages by privilege in the registry

**Verifies:** roleplay-privileged-access-258.AC2.1, roleplay-privileged-access-258.AC2.2, roleplay-privileged-access-258.AC2.3

**Files:**
- Modify: `src/promptgrimoire/pages/registry.py:7-160`
- Modify: `tests/unit/test_settings.py:210-246`

**Implementation:**

Update `src/promptgrimoire/pages/registry.py` so `get_visible_pages()` applies privilege filtering to any page with `requires_roleplay=True`.

1. Add:

```python
from promptgrimoire.auth import is_privileged_user
```

near the existing imports.

2. In `get_visible_pages()`, after the existing feature-flag check:

```python
        if meta.requires_roleplay and not roleplay_enabled:
            continue
```

add a second check:

```python
        if meta.requires_roleplay and not is_privileged_user(user):
            continue
```

This keeps the current meaning of `requires_roleplay=True` for feature-flag filtering, then layers the new privilege rule on top. It also ensures future pages that opt into `requires_roleplay=True` inherit the same nav visibility behavior automatically.

Do not add new page metadata fields. Do not special-case literal routes like `"/roleplay"` or `"/logs"`. The implementation should follow the existing registry pattern and act on `PageMeta.requires_roleplay`.

After the code change:
- run `ruff format` if import ordering or wrapping changes
- keep the function signature for `get_visible_pages()` unchanged
- do not modify `get_pages_by_category()` beyond relying on the updated `get_visible_pages()`

**Testing:**

Re-run the updated tests from Task 1 and confirm they now pass. The assertions should prove that:
- non-privileged users lose both `/roleplay` and `/logs`
- privileged users retain both when the feature flag is enabled
- the feature flag still hides both for everyone when disabled

**Verification:**

Run: `uv run pytest tests/unit/test_settings.py -v`
Expected: All settings and page-registry tests pass.

Run: `uv run ruff check src/promptgrimoire/pages/registry.py tests/unit/test_settings.py`
Expected: No lint errors.

Run: `uv run ruff format src/promptgrimoire/pages/registry.py tests/unit/test_settings.py --check`
Expected: No formatting changes needed after final edits.

Run: `uvx ty check`
Expected: No type errors in the modified registry or test module.

**Commit:** `feat: hide roleplay navigation from non-privileged users`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
