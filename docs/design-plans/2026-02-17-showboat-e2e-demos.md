# Showboat E2E Demo Documents Design

**GitHub Issue:** #156

## Summary

This design integrates Showboat (Simon Willison's CLI tool for documenting agent workflows) into the E2E test suite to produce stakeholder-readable demonstration documents. Each of the five persona tests (naughty student, translation student, history tutorial, law student, instructor workflow) will generate its own Markdown document that narrates what the test simulates, with screenshots at key moments. The test writes its own story as it runs by calling helper functions (`showboat_init()`, `showboat_note()`, `showboat_screenshot()`) at existing subtest checkpoints.

The integration is designed for graceful degradation: if Showboat isn't installed, the helpers become silent no-ops and tests run identically without producing demo output. After pytest completes, the `test-e2e` CLI automatically converts Showboat Markdown files to PDF via Pandoc and the existing TinyTeX installation. Conversion failures never affect test exit codes — demo output is a side effect, not a test assertion. This allows the E2E suite to double as both automated testing and stakeholder documentation generation without coupling the two concerns.

## Definition of Done

E2E persona tests produce Showboat Markdown documents during `uv run test-e2e` that serve as stakeholder-readable demonstrations of what each test simulates. Each narrative test (naughty student, translation student, history tutorial, law student, instructor workflow) generates its own document with narrative notes and screenshots at subtest checkpoints. Tests control their own Showboat narrative. Output is converted to PDF via Pandoc for distribution.

## Acceptance Criteria

### showboat-e2e-demos.AC1: Showboat helper module works with graceful degradation
- **showboat-e2e-demos.AC1.1 Success:** `showboat_init()` creates a valid Showboat Markdown document at `output/showboat/<slug>.md`
- **showboat-e2e-demos.AC1.2 Success:** `showboat_note()` appends narrative text to the document
- **showboat-e2e-demos.AC1.3 Success:** `showboat_screenshot()` captures a Playwright screenshot and appends it as a Showboat image
- **showboat-e2e-demos.AC1.4 Degradation:** All three helpers no-op silently when `showboat` binary is not on PATH
- **showboat-e2e-demos.AC1.5 Degradation:** Helpers accept `None` for the `doc` parameter without error

### showboat-e2e-demos.AC2: CLI lifecycle integration
- **showboat-e2e-demos.AC2.1 Success:** `uv run test-e2e` clears `output/showboat/` before running tests
- **showboat-e2e-demos.AC2.2 Success:** After tests complete, `.md` files in `output/showboat/` are converted to PDF via Pandoc
- **showboat-e2e-demos.AC2.3 Degradation:** PDF conversion skips silently if Pandoc or lualatex unavailable
- **showboat-e2e-demos.AC2.4 Isolation:** PDF conversion failure never changes the test exit code

### showboat-e2e-demos.AC3: Persona tests produce stakeholder-readable documents
- **showboat-e2e-demos.AC3.1 Success:** Each of the five persona tests produces its own Showboat document
- **showboat-e2e-demos.AC3.2 Success:** Documents contain narrative notes describing what the persona does
- **showboat-e2e-demos.AC3.3 Success:** Documents contain screenshots at key visual moments
- **showboat-e2e-demos.AC3.4 Quality:** Documents are readable standalone — a stakeholder unfamiliar with the codebase can follow the story

## Glossary

- **Showboat**: Simon Willison's CLI tool for documenting coding agent workflows. Creates Markdown files from commands like `init`, `note`, `image`, `exec`. Used here to generate narrative demo documents from E2E tests.
- **Persona tests**: The five narrative E2E tests that simulate end-user workflows: naughty student (security edge cases), translation student (multilingual annotation), history tutorial (collaborative sync), law student (legal annotation), instructor workflow (course setup).
- **Graceful degradation**: Design pattern where a feature becomes a silent no-op when its dependencies are unavailable. All Showboat helpers check `_SHOWBOAT_AVAILABLE` once at module load; if `showboat` binary is not on PATH, they do nothing instead of raising errors.
- **Subtest checkpoints**: Points within a test marked by `subtests.test(msg="...")` where narrative snapshots are taken. Existing persona tests already use these for logical test segmentation; Showboat integration adds narrative + screenshot calls at these same points.
- **TinyTeX**: Lightweight LaTeX distribution installed via `scripts/setup_latex.py`. Already used for PDF export in the annotation pipeline; reused here for converting Showboat Markdown to PDF via `pandoc --pdf-engine=lualatex`.
- **Playwright**: Browser automation library used by E2E tests. Provides `page.screenshot()` which Showboat helpers use to capture visual checkpoints.
- **Pandoc**: Universal document converter. Converts Showboat Markdown to PDF as a post-test CLI step.

## Architecture

Showboat (Simon Willison's CLI tool for coding agents) generates Markdown demo documents from CLI commands: `init`, `note`, `image`, `exec`, `pop`, `verify`. This design uses only `init`, `note`, and `image` — persona tests aren't reproducible shell commands, so `exec`/`verify` don't apply.

**Integration model:** Explicit helper functions in `tests/e2e/showboat_helpers.py` wrap the Showboat CLI. Each persona test calls these helpers at subtest checkpoints to build its own narrative document. The helpers shell out to the `showboat` binary via `subprocess.run()`.

**Graceful degradation:** If Showboat isn't installed, all helper functions become silent no-ops. A module-level `_SHOWBOAT_AVAILABLE` flag (checked once via `shutil.which("showboat")`) controls this. Tests run identically with or without Showboat — demo output is a side effect, never a test assertion.

**PDF conversion:** After pytest completes, the `test-e2e` CLI command converts Showboat Markdown files to PDF via `pandoc --pdf-engine=lualatex`. This reuses the existing TinyTeX installation. Conversion failure never affects the test exit code.

**Data flow:**

```
Persona test
  → showboat_init() → creates output/showboat/<slug>.md
  → showboat_note() → appends narrative text
  → showboat_screenshot() → page.screenshot() to temp file → showboat image → appends image
  → ... repeat at each checkpoint ...

test-e2e CLI (after pytest)
  → glob output/showboat/*.md
  → pandoc each .md → .pdf
```

**Output structure:**

```
output/showboat/
├── naughty-student.md
├── naughty-student/            # images (created by showboat image)
│   ├── naughty-student-001.png
│   └── ...
├── naughty-student.pdf         # generated post-test by pandoc
├── translation-student.md
├── translation-student/
│   └── ...
├── translation-student.pdf
└── ...
```

### Helper contracts

```python
def showboat_init(slug: str, title: str) -> Path | None:
    """Create a new Showboat document. Returns path or None if unavailable."""
    ...

def showboat_note(doc: Path | None, text: str) -> None:
    """Append narrative commentary. No-ops if doc is None."""
    ...

def showboat_screenshot(doc: Path | None, page: Page, caption: str) -> None:
    """Capture screenshot and append to document. No-ops if doc is None."""
    ...
```

The `Path | None` pattern means tests never need `if doc:` guards — all helpers accept `None` silently.

## Existing Patterns

**E2E test helpers:** The project already has `tests/e2e/annotation_helpers.py`, `tests/e2e/course_helpers.py`, and `tests/e2e/helpers.py` as thin helper modules for E2E tests. Showboat helpers follow the same pattern — a peer module in the same directory.

**Narrative persona tests:** The five persona tests (`test_naughty_student.py`, `test_translation_student.py`, `test_history_tutorial.py`, `test_law_student.py`, `test_instructor_workflow.py`) already use `subtests.test(msg="...")` checkpoints with descriptive labels. Showboat integration adds calls alongside these existing checkpoints — it does not replace or restructure them.

**External tool dependencies:** Pandoc and TinyTeX are both assumed on PATH without installation scripts managed by uv. Showboat follows the same model. The `latex` pytest marker demonstrates the pattern for optional system tools — tests that need them declare a marker; tests that benefit from them (like Showboat) degrade silently.

**Stale output cleanup:** `test_fixture_screenshots.py` clears stale screenshots per-fixture before regenerating. The `test-e2e` CLI will clear `output/showboat/` entirely at the start of each run — same principle, broader scope.

**CLI post-processing:** The `test-e2e` function in `cli.py` already has a `finally` block for server shutdown. PDF conversion slots into this block as a best-effort post-step.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Showboat dependency and helper module

**Goal:** Install Showboat and create the helper module with graceful degradation.

**Components:**
- `pyproject.toml` — add `showboat` to `[dependency-groups] dev`
- `tests/e2e/showboat_helpers.py` — new module with `showboat_init()`, `showboat_note()`, `showboat_screenshot()`, `_SHOWBOAT_AVAILABLE` flag

**Dependencies:** None

**Done when:** `uv sync` installs showboat, helpers produce a valid Showboat Markdown document when called manually, helpers no-op gracefully when `showboat` binary is absent. Tests verify both available and unavailable paths.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: CLI integration — stale cleanup and PDF conversion

**Goal:** Wire Showboat output into the `test-e2e` CLI lifecycle.

**Components:**
- `src/promptgrimoire/cli.py` — add `_clear_showboat_output()` (called before pytest), `_convert_showboat_to_pdf()` (called after pytest in finally block)
- `output/showboat/` directory convention (created by helpers, cleared by CLI)

**Dependencies:** Phase 1 (helpers exist)

**Done when:** `uv run test-e2e` clears stale output before running, converts any `.md` files to PDF after tests complete, degrades silently if Pandoc/lualatex unavailable. Tests verify cleanup and conversion behaviour.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Instrument persona tests with Showboat narratives

**Goal:** Add Showboat narrative calls to all five persona tests.

**Components:**
- `tests/e2e/test_naughty_student.py` — Showboat init + notes + screenshots at key checkpoints
- `tests/e2e/test_translation_student.py` — same
- `tests/e2e/test_history_tutorial.py` — same
- `tests/e2e/test_law_student.py` — same
- `tests/e2e/test_instructor_workflow.py` — same

**Dependencies:** Phase 1 (helpers available)

**Done when:** Running `uv run test-e2e` produces five Showboat Markdown documents in `output/showboat/`, each with narrative notes and screenshots that tell the persona's story. Documents are readable standalone by a stakeholder.
<!-- END_PHASE_3 -->

## Additional Considerations

**Image size:** Playwright's `page.screenshot()` produces full-viewport PNGs. For PDF rendering, Pandoc/LaTeX will scale these to page width. No explicit resize needed — LaTeX handles `\includegraphics` scaling automatically.

**Git ignore:** `output/showboat/` should be added to `.gitignore` — these are generated artefacts, not source. The `output/` directory likely already has a gitignore entry.
