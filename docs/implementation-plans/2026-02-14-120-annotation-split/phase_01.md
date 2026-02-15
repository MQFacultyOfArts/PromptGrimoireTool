# Annotation Module Split — Phase 1: Extract JS to Static Files

**Goal:** Move scroll-sync card positioning and copy protection JavaScript from Python string constants to static JS files.

**Architecture:** Extract two self-contained JS blocks from `annotation.py` into `static/` files, following the pattern established by `annotation-highlight.js`. Each block becomes a named function loaded via `<script>` tag and invoked from Python via `ui.run_javascript()`.

**Tech Stack:** JavaScript (browser), Python/NiceGUI (call sites)

**Scope:** 4 phases from original design (phase 1 of 4)

**Codebase verified:** 2026-02-14

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 120-annotation-split.AC2: JS extracted to static files
- **120-annotation-split.AC2.1 Success:** `static/annotation-card-sync.js` exists and exposes `setupCardPositioning()`
- **120-annotation-split.AC2.2 Success:** `static/annotation-copy-protection.js` exists and exposes `setupCopyProtection()`
- **120-annotation-split.AC2.3 Success:** Scroll-sync card positioning works in browser (cards track highlight positions on scroll)
- **120-annotation-split.AC2.4 Success:** Copy protection blocks copy/cut/drag/print when enabled
- **120-annotation-split.AC2.5 Success:** No `_COPY_PROTECTION_JS` Python string constant remains in the codebase

### 120-annotation-split.AC4: No logic changes (partial — Phase 1 contribution)
- **120-annotation-split.AC4.1 Success:** All existing tests pass (`uv run test-all`)
- **120-annotation-split.AC4.2 Success:** E2E tests pass (`uv run test-e2e`)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create `static/annotation-card-sync.js`

**Verifies:** 120-annotation-split.AC2.1

**Files:**
- Create: `src/promptgrimoire/static/annotation-card-sync.js`

**Implementation:**

Extract the scroll-sync IIFE from `src/promptgrimoire/pages/annotation.py:1253–1363` into a standalone JS file. Convert from Python string concatenation to clean JavaScript. Wrap in a named function `setupCardPositioning(docContainerId, sidebarId, minGap)` that:

1. Accepts element ID strings (not DOM references — Vue replaces DOM elements, so references go stale)
2. Closes over the IDs and resolves them via `document.getElementById()` on every call (existing behaviour)
3. Sets up:
   - `positionCards()` — positions sidebar cards to track their highlight's vertical position
   - Scroll event listener (passive, RAF-throttled)
   - `highlights-ready` event listener to re-attach MutationObserver when annotations container DOM is replaced by Vue
   - Card hover via event delegation on `document` (mouseover) — calls `showHoverHighlight()`/`clearHoverHighlight()` from `annotation-highlight.js`
4. Exposes `window._positionCards = positionCards` for external calls (existing behaviour)

The function depends on these globals from `annotation-highlight.js` (loaded first):
- `walkTextNodes(root)` — builds text node map
- `charOffsetToRect(textNodes, charIdx)` — maps character offset to screen rect
- `showHoverHighlight(nodes, startChar, endChar)` — highlights text range on card hover
- `clearHoverHighlight()` — removes hover highlight

The `window._textNodes` global is shared with `annotation-highlight.js` (existing convention).

**Verification:**

```bash
# File exists and is valid JS (no Python string artifacts)
grep -c 'function setupCardPositioning' src/promptgrimoire/static/annotation-card-sync.js
# Expected: 1
```

**Commit:** `refactor: extract scroll-sync card positioning JS to static file`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create `static/annotation-copy-protection.js`

**Verifies:** 120-annotation-split.AC2.2

**Files:**
- Create: `src/promptgrimoire/static/annotation-copy-protection.js`

**Implementation:**

Extract the `_COPY_PROTECTION_JS` constant from `src/promptgrimoire/pages/annotation.py:2802–2848` into a standalone JS file. Convert from Python triple-quoted string to clean JavaScript. Wrap in a named function `setupCopyProtection(protectedSelectors)` that:

1. Accepts a CSS selector string identifying protected areas (currently `'#doc-container, [data-testid="respond-reference-panel"]'`)
2. Registers event listeners on `document` (capture phase) for:
   - `copy`, `cut`, `contextmenu`, `dragstart` — blocks if target matches `protectedSelectors`
   - `paste` — blocks on `#milkdown-respond-editor` specifically
   - `keydown` — intercepts `Ctrl+P`/`Cmd+P`
3. Shows `Quasar.Notify.create()` toast on blocked actions (Quasar is loaded by NiceGUI)

The `protectedSelectors` parameter replaces the hardcoded `PROTECTED` variable in the original IIFE.

Note: `_COPY_PROTECTION_PRINT_CSS` and `_COPY_PROTECTION_PRINT_MESSAGE` (lines 2851–2863) stay in Python — they're CSS/HTML, not JS.

**Verification:**

```bash
# File exists and is valid JS
grep -c 'function setupCopyProtection' src/promptgrimoire/static/annotation-copy-protection.js
# Expected: 1
```

**Commit:** `refactor: extract copy protection JS to static file`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Update call sites in `annotation.py`

**Verifies:** 120-annotation-split.AC2.3, 120-annotation-split.AC2.4, 120-annotation-split.AC2.5

**Files:**
- Modify: `src/promptgrimoire/pages/annotation.py:1206` (script loading area)
- Modify: `src/promptgrimoire/pages/annotation.py:1248–1365` (scroll-sync block — remove and replace with function call)
- Modify: `src/promptgrimoire/pages/annotation.py:2802–2848` (remove `_COPY_PROTECTION_JS` constant)
- Modify: `src/promptgrimoire/pages/annotation.py:2876` (`_inject_copy_protection()` — update to use static file)
- Modify: `tests/unit/test_copy_protection_js.py` (remove `_COPY_PROTECTION_JS` import and `TestCopyProtectionJsContent` class)

**Implementation:**

**Step 1: Load the new static JS files.**

Near the existing `annotation-highlight.js` load at line 1206, add script tags for the two new files. They must load AFTER `annotation-highlight.js` since `annotation-card-sync.js` depends on functions from it:

```python
ui.add_body_html('<script src="/static/annotation-highlight.js"></script>')
ui.add_body_html('<script src="/static/annotation-card-sync.js"></script>')
ui.add_body_html('<script src="/static/annotation-copy-protection.js"></script>')
```

**Step 2: Replace scroll-sync IIFE with function call.**

Remove the `scroll_sync_js` string concatenation block (lines 1248–1363 including the `# fmt: off`/`# fmt: on` markers and the comments above it). Replace the `ui.run_javascript(scroll_sync_js)` call at line 1365 with:

```python
ui.run_javascript("setupCardPositioning('doc-container', 'annotations-container', 8)")
```

**Step 3: Replace `_COPY_PROTECTION_JS` usage.**

In `_inject_copy_protection()` (line 2876), replace:
```python
ui.run_javascript(_COPY_PROTECTION_JS)
```
with:
```python
_selectors = '#doc-container, [data-testid="respond-reference-panel"]'
ui.run_javascript(f"setupCopyProtection({_selectors!r})")
```

The `!r` format spec wraps the selector string in quotes and escapes any internal quotes, avoiding fragile manual escaping. The selector string must match the current hardcoded `PROTECTED` value in the original IIFE.

**Step 4: Remove the `_COPY_PROTECTION_JS` constant** (lines 2802–2848). The `_COPY_PROTECTION_PRINT_CSS` and `_COPY_PROTECTION_PRINT_MESSAGE` constants stay — they're CSS/HTML used by `_inject_copy_protection()`.

**Step 5: Update `test_copy_protection_js.py` to remove `_COPY_PROTECTION_JS` references.**

The `_COPY_PROTECTION_JS` constant no longer exists, so:

1. Remove `_COPY_PROTECTION_JS` from the import statement (line 27). The remaining imports (`_inject_copy_protection`, `_render_workspace_header`) stay.
2. Delete the entire `TestCopyProtectionJsContent` class (lines 173–238) — all its assertions checked substring content of the now-deleted Python constant. The Phase 1 Task 4 guard test covers the structural invariant (no constant, static JS file exists). The JS file's content is verified by E2E tests.

The other test classes (`TestCopyProtectionInactiveStates`, `TestInjectCopyProtectionFunction`, `TestRenderWorkspaceHeaderSignature`) remain unchanged — they test Python logic, not the JS constant.

**Verification:**

```bash
uv run test-all
# Expected: All tests pass (2471+)

# Verify constant is gone
grep -r '_COPY_PROTECTION_JS' src/promptgrimoire/
# Expected: No matches (the PRINT_CSS and PRINT_MESSAGE variants are different names)
```

**Commit:** `refactor: update annotation.py call sites to use extracted JS files`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Guard test — no `_COPY_PROTECTION_JS` constant and static files exist

**Verifies:** 120-annotation-split.AC2.1, 120-annotation-split.AC2.2, 120-annotation-split.AC2.5

**Files:**
- Create: `tests/unit/test_annotation_js_extraction.py`

**Implementation:**

Write a guard test that verifies the structural properties of the JS extraction:

1. `static/annotation-card-sync.js` exists
2. `static/annotation-copy-protection.js` exists
3. `annotation-card-sync.js` contains `function setupCardPositioning`
4. `annotation-copy-protection.js` contains `function setupCopyProtection`
5. No Python file in `src/promptgrimoire/` contains a `_COPY_PROTECTION_JS` string constant (grep for the assignment pattern `_COPY_PROTECTION_JS =`)

Follow the pattern in `tests/unit/export/test_no_fstring_latex.py` and `tests/unit/test_async_fixture_safety.py` for structural guard tests. Use `pathlib.Path` to locate files relative to the package root.

**Testing:**

Tests verify structural invariants (AC2.1, AC2.2, AC2.5). No mocking needed — these are filesystem checks.

- 120-annotation-split.AC2.1: Assert `annotation-card-sync.js` exists and contains `setupCardPositioning` function declaration
- 120-annotation-split.AC2.2: Assert `annotation-copy-protection.js` exists and contains `setupCopyProtection` function declaration
- 120-annotation-split.AC2.5: Assert no Python file defines `_COPY_PROTECTION_JS`

**Verification:**

```bash
uv run pytest tests/unit/test_annotation_js_extraction.py -v
# Expected: All guard tests pass

uv run test-all
# Expected: All tests pass including new guard tests
```

**Commit:** `test: add guard tests for JS extraction structural invariants`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
### Task 5: Smoke test — verify browser behaviour

**Verifies:** 120-annotation-split.AC2.3, 120-annotation-split.AC2.4, 120-annotation-split.AC4.1, 120-annotation-split.AC4.2

**Files:** None (verification only)

**Implementation:**

Run the full test suite and E2E tests to verify no regressions:

```bash
uv run test-all
# Expected: All tests pass

uv run test-e2e
# Expected: All E2E tests pass (scroll-sync and copy protection exercised by annotation E2E tests)
```

**UAT Steps (manual — AC2.3, AC2.4):**

1. Start the app: `uv run python -m promptgrimoire`
2. Navigate to an annotation workspace with a document and highlights
3. **Scroll test (AC2.3):** Scroll the document up and down. Annotation cards in the sidebar should track the vertical position of their associated highlights. Cards for off-screen highlights should hide.
4. **Hover test (AC2.3):** Hover over an annotation card in the sidebar. The corresponding text region in the document should glow/highlight.
5. **Copy protection test (AC2.4):** Enable copy protection on an Activity, open a student workspace. Try `Ctrl+C` on selected text in the document — should show "Copying is disabled" toast and block the copy. Try `Ctrl+P` — should be intercepted.

No commit for this task — verification only.
<!-- END_TASK_5 -->
