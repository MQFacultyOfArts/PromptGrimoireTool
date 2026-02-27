# Automated User Documentation Generation Design

**GitHub Issue:** #207

## Summary

PromptGrimoire currently has no end-user documentation. This design builds a pipeline that generates two user-facing PDF guides — one for instructors setting up a unit, and one for students working through the annotation workflow — by driving the live application with a browser automation tool, capturing screenshots at each step, and assembling them into readable documents. The guides are produced from scripts rather than written by hand, so they can be regenerated whenever the UI changes.

The pipeline runs as a single command (`uv run make-docs`). A Python orchestrator starts the application with mock authentication and a clean database, invokes two shell scripts that drive the browser and assemble narrative markdown, then converts both markdown files to PDF via Pandoc. The scripts use Rodney for browser interaction (navigate, click, type, screenshot) and Showboat for document assembly (writing text notes and embedding images into a structured markdown file). All generated files — screenshots, markdown, PDFs — are gitignored; only the scripts themselves are committed.

## Definition of Done

`uv run make-docs` generates two user-facing PDFs from a clean database: an instructor setup guide (create unit, week, activity, tags) and a student workflow guide (login, paste conversation, annotate, export). Documentation scripts use Rodney for browser automation and Showboat for markdown assembly. All generated artefacts are gitignored; only the scripts and orchestrator are committed. The pipeline is re-runnable when the UI changes.

## Acceptance Criteria

### user-docs-rodney-showboat-207.AC1: CLI entry point works end-to-end
- **user-docs-rodney-showboat-207.AC1.1 Success:** `uv run make-docs` starts app server with mock auth on a free port
- **user-docs-rodney-showboat-207.AC1.2 Success:** Server is stopped after scripts complete (even on failure)
- **user-docs-rodney-showboat-207.AC1.3 Success:** Both PDFs are produced in `docs/guides/`
- **user-docs-rodney-showboat-207.AC1.4 Failure:** If Rodney is not installed, command exits with clear error message
- **user-docs-rodney-showboat-207.AC1.5 Failure:** If Showboat is not installed, command exits with clear error message
- **user-docs-rodney-showboat-207.AC1.6 Failure:** If a script fails mid-way, error output identifies the failing step

### user-docs-rodney-showboat-207.AC2: Instructor guide is complete and accurate
- **user-docs-rodney-showboat-207.AC2.1 Success:** Guide starts from empty database and creates unit, week, activity through the UI
- **user-docs-rodney-showboat-207.AC2.2 Success:** Activity tag configuration (groups + tags) is documented with screenshots
- **user-docs-rodney-showboat-207.AC2.3 Success:** Guide includes enrollment instruction (provide list to admin)
- **user-docs-rodney-showboat-207.AC2.4 Success:** Guide verifies student view by re-authenticating as a student
- **user-docs-rodney-showboat-207.AC2.5 Quality:** PDF is readable standalone by an instructor unfamiliar with the tool

### user-docs-rodney-showboat-207.AC3: Student guide is complete and accurate
- **user-docs-rodney-showboat-207.AC3.1 Success:** Guide covers login, navigate, create workspace from activity, paste, annotate, comment, organise, respond, export
- **user-docs-rodney-showboat-207.AC3.2 Success:** Workspace inherits tags from instructor's activity configuration
- **user-docs-rodney-showboat-207.AC3.3 Success:** Each step has a corresponding screenshot
- **user-docs-rodney-showboat-207.AC3.4 Quality:** PDF is usable as a class handout — minimal jargon, task-oriented

### user-docs-rodney-showboat-207.AC4: Pipeline is re-runnable
- **user-docs-rodney-showboat-207.AC4.1 Success:** Running `uv run make-docs` twice produces valid PDFs containing expected sections and screenshots (content equivalence, not byte identity)
- **user-docs-rodney-showboat-207.AC4.2 Success:** All generated artefacts (screenshots, .md, .pdf) are gitignored
- **user-docs-rodney-showboat-207.AC4.3 Success:** Only `docs/guides/scripts/` is committed to git

## Glossary

- **Rodney**: A CLI browser automation tool (external Go binary, not managed by uv). Used in the shell scripts to navigate pages, interact with UI elements, and capture screenshots.
- **Showboat**: Simon Willison's CLI tool for documenting agent workflows. Accepts commands (`init`, `note`, `image`) to build a structured Markdown document incrementally.
- **Pandoc**: Universal document converter. Converts the Showboat-generated Markdown files to PDF using the LuaLaTeX engine.
- **TinyTeX**: Lightweight LaTeX distribution installed separately from uv. Required for `pandoc --pdf-engine=lualatex`. Already in use for the annotation export pipeline.
- **Mock auth**: A development-only authentication bypass. Navigating to `/auth/callback?token=mock-token-{email}` logs in as the named user without Stytch. Enabled via `DEV__AUTH_MOCK=true`.
- **NiceGUI**: The Python web UI framework used by PromptGrimoire. Renders UI server-side and pushes DOM updates to the browser via WebSocket — a complication for browser automation as elements may not be immediately present after an action.
- **Workspace**: PromptGrimoire's term for a student's working copy of a document for annotation. Created from an activity and inherits the activity's tag configuration.
- **Activity**: The instructor-created entry point for a student task. Configures tag groups, tags, and settings that workspaces inherit.
- **Tag / TagGroup**: The annotation taxonomy. Instructors configure groups (categories) and tags (labels within a category) on an activity; students apply these tags to highlights in their workspace.
- **Graceful degradation**: Referenced in the related #174 design. This design takes the stricter approach of failing fast with a clear error if Rodney or Showboat is missing.

## Architecture

Single entry point: `uv run make-docs` — a Python CLI command that orchestrates the full pipeline.

**Three-layer system:**

1. **Python orchestrator** (`make_docs()` in `cli.py`) — runs Alembic migrations, truncates all tables (same pattern as `test-e2e`), starts the app server with mock auth, invokes the shell scripts sequentially, runs Pandoc, stops the server. The truncation before each run ensures idempotent re-runs — the instructor script always starts from an empty database.

2. **Shell scripts** (`docs/guides/scripts/`) — each script uses Rodney for browser interaction and Showboat for document assembly. Scripts receive `$BASE_URL` as an argument. One script per PDF.

3. **Pandoc** — converts Showboat markdown (with embedded screenshot references) to PDF via `lualatex`.

**Data flow:**

```
uv run make-docs
  → Python: Alembic migrate, truncate, start NiceGUI server (DEV__AUTH_MOCK=true)
  → Python: invoke generate-instructor-setup.sh $BASE_URL
      → Rodney: authenticate, navigate, interact, screenshot
      → Showboat: init, note, image → instructor-setup.md
  → Python: invoke generate-student-workflow.sh $BASE_URL
      → Rodney: authenticate, navigate, interact, screenshot
      → Showboat: init, note, image → student-workflow.md
  → Python: pandoc instructor-setup.md → instructor-setup.pdf
  → Python: pandoc student-workflow.md → student-workflow.pdf
  → Python: stop server, report output paths
```

**Authentication:** Mock auth via URL navigation — `rodney navigate "$BASE_URL/auth/callback?token=mock-token-instructor@uni.edu"`. Same pattern as E2E tests.

**Viewport:** Consistent 1280x800 for all screenshots — wide enough for the annotation interface, standard for PDF embedding.

**Output structure:**

```
docs/guides/
├── scripts/
│   ├── common.sh                       # Server auth, screenshot wrapper, cleanup trap
│   ├── generate-instructor-setup.sh    # Instructor guide: 7 steps
│   └── generate-student-workflow.sh    # Student guide: 9 steps
├── screenshots/                        # Generated by Rodney (gitignored)
│   ├── instructor/
│   └── student/
├── instructor-setup.md                 # Generated by Showboat (gitignored)
├── student-workflow.md                 # Generated by Showboat (gitignored)
├── instructor-setup.pdf                # Generated by Pandoc (gitignored)
└── student-workflow.pdf                # Generated by Pandoc (gitignored)
```

Only `scripts/` is committed. Everything else is a build artefact.

## Existing Patterns

**CLI commands:** The project defines CLI entry points in `pyproject.toml` under `[project.scripts]` (e.g. `test-e2e`, `seed-data`, `manage-users`). `make-docs` follows this pattern — a new entry in `pyproject.toml` pointing to a function in `cli.py`.

**Server lifecycle:** `test-e2e` in `cli.py` already implements the full pattern: Alembic migrate, truncate tables, start NiceGUI subprocess on a free port with mock auth, wait for port readiness, run work, stop server. `make-docs` reuses this pattern, potentially extracting shared helpers.

**Mock auth:** E2E tests authenticate by navigating to `/auth/callback?token=mock-token-{email}`. Rodney does the same via `rodney navigate`.

**Showboat design plan:** #174 (`2026-02-17-showboat-e2e-demos.md`) designed Showboat integration for E2E persona tests. That plan adds Showboat helpers inside pytest; this design uses Showboat from standalone shell scripts. Both use the same Showboat CLI commands (`init`, `note`, `image`). If #174 is implemented first, the graceful-degradation pattern and `showboat` dev dependency would already exist.

**No existing user documentation:** Investigation found no end-user guides. This is the first user-facing documentation for the tool.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Dependencies and CLI skeleton

**Goal:** Install Rodney and Showboat, create the `make-docs` CLI entry point, and extract server lifecycle helpers from `test-e2e`.

**Components:**
- `pyproject.toml` — add `showboat` to dev dependencies, document Rodney as external Go dependency in README
- `src/promptgrimoire/cli.py` — new `make_docs()` function: start server, invoke scripts, invoke Pandoc, stop server. Extract shared server lifecycle helpers from `_run_e2e_tests_serial()` so both `test-e2e` and `make-docs` use the same startup/shutdown logic.
- `docs/guides/scripts/common.sh` — shared bash helpers: auth via Rodney, screenshot wrapper with consistent naming, server readiness wait, cleanup trap
- `.gitignore` — add `docs/guides/screenshots/`, `docs/guides/*.md`, `docs/guides/*.pdf`

**Dependencies:** None

**Done when:** `uv run make-docs` starts the server, invokes a stub script that takes one screenshot of the login page, produces a one-page PDF, and stops the server. Rodney and Showboat are callable from the shell scripts.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Instructor setup guide script

**Goal:** Complete the instructor guide — 7 steps from login to verifying the student view.

**Components:**
- `docs/guides/scripts/generate-instructor-setup.sh` — Rodney commands for each step:
  1. Login as instructor, screenshot navigator
  2. Create unit (TRAN8034), set policies, screenshot
  3. Create week (Week 3), publish, screenshot
  4. Create activity (Source Text Analysis with AI), configure settings, screenshot
  5. Configure activity tags (tag groups + tags for translation analysis), screenshot
  6. Note: "Provide student email list to admin for enrollment"
  7. Re-authenticate as student, verify activity visible, screenshot

**Dependencies:** Phase 1 (CLI, common.sh, Rodney, Showboat working)

**Done when:** `uv run make-docs` produces `docs/guides/instructor-setup.pdf` with 6+ screenshots and explanatory text walking through the full instructor setup workflow. The guide is readable by someone unfamiliar with the tool.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Student workflow guide script

**Goal:** Complete the student guide — 9 steps from login to export.

**Components:**
- `docs/guides/scripts/generate-student-workflow.sh` — Rodney commands for each step:
  1. Login (screenshot login page)
  2. Navigate to activity in navigator
  3. Create workspace from activity (inherits tags + template annotations)
  4. Paste AI conversation (simulate clipboard paste of HTML)
  5. Annotate tab — create highlight, assign to tag
  6. Annotate tab — add comment to highlight
  7. Organise tab — view by tag, drag to reclassify
  8. Respond tab — write in markdown editor with reference panel
  9. Export — generate PDF

**Dependencies:** Phase 2 (instructor script creates the unit/week/activity/tags the student script uses — scripts run sequentially)

**Done when:** `uv run make-docs` produces `docs/guides/student-workflow.pdf` with 8+ screenshots and explanatory text walking through the full student annotation workflow. The guide is usable as a class handout.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Robustness and NiceGUI interaction patterns

**Goal:** Harden Rodney/NiceGUI interaction — handle WebSocket-driven DOM updates, ensure reliable element waiting, and add error reporting.

**Components:**
- `docs/guides/scripts/common.sh` — add `wait_for_element()` helper using `rodney wait` or `rodney js` polling for NiceGUI DOM readiness. Add `rodney_click()` and `rodney_type()` wrappers that wait for element visibility before acting.
- Both guide scripts — replace raw Rodney calls with robust wrappers where NiceGUI async rendering requires waiting
- `src/promptgrimoire/cli.py` — add error reporting: if a script fails, print which step failed and the last screenshot taken

**Dependencies:** Phases 2 and 3 (scripts exist and work on happy path)

**Done when:** `uv run make-docs` succeeds reliably on repeated runs. Scripts handle NiceGUI's async DOM updates without race conditions. Failures produce actionable error output.
<!-- END_PHASE_4 -->

## Additional Considerations

**Rodney + NiceGUI is the primary risk.** NiceGUI updates the DOM via WebSocket pushes after server-side Python executes. Rodney commands that interact with elements may fire before the DOM has updated. Phase 4 exists specifically to address this — but it may surface earlier during Phase 2/3 implementation.

**Paste simulation.** Pasting HTML content into the annotation workspace (Phase 3, step 4) requires triggering the browser's paste event with HTML payload. This must be solved programmatically — `rodney js` to dispatch a ClipboardEvent with the HTML payload is the primary approach. If Rodney's JS execution cannot construct a realistic paste event, an alternative is to use `rodney js` to call the application's paste handler directly (bypassing the clipboard API). Manual screenshot placeholders are not acceptable — they break re-runnability.

**Relationship to #174.** If #174 (Showboat E2E demos) is implemented first, the `showboat` dev dependency and any shared patterns would already exist. The two designs are independent — #174 instruments pytest tests, this creates standalone scripts — but they share the Showboat tool dependency.

**Implementation scoping.** This design has 4 phases. If Rodney/NiceGUI interaction proves more complex than expected, Phase 4 could expand. The 8-phase limit is not at risk.
