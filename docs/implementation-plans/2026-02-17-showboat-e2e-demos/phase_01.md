# Showboat E2E Demo Documents Implementation Plan

**Goal:** Install Showboat and create the helper module with graceful degradation for E2E persona tests.

**Architecture:** Three thin wrapper functions (`showboat_init`, `showboat_note`, `showboat_screenshot`) shell out to the `showboat` CLI via `subprocess.run()`. A module-level `_SHOWBOAT_AVAILABLE` flag (set once via `shutil.which("showboat")`) gates all calls. When the binary is absent or `doc` is `None`, every helper is a silent no-op.

**Tech Stack:** showboat (Go binary on PyPI), subprocess, shutil, pathlib, Playwright sync API (Page)

**Scope:** 3 phases from original design (phase 1 of 3)

**Codebase verified:** 2026-02-17

---

## Acceptance Criteria Coverage

This phase implements and tests:

### showboat-e2e-demos.AC1: Showboat helper module works with graceful degradation
- **showboat-e2e-demos.AC1.1 Success:** `showboat_init()` creates a valid Showboat Markdown document at `output/showboat/<slug>.md`
- **showboat-e2e-demos.AC1.2 Success:** `showboat_note()` appends narrative text to the document
- **showboat-e2e-demos.AC1.3 Success:** `showboat_screenshot()` captures a Playwright screenshot and appends it as a Showboat image
- **showboat-e2e-demos.AC1.4 Degradation:** All three helpers no-op silently when `showboat` binary is not on PATH
- **showboat-e2e-demos.AC1.5 Degradation:** Helpers accept `None` for the `doc` parameter without error

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add showboat to dev dependencies

**Files:**
- Modify: `pyproject.toml` (line ~158, end of `[dependency-groups] dev` list)

**Step 1: Add showboat dependency**

Add `"showboat>=0.4"` to the `[dependency-groups] dev` list in `pyproject.toml`. Place it after the last entry in the list (currently `"ruff>=0.14.11"`).

**Step 2: Install**

Run: `uv sync`
Expected: Dependencies install without errors. `showboat --version` should work if the binary is available.

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add showboat to dev dependencies"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create showboat_helpers.py

**Files:**
- Create: `tests/e2e/showboat_helpers.py`

**Implementation:**

Create `tests/e2e/showboat_helpers.py` following the coding style of the existing `tests/e2e/helpers.py`:
- `from __future__ import annotations`
- `TYPE_CHECKING` guard for `Page` import from `playwright.sync_api`
- Module docstring explaining purpose
- Module-level `_SHOWBOAT_AVAILABLE = bool(shutil.which("showboat"))`
- Constants: `SHOWBOAT_OUTPUT_DIR = Path("output/showboat")`

Three public functions:

**`showboat_init(slug: str, title: str) -> Path | None`**
- If not `_SHOWBOAT_AVAILABLE`: return `None`
- Create `SHOWBOAT_OUTPUT_DIR` if it doesn't exist (`mkdir(parents=True, exist_ok=True)`)
- Target file: `SHOWBOAT_OUTPUT_DIR / f"{slug}.md"`
- Run: `subprocess.run(["showboat", "init", str(target), title], check=True)`
- Return `target`

**`showboat_note(doc: Path | None, text: str) -> None`**
- If `doc is None`: return immediately
- Run: `subprocess.run(["showboat", "note", str(doc), text], check=True)`

**`showboat_screenshot(doc: Path | None, page: Page, caption: str) -> None`**
- If `doc is None`: return immediately
- Create a temp file: `tempfile.NamedTemporaryFile(suffix=".png", delete=False)`
- Call `page.screenshot(path=tmp_path)` to capture the screenshot
- Run: `subprocess.run(["showboat", "image", str(doc), str(tmp_path)], check=True)`
- Add a note with the caption: `subprocess.run(["showboat", "note", str(doc), caption], check=True)`
- Clean up the temp file in a `finally` block (`Path(tmp_path).unlink(missing_ok=True)`)

**Note on image storage:** Showboat stores images alongside the `.md` file with auto-generated UUID-based filenames (e.g. `977dd76d-2026-02-06.png`), not in per-slug subdirectories. This is Showboat's standard behaviour.

**Step 2: Verify**

Run: `uv run ruff check tests/e2e/showboat_helpers.py`
Expected: No errors

Run: `uvx ty check`
Expected: No errors related to showboat_helpers

**Step 3: Commit**

```bash
git add tests/e2e/showboat_helpers.py
git commit -m "feat: add showboat E2E helper module with graceful degradation"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Unit tests for showboat helpers

**Verifies:** showboat-e2e-demos.AC1.1, showboat-e2e-demos.AC1.2, showboat-e2e-demos.AC1.4, showboat-e2e-demos.AC1.5

**Files:**
- Create: `tests/unit/test_showboat_helpers.py`

**Implementation:**

Follow the `test_latex_packages.py` pattern — integration tests that skip when the external tool isn't available, plus degradation tests that always run.

Two test groups:

**Group 1: Degradation path (always run, no external deps)**
- AC1.4 + AC1.5 (combined flow): Monkeypatch `showboat_helpers._SHOWBOAT_AVAILABLE = False`. Call `showboat_init("test", "Test")` — assert returns `None`. Then pass that `None` result to `showboat_note(None, "text")` — assert no error. Pass `None` to `showboat_screenshot(None, None, "caption")` — assert no error (the `doc is None` check returns before touching `page`). This naturally tests both AC1.4 (binary absent causes init to return None) and AC1.5 (None doc accepted by note/screenshot).
- AC1.5 (standalone): Additionally, test `showboat_note(None, "text")` and `showboat_screenshot(None, None, "caption")` without monkeypatching `_SHOWBOAT_AVAILABLE` — confirms None acceptance is independent of availability state.

**Group 2: Available path (skip if no showboat)**
- Use `pytest.mark.skipif(not shutil.which("showboat"), reason="showboat not installed")` at class or function level
- AC1.1: Call `showboat_init("test-slug", "Test Title")` with `tmp_path` fixture (monkeypatch `SHOWBOAT_OUTPUT_DIR` to a temp directory). Assert returned path exists, read the `.md` file, assert it contains `# Test Title`.
- AC1.2: After init, call `showboat_note(doc, "This is a test note.")`. Read the `.md` file. Assert it contains "This is a test note."
- **Idempotency**: Call `showboat_init("test-slug", "Test Title")` again with the same slug. Assert it returns the same `Path` as the first call. Read the `.md` file — assert the title from the first init is preserved (not overwritten). Assert `showboat_note` still appends to the existing document.

**Note:** AC1.3 (screenshot) is verified end-to-end in Phase 3 when real persona tests run with Showboat and a real browser. No unit test for screenshot — the integration is the test.

**Testing:**
- AC1.4: Verify that when `_SHOWBOAT_AVAILABLE` is `False`, init returns `None` and note/screenshot don't raise
- AC1.5: Verify that passing `None` as `doc` to note/screenshot doesn't raise
- AC1.1: Verify that `showboat_init()` creates a `.md` file with the expected title
- AC1.2: Verify that `showboat_note()` appends text to the document

**Verification:**

Run: `uv run pytest tests/unit/test_showboat_helpers.py -v`
Expected: Degradation tests pass. Available-path tests pass if showboat is installed, otherwise skipped.

**Commit:**

```bash
git add tests/unit/test_showboat_helpers.py
git commit -m "test: add showboat helper tests (degradation + available path)"
```
<!-- END_TASK_3 -->

## UAT Steps

1. [ ] Run `showboat --version` — verify showboat binary is available
2. [ ] Run `uv run pytest tests/unit/test_showboat_helpers.py -v` — all degradation tests pass, available-path tests pass (or skip if showboat absent)
3. [ ] Run `showboat init /tmp/uat-test.md "UAT Test"` — verify `/tmp/uat-test.md` is created with `# UAT Test`
4. [ ] Run `showboat note /tmp/uat-test.md "Hello from UAT"` — verify text appended to file
5. [ ] Run `showboat init /tmp/uat-test.md "UAT Test"` again — verify file is NOT overwritten (idempotency confirmed by unit test)

<!-- END_SUBCOMPONENT_A -->
