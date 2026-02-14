# Per-Activity Copy Protection Implementation Plan — Phase 3

**Goal:** Pure function for role check and wiring into annotation page lifecycle.

**Architecture:** `is_privileged_user()` lives in `src/promptgrimoire/auth/__init__.py` as a shared utility. It checks `auth_user["is_admin"]` and membership in `{"instructor", "stytch_admin"}` roles. The annotation page retrieves `auth_user` from `app.storage.user`, calls `get_placement_context()`, and computes `protect = ctx.copy_protection and not is_privileged_user(auth_user)`. The `protect` flag is threaded to JS injection in Phase 4.

**Tech Stack:** Python 3.14, NiceGUI (app.storage.user), Stytch roles

**Scope:** Phase 3 of 6 from original design

**Codebase verified:** 2026-02-13

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 103-copy-protection.AC5: Instructor/admin bypass
- **103-copy-protection.AC5.1 Success:** Admin user sees no protection even when `copy_protection=True`
- **103-copy-protection.AC5.2 Success:** User with `instructor` role sees no protection
- **103-copy-protection.AC5.3 Success:** User with `stytch_admin` role sees no protection
- **103-copy-protection.AC5.4 Failure:** Student sees protection when `copy_protection=True`
- **103-copy-protection.AC5.5 Failure:** Tutor sees protection when `copy_protection=True`
- **103-copy-protection.AC5.6 Edge:** Unauthenticated user sees protection when `copy_protection=True`

---

## Reference Files

The executor should read these files for context:

- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/src/promptgrimoire/auth/__init__.py` — Auth module public API
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/src/promptgrimoire/pages/auth.py` — Auth user dict construction (lines 58-68)
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/src/promptgrimoire/pages/annotation.py` — `_render_workspace_view()` at line 2881
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/tests/unit/pages/test_annotation_tags.py` — Example of pure function unit tests

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create is_privileged_user() in auth module

**Verifies:** 103-copy-protection.AC5.1, AC5.2, AC5.3, AC5.4, AC5.5, AC5.6

**Files:**
- Modify: `src/promptgrimoire/auth/__init__.py` (add function + export)
- Test: `tests/unit/test_auth_roles.py` (unit — new file, pure function tests)

**Implementation:**

Add to `src/promptgrimoire/auth/__init__.py`:

```python
_PRIVILEGED_ROLES = frozenset({"instructor", "stytch_admin"})


def is_privileged_user(auth_user: dict[str, object] | None) -> bool:
    """Check if user has instructor or admin privileges.

    Returns True if the user is an org-level admin or has an instructor/stytch_admin
    role. Returns False for students, tutors, unauthenticated users, or missing data.
    """
    if auth_user is None:
        return False
    if auth_user.get("is_admin") is True:
        return True
    roles = auth_user.get("roles")
    if not isinstance(roles, list):
        return False
    return bool(_PRIVILEGED_ROLES & set(roles))
```

Add `"is_privileged_user"` to `__all__`.

**Testing:**

Test class: `TestIsPrivilegedUser` in `tests/unit/test_auth_roles.py`

Tests must verify each AC listed above:
- AC5.1: `auth_user={"is_admin": True, "roles": []}` returns True
- AC5.2: `auth_user={"is_admin": False, "roles": ["instructor"]}` returns True
- AC5.3: `auth_user={"is_admin": False, "roles": ["stytch_admin"]}` returns True
- AC5.4: `auth_user={"is_admin": False, "roles": []}` (student) returns False
- AC5.5: `auth_user={"is_admin": False, "roles": ["tutor"]}` returns False
- AC5.6: `auth_user=None` (unauthenticated) returns False
- Edge: `auth_user={}` (missing keys) returns False
- Edge: `auth_user={"is_admin": False, "roles": None}` returns False

**Verification:**

Run:
```bash
uv run pytest tests/unit/test_auth_roles.py -v
```

Expected: All tests pass.

**Commit:**

```bash
git add src/promptgrimoire/auth/__init__.py tests/unit/test_auth_roles.py
git commit -m "feat: add is_privileged_user() to auth module for copy protection bypass"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Wire protection decision into annotation page

**Verifies:** None new (wiring only — protection effect verified in Phase 4 E2E tests)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py:2881+` (`_render_workspace_view()` — add protection flag computation)

**Implementation:**

In `_render_workspace_view()`, after the workspace and documents are loaded, compute the protection flag:

1. Retrieve auth_user: `auth_user = app.storage.user.get("auth_user")`
2. Get placement context: `ctx = await get_placement_context(workspace_id)` — note that `get_placement_context()` is currently called inside `_render_workspace_header()` (line 2659) but its result is NOT returned to `_render_workspace_view()`. Add a new call in `_render_workspace_view()` before computing the protect flag. (The call is cheap — single DB query.)
3. Compute: `protect = ctx.copy_protection and not is_privileged_user(auth_user)`
4. Store `protect` as a local variable in `_render_workspace_view()`. Phase 4 will consume it by passing `protect` as an argument to `_inject_copy_protection(protect)` (called at the end of `_render_workspace_view()` after the three-tab container) and to `_render_workspace_header(..., protect=protect)` (for the lock icon chip). For now, just compute the variable — no function calls yet.

Import at the top of annotation.py:
```python
from promptgrimoire.auth import is_privileged_user
```

The `protect` boolean determines whether Phase 4 injects client-side protections. For now, just compute and store it as a local variable — no JS injection yet.

**Verification:**

Run:
```bash
uv run test-all
```

Expected: All tests pass (no behavioral change yet — just wiring).

**Commit:**

```bash
git add src/promptgrimoire/pages/annotation.py
git commit -m "feat: compute copy protection flag in annotation page lifecycle"
```

**UAT Steps (end of Phase 3):**

1. [ ] Verify tests: `uv run test-all` — all pass, including `TestIsPrivilegedUser`
2. [ ] Start the app: `uv run python -m promptgrimoire`
3. [ ] Seed data (`uv run seed-data`), then enable copy protection on the seed activity via SQL: `UPDATE activity SET copy_protection = true WHERE title = 'Annotate Becky Bennett Interview';` — navigate to an annotation page for that activity
4. [ ] As instructor: verify `protect` is False (no JS injection — DevTools console shows no copy protection script)
5. [ ] As student: verify `protect` is True (Phase 4 will make this observable — for now, add a temporary `print(f"protect={protect}")` to server logs to verify)

**Evidence Required:**
- [ ] Test output showing all `TestIsPrivilegedUser` tests green
- [ ] Server log showing `protect=True` for student, `protect=False` for instructor (temporary log line)
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
