# Automated User Documentation — Phase 1: Dependencies and CLI Skeleton

**Goal:** Install Showboat, document Rodney, create the `make-docs` CLI entry point, and wire up the server lifecycle with dependency checking.

**Architecture:** Python orchestrator in `cli.py` checks for external tools, starts the app server (reusing existing E2E helpers), invokes shell scripts, converts output to PDF via Pandoc, stops the server. Shell scripts in `docs/guides/scripts/` use Rodney + Showboat.

**Tech Stack:** Python (cli.py), bash (common.sh), Showboat (CLI), Rodney (CLI), Pandoc + LuaLaTeX

**Scope:** Phase 1 of 4 from design plan

**Codebase verified:** 2026-02-27

---

## Acceptance Criteria Coverage

This phase implements and tests:

### user-docs-rodney-showboat-207.AC1: CLI entry point works end-to-end
- **user-docs-rodney-showboat-207.AC1.1 Success:** `uv run make-docs` starts app server with mock auth on a free port
- **user-docs-rodney-showboat-207.AC1.2 Success:** Server is stopped after scripts complete (even on failure)
- **user-docs-rodney-showboat-207.AC1.4 Failure:** If Rodney is not installed, command exits with clear error message
- **user-docs-rodney-showboat-207.AC1.5 Failure:** If Showboat is not installed, command exits with clear error message

### user-docs-rodney-showboat-207.AC4: Pipeline is re-runnable
- **user-docs-rodney-showboat-207.AC4.2 Success:** All generated artefacts (screenshots, .md, .pdf) are gitignored
- **user-docs-rodney-showboat-207.AC4.3 Success:** Only `docs/guides/scripts/` is committed to git

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add Showboat dev dependency and make-docs script entry point

**Files:**
- Modify: `pyproject.toml` (lines 36-49 for scripts, lines 159-181 for dev deps)

**Step 1: Add showboat to dev dependencies**

In `pyproject.toml` under `[dependency-groups] dev`, add:
```
"showboat>=0.6",
```

**Step 2: Add make-docs script entry point**

In `pyproject.toml` under `[project.scripts]`, add:
```
make-docs = "promptgrimoire.cli:make_docs"
```

**Step 3: Sync dependencies**

Run: `uv sync`
Expected: Installs showboat, creates `make-docs` entry point.

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add showboat and make-docs entry point"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create `make_docs()` CLI function with dependency checks and server lifecycle

**Verifies:** user-docs-rodney-showboat-207.AC1.1, user-docs-rodney-showboat-207.AC1.2, user-docs-rodney-showboat-207.AC1.4, user-docs-rodney-showboat-207.AC1.5

**Files:**
- Modify: `src/promptgrimoire/cli.py` (add `make_docs()` function near the end, after existing CLI functions)

**Implementation:**

The `make_docs()` function:

1. Check `shutil.which("rodney")` and `shutil.which("showboat")` — if either is missing, print an error naming the missing tool with install instructions and `sys.exit(1)`.
2. Call `_pre_test_db_cleanup()` to run Alembic migrations and truncate tables.
3. Find a free port using the same socket-binding pattern as `test_e2e()`.
4. Call `_start_e2e_server(port)` to start the NiceGUI server with `DEV__AUTH_MOCK=true`.
5. In a try/finally block:
   - Construct `base_url = f"http://localhost:{port}"`
   - Define script paths: `docs/guides/scripts/generate-instructor-setup.sh` and `docs/guides/scripts/generate-student-workflow.sh`
   - Run each script as a subprocess with `base_url` as the first argument. Capture exit codes.
   - If any script fails, print which script failed and exit.
   - Run Pandoc to convert each `.md` output to `.pdf`: `pandoc docs/guides/instructor-setup.md -o docs/guides/instructor-setup.pdf --pdf-engine=lualatex`
   - Print output paths.
6. In the finally block: call `_stop_e2e_server(server_process)`.

Use `subprocess.run()` for shell scripts (not `Popen`) since they run sequentially. **Pass `cwd` pointing to the project root** (e.g., `Path(__file__).resolve().parents[2]`, since `cli.py` is at `src/promptgrimoire/cli.py`) to ensure scripts and their `uv run` subcommands can find `pyproject.toml`.

For the free port, reuse the pattern from `test_e2e()`:
```python
import socket
with socket.socket() as s:
    s.bind(("", 0))
    port = s.getsockname()[1]
```

**Testing:**

Tests must verify each AC listed above:
- AC1.1: `make_docs()` with mocked `_start_e2e_server` verifies it's called with a port and `DEV__AUTH_MOCK=true` is set.
- AC1.2: `make_docs()` with a script that raises an error still calls `_stop_e2e_server` (mock and assert).
- AC1.4: `make_docs()` with `shutil.which("rodney")` returning `None` exits with error mentioning "rodney" and does NOT call `_start_e2e_server`.
- AC1.5: `make_docs()` with `shutil.which("showboat")` returning `None` exits with error mentioning "showboat" and does NOT call `_start_e2e_server`.

Place tests in `tests/unit/test_make_docs.py`. Mock `shutil.which`, `_pre_test_db_cleanup`, `_start_e2e_server`, `_stop_e2e_server`, and `subprocess.run` to isolate the orchestration logic.

**Verification:**
Run: `uv run pytest tests/unit/test_make_docs.py -v`
Expected: All tests pass.

**Commit:** `feat: add make_docs() CLI with dependency checks and server lifecycle`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Start/stop Rodney in the orchestrator

**Files:**
- Modify: `src/promptgrimoire/cli.py` (within `make_docs()`)

**Implementation:**

After starting the E2E server and before invoking scripts, start Rodney with `--local` scope:
```bash
rodney start --local
```

In the finally block, after the script invocations but before `_stop_e2e_server()`, stop Rodney:
```bash
rodney stop --local
```

Use `subprocess.run(["rodney", "start", "--local"], check=True)` and `subprocess.run(["rodney", "stop", "--local"], check=False)` (don't fail on stop errors during cleanup).

**Testing:**

Update `tests/unit/test_make_docs.py`:
- Verify `rodney start --local` is called after server starts
- Verify `rodney stop --local` is called in finally block, even on script failure

**Verification:**
Run: `uv run pytest tests/unit/test_make_docs.py -v`
Expected: All tests pass.

**Commit:** `feat: add Rodney start/stop lifecycle to make_docs`
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->

<!-- START_TASK_4 -->
### Task 4: Create directory structure and gitignore entries

**Verifies:** user-docs-rodney-showboat-207.AC4.2, user-docs-rodney-showboat-207.AC4.3

**Files:**
- Create: `docs/guides/scripts/` directory
- Modify: `.gitignore` (add entries near line 42 where `tests/e2e/screenshots/` is)

**Step 1: Create directory**

```bash
mkdir -p docs/guides/scripts
```

**Step 2: Add gitignore entries**

Add to `.gitignore`:
```
# Documentation generation artefacts (uv run make-docs)
docs/guides/screenshots/
docs/guides/*.md
docs/guides/*.pdf
```

**Step 3: Verify**

Run: `git status`
Expected: `.gitignore` modified, `docs/guides/scripts/` won't show (empty dir).

**Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: add gitignore entries for docs/guides artefacts"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Create common.sh with auth and screenshot helpers

**Files:**
- Create: `docs/guides/scripts/common.sh`

**Implementation:**

`common.sh` is sourced by each guide script. It provides:

1. **`authenticate_as(email)`** — Navigate Rodney to the mock auth callback URL, wait for redirect.
   ```bash
   authenticate_as() {
     local email="$1"
     rodney open --local "$BASE_URL/auth/callback?token=mock-token-${email}"
     rodney waitload --local
     # Wait for redirect away from /auth/callback
     sleep 1
     rodney waitstable --local
   }
   ```

2. **`take_screenshot(name)`** — Capture a screenshot with consistent viewport (1280x800) and save to the correct subdirectory.
   ```bash
   take_screenshot() {
     local name="$1"
     rodney waitstable --local
     rodney screenshot --local -w 1280 -h 800 "$SCREENSHOT_DIR/${name}.png"
   }
   ```

3. **`note(text)`** — Wrapper around `showboat note` that passes the doc path.
   ```bash
   note() {
     showboat note "$DOC_PATH" "$1"
   }
   ```

4. **`add_image(name)`** — Add screenshot to showboat doc.
   ```bash
   add_image() {
     showboat image "$DOC_PATH" "$SCREENSHOT_DIR/${name}.png"
   }
   ```

5. **`step(name, text)`** — Combined note + screenshot + image for a standard step.
   ```bash
   step() {
     local name="$1"
     local text="$2"
     note "## $text"
     take_screenshot "$name"
     add_image "$name"
   }
   ```

6. **Setup/teardown**: Each script sources `common.sh` and sets `BASE_URL`, `DOC_PATH`, `SCREENSHOT_DIR` before calling any helpers. `common.sh` applies `set -euo pipefail`.

**Verification:**

Run: `bash -n docs/guides/scripts/common.sh`
Expected: Syntax check passes (no errors).

**Commit:** `feat: add common.sh with Rodney/Showboat helpers`
<!-- END_TASK_5 -->

<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_6 -->
### Task 6: Create stub instructor script for end-to-end verification

**Files:**
- Create: `docs/guides/scripts/generate-instructor-setup.sh`

**Implementation:**

A minimal stub that verifies the full pipeline works:

```bash
#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_URL="$1"
GUIDE_DIR="$(dirname "$SCRIPT_DIR")"
DOC_PATH="$GUIDE_DIR/instructor-setup.md"
SCREENSHOT_DIR="$GUIDE_DIR/screenshots/instructor"

source "$SCRIPT_DIR/common.sh"

mkdir -p "$SCREENSHOT_DIR"

showboat init "$DOC_PATH" "Instructor Setup Guide"
note "This guide walks through setting up a unit in PromptGrimoire."

authenticate_as "instructor@uni.edu"
step "01_navigator" "Step 1: The Navigator (Home Page)"

echo "✓ Instructor setup guide generated: $DOC_PATH"
```

This is a stub — Phase 2 will flesh it out with all 7 steps.

**Step 1: Create the file and make executable**

```bash
chmod +x docs/guides/scripts/generate-instructor-setup.sh
```

**Step 2: Create matching stub for student workflow**

Create `docs/guides/scripts/generate-student-workflow.sh` with the same structure but different doc name. Phase 3 will flesh it out.

```bash
#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_URL="$1"
GUIDE_DIR="$(dirname "$SCRIPT_DIR")"
DOC_PATH="$GUIDE_DIR/student-workflow.md"
SCREENSHOT_DIR="$GUIDE_DIR/screenshots/student"

source "$SCRIPT_DIR/common.sh"

mkdir -p "$SCREENSHOT_DIR"

showboat init "$DOC_PATH" "Student Workflow Guide"
note "This guide walks through using PromptGrimoire for annotation."

authenticate_as "student-demo@test.example.edu.au"
step "01_login" "Step 1: Logging In"

echo "✓ Student workflow guide generated: $DOC_PATH"
```

Make executable: `chmod +x docs/guides/scripts/generate-student-workflow.sh`

**Note:** The student stub authenticates as `student-demo@test.example.edu.au`, but this user won't be enrolled in any unit yet (enrollment happens in Phase 2's instructor script). The stub's navigator screenshot will show an empty page. This is expected — the stub only tests the pipeline, not the content.

**Step 3: Run `uv run make-docs` end-to-end**

This is the real verification — it exercises the full pipeline:
- Python starts server → starts Rodney → invokes instructor stub → invokes student stub → Pandoc → stops Rodney → stops server
- Produces `docs/guides/instructor-setup.pdf` and `docs/guides/student-workflow.pdf`

Run: `uv run make-docs`
Expected: Both PDFs produced with one screenshot each. Verify PDFs exist and are non-empty.

**Step 4: Verify gitignore**

Run: `git status`
Expected: Only `docs/guides/scripts/` files shown as untracked. No `.md`, `.pdf`, or `screenshots/` in status.

**Step 5: Commit**

```bash
git add docs/guides/scripts/generate-instructor-setup.sh docs/guides/scripts/generate-student-workflow.sh
git commit -m "feat: add stub guide scripts for end-to-end pipeline verification"
```
<!-- END_TASK_6 -->
