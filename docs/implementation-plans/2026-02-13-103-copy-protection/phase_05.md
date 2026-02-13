# Per-Activity Copy Protection Implementation Plan — Phase 5

**Goal:** CSS `@media print` suppression and Ctrl+P/Cmd+P intercept when copy protection is active.

**Architecture:** Conditional CSS block injected via `ui.add_css()` hides tab panels at print time and shows a "Printing is disabled" message. Ctrl+P/Cmd+P keydown handler added **inside the same IIFE** in the Phase 4 `_inject_copy_protection()` function — the Ctrl+P handler reuses the `showToast()` function already defined within the IIFE scope. Phase 5 modifies `_inject_copy_protection()` directly (not a separate injection), ensuring the JS block remains a single atomic unit.

**Tech Stack:** CSS @media print, JavaScript keydown, NiceGUI (ui.add_css)

**Scope:** Phase 5 of 6 from original design

**Codebase verified:** 2026-02-13

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 103-copy-protection.AC4: Client-side protections (E2E)
- **103-copy-protection.AC4.6 Success:** Print suppressed (CSS @media print shows message, Ctrl+P intercepted)

---

## Reference Files

The executor should read these files for context:

- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/src/promptgrimoire/pages/annotation.py` — `ui.add_css()` pattern at line 639, protection JS injection from Phase 4

---

<!-- START_TASK_1 -->
### Task 1: Add print suppression CSS and Ctrl+P intercept

**Verifies:** 103-copy-protection.AC4.6

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py` — add conditional print CSS and Ctrl+P handler
- Test: `tests/unit/test_copy_protection_js.py` (unit — extend with print suppression conditional tests)

**Implementation:**

1. **CSS @media print block** — inject conditionally when `protect=True`:

```css
@media print {
  .q-tab-panels { display: none !important; }
  .copy-protection-print-message { display: block !important; }
}
.copy-protection-print-message { display: none; }
```

Inject using `ui.add_css()` within the `_inject_copy_protection()` function (or alongside it).

Also inject a hidden message div that becomes visible only in print:

```python
ui.html('<div class="copy-protection-print-message" style="display:none; padding: 2rem; text-align: center; font-size: 1.5rem;">Printing is disabled for this activity.</div>')
```

2. **Ctrl+P/Cmd+P keydown handler** — add **inside the existing IIFE** in `_inject_copy_protection()` (the same function from Phase 4), after the existing event handlers:

```javascript
// Ctrl+P / Cmd+P print intercept
document.addEventListener('keydown', function(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'p') {
    e.preventDefault();
    showToast();
  }
}, true);
```

This reuses the `showToast()` function already defined within the IIFE scope from Phase 4. The implementor should add this handler inside the existing `(function() { ... })()` block, not as a separate `ui.run_javascript()` call. The CSS injection (`ui.add_css()`) and hidden message div (`ui.html()`) can be added alongside the IIFE within `_inject_copy_protection()`.

**Testing:**

Unit tests in `tests/unit/test_copy_protection_js.py` (extend existing file from Phase 4), testing **conditional injection boundaries** (consistent with Phase 4's anti-brittle-string-matching guidance):
- Verify `ui.add_css` is called (print CSS injected) when `protect=True` — mock `ui.add_css` and assert it was called
- Verify `ui.add_css` is NOT called when `protect=False`
- Verify `ui.html` is called (print message div injected) when `protect=True`
- Do NOT test JS string content for the Ctrl+P handler — it lives inside the same IIFE as Phase 4's handlers, so it is implicitly present whenever `_inject_copy_protection()` is called

E2E testing of actual print behavior is impractical in headless Playwright (print dialog is OS-level). The CSS rule can be verified by checking computed styles with `@media print` emulation.

**Verification:**

Run:
```bash
uv run test-all
```

Expected: All tests pass.

**Commit:**

```bash
git add src/promptgrimoire/pages/annotation.py tests/unit/test_copy_protection_js.py
git commit -m "feat: add CSS print suppression and Ctrl+P intercept for copy protection"
```

**UAT Steps (end of Phase 5):**

1. [ ] Verify tests: `uv run test-all` — all pass
2. [ ] Start the app: `uv run python -m promptgrimoire`
3. [ ] As student, navigate to annotation page for a protected activity:
   - [ ] Press Ctrl+P (or Cmd+P on Mac) — blocked, toast shown, no print dialog
   - [ ] Use browser menu File > Print — print preview shows "Printing is disabled for this activity" message instead of content
4. [ ] As instructor, navigate to same activity:
   - [ ] Press Ctrl+P — print dialog opens normally
   - [ ] Print preview shows normal content

**Evidence Required:**
- [ ] Test output showing all tests green
- [ ] Screenshot of print preview showing "Printing is disabled" message for student
- [ ] Confirmation that Ctrl+P is intercepted for student
<!-- END_TASK_1 -->
