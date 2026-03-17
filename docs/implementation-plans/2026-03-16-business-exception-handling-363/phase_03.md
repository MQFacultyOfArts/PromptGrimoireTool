# Business Exception Handling Implementation Plan — Phase 3

**Goal:** Hide "Share with user" button when sharing is disabled for non-staff users. Staff retain bypass.

**Architecture:** Single-line guard change in `sharing.py:68`. Unit tests verify all 4 AC combinations by testing the conditional logic with mocked NiceGUI ui.

**Tech Stack:** Python 3.14, NiceGUI, pytest

**Scope:** 4 phases from original design (phases 1-4). This is Phase 3.

**Codebase verified:** 2026-03-16

---

## Acceptance Criteria Coverage

This phase implements and tests:

### business-exception-handling-363.AC3: Share Button Visibility
- **business-exception-handling-363.AC3.1 Success:** Share button rendered when `allow_sharing=True` and `can_manage_sharing=True`
- **business-exception-handling-363.AC3.2 Failure:** Share button NOT rendered when `allow_sharing=False` and `viewer_is_privileged=False`, regardless of `can_manage_sharing`
- **business-exception-handling-363.AC3.3 Success:** Share button rendered for staff (`viewer_is_privileged=True`) even when `allow_sharing=False` — staff bypass preserved
- **business-exception-handling-363.AC3.4 Success:** "Share with class" toggle still gated on both `allow_sharing` and `can_manage_sharing` (regression guard)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Fix share button visibility guard

**Verifies:** business-exception-handling-363.AC3.1, business-exception-handling-363.AC3.2, business-exception-handling-363.AC3.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/sharing.py` — line 68

**Implementation:**

Change the guard at line 68 from:
```python
if can_manage_sharing:
```

To:
```python
if (allow_sharing or viewer_is_privileged) and can_manage_sharing:
```

This ensures:
- Non-staff users see the button only when `allow_sharing=True` AND `can_manage_sharing=True`
- Staff users (`viewer_is_privileged=True`) see the button whenever `can_manage_sharing=True`, regardless of `allow_sharing`

Do NOT modify line 48 ("Share with class" toggle) — it correctly gates on `allow_sharing and can_manage_sharing` with no staff bypass. This is intentional per the design.

**Verification:**

```bash
# Verify the change parses
uv run python -c "
import ast
with open('src/promptgrimoire/pages/annotation/sharing.py') as f:
    ast.parse(f.read())
print('sharing.py parses successfully')
"
```

**Commit:** `fix: gate share button on allow_sharing with staff bypass`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Unit tests for share button visibility

**Verifies:** business-exception-handling-363.AC3.1, business-exception-handling-363.AC3.2, business-exception-handling-363.AC3.3, business-exception-handling-363.AC3.4

**Files:**
- Create: `tests/unit/test_sharing_button_visibility.py`

**Testing:**

**Test approach:** The guard conditions at lines 48 and 68 are pure boolean expressions evaluated before any NiceGUI rendering. We test the boolean logic directly — no NiceGUI context needed. This keeps tests in the **unit lane** (xdist-compatible, no `nicegui_ui` marker required).

Two complementary strategies:
1. **Pure logic tests** — parametrized tests that evaluate the boolean expressions `(allow_sharing or viewer_is_privileged) and can_manage_sharing` (line 68) and `allow_sharing and can_manage_sharing` (line 48) with all AC combinations.
2. **Structural guard test** — use ast-grep to verify the exact guard expression in `sharing.py:68` matches `(allow_sharing or viewer_is_privileged) and can_manage_sharing`. This prevents silent regressions if someone simplifies the condition.

Test cases (parametrized boolean logic):
- business-exception-handling-363.AC3.1: `allow_sharing=True, can_manage_sharing=True, viewer_is_privileged=False` → expression evaluates True (button visible)
- business-exception-handling-363.AC3.2: `allow_sharing=False, can_manage_sharing=True, viewer_is_privileged=False` → expression evaluates False (button hidden)
- business-exception-handling-363.AC3.3: `allow_sharing=False, can_manage_sharing=True, viewer_is_privileged=True` → expression evaluates True (staff bypass)
- business-exception-handling-363.AC3.4: Regression guard — verify line 48's expression `allow_sharing and can_manage_sharing` evaluates to False when `allow_sharing=False` even with `viewer_is_privileged=True` (no staff bypass on class toggle)

Additional edge cases:
- `can_manage_sharing=False` → both expressions evaluate False regardless of other flags
- `allow_sharing=True, can_manage_sharing=False` → both evaluate False

**Verification:**

```bash
uv run grimoire test run tests/unit/test_sharing_button_visibility.py
uv run grimoire test all
```

**Commit:** `test: add share button visibility tests covering AC3.1-AC3.4`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_3 -->
### Task 3: Run complexipy on modified files

**Files:** None (diagnostic only)

**Verification:**

```bash
uv run complexipy src/promptgrimoire/pages/annotation/sharing.py --max-complexity-allowed 15
```

The change is a single-line condition modification. Unlikely to affect complexity. If the file already has functions near the threshold, note them.

No commit needed for this task.
<!-- END_TASK_3 -->

## UAT Steps

1. [ ] Start the app: `uv run run.py`
2. [ ] Log in as a **non-staff** user who owns a workspace with `allow_sharing=False` (e.g., workspace in a course with sharing disabled)
3. [ ] Navigate to the annotation page for that workspace
4. [ ] Verify: The "Share with user" button is NOT visible
5. [ ] Log in as a **staff** user (instructor or admin)
6. [ ] Navigate to the same workspace
7. [ ] Verify: The "Share with user" button IS visible (staff bypass)
8. [ ] Navigate to a workspace with `allow_sharing=True` as a non-staff user
9. [ ] Verify: The "Share with user" button IS visible

## Evidence Required
- [ ] Test output showing green (`uv run grimoire test all`)
- [ ] Screenshot: non-staff user cannot see share button when sharing disabled
- [ ] Screenshot: staff user can see share button when sharing disabled
