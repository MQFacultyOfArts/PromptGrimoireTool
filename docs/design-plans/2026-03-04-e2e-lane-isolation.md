# E2E Lane Isolation Design

**GitHub Issue:** None

## Summary

The current test harness overloads the `e2e` marker to mean two different things: real browser Playwright tests in `tests/e2e/` and in-process NiceGUI `user_simulation` tests in `tests/integration/`. The `grimoire e2e run` command then executes `pytest -m e2e` in a single pytest process, which mixes those incompatible harnesses. The observed result is stable harness corruption rather than application regressions: NiceGUI files lose `/login` route registration (`http://test/login not found`) in the mixed lane, while the same files pass when retried in fresh subprocesses.

This design separates test selection, execution, and reporting into two explicit lanes:

1. **Playwright lane**: browser/server-backed tests from `tests/e2e/`
2. **NiceGUI lane**: in-process `nicegui_user` tests from `tests/integration/`

The isolation boundary is the **test file**, not the individual test function. Each file runs in a fresh pytest subprocess with a fresh database clone. Playwright files additionally get a dedicated NiceGUI server process. NiceGUI files do not start an external server; they rely on the existing `user_simulation(main_file=...)` fixture and need only a fresh interpreter and database. Both lanes write structured per-file artifacts so GitHub Actions can upload failure diagnostics directly. An umbrella command, `grimoire e2e all`, runs the Playwright lane, performs lane cleanup, then runs the NiceGUI lane as a second independent invocation.

## Definition of Done

1. NiceGUI user-simulation tests are no longer selected by `grimoire e2e run`.
2. A dedicated NiceGUI lane exists and runs only tests marked `nicegui_ui`, using one fresh pytest subprocess per test file and one fresh PostgreSQL database per file.
3. The Playwright lane runs only browser-backed files from `tests/e2e/`, preserving per-file database and server isolation when requested.
4. The CLI exposes explicit lane commands and a required umbrella command, `grimoire e2e all`, that runs Playwright cleanup and NiceGUI cleanup as two independent sub-runs.
5. `grimoire test all` excludes both Playwright `e2e` tests and NiceGUI `nicegui_ui` tests.
6. CI runs the Playwright and NiceGUI lanes as separate jobs or logically separate commands and uploads per-lane artifact bundles on failure.
7. Failure logs are preserved as structured artifacts, not only appended to a single `test-e2e.log`.

## Acceptance Criteria

### e2e-lane-isolation.AC1: Test taxonomy is explicit
- **e2e-lane-isolation.AC1.1 Success:** `pyproject.toml` defines a `nicegui_ui` pytest marker.
- **e2e-lane-isolation.AC1.2 Success:** NiceGUI user-simulation files under `tests/integration/` use `@pytest.mark.nicegui_ui` and no longer rely on `@pytest.mark.e2e` for selection.
- **e2e-lane-isolation.AC1.3 Success:** `grimoire e2e run` no longer discovers NiceGUI integration files via marker selection.
- **e2e-lane-isolation.AC1.4 Success:** `grimoire test all` excludes `nicegui_ui` tests as well as `e2e` tests, preventing NiceGUI user tests from re-entering the mixed async test lane.

### e2e-lane-isolation.AC2: NiceGUI tests run in their own isolated lane
- **e2e-lane-isolation.AC2.1 Success:** `uv run grimoire e2e nicegui` executes only `nicegui_ui` files.
- **e2e-lane-isolation.AC2.2 Success:** Each NiceGUI file runs in a fresh pytest subprocess with a fresh database clone.
- **e2e-lane-isolation.AC2.3 Restriction:** NiceGUI workers do not start an external server or require `E2E_BASE_URL`.
- **e2e-lane-isolation.AC2.4 Success:** The known mixed-lane `/login` 404 failure mode is not reproducible in the NiceGUI lane.

### e2e-lane-isolation.AC3: Playwright lane remains explicit and isolated
- **e2e-lane-isolation.AC3.1 Success:** `uv run grimoire e2e run` executes only `tests/e2e/` files.
- **e2e-lane-isolation.AC3.2 Success:** Playwright files can run with file-level isolation using a bounded worker pool (`--workers N` or equivalent), with one database clone and one server per file.
- **e2e-lane-isolation.AC3.3 Edge:** A `-k` filter that matches no tests in a file yields pytest exit code 5 and is treated as a non-failure for aggregation.
- **e2e-lane-isolation.AC3.4 Success:** `uv run grimoire e2e all` runs the Playwright lane first, performs cleanup, then runs the NiceGUI lane as a second independent sub-run, and returns a non-zero exit code if either lane fails.

### e2e-lane-isolation.AC4: Artifacts are preserved per file
- **e2e-lane-isolation.AC4.1 Success:** Each worker writes a dedicated artifact directory containing stdout/stderr logs, JUnit XML, and worker metadata.
- **e2e-lane-isolation.AC4.2 Success:** Playwright workers additionally preserve server logs and any screenshots/traces/videos produced by pytest-playwright.
- **e2e-lane-isolation.AC4.3 Success:** Retry output is preserved in the same structured artifact tree, not only in `test-e2e.log`.
- **e2e-lane-isolation.AC4.4 Success:** CI uploads artifact directories for failed Playwright and NiceGUI runs.

### e2e-lane-isolation.AC5: CI reflects the lane split
- **e2e-lane-isolation.AC5.1 Success:** `.github/workflows/ci.yml` runs Playwright and NiceGUI in separate jobs or separate top-level steps with independent result reporting.
- **e2e-lane-isolation.AC5.2 Success:** The NiceGUI CI job does not install Playwright browsers.
- **e2e-lane-isolation.AC5.3 Success:** The Playwright CI job does not select `nicegui_ui` tests.
- **e2e-lane-isolation.AC5.4 Success:** Artifact upload occurs even when the test job fails.

## Glossary

- **lane**: One logically coherent test suite with a dedicated selection rule, runtime model, and artifact bundle.
- **Playwright lane**: Browser-backed tests in `tests/e2e/` that need a live NiceGUI server and `E2E_BASE_URL`.
- **NiceGUI lane**: In-process UI tests using `nicegui.testing.user_simulation`, running from `tests/integration/`.
- **file-level isolation**: Fresh pytest process and fresh database per test file; for Playwright, also a fresh server per file.
- **worker pool**: A bounded set of concurrently running file workers managed by the CLI, replacing raw pytest-xdist for these suites.
- **artifact bundle**: The directory of logs, metadata, XML, and optional screenshots/traces preserved for one lane or one file.
- **retry classification**: Re-running failed files or node IDs in fresh isolation to distinguish harness interaction from genuine failures.

## Architecture

The design introduces a clean separation between **selection**, **execution**, and **reporting**.

### 1. Selection Model

Selection stops being marker-only.

- **Playwright lane**
  - Source of truth: `tests/e2e/test_*.py`
  - Marker: existing `e2e` marker may remain on browser tests, but path selection becomes authoritative
- **NiceGUI lane**
  - Source of truth: `tests/integration/test_*.py` filtered by `@pytest.mark.nicegui_ui`
  - These tests are explicitly excluded from Playwright runs

This removes the current ambiguity where `pytest -m e2e` selects tests from both directories.

### 2. Execution Model

Each lane is executed by the same high-level orchestrator contract:

- discover files for the lane
- build a fresh database clone per file
- run one pytest subprocess per file
- preserve per-file artifacts
- aggregate exit codes and summaries

The lane contract is explicit:

```python
@dataclass(frozen=True)
class LaneSpec:
    name: str
    test_paths: tuple[str, ...]
    marker_expr: str | None
    needs_server: bool
    artifact_subdir: str


@dataclass(frozen=True)
class WorkerResult:
    file: Path
    exit_code: int
    duration_s: float
    artifact_dir: Path
```

The orchestrator owns file discovery, DB lifecycle, cleanup ordering, result aggregation, and umbrella-command sequencing. Lane-specific workers own only “run this file under this runtime model”.

The worker implementation differs by lane:

#### Playwright worker
- Clones branch test DB into a worker DB
- Allocates a unique port
- Starts the existing server subprocess (`_SERVER_SCRIPT_PATH`)
- Runs `pytest <file>` with `E2E_BASE_URL` and `DATABASE__URL`
- Captures pytest log, server log, JUnit XML, and browser artifacts

#### NiceGUI worker
- Clones branch test DB into a worker DB
- Does **not** allocate a port
- Does **not** start an external server
- Runs `pytest <file>` with `DATABASE__URL`
- Lets the existing `nicegui_user` fixture create the in-process app via `user_simulation(main_file=...)`
- Captures pytest log and JUnit XML

This directly matches the local evidence: isolated subprocesses are sufficient for NiceGUI stability, while shared-process mixed execution is not.

Per-file DB cloning for NiceGUI is a conservative choice. A shared DB with pre-run cleanup might eventually prove sufficient, but the design intentionally keeps the DB boundary aligned with the already-working Playwright model so the first implementation optimises for stability over minimalism.

### 3. Worker Pool, Not xdist

Concurrency happens at the file boundary through a bounded orchestrator-managed worker pool.

- No pytest-xdist for NiceGUI files
- No mixed-lane `pytest -m e2e`
- One file is the largest shared state domain

This reuses the same successful idea already present in the parallel Playwright runner: isolated databases and subprocesses. The difference is that the design generalises that model to multiple lane types and caps concurrency intentionally instead of blindly starting every file at once.

### 4. CLI Shape

The CLI exposes lane-specific entrypoints rather than one overloaded command:

- `uv run grimoire e2e run`
  - Playwright lane only
- `uv run grimoire e2e nicegui`
  - NiceGUI lane only
- `uv run grimoire e2e all`
  - Required umbrella command that invokes Playwright first, waits for cleanup to complete, then invokes NiceGUI second, and aggregates exit status

Supporting commands align with those semantics:

- `grimoire e2e noretry`
  - Playwright-only debug command, unchanged initially
- `grimoire e2e changed`
  - Initially remains Playwright-only unless explicit NiceGUI support is added in a later phase

This avoids a silent semantic break where `run` would continue to sound like “everything” while only meaning one lane. CI should call `grimoire e2e all`, while humans can use the lane-specific commands for debugging.

### 5. Artifact Model

A lane writes into a stable artifact root, for example:

`output/test_output/e2e/<lane>/<run-id>/`

Recommended structure:

- `summary.json`
- `combined.xml`
- `<file-stem>/worker.json`
- `<file-stem>/pytest.log`
- `<file-stem>/junit.xml`
- `<file-stem>/server.log` for Playwright only
- `<file-stem>/playwright/` for screenshots, traces, videos when present
- `<file-stem>/retry/` for isolated retry logs and metadata

This replaces the current debugging blind spot where `_retry.py` appends opaque output to `test-e2e.log`, which CI does not surface well.

### 6. CI Integration

CI should stop treating these suites as one job.

Recommended job split:

- `e2e-playwright`
  - installs Playwright browsers
  - runs `uv run grimoire e2e run ...`
  - uploads Playwright artifacts
- `nicegui-ui`
  - does not install browsers
  - runs `uv run grimoire e2e nicegui ...`
  - uploads NiceGUI artifacts

Jobs can run in parallel because they no longer share selection or artifacts. If CI prefers one top-level command for local parity, `grimoire e2e all` should still model the same two-lane sequencing and cleanup order.

## Existing Patterns

Investigation found four existing patterns worth preserving.

1. **Single-server serial runner**
   - `src/promptgrimoire/cli/e2e/__init__.py`
   - `_run_serial_e2e()` currently runs `pytest -m e2e` against one server and one DB
   - This is the source of the mixed-lane problem and should remain only for Playwright-only serial/debug flows

2. **File-level Playwright isolation**
   - `src/promptgrimoire/cli/e2e/_parallel.py`
   - `src/promptgrimoire/cli/e2e/_workers.py`
   - Already clones one database per file and starts one server per file
   - This is the correct architectural base for file-level isolation

3. **Retry in fresh subprocesses**
   - `src/promptgrimoire/cli/e2e/_retry.py`
   - Already proves that fresh subprocesses can separate flaky interaction from genuine failure
   - The problem is not the isolation idea; it is late application and weak artifact surfacing

4. **NiceGUI user harness**
   - `tests/integration/conftest.py`
   - `nicegui_user` uses `user_simulation(main_file=...)` and `_authenticate()` writes directly into `app.storage.user`
   - These tests are in-process integration tests, not browser/server E2E

The design follows patterns 2-4 and narrows pattern 1 so it no longer mixes incompatible suites.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Make Test Taxonomy Explicit
**Goal:** Separate Playwright and NiceGUI selection rules so the CLI can stop using one overloaded marker.

**Components:**
- `pyproject.toml` — add `nicegui_ui` marker and update marker descriptions
- `src/promptgrimoire/cli/testing.py` or the current `test all` entrypoint — exclude `nicegui_ui` alongside `e2e`
- `tests/integration/conftest.py` — update fixture docstrings/comments so `nicegui_user` no longer instructs authors to mark those tests as `e2e`
- `tests/integration/test_instructor_course_admin_ui.py` — replace `pytest.mark.e2e` with `pytest.mark.nicegui_ui`
- `tests/integration/test_instructor_template_ui.py` — replace `pytest.mark.e2e` with `pytest.mark.nicegui_ui`
- `tests/integration/test_crud_management_ui.py` — replace `pytest.mark.e2e` with `pytest.mark.nicegui_ui`

**Dependencies:** None

**Done when:** `pytest tests/e2e -m e2e` selects only browser files, `pytest tests/integration -m nicegui_ui` selects only NiceGUI user-simulation files, and `grimoire test all` excludes both markers.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Introduce a Generic File-Worker Orchestrator
**Goal:** Generalise the existing Playwright file-runner so it can execute both lane types with the same result model.

**Components:**
- `src/promptgrimoire/cli/e2e/_parallel.py` — own lane orchestration, bounded worker-pool execution, and `e2e all` sequencing
- `src/promptgrimoire/cli/e2e/_workers.py` — expose separate `run_playwright_file(...)` and `run_nicegui_file(...)` worker implementations that return a shared `WorkerResult`
- `src/promptgrimoire/cli/e2e/_workers.py` or a new lane module — define the `LaneSpec` contract used by orchestration
- `src/promptgrimoire/db/bootstrap.py` — continue using `clone_database()` / `drop_database()` for per-file DB lifecycle
- Optional new modules such as `src/promptgrimoire/cli/e2e/_artifacts.py` or `src/promptgrimoire/cli/e2e/_lanes.py` if that keeps contracts clean

**Dependencies:** Phase 1

**Done when:** One orchestrator can run a bounded set of isolated file workers, aggregate shared `WorkerResult` values, and sequence full-lane runs for `e2e all` without mixing runtime models.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Add a Dedicated NiceGUI Lane
**Goal:** Create a first-class CLI command for NiceGUI UI tests using file-level subprocess isolation and no external server.

**Components:**
- `src/promptgrimoire/cli/e2e/__init__.py` — add `nicegui` command and wire it to lane-aware orchestration
- `src/promptgrimoire/cli/e2e/_retry.py` — support file-level retry metadata and structured artifact output for NiceGUI failures
- `tests/integration/` NiceGUI files — verified under isolated-file execution

**Dependencies:** Phase 2

**Done when:** `uv run grimoire e2e nicegui` runs only NiceGUI files, each in a fresh subprocess with a fresh DB, and preserves per-file artifacts on failure.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Narrow the Playwright Command Surface
**Goal:** Make `grimoire e2e run` mean Playwright-only, add required `grimoire e2e all`, and preserve existing browser debugging workflows.

**Components:**
- `src/promptgrimoire/cli/e2e/__init__.py` — change `run`, `noretry`, and `changed` selection from marker-only to explicit Playwright selection
- `src/promptgrimoire/cli/e2e/__init__.py` — add `all` command that calls the Playwright lane, performs cleanup, then calls the NiceGUI lane as a second independent sub-run
- `src/promptgrimoire/cli/e2e/_workers.py` — ensure Playwright workers continue to capture server logs and browser artifacts
- Documentation in `docs/testing.md` or equivalent — explain the new command split

**Dependencies:** Phase 3

**Done when:** `uv run grimoire e2e run` no longer touches NiceGUI tests, `uv run grimoire e2e all` runs both lanes sequentially with cleanup between them, and existing Playwright-only debugging still works.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Upload Lane Artifacts in CI and Finalise Operator Workflow
**Goal:** Surface failure evidence in GitHub Actions and make the new two-lane workflow the documented default.

**Components:**
- `.github/workflows/ci.yml` — split the current `e2e` job into `e2e-playwright` and `nicegui-ui`, or equivalent separate steps with separate artifact names
- Artifact upload steps in `.github/workflows/ci.yml` — always upload `output/test_output/e2e/...` (or chosen stable root), especially on failure
- `src/promptgrimoire/cli/e2e/_retry.py` and result-writing code — ensure retry logs land under the artifact root
- `docs/testing.md` — document when to use `grimoire e2e run`, `grimoire e2e nicegui`, and `grimoire e2e all`
- `docs/design-plans/2026-03-03-ci-harness.md` cross-reference or follow-up implementation docs — note the two-lane CI model

**Dependencies:** Phase 4

**Done when:** A failing CI run exposes per-file logs and retry traces as downloadable artifacts for the affected lane, and the documented default workflow uses `grimoire e2e all` for full-suite execution.
<!-- END_PHASE_5 -->

## Additional Considerations

**Why not batch all NiceGUI files in one pytest subprocess?**
That experiment already failed with `/login` 404s despite being logically separate from Playwright. The design therefore treats the fresh pytest interpreter as part of the isolation contract for NiceGUI files, not an optional implementation detail.

**Why not per-test-function isolation?**
Per-test server and DB churn would be slower, more complex, and not supported by the evidence. The failures observed are suite/session contamination problems. File-level isolation is the smallest boundary that has already proven effective in retries.

**Why not raw pytest-xdist?**
The current failures are specifically about event-loop and harness interaction. Reintroducing xdist at the test-function level recreates that failure surface. A bounded worker pool at the file boundary gives parallelism without surrendering control of the runtime model.

**Changed-tests support can lag behind the lane split.**
If `grimoire e2e changed` remains Playwright-only for an initial implementation, that is acceptable as long as the command contract is explicit. NiceGUI changed-test selection can be added after the split is stable.

**Artifact retention should be lane-aware and reversible.**
The artifact root should be stable and gitignored. Local successful runs may still clean up artifacts, but CI failures must preserve them. The design deliberately keeps this additive so the current harness can be compared against the new lane model during rollout.
