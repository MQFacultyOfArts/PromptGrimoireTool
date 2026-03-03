# Word Count with Configurable Limits Implementation Plan

**Goal:** Export respects word limit enforcement mode — soft shows warning + snitch badge, hard blocks export.

**Architecture:** Pre-export word count check in _handle_pdf_export() using PageState values. Soft mode: warning dialog with "Export Anyway" + "Cancel", then LaTeX \fcolorbox snitch badge injected before body. Hard mode: blocking dialog with "Dismiss" only.

**Tech Stack:** NiceGUI (ui.dialog), LaTeX (\fcolorbox), word_count module from Phase 1

**Scope:** 6 phases from original design (phase 5 of 6)

**Codebase verified:** 2026-03-02

---

## Acceptance Criteria Coverage

This phase implements and tests:

### word-count-limits-47.AC5: Export enforcement (soft mode)
- **word-count-limits-47.AC5.1 Success:** Export shows warning dialog: "Your response is X words over/under the limit"
- **word-count-limits-47.AC5.2 Success:** User can confirm and proceed with export
- **word-count-limits-47.AC5.3 Success:** PDF page 1 shows red badge: "Word Count: 1,567 / 1,500 (Exceeded)"
- **word-count-limits-47.AC5.4 Success:** PDF shows neutral word count line when within limits
- **word-count-limits-47.AC5.5 Edge:** Both min and max violated -- dialog shows both violations

### word-count-limits-47.AC6: Export enforcement (hard mode)
- **word-count-limits-47.AC6.1 Success:** Export blocked with dialog explaining violation
- **word-count-limits-47.AC6.2 Success:** Dialog has no export button -- only dismiss
- **word-count-limits-47.AC6.3 Edge:** Within limits -- export proceeds normally with no dialog

### word-count-limits-47.AC7: Non-blocking behaviour
- **word-count-limits-47.AC7.1 Success:** Word count status does not prevent saving
- **word-count-limits-47.AC7.2 Success:** Word count status does not prevent editing
- **word-count-limits-47.AC7.3 Success:** Word count status does not prevent sharing
- **word-count-limits-47.AC7.4 Success:** Only export is affected by enforcement mode

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Create word count violation check helper

**Verifies:** word-count-limits-47.AC5.1, word-count-limits-47.AC5.5, word-count-limits-47.AC6.1

**Files:**
- Create: `src/promptgrimoire/pages/annotation/word_count_enforcement.py`
- Test: `tests/unit/test_word_count_enforcement.py` (unit)

**Implementation:**

Pure function module for computing violation state:

```python
@dataclass(frozen=True)
class WordCountViolation:
    over_limit: bool = False
    under_minimum: bool = False
    over_by: int = 0
    under_by: int = 0
    count: int = 0
    word_minimum: int | None = None
    word_limit: int | None = None

    @property
    def has_violation(self) -> bool:
        return self.over_limit or self.under_minimum
```

`check_word_count_violation(count: int, word_minimum: int | None, word_limit: int | None) -> WordCountViolation`:
- If word_limit is set and count >= word_limit: over_limit=True, over_by=count-word_limit
- If word_minimum is set and count < word_minimum: under_minimum=True, under_by=word_minimum-count
- Both can be True simultaneously

**Testing:**

Tests must verify:
- Over limit: count=150, limit=100 → over_limit=True, over_by=50
- Under minimum: count=50, min=100 → under_minimum=True, under_by=50
- Under minimum only: count=50, min=100, limit=200 → under_minimum=True, over_limit=False, has_violation=True
- Within range: count=150, min=100, limit=200 → has_violation=False
- No limits: count=150, min=None, limit=None → has_violation=False
- At exactly limit: count=100, limit=100 → over_limit=True (at limit counts as over)
- At exactly minimum: count=100, min=100 → under_minimum=False (at minimum is OK)

**Note on "both violated" (AC5.5):** When `word_minimum < word_limit` (enforced by AC2.5 validation), both `over_limit` and `under_minimum` CANNOT be True simultaneously. If `count >= word_limit` then `count > word_minimum` (not under minimum). If `count < word_minimum` then `count < word_limit` (not over limit). The `has_violation` property still works correctly — it returns True if either condition is violated. The `both True` path is architecturally unreachable through validated data and does not need a test. AC5.5 is satisfied by testing each violation independently and verifying the message formatting handles both fields.

**Verification:**

Run: `uv run pytest tests/unit/test_word_count_enforcement.py -v`
Expected: All tests pass.

**Commit:** `feat: add word count violation check helper`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create violation dialog message builder

**Verifies:** word-count-limits-47.AC5.1, word-count-limits-47.AC5.5

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/word_count_enforcement.py`
- Modify: `tests/unit/test_word_count_enforcement.py`

**Implementation:**

`format_violation_message(violation: WordCountViolation) -> str`:
- If over_limit and under_minimum: "Your response is {over_by} words over the limit and {under_by} words under the minimum."
- If over_limit only: "Your response is {over_by} words over the {word_limit}-word limit (current count: {count:,})."
- If under_minimum only: "Your response is {under_by} words under the {word_minimum}-word minimum (current count: {count:,})."

**Testing:**

- Over by 50: "Your response is 50 words over the 100-word limit (current count: 150)."
- Under by 50: "Your response is 50 words under the 100-word minimum (current count: 50)."
- Both violated: construct a `WordCountViolation` directly with `over_limit=True, under_minimum=True, over_by=50, under_by=30` (bypassing `check_word_count_violation()` since this state is unreachable through validated data — see Task 1 note). Verify the message mentions both violations. This tests the formatting code path even though the check function cannot produce this state.

**Verification:**

Run: `uv run pytest tests/unit/test_word_count_enforcement.py -v`
Expected: All tests pass.

**Commit:** `feat: add violation message formatting`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Tests for violation edge cases

**Verifies:** word-count-limits-47.AC6.3, word-count-limits-47.AC7.1, word-count-limits-47.AC7.2, word-count-limits-47.AC7.3, word-count-limits-47.AC7.4

**Files:**
- Modify: `tests/unit/test_word_count_enforcement.py`

**Testing:**

Edge cases:
- count=0, no limits → no violation
- count=0, limit=100 → under minimum if minimum set, but not "over limit"
- Large counts: count=10000, limit=5000 → over_by=5000

AC7 non-blocking behaviour tests (word-count-limits-47.AC7.1-AC7.4):

These verify that word count enforcement ONLY affects export — save, edit, and share are never blocked. Add tests that prove the `check_word_count_violation()` function is NOT called by any save/edit/share code path. The simplest approach: verify that the violation check module is only imported by `pdf_export.py` and `word_count_enforcement.py` (not by save, annotation, or share modules). Additionally:
- AC7.1-AC7.3: Verify that the `word_count_enforcement` module is not imported by any save, edit, or share code path. Use `importlib` to import the relevant modules (`promptgrimoire.db.acl`, `promptgrimoire.crdt`, `promptgrimoire.pages.annotation.respond`) and assert that `WordCountViolation` and `check_word_count_violation` are not in their namespace (`assert not hasattr(module, 'WordCountViolation')`). This provides a concrete regression guard: if someone adds enforcement to a non-export path, the test fails.
- AC7.4: Verify that the enforcement module is ONLY imported by export-related modules. Import `promptgrimoire.pages.annotation.pdf_export` and assert it DOES reference `check_word_count_violation` (positive control), then assert `promptgrimoire.pages.annotation.respond` and `promptgrimoire.db.acl` do NOT. Every test must contain at least one `assert` statement.

**Verification:**

Run: `uv run pytest tests/unit/test_word_count_enforcement.py -v`
Expected: All tests pass.

**Commit:** `test: add word count violation edge cases`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->
<!-- START_TASK_4 -->
### Task 4: Add pre-export word count check with dialogs

**Verifies:** word-count-limits-47.AC5.1, word-count-limits-47.AC5.2, word-count-limits-47.AC6.1, word-count-limits-47.AC6.2, word-count-limits-47.AC6.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/pdf_export.py` (lines 88-188, _handle_pdf_export)

**Implementation:**

In `_handle_pdf_export()`, after extracting response_markdown (around line 155) but before calling `export_annotation_pdf()` (line 169):

1. Check if word limits are configured on PageState
2. If limits configured, compute word count and check violation
3. If no violation → proceed normally (AC6.3)
4. If violation + soft enforcement:
   - Show warning dialog with violation message
   - "Export Anyway" button → proceeds to export
   - "Cancel" button → returns without exporting
   - Use `asyncio.Event` or dialog result pattern for async flow control
5. If violation + hard enforcement:
   - Show blocking dialog with violation message
   - "Dismiss" button only → returns without exporting

Dialog structure following existing codebase pattern:

```python
async def _show_word_count_warning(violation: WordCountViolation) -> bool:
    """Show word count warning dialog. Returns True if user wants to proceed."""
    result = asyncio.Event()
    proceed = False

    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("Word Count Warning").classes("text-lg font-bold text-amber-800")
        ui.label(format_violation_message(violation)).classes("text-sm")

        with ui.row().classes("w-full justify-end gap-2 mt-4"):
            def on_cancel():
                nonlocal proceed
                proceed = False
                dialog.close()
                result.set()

            def on_export():
                nonlocal proceed
                proceed = True
                dialog.close()
                result.set()

            ui.button("Cancel", on_click=on_cancel).props('flat data-testid="wc-cancel-btn"')
            ui.button("Export Anyway", on_click=on_export).props(
                'color=warning data-testid="wc-export-anyway-btn"'
            )

    dialog.open()
    await result.wait()
    return proceed
```

Similar function for hard enforcement but with only a "Dismiss" button (`.props('data-testid="wc-dismiss-btn"')`) and no return value (always blocks). No "Export Anyway" button in the hard enforcement dialog.

**Testing:**

Tested in Phase 6 E2E. Unit tests for violation check already in Task 1-3.

**Verification:**

Run: `uvx ty check`
Expected: No type errors.

**Commit:** `feat: add pre-export word count check with warning/blocking dialogs`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Add snitch badge to PDF export

**Verifies:** word-count-limits-47.AC5.3, word-count-limits-47.AC5.4

**Files:**
- Modify: `src/promptgrimoire/export/pdf_export.py` (LaTeX template and generation)

**Implementation:**

Add a LaTeX snitch badge function:

`_build_word_count_badge(count: int, word_minimum: int | None, word_limit: int | None) -> str`:
- If violation exists: return red `\fcolorbox` with violation text
- If within limits: return neutral word count line (no colour)
- If no limits: return empty string

LaTeX for red violation badge:
```latex
\noindent\fcolorbox{red}{red!10}{%
\parbox{\dimexpr\textwidth-2\fboxsep-2\fboxrule}{%
\textcolor{red}{\textbf{Word Count: 1,567 / 1,500 (Exceeded)}}%
}}
\vspace{1em}
```

LaTeX for neutral word count:
```latex
\noindent\textit{Word Count: 1,234 / 1,500}
\vspace{1em}
```

Inject the badge into the LaTeX document by modifying `generate_tex_only()` to accept word count parameters as keyword-only arguments with defaults of `None` for backward compatibility:

```python
def generate_tex_only(
    ...,  # existing params
    *,
    word_count: int | None = None,
    word_minimum: int | None = None,
    word_limit: int | None = None,
) -> str:
```

All existing call sites continue to work unchanged (no word count params = no badge). Prepend the badge to the body when any word count parameter is provided.

Update `_handle_pdf_export()` to pass word count info through to the export pipeline.

**Testing:**

Unit test for `_build_word_count_badge()`:
- AC5.3: Over limit → red fcolorbox with "(Exceeded)"
- AC5.4: Within limits → neutral italic line
- No limits → empty string
- Under minimum → red fcolorbox with "(Below Minimum)"

**Verification:**

Run: `uv run pytest tests/unit/ -k word_count -v`
Expected: All tests pass.

Run: `uvx ty check`
Expected: No type errors.

**Commit:** `feat: add snitch badge to PDF export for word count violations`
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_6 -->
### Task 6: Final verification

**Files:**
- All files from this phase

**Step 1: Run full test suite**

Run: `uv run test-changed`
Expected: All tests pass, no regressions.

**Step 2: Run linting and type checking**

Run: `uv run ruff check src/promptgrimoire/pages/annotation/ src/promptgrimoire/export/`
Expected: No lint errors.

Run: `uvx ty check`
Expected: No type errors.

**Step 3: Verify commit history**

Run: `git log --oneline -6`
Expected: Clean commit history with conventional prefixes.
<!-- END_TASK_6 -->
