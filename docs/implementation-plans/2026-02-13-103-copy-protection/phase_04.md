# Per-Activity Copy Protection Implementation Plan — Phase 4

**Goal:** JS event interception for copy, cut, paste, drag, and right-click on protected content areas. Student-facing lock icon chip and toast notifications.

**Architecture:** Single JS block injected via `ui.run_javascript()` when `protect=True`. Uses event delegation from protected selectors. Copy/cut/contextmenu/dragstart intercepted on `#doc-container`, `[data-testid="organise-columns"]`, `[data-testid="respond-reference-panel"]`. Paste intercepted on `#milkdown-respond-editor` in capture phase (before ProseMirror). Debounced toast via `Quasar.Notify.create()` with `group` key. Lock icon chip added to workspace header alongside placement chip.

**Tech Stack:** JavaScript (DOM events), Quasar.Notify, NiceGUI (ui.run_javascript, ui.chip)

**Scope:** Phase 4 of 6 from original design

**Codebase verified:** 2026-02-13

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 103-copy-protection.AC4: Client-side protections (E2E)
- **103-copy-protection.AC4.1 Success:** Copy blocked on Tab 1 document content for student
- **103-copy-protection.AC4.2 Success:** Copy blocked on Tab 2 organise cards for student
- **103-copy-protection.AC4.3 Success:** Copy blocked on Tab 3 reference cards for student
- **103-copy-protection.AC4.4 Success:** Cut blocked on same protected areas
- **103-copy-protection.AC4.5 Success:** Right-click context menu blocked on protected areas
- **103-copy-protection.AC4.7 Success:** Drag-text-out blocked on protected areas
- **103-copy-protection.AC4.8 Success:** Paste blocked in Milkdown editor for student
- **103-copy-protection.AC4.9 Success:** Copy from Milkdown editor (student's own writing) still works
- **103-copy-protection.AC4.10 Success:** Text selection for highlighting unaffected by protection
- **103-copy-protection.AC4.11 Success:** Debounced toast notification shown on blocked action
- **103-copy-protection.AC4.12 Failure:** Protection not active when `copy_protection=False` on activity
- **103-copy-protection.AC4.13 Failure:** Protection not active for loose workspace

### 103-copy-protection.AC6: Student-facing indicator
- **103-copy-protection.AC6.1 Success:** Lock icon chip visible in header when protection active
- **103-copy-protection.AC6.2 Success:** Lock chip tooltip reads "Copy protection is enabled for this activity"
- **103-copy-protection.AC6.3 Failure:** Lock chip not visible when protection inactive

---

## Reference Files

The executor should read these files for context:

- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/src/promptgrimoire/pages/annotation.py` — `_render_workspace_view()` at line 2881, `_render_workspace_header()` at line 2613, JS injection patterns throughout
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/src/promptgrimoire/pages/annotation_organise.py` — Tab 2 selectors
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/src/promptgrimoire/pages/annotation_respond.py` — Tab 3 selectors, Milkdown editor ID
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/tests/e2e/test_annotation_tabs.py` — E2E test patterns for tab interactions

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Inject copy protection JS and lock icon chip

**Verifies:** 103-copy-protection.AC4.1, AC4.2, AC4.3, AC4.4, AC4.5, AC4.7, AC4.8, AC4.9, AC4.10, AC4.11, AC6.1, AC6.2, AC6.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py` — inject JS block when `protect=True`, add lock chip to header
- Test: `tests/unit/test_copy_protection_js.py` (unit — verify JS string generation)

**Implementation:**

Create a function `_inject_copy_protection(state)` in annotation.py (or a helper module) that:

1. Injects a JS block via `ui.run_javascript()` containing:

```javascript
(function() {
  const PROTECTED = '#doc-container, [data-testid="organise-columns"], [data-testid="respond-reference-panel"]';

  function isProtected(e) {
    return e.target.closest && e.target.closest(PROTECTED);
  }

  function showToast() {
    Quasar.Notify.create({
      message: 'Copying is disabled for this activity.',
      type: 'warning',
      position: 'top-right',
      timeout: 3000,
      icon: 'content_copy',
      group: 'copy-protection'
    });
  }

  // Copy/cut on protected areas only
  document.addEventListener('copy', function(e) {
    if (isProtected(e)) { e.preventDefault(); showToast(); }
  }, true);
  document.addEventListener('cut', function(e) {
    if (isProtected(e)) { e.preventDefault(); showToast(); }
  }, true);

  // Right-click on protected areas
  document.addEventListener('contextmenu', function(e) {
    if (isProtected(e)) { e.preventDefault(); showToast(); }
  }, true);

  // Drag on protected areas
  document.addEventListener('dragstart', function(e) {
    if (isProtected(e)) { e.preventDefault(); showToast(); }
  }, true);

  // Paste blocked on Milkdown editor (capture phase — before ProseMirror)
  var editor = document.querySelector('#milkdown-respond-editor');
  if (editor) {
    editor.addEventListener('paste', function(e) {
      e.preventDefault();
      e.stopImmediatePropagation();
      showToast();
    }, true);
  }
})();
```

Key behavioral notes:
- Copy/cut handlers check `isProtected()` so Milkdown copy (AC4.9) passes through
- Paste handler is on Milkdown only — capture phase blocks before ProseMirror
- `e.stopImmediatePropagation()` on paste prevents ProseMirror from seeing the event
- Text selection is unaffected (AC4.10) — no `selectstart` or `mousedown` interception
- `Quasar.Notify.create()` with `group: 'copy-protection'` auto-deduplicates

2. Update `_render_workspace_header()` signature to accept the `protect` flag. The current signature is `async def _render_workspace_header(state: PageState, workspace_id: UUID) -> None:` (line 2613). Change to:

```python
async def _render_workspace_header(state: PageState, workspace_id: UUID, protect: bool = False) -> None:
```

Update the call site in `_render_workspace_view()` to pass `protect=protect`.

After the placement chip (around line 2682), conditionally render the lock icon chip:

```python
if protect:
    ui.chip(
        "Protected",
        icon="lock",
        color="amber-7",
        text_color="white",
    ).props('dense').tooltip("Copy protection is enabled for this activity").props(
        'aria-label="Copy protection is enabled for this activity"'
    )
```

3. Call `_inject_copy_protection()` at the end of `_render_workspace_view()` after the three-tab container is built, only when `protect=True`.

**Testing:**

Unit tests verify the **conditional logic** (not JS string content — avoid brittle string assertions):
- Test that `_inject_copy_protection()` is called when `protect=True` (mock `ui.run_javascript` and verify it was called)
- Test that `_inject_copy_protection()` is NOT called when `protect=False` (mock `ui.run_javascript` and verify it was NOT called)
- Test lock chip rendering logic: verify `ui.chip` is called with icon="lock" when `protect=True`, and NOT called when `protect=False`

Do NOT test the JS string content directly — this creates fragile tests that break on whitespace or formatting changes. Instead test the conditional injection boundary: was JS injected or not?

E2E testing of actual clipboard interception requires Phase 4 to be functionally complete and a running app. E2E tests for AC4.1-AC4.13 should be placed in a new test file `tests/e2e/test_copy_protection.py` following patterns from `test_annotation_tabs.py`.

**Verification:**

Run:
```bash
uv run test-all
```

Expected: All tests pass.

**Commit:**

```bash
git add src/promptgrimoire/pages/annotation.py tests/unit/test_copy_protection_js.py
git commit -m "feat: inject client-side copy/paste/drag protection JS and lock icon chip"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Verify protection inactive states (AC4.12, AC4.13)

**Verifies:** 103-copy-protection.AC4.12, AC4.13

**Files:**
- Test: `tests/unit/test_copy_protection_js.py` (unit — extend with inactive state tests)

**Implementation:**

No new code — this task adds tests verifying the negative cases:
- When `copy_protection=False` on the activity, the JS block is NOT injected
- When workspace is loose (no activity), the JS block is NOT injected
- Lock chip is NOT rendered in these cases

These are verified by the conditional `if protect:` gate in Task 1. Tests confirm the gate works correctly by checking that `_inject_copy_protection()` is not called when `protect=False`.

**Testing:**

Add to `TestCopyProtectionConditions` class:
- AC4.12: Activity with `copy_protection=False` — verify protect flag is False, JS not injected
- AC4.13: Loose workspace — verify protect flag is False, JS not injected

**Verification:**

Run:
```bash
uv run pytest tests/unit/test_copy_protection_js.py -v
```

Expected: All tests pass.

**Commit:**

```bash
git add tests/unit/test_copy_protection_js.py
git commit -m "test: verify copy protection inactive for disabled activities and loose workspaces"
```

**UAT Steps (end of Phase 4):**

1. [ ] Verify tests: `uv run test-all` — all pass
2. [ ] Start the app: `uv run python -m promptgrimoire`
3. [ ] Seed data: `uv run seed-data`
4. [ ] As student, navigate to annotation page for a protected activity:
   - [ ] Try to copy text from Tab 1 document — blocked, toast shown
   - [ ] Try to copy text from Tab 2 organise cards — blocked, toast shown
   - [ ] Try to copy text from Tab 3 reference cards — blocked, toast shown
   - [ ] Try to right-click on document content — blocked, toast shown
   - [ ] Try to paste into Milkdown editor — blocked, toast shown
   - [ ] Try to drag text out of document — blocked, toast shown
   - [ ] Try to copy from Milkdown editor (own writing) — works normally
   - [ ] Verify text selection/highlighting still works
   - [ ] Verify lock icon chip visible in header with tooltip
5. [ ] As instructor, navigate to same activity:
   - [ ] Verify no lock chip, copy/paste/drag all work normally
6. [ ] Navigate to a loose workspace (no activity):
   - [ ] Verify no lock chip, no protection

**Evidence Required:**
- [ ] Test output showing all copy protection tests green
- [ ] Screenshot showing lock chip and toast notification
- [ ] Confirmation that instructor bypass works
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->
