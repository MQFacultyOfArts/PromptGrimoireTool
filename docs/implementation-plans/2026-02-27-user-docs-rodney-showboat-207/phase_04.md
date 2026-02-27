# Automated User Documentation — Phase 4: Robustness and NiceGUI Interaction Patterns

**Goal:** Harden Rodney/NiceGUI interaction by replacing fragile sleep-based waits with element-targeted synchronisation, adding error context for debugging, and setting explicit timeouts.

**Architecture:** Add a `wait_for()` bash helper to `common.sh` that wraps `rodney wait` with error context and failure screenshots. Replace fragile `sleep` + `waitstable` patterns in both guide scripts with `wait_for` calls targeting specific elements. Set `ROD_TIMEOUT` in the Python orchestrator for predictable failure windows.

**Tech Stack:** Bash (common.sh), Python (cli.py), Rodney (CLI browser automation via go-rod/rod)

**Scope:** Phase 4 of 4 from design plan

**Codebase verified:** 2026-02-27

**Evidence base:** Rodney source analysis (`main.go` at commit `9e7ae93`, go-rod/rod wrapper). Live testing against NiceGUI app confirmed `rodney wait` handles WebSocket-driven DOM updates.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### user-docs-rodney-showboat-207.AC4: Pipeline is re-runnable
- **user-docs-rodney-showboat-207.AC4.1 Success:** Running `uv run make-docs` twice produces valid PDFs containing expected sections and screenshots (content equivalence, not byte identity)

### user-docs-rodney-showboat-207.AC1: CLI entry point works end-to-end (partial)
- **user-docs-rodney-showboat-207.AC1.6 Failure:** If a script fails mid-way, error output identifies the failing step

---

## Rodney Behaviour Reference (from source analysis)

The following table summarises Rodney command behaviour relevant to NiceGUI integration. All timeouts default to 30s, configurable via `ROD_TIMEOUT` env var (float seconds).

| Command | Waits for element? | What it waits for | Notes |
|---------|-------------------|-------------------|-------|
| `wait <sel>` | Yes (up to timeout) | DOM existence + CSS visibility | Two-stage: `page.Element()` then `MustWaitVisible()` |
| `click <sel>` | Yes (up to timeout) | DOM existence only | 100ms post-click sleep. Does NOT wait for visibility. |
| `input <sel> <text>` | Yes (up to timeout) | DOM existence only | Clears first via `MustSelectAllText()`. Real keyboard events. |
| `exists <sel>` | **No** (instant) | N/A | Uses `page.Has()`. Exit 0/1. |
| `visible <sel>` | Partial | Waits for DOM existence, then instant visibility check | Exit 0/1. |
| `count <sel>` | **No** (instant) | N/A | Always exits 0. |
| `waitload` | N/A (page-level) | Browser `load` event | No selector argument. |
| `waitstable` | N/A (page-level) | DOM stops changing | No selector argument. |
| `waitidle` | N/A (page-level) | Zero network requests | No selector argument. |
| `sleep <seconds>` | **No** (explicit duration) | N/A | Accepts float (e.g., 0.5). Process-level `time.Sleep()`, no browser interaction. |

**Exit codes:** 0 = success, 1 = check failed (exists/visible/assert), 2 = error/timeout.

**Why this matters for NiceGUI:** NiceGUI pushes DOM updates via WebSocket after server-side Python executes. `rodney wait` and `rodney click` both poll for element existence (up to 30s), so they naturally handle the async gap. Explicit `sleep` calls are only needed for genuinely slow operations (e.g., LaTeX compilation).

---

<!-- START_TASK_1 -->
### Task 1: Add `wait_for` helper and set `ROD_TIMEOUT` in orchestrator

**Verifies:** user-docs-rodney-showboat-207.AC1.6

**Files:**
- Modify: `docs/guides/scripts/common.sh`
- Modify: `src/promptgrimoire/cli.py` (within `make_docs()`, the subprocess environment)

**Implementation:**

**1a. Add `wait_for()` to common.sh:**

Add after the existing `step()` function:

```bash
# Wait for a specific element to appear and become visible.
# On failure, captures an error screenshot and prints context.
wait_for() {
  local selector="$1"
  local context="${2:-$selector}"
  if ! rodney wait --local "$selector"; then
    echo "FAILED waiting for: $context (selector: $selector)" >&2
    rodney screenshot --local -w 1280 -h 800 "$SCREENSHOT_DIR/ERROR_$(date +%s).png" 2>/dev/null || true
    return 1
  fi
}
```

This wrapper:
- Calls `rodney wait` which polls for DOM existence + visibility (up to `ROD_TIMEOUT`)
- On failure: prints human-readable context to stderr, captures an error screenshot showing page state at failure time
- Returns 1 to trigger `set -e` exit, which the orchestrator catches

**1b. Set `ROD_TIMEOUT` in cli.py:**

In the `make_docs()` function, when constructing the subprocess environment for script invocation, add `ROD_TIMEOUT`:

```python
script_env = os.environ.copy()
script_env["ROD_TIMEOUT"] = "15"
```

Pass `env=script_env` to each `subprocess.run()` call that invokes the guide scripts.

This sets a 15-second timeout for all Rodney wait operations. The default 30s is generous but makes failures slow to detect. 15s is ample for NiceGUI page transitions while providing faster feedback on broken selectors.

**Verification:**

Run: `bash -n docs/guides/scripts/common.sh`
Expected: Syntax check passes.

Run: `uv run ruff check src/promptgrimoire/cli.py`
Expected: No lint errors.

Run: `uv run test-all`
Expected: Existing tests pass (including test_make_docs.py — update mocks if subprocess.run calls change signature).

**Commit:**

```bash
git add docs/guides/scripts/common.sh src/promptgrimoire/cli.py
git commit -m "feat: add wait_for helper and ROD_TIMEOUT for robust NiceGUI waits"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Replace fragile waits in instructor guide script

**Verifies:** user-docs-rodney-showboat-207.AC4.1, user-docs-rodney-showboat-207.AC1.6

**Files:**
- Modify: `docs/guides/scripts/generate-instructor-setup.sh`

**Implementation:**

Apply the following replacement strategy to the instructor script:

**Replace** `sleep N` + `waitstable` before interactions with `wait_for` targeting the next element:

| Location | Current pattern | Replacement |
|----------|----------------|-------------|
| After `rodney open` (navigator) | `rodney waitload` + `rodney waitstable` | `rodney waitload --local` + `wait_for '.q-page' 'Navigator page container'` |
| After `rodney open` (courses/new) | `rodney waitload` + `rodney waitstable` | `rodney waitload --local` + `wait_for '[data-testid="course-code-input"]' 'Create unit form'` |
| After create unit click | `rodney waitload` + `rodney waitstable` | `rodney waitload --local` + `wait_for '[data-testid="add-week-btn"]' 'Unit detail page'` |
| After add week click | `rodney waitload` + `rodney waitstable` | `rodney waitload --local` + `wait_for '[data-testid="week-number-input"]' 'Week creation form'` |
| After create week click | `rodney waitload` + `rodney waitstable` | `rodney waitload --local` + `wait_for '[data-testid="publish-week-btn"]' 'Week publish button'` |
| After start activity click (annotation page) | `sleep 1` | `wait_for '[data-testid="content-editor"]' 'Annotation page editor'` |
| After tag settings click | `sleep 0.5` + `rodney waitstable` | `wait_for '[data-testid="add-tag-group-btn"]' 'Tag management dialog'` |
| After student re-auth + navigate | `rodney waitload` + `rodney waitstable` | `rodney waitload --local` + `wait_for '.q-page' 'Student navigator page'` |

**Keep unchanged:**
- `rodney waitstable --local` after `rodney click '[data-testid="publish-week-btn"]'` — publishing doesn't navigate, just updates in-place, no specific new element to target
- `uv run manage-users` commands — not browser interaction

**Key implementation notes:**
- Every `wait_for` call gets a human-readable context string as second argument. This appears in error messages when AC1.6 fires.
- `rodney waitload` is kept before `wait_for` after page navigations — `waitload` waits for the browser's `load` event (subresources), while `wait_for` then waits for a specific NiceGUI-rendered element.
- After navigation within the SPA (clicks that change NiceGUI route), skip `waitload` and use `wait_for` directly — the SPA doesn't fire a new `load` event.

**Verification:**

Run: `bash -n docs/guides/scripts/generate-instructor-setup.sh`
Expected: Syntax check passes.

Run: `uv run make-docs`
Expected: Both PDFs produced. Instructor guide has all 7 screenshots.

**Commit:**

```bash
git add docs/guides/scripts/generate-instructor-setup.sh
git commit -m "refactor: replace fragile sleeps with wait_for in instructor script"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Replace fragile waits in student workflow guide script

**Verifies:** user-docs-rodney-showboat-207.AC4.1, user-docs-rodney-showboat-207.AC1.6

**Files:**
- Modify: `docs/guides/scripts/generate-student-workflow.sh`

**Implementation:**

Apply the same replacement strategy to the student script:

| Location | Current pattern | Replacement |
|----------|----------------|-------------|
| After login + navigate | `rodney waitload` + `rodney waitstable` | `rodney waitload --local` + `wait_for '.q-page' 'Navigator after login'` |
| After start activity click | `sleep 1` | `wait_for '[data-testid="content-editor"]' 'Annotation page loaded'` |
| After content editor click | `rodney waitstable` | `wait_for '[data-testid="content-editor"]' 'Content editor focused'` (already there from click wait) |
| After paste (Ctrl+v) | `sleep 1` + `rodney waitstable` | `rodney sleep 1` + `rodney waitstable --local` (keep — paste processing is asynchronous, no specific element signals completion) |
| After text selection JS | `sleep 1` + `rodney waitstable` | `wait_for '[data-testid="highlight-menu"]' 'Highlight tag menu appeared'` |
| After highlight tag click | `sleep 1` + `rodney waitstable` | `wait_for '[data-testid="annotation-card"]' 'Annotation card created in sidebar'` |
| After comment input + Enter | `sleep 0.5` + `rodney waitstable` | `wait_for '[data-testid="comment"]' 'Comment saved'` |
| After tab-organise click | `rodney waitload` + `rodney waitstable` + `sleep 0.5` | `wait_for '[data-testid="organise-columns"]' 'Organise tab loaded'` |
| After tab-respond click | `rodney waitload` + `rodney waitstable` + `sleep 1` | `wait_for '[data-testid="milkdown-editor-container"]' 'Respond tab editor loaded'` |
| After export PDF click | `sleep 3` + `rodney waitstable` | `rodney sleep 3` + `rodney waitstable --local` (keep — LaTeX compilation is genuinely slow, no DOM element signals completion) |

**Keep unchanged:**
- `rodney sleep 1` after paste — HTML processing is async server-side, no specific element signals completion
- `rodney sleep 3` after export PDF click — LaTeX compilation takes real time
- `rodney sleep 0.5` before Milkdown editor JS focus — editor initialisation timing

**Verification:**

Run: `bash -n docs/guides/scripts/generate-student-workflow.sh`
Expected: Syntax check passes.

Run: `uv run make-docs`
Expected: Both PDFs produced. Student guide has all 9 screenshots.

Run `uv run make-docs` a second time.
Expected: Both PDFs produced again (AC4.1 — re-runnable).

**Commit:**

```bash
git add docs/guides/scripts/generate-student-workflow.sh
git commit -m "refactor: replace fragile sleeps with wait_for in student script"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add error reporting with last screenshot to orchestrator

**Verifies:** user-docs-rodney-showboat-207.AC1.6

**Files:**
- Modify: `src/promptgrimoire/cli.py` (within `make_docs()`)

**Implementation:**

When a guide script fails (non-zero exit code from `subprocess.run()`), the orchestrator should report:
1. Which script failed (instructor or student)
2. The stderr output from the script (which includes `wait_for` context messages)
3. The path to the most recent `ERROR_*` screenshot, if any

```python
result = subprocess.run(
    ["bash", script_path, base_url],
    env=script_env,
    capture_output=True,
    text=True,
)
if result.returncode != 0:
    print(f"ERROR: {script_path} failed (exit {result.returncode})", file=sys.stderr)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    # Find most recent error screenshot
    from pathlib import Path
    error_shots = sorted(Path(guide_dir).glob("screenshots/*/ERROR_*.png"))
    if error_shots:
        print(f"Last error screenshot: {error_shots[-1]!s}", file=sys.stderr)
    sys.exit(1)
```

**Key notes:**
- Change from `check=True` (which raises CalledProcessError) to manual exit code checking, so we can format the error before exiting.
- The `wait_for` helper in common.sh prints "FAILED waiting for: [context]" to stderr, which is captured by `capture_output=True`.
- Error screenshots are timestamped (`ERROR_<epoch>.png`), so the most recent one (`sorted()[-1]`) corresponds to the failure.

**Verification:**

Run: `uv run ruff check src/promptgrimoire/cli.py`
Expected: No lint errors.

Run: `uv run test-all`
Expected: All tests pass. Update `tests/unit/test_make_docs.py` to verify:
- When subprocess returns non-zero, make_docs prints the script name and exit code
- stderr from the script is forwarded to the user

**Testing:**
Tests must verify:
- user-docs-rodney-showboat-207.AC1.6: Mock subprocess to return non-zero exit code with stderr containing "FAILED waiting for: Create unit form". Verify make_docs prints the script name and the wait_for context message.

**Commit:**

```bash
git add src/promptgrimoire/cli.py tests/unit/test_make_docs.py
git commit -m "feat: add error reporting with context and screenshot paths on script failure"
```
<!-- END_TASK_4 -->
