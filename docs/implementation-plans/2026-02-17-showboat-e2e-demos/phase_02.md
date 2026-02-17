# Showboat E2E Demo Documents Implementation Plan

**Goal:** Wire Showboat output cleanup and PDF conversion into the `test-e2e` CLI lifecycle.

**Architecture:** Two private functions in `cli.py`: `_clear_showboat_output()` removes stale output before pytest runs (matching `_pre_test_db_cleanup()` placement), `_convert_showboat_to_pdf()` converts Markdown to PDF after pytest completes (in the `finally` block). PDF conversion uses synchronous `subprocess.run()` with Pandoc + lualatex, wrapped in try/except to guarantee test exit codes are never affected.

**Tech Stack:** subprocess, shutil, pathlib, glob, Pandoc CLI, lualatex (TinyTeX)

**Scope:** 3 phases from original design (phase 2 of 3)

**Codebase verified:** 2026-02-17

---

## Acceptance Criteria Coverage

This phase implements and tests:

### showboat-e2e-demos.AC2: CLI lifecycle integration
- **showboat-e2e-demos.AC2.1 Success:** `uv run test-e2e` clears `output/showboat/` before running tests
- **showboat-e2e-demos.AC2.2 Success:** After tests complete, `.md` files in `output/showboat/` are converted to PDF via Pandoc
- **showboat-e2e-demos.AC2.3 Degradation:** PDF conversion skips silently if Pandoc or lualatex unavailable
- **showboat-e2e-demos.AC2.4 Isolation:** PDF conversion failure never changes the test exit code

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Add showboat cleanup and PDF conversion to cli.py

**Verifies:** showboat-e2e-demos.AC2.1, showboat-e2e-demos.AC2.2, showboat-e2e-demos.AC2.3, showboat-e2e-demos.AC2.4

**Files:**
- Modify: `src/promptgrimoire/cli.py` (add two private functions, modify `test_e2e()`)

**Implementation:**

Add two private functions to `cli.py`, placed near the other `test_e2e` helper functions (after `_stop_e2e_server` around line 372):

**`_clear_showboat_output() -> None`**
- Import `shutil` and `Path` (already available in module)
- Define `SHOWBOAT_OUTPUT_DIR = Path("output/showboat")` — uses the same name as `showboat_helpers.py` for grep-ability. Cannot import from `tests/` (anti-pattern for production code), so the duplication is intentional.
- If `SHOWBOAT_OUTPUT_DIR.exists()`: `shutil.rmtree(SHOWBOAT_OUTPUT_DIR)`
- Always: `SHOWBOAT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)`
- Print `[dim]Cleared output/showboat/[/]` via the module-level `console` (Rich Console)

**`_convert_showboat_to_pdf() -> None`**
- Glob `SHOWBOAT_OUTPUT_DIR.glob("*.md")`
- If no `.md` files found: return silently
- Print `[dim]Converting showboat docs to PDF...[/]`
- For each `.md` file:
  - Target: same path with `.pdf` suffix
  - Run: `subprocess.run(["pandoc", str(md_path), "-o", str(pdf_path), "--pdf-engine=lualatex"], capture_output=True, text=True)`
  - If return code is 0: print `[dim]  {md_path.name} -> {pdf_path.name}[/]`
  - If return code is non-zero: print `[yellow]  Warning: failed to convert {md_path.name}: {result.stderr[:200]}[/]`
- Wrap the ENTIRE function body in `try: ... except Exception as exc:` that prints `[yellow]Warning: showboat PDF conversion failed: {exc}[/]` — never re-raises

**Modify `test_e2e()`:**
- Add `_clear_showboat_output()` call AFTER `_pre_test_db_cleanup()` and BEFORE the socket/server setup (around line 400)
- Add `_convert_showboat_to_pdf()` call in the `finally` block, AFTER `_stop_e2e_server(server_process)` (line 440)

The modified `test_e2e` structure becomes:
```python
def test_e2e() -> None:
    ...
    _pre_test_db_cleanup()
    _clear_showboat_output()       # NEW

    # ... socket, server, pytest ...

    try:
        _run_pytest(...)
    finally:
        _stop_e2e_server(server_process)
        _convert_showboat_to_pdf()  # NEW — wrapped in its own try/except
```

**Verification:**

Run: `uv run ruff check src/promptgrimoire/cli.py`
Expected: No errors

Run: `uvx ty check`
Expected: No errors

**Commit:**

```bash
git add src/promptgrimoire/cli.py
git commit -m "feat: add showboat output cleanup and PDF conversion to test-e2e"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Unit tests for CLI showboat functions

**Verifies:** showboat-e2e-demos.AC2.1, showboat-e2e-demos.AC2.2, showboat-e2e-demos.AC2.3, showboat-e2e-demos.AC2.4

**Files:**
- Create: `tests/unit/test_showboat_cli.py`

**Implementation:**

Test the two private functions directly. Import them from `promptgrimoire.cli`.

**Tests for `_clear_showboat_output()`:**
- AC2.1: Create `output/showboat/` with some dummy files (using `tmp_path` + monkeypatch of the SHOWBOAT_OUTPUT_DIR constant). Call `_clear_showboat_output()`. Assert the directory exists and is empty.
- Edge case: Call when directory doesn't exist. Assert directory is created (not an error).

**Tests for `_convert_showboat_to_pdf()`:**
- AC2.2: Create a `.md` file in the showboat dir with valid Markdown content. Call `_convert_showboat_to_pdf()`. Assert `.pdf` file exists alongside the `.md`. Skip if `shutil.which("pandoc")` is None.
- AC2.3: Skip test if pandoc IS available (this tests the degradation). Or better: create a `.md` file, temporarily rename pandoc (not practical). Instead: verify the function doesn't raise when pandoc returns a non-zero exit code — create a `.md` file with content that pandoc can't convert (e.g. a reference to a missing image), verify function completes without exception. Skip if pandoc unavailable.
- AC2.4: Verify `_convert_showboat_to_pdf()` never raises. Call it with an empty directory — no error. Call it when `SHOWBOAT_OUTPUT_DIR` doesn't exist — no error (the outer try/except catches).

**Testing:**
- AC2.1: Verify cleanup removes files and recreates empty directory
- AC2.2: Verify `.md` files are converted to `.pdf` (skip if no pandoc)
- AC2.3: Verify function completes without error when pandoc fails
- AC2.4: Verify function never raises exceptions regardless of state

**Verification:**

Run: `uv run pytest tests/unit/test_showboat_cli.py -v`
Expected: All tests pass. Pandoc-dependent tests skip if pandoc unavailable.

**Commit:**

```bash
git add tests/unit/test_showboat_cli.py
git commit -m "test: add unit tests for showboat CLI cleanup and PDF conversion"
```
<!-- END_TASK_2 -->

## UAT Steps

1. [ ] Run `uv run pytest tests/unit/test_showboat_cli.py -v` — all unit tests pass
2. [ ] Create a dummy file: `mkdir -p output/showboat && echo "# Test" > output/showboat/test.md`
3. [ ] Run `uv run test-e2e -k test_law_student` — verify `output/showboat/` was cleared (test.md gone) before tests ran
4. [ ] After tests complete, check terminal output for `[dim]Cleared output/showboat/[/]` message
5. [ ] If Pandoc installed: verify `output/showboat/*.pdf` files exist alongside `.md` files after test run
6. [ ] If Pandoc NOT installed: verify no error output and test exit code is unaffected

<!-- END_SUBCOMPONENT_A -->
