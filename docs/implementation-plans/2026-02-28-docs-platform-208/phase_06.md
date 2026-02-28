# Documentation Platform Implementation Plan — Phase 6

**Goal:** Remove all remaining rodney/showboat references, delete obsolete files, and update project documentation to reflect the new Python+Playwright+MkDocs pipeline.

**Architecture:** Cleanup phase — no new code. Delete obsolete files, update documentation, verify no references remain.

**Tech Stack:** N/A (cleanup)

**Scope:** 6 phases from original design (phase 6 of 6)

**Codebase verified:** 2026-02-28

---

## Acceptance Criteria Coverage

This phase implements and tests:

### docs-platform-208.AC8: Old pipeline fully replaced
- **docs-platform-208.AC8.1 Success:** No references to `rodney` or `showboat` remain in production code or `pyproject.toml`
- **docs-platform-208.AC8.2 Success:** All bash guide scripts (`generate-instructor-setup.sh`, `generate-student-workflow.sh`, `common.sh`, `debug-instructor.sh`) are deleted
- **docs-platform-208.AC8.3 Success:** `CLAUDE.md` documents the new `make-docs` pipeline accurately

---

## Important Notes

Many of the files listed for deletion below may have already been handled in earlier phases:
- `showboat` removed from `pyproject.toml` in Phase 2 (Task 1)
- `generate-instructor-setup.sh` deleted in Phase 3 (Task 2)
- `generate-student-workflow.sh`, `common.sh`, `debug-instructor.sh` deleted in Phase 4 (Task 2)
- `rodney`/`showboat` references in `cli.py` removed in Phase 2 (Task 2)
- `test_make_docs.py` updated in Phase 2 (Task 2)

This phase serves as a **sweep** to catch anything that was missed and to handle documentation updates.

---

<!-- START_TASK_1 -->
### Task 1: Delete docs/rodney/ directory

**Verifies:** docs-platform-208.AC8.1

**Files:**
- Delete: `docs/rodney/cli-reference.md`
- Delete: `docs/rodney/` directory

**Step 1: Delete the directory**

```bash
git rm -r docs/rodney/
```

**Step 2: Verify**

Run: `ls docs/rodney/`
Expected: Directory does not exist

**Step 3: Commit**

```bash
git commit -m "chore: remove obsolete rodney CLI reference docs"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Remove .rodney/ from .gitignore

**Files:**
- Modify: `.gitignore` (lines 59-60)

**Step 1: Remove rodney gitignore entry**

Delete these two lines from `.gitignore`:
```
# Rodney browser automation state
.rodney/
```

**Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: remove .rodney/ from gitignore"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update docs/_index.md

**Files:**
- Modify: `docs/_index.md` (around lines 89-91)

**Step 1: Remove rodney section**

Delete the rodney section:
```markdown
## rodney

- [Rodney CLI Reference](rodney/cli-reference.md)
```

**Step 2: Commit**

```bash
git add docs/_index.md
git commit -m "docs: remove rodney reference from docs index"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update docs/dependency-rationale.md

**Files:**
- Modify: `docs/dependency-rationale.md` (around lines 275-287)

**Step 1: Remove rodney and showboat sections**

Delete the `### ~~showboat~~ (TO BE REMOVED)` section (around line 275) and the `### ~~rodney~~ (external — TO BE REMOVED)` section (around line 282). These were already marked as to-be-removed.

**Step 2: Commit**

```bash
git add docs/dependency-rationale.md
git commit -m "docs: remove deprecated rodney/showboat from dependency rationale"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Update CLAUDE.md

**Verifies:** docs-platform-208.AC8.3

**Files:**
- Modify: `CLAUDE.md` (lines 105 and 161)

**Step 1: Update make-docs command description**

Change line 105 from:
```
# Generate user-facing documentation (requires rodney, showboat, pandoc)
```
to:
```
# Generate user-facing documentation (requires pandoc)
```

**Step 2: Remove rodney documentation reference**

Delete the table row at line 161:
```
| [rodney/cli-reference.md](docs/rodney/cli-reference.md) | Rodney browser automation CLI (used by make-docs) |
```

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md to reflect new make-docs pipeline"
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Clean up test-pseudocode.md

**Files:**
- Modify: `tests/test-pseudocode.md` (around lines 3022-3057)

**Step 1: Remove or update rodney/showboat test pseudocode sections**

Delete the following test pseudocode sections:
- "Server and Rodney stop on script failure" (around line 3022)
- "Rodney start/stop lifecycle order" (around line 3031)
- "Missing rodney causes early exit" (around line 3041)
- "Missing showboat causes early exit" (around line 3050)

These tests were replaced by Playwright lifecycle tests in Phase 2.

**Step 2: Commit**

```bash
git add tests/test-pseudocode.md
git commit -m "docs: remove obsolete rodney/showboat test pseudocode"
```
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Delete superseded implementation plans

**Files:**
- Delete: `docs/implementation-plans/2026-02-17-showboat-e2e-demos/` directory (if it exists)

**Step 1: Check existence**

Verify whether `docs/implementation-plans/2026-02-17-showboat-e2e-demos/` exists by listing the directory. If it does not exist (may have been cleaned up already), verify it is not tracked by git either (`git ls-files docs/implementation-plans/2026-02-17-showboat-e2e-demos/` returns no results), then skip to Step 3.

**Step 2: Delete if present**

```bash
git rm -r docs/implementation-plans/2026-02-17-showboat-e2e-demos/
```

**Step 3: Commit (only if files were deleted)**

```bash
git commit -m "chore: remove superseded showboat implementation plans"
```
<!-- END_TASK_7 -->

<!-- START_TASK_8 -->
### Task 8: Verify no rodney/showboat references remain

**Verifies:** docs-platform-208.AC8.1, docs-platform-208.AC8.2

**Files:** None (verification only)

**Step 1: Search for remaining references**

Search the codebase for "rodney" (case-insensitive) in `.py`, `.toml`, `.md`, `.sh`, `.yml`, and `.yaml` files. Exclude matches in `docs/design-plans/` and `docs/implementation-plans/` (these document the transition and are allowed to reference old tools).

Expected: No results outside of plan documentation.

Repeat the same search for "showboat".

Expected: No results outside of plan documentation.

**Step 2: Verify bash scripts are gone**

List `docs/guides/scripts/` directory contents.
Expected: Only Python files remain (no `.sh` files)

**Step 3: Verify production code is clean**

Search `src/` for "rodney" or "showboat" (case-insensitive).
Expected: No results

Search `pyproject.toml` for "rodney" or "showboat".
Expected: No results

**Step 4: Run full test suite**

Run: `uv run test-all`
Expected: All tests pass

Run: `uv run ruff check .`
Expected: No lint errors

Run: `uvx ty check`
Expected: No type errors

**Step 5: Run make-docs end-to-end**

Run: `uv run make-docs`
Expected: Full pipeline completes successfully — guides, HTML site, PDFs all generated.
<!-- END_TASK_8 -->
