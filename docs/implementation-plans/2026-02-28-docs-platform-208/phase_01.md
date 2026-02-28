# Documentation Platform Implementation Plan — Phase 1

**Goal:** Build the Guide DSL context managers and screenshot post-processing module.

**Architecture:** Context-manager-based Python DSL (`Guide`, `Step`) that receives a Playwright `Page`, builds a markdown buffer with headings and image references, and captures/annotates screenshots. Screenshot module handles CSS injection for element highlighting and Pillow-based whitespace trimming.

**Tech Stack:** Python 3.14, Playwright sync API, Pillow (PIL)

**Scope:** 6 phases from original design (phase 1 of 6)

**Codebase verified:** 2026-02-28

---

## Acceptance Criteria Coverage

This phase implements and tests:

### docs-platform-208.AC1: Guide DSL produces structured markdown
- **docs-platform-208.AC1.1 Success:** `Guide` context manager creates output directory and writes a complete markdown file on exit
- **docs-platform-208.AC1.2 Success:** `Step` context manager appends `## heading` to the markdown buffer on entry
- **docs-platform-208.AC1.3 Success:** `guide.note(text)` appends narrative paragraphs to the markdown buffer
- **docs-platform-208.AC1.4 Success:** `guide.screenshot()` captures a PNG and appends a markdown image reference (`![caption](path)`) to the buffer
- **docs-platform-208.AC1.5 Success:** Step exit auto-captures a screenshot without explicit `guide.screenshot()` call
- **docs-platform-208.AC1.6 Edge:** Multiple steps in one guide produce sequential headings and image references in correct order

### docs-platform-208.AC2: Screenshots are annotated with element highlights
- **docs-platform-208.AC2.1 Success:** CSS injection adds a visible outline to the element matching a `data-testid` selector before capture
- **docs-platform-208.AC2.2 Success:** Injected CSS `<style>` element is removed after capture (no visual artefact persists in the browser)
- **docs-platform-208.AC2.3 Success:** Multiple elements can be highlighted simultaneously in a single screenshot
- **docs-platform-208.AC2.4 Edge:** Highlighting a non-existent `data-testid` does not cause an error (no-op)

### docs-platform-208.AC3: Screenshots are trimmed of whitespace
- **docs-platform-208.AC3.1 Success:** Pillow-based trimming removes empty margins from captured screenshots
- **docs-platform-208.AC3.2 Success:** Trimmed image retains all non-empty content (no content cropped)
- **docs-platform-208.AC3.3 Edge:** An image with no whitespace margins is returned unchanged
- **docs-platform-208.AC3.4 Success:** Focused element capture (`locator.screenshot()`) produces a tightly-cropped image of just that element

---

<!-- START_TASK_1 -->
### Task 1: Add Pillow dev dependency

**Files:**
- Modify: `pyproject.toml` (dev dependencies section, around line 160-183)

**Step 1: Add Pillow to dev dependencies**

In `pyproject.toml`, add `"Pillow>=11.0"` to the `[dependency-groups] dev` list.

**Step 2: Verify operationally**

Run: `uv sync`
Expected: Dependencies install without errors, Pillow is resolved.

Run: `uv run python -c "from PIL import Image, ImageChops; print('Pillow OK')"  `
Expected: Prints "Pillow OK"

**Step 3: Commit**

Verify `uv.lock` was updated by `uv sync` (it should exist and show changes in `git diff`), then commit both files:

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add Pillow to dev dependencies for guide screenshot trimming"
```
<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-5) -->
<!-- START_TASK_2 -->
### Task 2: Create docs package with screenshot module

**Verifies:** docs-platform-208.AC2.1, docs-platform-208.AC2.2, docs-platform-208.AC2.3, docs-platform-208.AC2.4, docs-platform-208.AC3.1, docs-platform-208.AC3.2, docs-platform-208.AC3.3

**Files:**
- Create: `src/promptgrimoire/docs/__init__.py`
- Create: `src/promptgrimoire/docs/screenshot.py`
- Test: `tests/unit/test_docs_screenshot.py` (unit)

**Implementation:**

Create `src/promptgrimoire/docs/__init__.py` as an empty package init.

Create `src/promptgrimoire/docs/screenshot.py` with:

1. `trim_whitespace(image_bytes: bytes) -> bytes` — Takes raw PNG bytes, detects content bounds using `ImageChops.difference()` against a white background, crops empty margins with `Image.crop()`, returns trimmed PNG bytes. If the image has no whitespace margins (bbox matches full image), returns the input unchanged. Uses `io.BytesIO` for in-memory byte conversion.

2. `highlight_elements(page: Page, test_ids: Sequence[str]) -> ElementHandle | None` — Injects a `<style>` element via `page.add_style_tag(content=...)` that applies `outline: 3px solid #e53e3e; outline-offset: 2px;` to each `[data-testid="<id>"]` selector. Returns the `ElementHandle` for later removal. If `test_ids` is empty, returns `None`.

3. `remove_highlight(page: Page, style_handle: ElementHandle | None) -> None` — Removes the injected style element via `page.evaluate("el => el.remove()", style_handle)`. If `style_handle` is `None`, no-op.

4. `capture_screenshot(page: Page, path: Path, *, highlight: Sequence[str] = (), focus: str | None = None, trim: bool = True) -> Path` — Orchestrates the full capture workflow:
   - If `highlight` is non-empty, call `highlight_elements()`
   - If `focus` is provided, use `page.get_by_test_id(focus).screenshot()` for element-specific capture; otherwise use `page.screenshot()`
   - If `highlight` was applied, call `remove_highlight()`
   - If `trim` is True, pass bytes through `trim_whitespace()`
   - Write final bytes to `path`
   - Return `path`

Import `Page` and `ElementHandle` from `playwright.sync_api`. Use `from __future__ import annotations` for deferred annotation evaluation.

**Testing:**

Tests must verify each AC listed above:
- docs-platform-208.AC3.1: Create a test PNG with known white margins using Pillow, pass through `trim_whitespace()`, verify output dimensions are smaller than input
- docs-platform-208.AC3.2: Open both original and trimmed images with `Image.open()`. Crop the original to the expected content bbox (computed via `ImageChops.difference()` and `getbbox()`). Compare the cropped original's pixel data against the trimmed image's pixel data using `assert original_cropped.tobytes() == trimmed.tobytes()`
- docs-platform-208.AC3.3: Create a test PNG with no margins (content fills entire image), pass through `trim_whitespace()`, verify output bytes equal input bytes

Note: AC3.4 (focused element capture via `locator.screenshot()`) requires a live Playwright browser and will be verified during E2E/integration testing in later phases. The `capture_screenshot()` function delegates to Playwright's `locator.screenshot()` for this — no custom cropping needed.

For `highlight_elements` and `remove_highlight`, unit testing requires mocking the Playwright `Page` object since these inject CSS into a live browser. Mock `page.add_style_tag()` to return a mock `ElementHandle`, and verify `page.evaluate()` is called with the correct removal expression.

Follow project testing patterns from `tests/unit/conftest.py` (factory fixtures, `unittest.mock` for external deps).

**Verification:**

Run: `uv run pytest tests/unit/test_docs_screenshot.py -v`
Expected: All tests pass

**Commit:** `feat: add screenshot module with whitespace trimming and CSS highlight injection`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create Guide DSL context managers

**Verifies:** docs-platform-208.AC1.1, docs-platform-208.AC1.2, docs-platform-208.AC1.3, docs-platform-208.AC1.4, docs-platform-208.AC1.5, docs-platform-208.AC1.6

**Files:**
- Create: `src/promptgrimoire/docs/guide.py`
- Test: `tests/unit/test_docs_guide.py` (unit)

**Implementation:**

Create `src/promptgrimoire/docs/guide.py` with two classes:

**`Guide` class** — Context manager for a single guide document:
- `__init__(self, title: str, output_dir: Path, page: Page, *, screenshot_subdir: str = "screenshots")` — Store params; initialise empty `_buffer: list[str]` for markdown lines and `_screenshot_counter: int = 0`.
- `__enter__(self) -> Self` — Create `output_dir` and `output_dir / screenshot_subdir` directories (using `mkdir(parents=True, exist_ok=True)`). Append `# {title}\n` to buffer. Return self.
- `__exit__(self, *exc_info)` — Write `_buffer` contents joined with `\n` to `output_dir / f"{self._slug}.md"` where `_slug` is the title lowercased with spaces replaced by hyphens. If an exception occurred (exc_info[0] is not None), re-raise it (return False).
- `step(self, heading: str) -> Step` — Return a `Step` instance bound to this guide.
- `note(self, text: str) -> None` — Append `text + "\n"` to buffer.
- `screenshot(self, caption: str = "", *, highlight: Sequence[str] = (), focus: str | None = None, trim: bool = True) -> Path` — Increment `_screenshot_counter`, compute filename `f"{self._slug}-{self._screenshot_counter:02d}.png"`, call `capture_screenshot()` from the screenshot module, append `![{caption}]({screenshot_subdir}/{filename})\n` to buffer, return the path.
- `_slug` property — Derive from title: lowercase, replace spaces with hyphens, strip non-alphanumeric (except hyphens).

**`Step` class** — Context manager for a guide step:
- `__init__(self, guide: Guide, heading: str)` — Store reference to parent guide and heading.
- `__enter__(self) -> Guide` — Append `## {heading}\n` to guide's buffer. Return the guide (so `with guide.step("foo") as g:` gives access to guide methods).
- `__exit__(self, *exc_info)` — Auto-capture a screenshot (call `guide.screenshot(caption=self._heading)`). If an exception occurred, do not capture, re-raise.

Use `from __future__ import annotations` for deferred annotations. Import `Page` from `playwright.sync_api`.

**Testing:**

Tests must verify each AC:
- docs-platform-208.AC1.1: Create a `Guide` with a mock `Page` and a temp directory. Enter and exit the context manager. Verify the output directory was created and a `.md` file was written.
- docs-platform-208.AC1.2: Enter a `Step` context. Verify `## heading` appears in the guide's buffer.
- docs-platform-208.AC1.3: Call `guide.note("some text")`. Verify "some text" appears in the buffer.
- docs-platform-208.AC1.4: Mock `capture_screenshot` to return a path. Call `guide.screenshot("caption")`. Verify `![caption](screenshots/...)` appears in the buffer.
- docs-platform-208.AC1.5: Enter and exit a `Step`. Verify a screenshot was auto-captured (mock `capture_screenshot` and assert it was called).
- docs-platform-208.AC1.6: Create two steps in sequence. Verify both headings and both image references appear in order in the final markdown.

Mock `capture_screenshot` from `promptgrimoire.docs.screenshot` for all Guide/Step tests since they don't need a real browser. Use `unittest.mock.patch`.

**Verification:**

Run: `uv run pytest tests/unit/test_docs_guide.py -v`
Expected: All tests pass

**Commit:** `feat: add Guide DSL context managers for documentation generation`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update docs package __init__.py exports

**Files:**
- Modify: `src/promptgrimoire/docs/__init__.py`

**Step 1: Add public API exports**

Update `__init__.py` to export the public API:

```python
from promptgrimoire.docs.guide import Guide
from promptgrimoire.docs.screenshot import capture_screenshot, trim_whitespace

__all__ = ["Guide", "capture_screenshot", "trim_whitespace"]
```

**Step 2: Verify operationally**

Run: `uv run python -c "from promptgrimoire.docs import Guide; print('Import OK')"`
Expected: Prints "Import OK"

Run: `uv run ruff check src/promptgrimoire/docs/`
Expected: No lint errors

Run: `uvx ty check`
Expected: No type errors in docs module

**Step 3: Commit**

```bash
git add src/promptgrimoire/docs/__init__.py
git commit -m "chore: add public exports for docs package"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Run full test suite to verify no regressions

**Files:** None (verification only)

**Step 1: Run all tests**

Run: `uv run test-all`
Expected: All tests pass (2980+ tests), no regressions

Run: `uv run pytest tests/unit/test_docs_guide.py tests/unit/test_docs_screenshot.py -v`
Expected: All new tests pass

**Step 2: Run linting and type checking**

Run: `uv run ruff check .`
Expected: No errors

Run: `uvx ty check`
Expected: No errors

**Step 3: Commit (if any formatting changes occurred)**

Only if hooks modified files:
```bash
git add -u
git commit -m "chore: formatting fixes from Phase 1"
```
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_A -->
