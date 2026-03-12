# Documentation Flight Rules Design

**GitHub Issue:** #230, #281

## Summary

This design consolidates user-facing documentation for PromptGrimoire into a searchable, always-current reference. The work has two main threads running in sequence.

The first thread corrects a known flaw in the existing instructor guide: Step 5 currently uses a database workaround to access the template workspace. This is replaced with the proper UI path — navigating to Unit Settings and clicking the template button — and the narrative is rewritten to explain the visual distinction between a template workspace (purple chip) and a student instance (blue chip).

The second thread builds a new "Using the Application" reference page modelled after git flight rules: a single document organised by feature domain, where each entry answers a specific first-person question ("I want to..." or "Why is...?"). Screenshots are generated automatically by Playwright on every build so they cannot go stale. An existing standalone script (`flight_rules.py`) that was never wired into the pipeline is absorbed into this new page and deleted. The final phase adds an optional in-app help button in the application header that opens an Algolia DocSearch modal (or a simpler MkDocs search fallback), controlled by a three-way feature flag in pydantic-settings. When the flag is `"off"`, no help UI is rendered at all.

## Definition of Done

1. A "Using PromptGrimoire" section on the docs site with flight-rules-style entries grouped by feature domain, each with Playwright-generated screenshots
2. Entries sourced from UATs across design plans and issues, covering what genuine users can do
3. Cross-links between the new entries and existing sequential guides
4. Help link in the navigator pointing to the docs site (#281)
5. Instructor guide Step 5 rewritten to use template workflow (#230)
6. Guide generation pipeline extended to produce the new entries

## Acceptance Criteria

### docs-flight-rules-230.AC1: Flight-rules reference page exists with correct structure
- **docs-flight-rules-230.AC1.1 Success:** `uv run grimoire docs build` generates `docs/guides/using-promptgrimoire.md` with `##` domain headings and `###` first-person entry headings
- **docs-flight-rules-230.AC1.2 Success:** Each domain section contains at least one entry with a screenshot
- **docs-flight-rules-230.AC1.3 Success:** Problem/diagnosis entries include **Diagnosis:** and **Fix:** blocks
- **docs-flight-rules-230.AC1.4 Success:** Cross-links to sequential guides use relative markdown links with anchor fragments

### docs-flight-rules-230.AC2: Template vs instance workflow is correct
- **docs-flight-rules-230.AC2.1 Success:** Instructor guide Step 5 navigates to template workspace via Unit Settings → `template-btn-{act.id}`, not via Navigator → Start
- **docs-flight-rules-230.AC2.2 Success:** `_seed_template_tags()` and `_SEED_TEMPLATE_TAGS_SCRIPT` are removed from `instructor_setup.py`
- **docs-flight-rules-230.AC2.3 Success:** Step 5 narrative explains template (purple chip) vs instance (blue chip) distinction
- **docs-flight-rules-230.AC2.4 Success:** Screenshot in Step 5 shows the purple chip highlighted

### docs-flight-rules-230.AC3: Pipeline generates and serves all guides
- **docs-flight-rules-230.AC3.1 Success:** `_GENERATED_GUIDE_MARKDOWN` tuple in `cli/docs.py` includes `"using-promptgrimoire.md"`
- **docs-flight-rules-230.AC3.2 Success:** `mkdocs.yml` has explicit `nav:` with "Getting Started" group and "Using the Application" entry
- **docs-flight-rules-230.AC3.3 Success:** MkDocs build produces navigable site with correct section ordering
- **docs-flight-rules-230.AC3.4 Success:** PDF generation via pandoc includes `using-promptgrimoire.md`
- **docs-flight-rules-230.AC3.5 Failure:** Build exits non-zero with an error message naming the missing screenshot file if Playwright screenshots are absent

### docs-flight-rules-230.AC4: Algolia DocSearch configured
- **docs-flight-rules-230.AC4.1 Success:** `HelpConfig` sub-model loads `help_enabled`, `help_backend`, `algolia_app_id`, `algolia_search_api_key`, `algolia_index_name` from env vars with `HELP__` prefix
- **docs-flight-rules-230.AC4.2 Success:** Default `help_enabled` is `False` (no help button when unconfigured)
- **docs-flight-rules-230.AC4.3 Failure:** Missing `algolia_app_id` when `help_enabled=True` and `help_backend="algolia"` raises validation error at startup
- **docs-flight-rules-230.AC4.4 Success:** Write API key is not referenced anywhere in application code or client-side assets

### docs-flight-rules-230.AC5: In-app help button works
- **docs-flight-rules-230.AC5.1 Success:** Help button with `data-testid="help-btn"` renders in header on every page when `help_enabled=True`
- **docs-flight-rules-230.AC5.2 Success:** With `help_backend="algolia"`, clicking help button opens DocSearch modal overlay
- **docs-flight-rules-230.AC5.3 Success:** With `help_backend="mkdocs"`, clicking help button opens MkDocs search in a modal
- **docs-flight-rules-230.AC5.4 Success:** When `help_enabled=False`, no help button is rendered
- **docs-flight-rules-230.AC5.5 Edge:** Help button does not interfere with existing header elements (logout, menu) on narrow viewports

### docs-flight-rules-230.AC6: `flight_rules.py` absorbed
- **docs-flight-rules-230.AC6.1 Success:** `flight_rules.py` is deleted from `src/promptgrimoire/docs/scripts/`
- **docs-flight-rules-230.AC6.2 Success:** All 4 existing flight rule entries (template vs instance, chip colours, start vs template, import tags) appear in `using-promptgrimoire.md`
- **docs-flight-rules-230.AC6.3 Failure:** No imports or references to `flight_rules` remain in the codebase

## Glossary

- **Flight rules**: A documentation pattern — borrowed from NASA's pre-launch procedures — where each entry is written as a first-person task or problem statement with a specific, actionable answer. Popularised for software development by the [git-flight-rules](https://github.com/k88hudson/git-flight-rules) project.
- **Template workspace**: In PromptGrimoire, a workspace created by an instructor that holds the canonical tag configuration for an activity. Students receive cloned instances of it, not the template itself. Visually identified by a purple chip in the UI.
- **Instance workspace**: A student-facing copy of a template workspace. Identified by a blue chip in the UI.
- **MkDocs**: A Python static site generator that builds documentation from Markdown files. Used here to produce the user-facing docs site.
- **Algolia DocSearch**: A hosted full-text search service for documentation sites. Provides a JS widget (`DocSearch`) that renders an in-page search modal. Requires an application ID and a read-only search API key on the client; a separate write API key is used only by the Algolia crawler and must never reach the client.
- **Playwright**: A browser automation library used here to drive the running application during the docs build, capturing screenshots of actual UI state at each guide step.
- **`data-testid`**: An HTML attribute convention used in this codebase to mark UI elements for both Playwright automation and screenshot highlighting. Playwright locates elements via `get_by_test_id()`.
- **pydantic-settings**: A Pydantic extension that loads configuration from environment variables into typed Python models. Sub-models use double-underscore prefixes (e.g., `HELP__MODE`) to namespace their env vars.
- **Guide DSL**: The project's internal API (`guide.py`) for writing guide scripts. Provides `Guide` and `Step` context managers that handle screenshot capture, thumbnail generation, and Markdown output in a consistent format.
- **`_GENERATED_GUIDE_MARKDOWN` tuple**: A registry in `cli/docs.py` that declares which guide Markdown files are included in PDF generation. New guides must be added here as well as wired into the Playwright execution sequence.
- **glightbox**: A MkDocs plugin that wraps inline images into a lightbox overlay, used here so thumbnail screenshots link to full-resolution versions.
- **UAT (User Acceptance Test)**: In this codebase, acceptance criteria written in user-facing terms and extracted from design plans and GitHub issues. The 691 UAT criteria mentioned in the document serve as a backlog of potential flight-rules entries.
- **Chip**: A small UI badge element in NiceGUI/Quasar that displays the workspace type. Purple = template, blue = instance.

## Architecture

### Content Structure

A single-page reference document (`docs/guides/using-promptgrimoire.md`) following the git flight rules pattern. Top-level `##` headings group entries by feature domain; `###` headings are first-person task or problem statements. Each entry contains:

- **Context/diagnosis** — what the user is trying to do or what went wrong
- **Steps/fix** — how to accomplish the task or resolve the problem, with Playwright-captured screenshots highlighting relevant UI elements via `data-testid`
- **Cross-link** — where applicable, a link to the relevant step in the sequential guides (Instructor Setup, Student Workflow, Your Personal Grimoire)

The page title in MkDocs navigation is "Using the Application". The generated markdown filename is `using-promptgrimoire.md` (slug: `using-promptgrimoire`).

### Domain Sections and Initial Entries

Each domain gets at least one happy-path entry ("I want to...") and one problem/diagnosis entry where applicable:

| Domain | Entry | Type |
|--------|-------|------|
| Getting Started | I want to log in for the first time | Happy path |
| Getting Started | I don't see any activities after logging in | Problem |
| Workspaces | I want to create a workspace for an activity | Happy path |
| Workspaces | I configured tags but students can't see them | Problem |
| Workspaces | I clicked Start but wanted the template | Problem |
| Tags | I want to create a tag group for my activity | Happy path |
| Tags | Tag import from another activity shows nothing | Problem |
| Annotating | I want to highlight text and apply a tag | Happy path |
| Annotating | I want to add a comment to my highlight | Happy path |
| Organising | I want to view my highlights grouped by tag | Happy path |
| Responding | I want to write a response using my highlights as reference | Happy path |
| Export | I want to export my work as PDF | Happy path |
| Unit Settings | I want to create a unit and activity | Happy path |
| Unit Settings | How do I know if I'm in a template or instance? | Orientation |
| Enrolment | I want to enrol students in my unit | Happy path |
| Navigation | I want to find my workspace | Happy path |
| Navigation | I want to search across my workspaces | Happy path |
| Sharing | I want to share my workspace with someone | Happy path |
| File Upload | I want to upload a document instead of pasting | Happy path |

### In-App Help with Algolia DocSearch

A help button in the application header opens an Algolia DocSearch modal overlay. Three-way feature flag controls behaviour:

Two orthogonal settings control behaviour:

- **`help_enabled`** (bool, default `False`) — whether the help button renders at all
- **`help_backend`** (Literal `"algolia"`, `"mkdocs"`, default `"mkdocs"`) — which search provider powers the modal. `algolia` loads the DocSearch JS widget; `mkdocs` embeds MkDocs built-in search

The Algolia application ID and search API key are stored in pydantic-settings configuration. The write API key is never shipped to the client.

### MkDocs Navigation

Explicit `nav:` section in `mkdocs.yml` replaces the current auto-generated comment:

```yaml
nav:
  - Home: index.md
  - Getting Started:
    - Instructor Setup: instructor-setup.md
    - Student Workflow: student-workflow.md
    - Your Personal Grimoire: your-personal-grimoire.md
  - Using the Application: using-promptgrimoire.md
```

## Existing Patterns

### Guide DSL (`src/promptgrimoire/docs/guide.py`)

The new script follows the same `Guide` + `Step` context manager pattern used by all existing guide scripts. Key conventions:

- Output directory: `GUIDE_OUTPUT_DIR = Path("docs/guides")`
- Screenshots captured via `guide.screenshot(caption, highlight=[testid, ...])` with red-border highlight on `data-testid` elements
- Thumbnails generated at 480px width, linked to full-res via glightbox
- Stale screenshots cleaned on each run by slug prefix

### CLI Registration (`src/promptgrimoire/cli/docs.py`)

Guide scripts are registered in two places:
1. `_GENERATED_GUIDE_MARKDOWN` tuple (line 22-26) — controls PDF generation
2. Sequential function calls in `build()` (lines 105-107) — controls Playwright execution order

The new script follows this pattern: add to tuple, add function call after existing guides.

### Settings Sub-Models (`src/promptgrimoire/config.py`)

New configuration follows the existing sub-model pattern (e.g., `StytchConfig`, `FeaturesConfig`). Algolia config would be a new `AlgoliaConfig` sub-model with env var prefix `ALGOLIA__`.

### Layout Header (`src/promptgrimoire/pages/layout.py`)

The help button goes in `_render_header()` (lines 128-139), between the flex spacer and the user email label. Follows the existing pattern of icon buttons in the header (hamburger menu, logout).

### Divergence: `flight_rules.py` Absorbed

The existing `flight_rules.py` script is not yet integrated into the CLI pipeline. Rather than integrating it separately, this design absorbs its 4 entries into the new `using_promptgrimoire.py` script and deletes `flight_rules.py`.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: #230 Fix — Instructor Guide Template Workflow

**Goal:** Rewrite instructor guide Step 5 to use the template button instead of the Start button + DB workaround.

**Components:**
- `src/promptgrimoire/docs/scripts/instructor_setup.py` — rewrite `_step_configure_tags()` to navigate via Unit Settings and click `template-btn-{act.id}`, remove `_seed_template_tags()` and `_SEED_TEMPLATE_TAGS_SCRIPT`
- Add narrative explaining template (purple chip) vs instance (blue chip) distinction

**Dependencies:** None (first phase)

**Done when:** `uv run grimoire docs build` generates `instructor-setup.md` with Step 5 showing the template workflow via Unit Settings, no DB workaround code remains in the script, screenshots show the purple chip
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Flight Rules Guide Script

**Goal:** Create the "Using the Application" guide script that generates the flight-rules-style reference page.

**Components:**
- `src/promptgrimoire/docs/scripts/using_promptgrimoire.py` — new Playwright script with `run_using_promptgrimoire_guide(page, base_url)` entry point. Domain sections as `##` headings, entries as `guide.step("I want to...")` with first-person `###` headings. ~19 entries across 10 domains. Reuses data state from instructor + student guides (unit, activity, workspace, tags all exist).
- Delete `src/promptgrimoire/docs/scripts/flight_rules.py` — absorbed into above
- `src/promptgrimoire/docs/scripts/__init__.py` — update exports

**Dependencies:** Phase 1 (template workflow must work for template-related entries)

**Done when:** Script generates `docs/guides/using-promptgrimoire.md` with all domain sections and entries, each with screenshots where applicable, cross-links to sequential guides present
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Pipeline Integration

**Goal:** Wire the new guide into the CLI build pipeline, MkDocs nav, and tests.

**Components:**
- `src/promptgrimoire/cli/docs.py` — add `"using-promptgrimoire.md"` to `_GENERATED_GUIDE_MARKDOWN` tuple, add `run_using_promptgrimoire_guide(page, base_url)` call after existing guides, remove `flight_rules` import if present
- `mkdocs.yml` — add explicit `nav:` section with Getting Started group + Using the Application entry
- `docs/guides/index.md` — update links to include all guides and the new reference page
- `tests/unit/test_make_docs.py` — add `"using-promptgrimoire"` to expected guide names, verify PDF generation includes the new guide

**Dependencies:** Phase 2 (script must exist)

**Done when:** `uv run grimoire docs build` generates all guides including the new reference page, `uv run grimoire docs build serve` shows correct MkDocs nav with "Using the Application" section, tests pass
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Algolia DocSearch Configuration

**Goal:** Configure Algolia search on the MkDocs site and add settings for in-app integration.

**Components:**
- `src/promptgrimoire/config.py` — new `HelpConfig` sub-model with fields: `help_enabled` (bool, default `False`), `help_backend` (Literal `"algolia"`, `"mkdocs"`, default `"mkdocs"`), `algolia_app_id` (str, default `""`), `algolia_search_api_key` (str, default `""`), `algolia_index_name` (str, default `""`)
- `mkdocs.yml` — replace `- search` plugin with Algolia DocSearch configuration for the static site
- `.env.example` — add `HELP__HELP_ENABLED`, `HELP__HELP_BACKEND`, `HELP__ALGOLIA_APP_ID`, `HELP__ALGOLIA_SEARCH_API_KEY`, `HELP__ALGOLIA_INDEX_NAME` entries

**Dependencies:** Phase 3 (docs site must be building correctly)

**Done when:** MkDocs site search uses Algolia when configured, `HelpConfig` loads from env vars, unit tests verify config loading for both `help_enabled` states and both `help_backend` values
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: In-App Help Button

**Goal:** Add help button to the application header that opens a search modal.

**Components:**
- `src/promptgrimoire/pages/layout.py` — add help button with `data-testid="help-btn"` in `_render_header()` between spacer and user email. Button renders conditionally based on `HelpConfig.help_enabled`. When `help_backend` is `"algolia"`: injects DocSearch JS/CSS via `ui.add_head_html()`, button click opens DocSearch modal. When `"mkdocs"`: button click opens a modal with embedded MkDocs search. When `help_enabled` is `False`: button not rendered.
- `src/promptgrimoire/static/` — any required JS glue for DocSearch widget initialisation

**Dependencies:** Phase 4 (config must exist)

**Done when:** Help button visible in header on every page, clicking opens appropriate search modal based on config mode, `data-testid="help-btn"` present, E2E test verifies button renders and is clickable in `mkdocs` mode
<!-- END_PHASE_5 -->

## Additional Considerations

**Prerequisite state coupling:** The new guide script depends on data created by the instructor and student guides (unit, activity, workspace, tags). This coupling already exists between the personal grimoire and instructor guides. The new script should validate prerequisites exist and seed missing state if needed, following the `_ensure_unit_exists()` pattern already in `flight_rules.py`. This prevents failures when running guides in isolation during development.

**Entry extensibility:** New entries can be added to `using_promptgrimoire.py` by adding a new function and calling it within the appropriate domain section. The UAT extraction (691 user-facing criteria) serves as a backlog — future work can add entries without architectural changes.

**Screenshot staleness:** All screenshots are regenerated on every `uv run grimoire docs build` run, so they cannot go stale. This is an existing property of the pipeline.

**Write API key security:** The Algolia write API key is used only for crawler configuration (outside this application). It must never appear in `HelpConfig` or client-side code. Only the search API key (read-only, safe for client exposure) is configured in the application.

**Agent team for implementation:** Phase 2 (the ~19-entry guide script) is well-suited to agent team parallelisation. Each domain section's entries are independent — an agent can write one domain's entries while another writes a different domain. The orchestrating implementation plan should dispatch domain sections to parallel agents, then assemble the results into the final script.
