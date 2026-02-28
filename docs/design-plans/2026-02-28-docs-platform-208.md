# Documentation Platform Design

**GitHub Issue:** #208

## Summary

PromptGrimoire currently generates user-facing guides through a pipeline built on two external CLI tools — rodney and showboat — driven by bash scripts. This design replaces that pipeline with a fully Python-native system. A new Guide DSL, built around Python context managers, lets authors write guide scripts that navigate the live application through a Playwright-controlled browser, capture annotated screenshots, and emit structured markdown — all in a single Python function. Screenshots are enhanced automatically: a CSS highlight is injected before capture to draw attention to relevant UI elements, then removed; Pillow trims empty margins from the result.

The entry point `uv run make-docs` orchestrates the entire pipeline: it starts the NiceGUI server with mock authentication, runs the instructor and student guide scripts in order (instructor first, because the student guide depends on data the instructor creates), builds an HTML documentation site with MkDocs Material, and produces PDFs via Pandoc. Because the guides drive the real application through a real browser, a guide that fails to run signals a broken feature — making guide generation an integration test by design. The system is structured so that writing a new guide requires only a Python function and an entry in the nav configuration.

## Definition of Done

`uv run make-docs` generates user-facing guide documentation using a Python DSL backed by Playwright for browser automation and MkDocs Material for site rendering. Guide scripts are Python files that use the DSL to navigate the app, interact with UI, capture annotated screenshots (with element highlighting and whitespace trimming), and emit narrative markdown. The generated markdown is built into an HTML site deployable to GitHub Pages and exportable as PDF. Running the guides serves as an integration test — if the app breaks, guide generation fails. The system replaces the current bash/rodney/showboat pipeline and is designed for easy authoring of new guides as features are added. MkDocs configuration is structured for future migration to Zensical.

## Acceptance Criteria

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

### docs-platform-208.AC4: make_docs() orchestrates the full pipeline
- **docs-platform-208.AC4.1 Success:** `uv run make-docs` starts the NiceGUI server with mock auth, launches Playwright, runs guides, and stops both on completion
- **docs-platform-208.AC4.2 Success:** Instructor guide runs before student guide (student depends on data created by instructor)
- **docs-platform-208.AC4.3 Success:** Pipeline produces both markdown files and all screenshots in the expected output directories
- **docs-platform-208.AC4.4 Failure:** If a guide function raises an exception, `make_docs()` exits non-zero (integration test property)
- **docs-platform-208.AC4.5 Failure:** If pandoc is not on PATH, `make_docs()` exits with a clear error message before starting the server

### docs-platform-208.AC5: Guide scripts produce correct output
- **docs-platform-208.AC5.1 Success:** Instructor setup guide produces markdown with ~7 screenshots covering: login, create unit, create week, create activity, configure tags, enrol note, student view
- **docs-platform-208.AC5.2 Success:** Student workflow guide produces markdown with ~10 screenshots covering: login, navigate, create workspace, paste content, highlight text, add comment, organise tab, respond tab, export PDF
- **docs-platform-208.AC5.3 Success:** All screenshots show element highlights where the guide directs attention and are trimmed of excess whitespace

### docs-platform-208.AC6: MkDocs Material renders HTML site
- **docs-platform-208.AC6.1 Success:** `mkdocs build` produces an HTML site in `docs/guides/site/` with landing page, both guides, and embedded screenshots
- **docs-platform-208.AC6.2 Success:** Navigation between landing page and individual guides works
- **docs-platform-208.AC6.3 Success:** `mkdocs serve` starts a local preview server for development

### docs-platform-208.AC7: PDF export via Pandoc
- **docs-platform-208.AC7.1 Success:** Pandoc produces a PDF for each guide with embedded screenshots
- **docs-platform-208.AC7.2 Failure:** Missing `--resource-path` causes image resolution failure (design requires it)

### docs-platform-208.AC8: Old pipeline fully replaced
- **docs-platform-208.AC8.1 Success:** No references to `rodney` or `showboat` remain in production code or `pyproject.toml`
- **docs-platform-208.AC8.2 Success:** All bash guide scripts (`generate-instructor-setup.sh`, `generate-student-workflow.sh`, `common.sh`, `debug-instructor.sh`) are deleted
- **docs-platform-208.AC8.3 Success:** `CLAUDE.md` documents the new `make-docs` pipeline accurately

### docs-platform-208.AC9: Zensical migration compatibility
- **docs-platform-208.AC9.1 Success:** `mkdocs.yml` uses standard MkDocs Material configuration with no plugins that would prevent Zensical migration

## Glossary

- **Guide DSL**: A Python domain-specific language built on context managers (`Guide`, `Step`) that drives browser automation, builds a markdown buffer, and captures screenshots.
- **Context manager**: A Python construct (`with` statement) that runs setup code on entry and teardown code on exit, used here to open/close guides and steps automatically.
- **Playwright**: A browser automation library used to control a real browser, click UI elements, fill forms, and take screenshots — the same tool used for E2E tests.
- **MkDocs Material**: A documentation site generator that takes markdown files and produces a styled HTML site. "Material" is the theme and the most commonly used MkDocs distribution.
- **Zensical**: A documentation platform that MkDocs Material sites can migrate to. The `mkdocs.yml` configuration is kept compatible to make future migration straightforward.
- **Pandoc**: A command-line document converter used to turn guide markdown into PDFs with embedded screenshots.
- **Pillow**: A Python image processing library (`PIL`) used to detect and crop empty margins from screenshots (`ImageChops.difference()` + `Image.crop()`).
- **CSS injection**: Temporarily inserting a `<style>` element into the live browser page to apply a visible outline to a UI element before a screenshot, then removing it.
- **data-testid**: An HTML attribute convention used throughout the project to give UI elements stable, test-friendly identifiers. CSS injection and guide scripts both locate elements by these selectors.
- **Mock authentication**: A development-only auth bypass (`DEV__AUTH_MOCK=true`) that accepts a specially-formatted URL token instead of a real Stytch session.
- **Rodney / Showboat**: The two external CLI tools being replaced. Binary dependencies invoked by the old bash guide scripts for browser automation and documentation generation.
- **Integration test property**: The design property that running `make-docs` constitutes a test — if any guide interaction fails because the application is broken, the command exits non-zero.

## Architecture

Two-pipeline system: a **guide runner** that drives Playwright to produce markdown and screenshots, and a **site builder** that renders them into HTML and PDF.

**Guide DSL** (`src/promptgrimoire/docs/guide.py`). Context-manager-based Python DSL exposing `Guide` and `Step`. A `Guide` manages a single document's lifecycle — on entry it creates the output directory and markdown buffer; on exit it writes the completed markdown file. `Step` is obtained via `with guide.step(heading):` — on entry it appends a `## heading` to the buffer, on exit it auto-captures a screenshot. Within a step, authors call `guide.screenshot()` for explicit mid-step captures and `guide.note()` for narrative text. The `Guide` receives a Playwright `Page` but does not own it — the runner manages the browser lifecycle.

**Screenshot annotation** (`src/promptgrimoire/docs/screenshot.py`). Two operations: element highlighting via CSS injection and whitespace trimming via Pillow. For highlighting, the DSL injects a temporary `<style>` element targeting the `data-testid` selector (e.g. `outline: 3px solid red`) before capture and removes it after. For trimming, Pillow's `ImageChops.difference()` detects content bounds and `Image.crop()` removes empty margins. An optional `focus` mode uses Playwright's `locator.screenshot()` to capture just a specific element.

**Guide runner** (`src/promptgrimoire/cli.py`, refactored `make_docs()`). Orchestrates the full lifecycle:
1. Check dependencies (pandoc on PATH)
2. DB cleanup via `_pre_test_db_cleanup()` (Alembic migrate + truncate)
3. Start server via `_start_e2e_server(port)` with `DEV__AUTH_MOCK=true`
4. Launch Playwright (sync API, 1280x800 viewport)
5. Import and call guide functions sequentially — instructor first (creates unit/week/activity), student second (uses them)
6. `mkdocs build` to render HTML site
7. Pandoc to render PDFs (with `--resource-path` for image resolution)
8. Stop browser, stop server

**Guide scripts** (`docs/guides/scripts/instructor_setup.py`, `student_workflow.py`). Plain Python functions that receive a `Page` and `base_url`. They use the DSL to narrate and screenshot each step. Authentication via mock token: `page.goto(f"{base_url}/auth/callback?token=mock-token-{email}")`. Interaction patterns reuse the same `data-testid` selectors and wait strategies as E2E tests.

**MkDocs site** (`mkdocs.yml` at project root). MkDocs Material renders guide markdown and screenshots into an HTML site at `docs/guides/site/`. Configuration is Zensical-compatible for future migration. GitHub Pages deployment via `mkdocs gh-deploy`.

**Data flow:**

```
uv run make-docs
  → DB cleanup (Alembic + truncate)
  → Start NiceGUI server (mock auth)
  → Playwright browser (1280x800)
  → instructor_setup.py(page, base_url)
      → Guide DSL: navigate, interact, screenshot, narrate
      → Output: instructor-setup.md + screenshots/instructor/*.png
  → student_workflow.py(page, base_url)
      → Guide DSL: navigate, interact, screenshot, narrate
      → Output: student-workflow.md + screenshots/student/*.png
  → mkdocs build → docs/guides/site/ (HTML)
  → pandoc → instructor-setup.pdf, student-workflow.pdf
  → Stop browser, stop server
```

## Existing Patterns

**Server lifecycle.** `make_docs()` already reuses `_start_e2e_server()` and `_pre_test_db_cleanup()` from the E2E infrastructure in `cli.py`. This design continues that pattern — same server startup, same mock auth, same DB cleanup.

**Mock authentication.** E2E tests authenticate by navigating to `/auth/callback?token=mock-token-{email}`. Guide scripts use the same pattern. No database user creation needed.

**data-testid convention.** All interactable UI elements have `data-testid` attributes. E2E tests use `page.get_by_test_id()` exclusively. Guide scripts follow the same convention, ensuring locator stability across UI changes.

**E2E interaction helpers.** `tests/e2e/annotation_helpers.py` contains `wait_for_text_walker()`, `select_chars()`, `create_highlight_with_tag()`, and other helpers. Guide scripts can import these directly for complex annotation interactions (text selection, highlight creation). Simpler interactions (click, fill, navigate) use Playwright's API directly.

**CLI entry points.** `pyproject.toml` defines CLI commands (`test-e2e`, `seed-data`, `manage-users`, `make-docs`). This design modifies the existing `make-docs` entry point in place.

**Divergence: bash → Python.** The current guide scripts are bash files invoking rodney and showboat CLIs. This design replaces them with Python modules using Playwright directly. The divergence is justified by: eliminating two external binary dependencies (rodney, showboat), gaining Python-native error handling, and enabling code sharing with the E2E test suite.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Guide DSL module and screenshot annotation

**Goal:** Build the context-manager DSL and screenshot post-processing module.

**Components:**
- `src/promptgrimoire/docs/__init__.py` — package init
- `src/promptgrimoire/docs/guide.py` — `Guide` and `Step` context managers, markdown buffer, screenshot naming
- `src/promptgrimoire/docs/screenshot.py` — CSS injection for element highlighting, Pillow-based whitespace trimming
- `Pillow` added to dev dependencies in `pyproject.toml`

**Dependencies:** None

**Done when:** DSL can be instantiated with a Playwright `Page`, steps produce markdown with `## heading` and image references, screenshots are annotated with element highlights and trimmed of whitespace. Unit tests verify markdown output structure, CSS injection/removal, and image cropping.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Refactor make_docs() to use Playwright

**Goal:** Replace rodney/showboat subprocess invocation with Playwright browser launch and Python guide function calls.

**Components:**
- `src/promptgrimoire/cli.py` — refactor `make_docs()`: remove rodney/showboat dependency checks, add Playwright sync API launch (1280x800 viewport), call guide functions instead of bash subprocesses, explicit `_stop_e2e_server()` on cleanup
- `pyproject.toml` — remove `showboat` from dev dependencies, remove `rodney` from documented external dependencies

**Dependencies:** Phase 1 (DSL module exists)

**Done when:** `make_docs()` starts Playwright, calls stub guide functions, captures screenshots via the DSL, and produces markdown files. Rodney and showboat are no longer invoked. Unit tests for CLI orchestration updated.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Migrate instructor guide to Python DSL

**Goal:** Rewrite the instructor setup guide as a Python module using the DSL.

**Components:**
- `docs/guides/scripts/instructor_setup.py` — Python guide function: login, create unit, create week, create activity, configure tags (with inline DB seeding for template workspace), enroll note, verify student view
- Delete `docs/guides/scripts/generate-instructor-setup.sh`

**Dependencies:** Phase 2 (Playwright runner works)

**Done when:** `uv run make-docs` produces `instructor-setup.md` with 7 screenshots, element highlights, trimmed whitespace, and narrative text. Guide content matches the current bash-generated output.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Migrate student guide to Python DSL

**Goal:** Rewrite the student workflow guide as a Python module using the DSL.

**Components:**
- `docs/guides/scripts/student_workflow.py` — Python guide function: login, navigate, create workspace, paste content, highlight text, add comment, organise tab, respond tab, export PDF
- Imports `wait_for_text_walker()` and `select_chars()` from `tests/e2e/annotation_helpers.py` for text selection
- Delete `docs/guides/scripts/generate-student-workflow.sh`
- Delete `docs/guides/scripts/common.sh`

**Dependencies:** Phase 3 (instructor guide creates the unit/week/activity the student uses)

**Done when:** `uv run make-docs` produces `student-workflow.md` with 10 screenshots. Full pipeline produces both guides. All bash scripts removed.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: MkDocs Material site

**Goal:** Add MkDocs Material and configure the HTML documentation site.

**Components:**
- `mkdocs.yml` at project root — site name, Material theme, nav structure, docs_dir pointing to `docs/guides/`
- `docs/guides/index.md` — hand-written landing page with links to guides and project description
- `mkdocs-material` added to dev dependencies in `pyproject.toml`
- `src/promptgrimoire/cli.py` — add `mkdocs build` step after guide generation
- `.gitignore` — add `docs/guides/site/`

**Dependencies:** Phase 4 (both guides produce markdown)

**Done when:** `uv run make-docs` produces an HTML site in `docs/guides/site/` with a landing page, both guides rendered with screenshots, and working navigation. `mkdocs serve` allows local preview.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Cleanup and documentation

**Goal:** Remove old dependencies and update project documentation.

**Components:**
- `pyproject.toml` — remove `showboat` from dev dependencies
- Delete `docs/rodney/cli-reference.md` (rodney no longer used)
- Delete `docs/guides/scripts/debug-instructor.sh` (superseded)
- `CLAUDE.md` — update `make-docs` description to reflect new pipeline
- `.gitignore` — verify all generated artefacts are ignored

**Dependencies:** Phase 5 (full pipeline works)

**Done when:** No references to rodney or showboat remain in the codebase. `uv run make-docs` produces HTML site + PDFs from Python guide scripts. Project documentation is accurate.
<!-- END_PHASE_6 -->

## Additional Considerations

**Zensical migration.** `mkdocs.yml` is compatible with Zensical. When Zensical adds PDF export and reaches plugin parity, swap `mkdocs build` for `zensical build` in the runner. Markdown and configuration require no changes.

**E2E helper sharing.** Guide scripts import helpers from `tests/e2e/annotation_helpers.py`. If this coupling becomes problematic (e.g. circular imports, test-only code leaking into production paths), extract shared helpers to `src/promptgrimoire/docs/helpers.py`. For now, direct import is simpler.

**Re-run behaviour.** `make_docs()` always starts clean — step 2 truncates all tables. A failed guide leaves partial output, but re-running rebuilds everything from scratch. There is no incremental mode.

**Pandoc.** Pandoc is an existing system dependency (already used for PDF export). It is checked at startup to give a clear error message rather than failing mid-pipeline.

**GitHub Pages deployment.** `mkdocs gh-deploy` pushes to the `gh-pages` branch. This is a manual command, not part of `make-docs`. CI/CD automation is deferred.

**Future guide authoring.** New guides are added by: (1) writing a Python function using the DSL, (2) adding it to the runner's guide list in `make_docs()`, (3) adding a nav entry to `mkdocs.yml`. The DSL's context-manager pattern and auto-screenshot make new guides straightforward to write.
