# PDF Paragraph Numbering — Phase 5: Documentation

**Goal:** Update user-facing guide to document paragraph numbering in PDF export.

**Architecture:** Add a text-only guide entry to `using_promptgrimoire.py` in the Export section using the Guide DSL. Verify docs build succeeds.

**Tech Stack:** Python (Guide DSL), pandoc (docs build)

**Scope:** Phase 5 of 5 from original design

**Codebase verified:** 2026-03-24

---

## Acceptance Criteria Coverage

**Verifies: None** — This is an infrastructure/documentation phase.

---

## Reference Files for Subagents

- **Guide script:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/src/promptgrimoire/docs/scripts/using_promptgrimoire.py`
- **Export section:** Lines 1426-1428 in `_run_screenshot_sections()`
- **Existing export entry pattern:** `_entry_export_pdf()` at lines 418-435
- **Guide DSL:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/src/promptgrimoire/docs/guide.py`
- **add-docs-entry skill:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/.claude/skills/add-docs-entry/SKILL.md`
- **Project conventions:** `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/pdf-para-numbering-417/CLAUDE.md`

---

<!-- START_TASK_1 -->
### Task 1: Add paragraph numbering guide entry

**Verifies:** None (documentation)

**Files:**
- Modify: `src/promptgrimoire/docs/scripts/using_promptgrimoire.py` (add new entry function + register in Export section)

**Implementation:**

Use the `add-docs-entry` skill for DSL patterns and conventions.

**New entry function:** Create `_entry_paragraph_numbers_export(guide: Guide)` (text-only — no `page` parameter needed).

Content should cover:
1. **Paragraph numbers in PDF:** When a workspace uses auto-numbering, the exported PDF shows small grey paragraph numbers in the left margin. These match the on-screen paragraph numbers. Source-number mode documents already show numbers as list items, so no margin numbers are added.
2. **Endnote cross-references:** Long annotations that overflow into the endnotes section have clickable links. Click the superscript number in the body to jump to the endnote. Click the number in the endnote to jump back to the body location.

**Cite backing tests:** Per project conventions, feature assertions must reference the tests that verify the behaviour. Reference `test_paragraph_markers.py` (paragraph marker injection), `test_paranumber_latex.py` (LaTeX rendering), and `test_endnote_crossref.py` (endnote cross-references) in the guide entry.

**Register in Export section:** In `_run_screenshot_sections()`, add `_entry_paragraph_numbers_export(guide)` after line 1428 (after `_entry_pdf_filename(guide)`) within the "Export" section.

**Guide DSL pattern (text-only entry):**
```python
def _entry_paragraph_numbers_export(guide: Guide) -> None:
    with guide.step("How do paragraph numbers appear in PDF export?", text_only=True) as g:
        g.note("When auto-numbering is enabled...")
        g.note("Long annotations that are deferred to the endnotes section...")
```

**Verification:**

Run: `uv run grimoire docs build`
Expected: Build succeeds, new entry appears in generated markdown

**Commit:** `docs: add paragraph numbering and endnote cross-reference guide entry (#417)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Verify docs build

**Verifies:** None (infrastructure verification)

**Files:** None (no modifications)

**Implementation:** No code changes. Verify the documentation build succeeds after adding the new entry.

**Verification:**

Run: `uv run grimoire docs build`
Expected: Build completes without errors. Generated markdown at `docs/guides/using-promptgrimoire.md` contains the new Export section entry.

**Commit:** No commit (verification only)
<!-- END_TASK_2 -->
