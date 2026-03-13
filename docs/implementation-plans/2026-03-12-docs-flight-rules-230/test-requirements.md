# Test Requirements: docs-flight-rules-230

**Plan:** Documentation Flight Rules — Instructor Guide, Flight Rules Guide, Pipeline Integration, Algolia DocSearch, In-App Help Button
**Issues:** #230 (guide infrastructure), #281 (in-app help)
**Generated:** 2026-03-12

---

## Acceptance Criteria Summary

| AC | Description | Phase | Test Type |
|----|-------------|-------|-----------|
| AC1.1 | `using-promptgrimoire.md` generated with `##`/`###` heading hierarchy | Phase 2 | Operational |
| AC1.2 | Each domain section contains at least one screenshot | Phase 2 | Operational |
| AC1.3 | Problem/diagnosis entries have **Diagnosis:** and **Fix:** blocks | Phase 2 | Operational |
| AC1.4 | Cross-links use relative markdown links with anchor fragments | Phase 2 | Operational |
| AC2.1 | Step 5 navigates via template button, not Start button | Phase 1 | Operational |
| AC2.2 | `_seed_template_tags()` and `_SEED_TEMPLATE_TAGS_SCRIPT` removed | Phase 1 | Static grep |
| AC2.3 | Step 5 narrative explains template (purple) vs instance (blue) | Phase 1 | Operational |
| AC2.4 | Step 5 screenshot shows Unit Settings with template button highlighted | Phase 1 | Operational |
| AC3.1 | `_GENERATED_GUIDE_MARKDOWN` includes `"using-promptgrimoire.md"` | Phase 3 | Unit |
| AC3.2 | `mkdocs.yml` has explicit `nav:` with correct section ordering | Phase 3 | Static parse |
| AC3.3 | MkDocs build produces navigable site with correct ordering | Phase 3 | Operational |
| AC3.4 | Pandoc includes `using-promptgrimoire.md` in PDF generation | Phase 3 | Unit |
| AC3.5 | Build exits non-zero naming missing screenshot file | Phase 3 | Unit |
| AC4.1 | `HelpConfig` loads all five fields from `HELP__` env vars | Phase 4 | Unit |
| AC4.2 | Default `help_enabled` is `False` | Phase 4 | Unit |
| AC4.3 | Missing Algolia credentials raise `ValidationError` at startup | Phase 4 | Unit |
| AC4.4 | Write API key not referenced anywhere in application code | Phase 4 | Static grep |
| AC5.1 | `data-testid="help-btn"` renders in header when `help_enabled=True` | Phase 5 | Unit + E2E |
| AC5.2 | Algolia backend: clicking help button opens DocSearch modal | Phase 5 | UAT only |
| AC5.3 | MkDocs backend: clicking help button opens docs site (new tab) | Phase 5 | E2E |
| AC5.4 | `help_enabled=False`: no help button rendered | Phase 5 | Unit + E2E |
| AC5.5 | Help button does not interfere with header on narrow viewports | Phase 5 | UAT only |
| AC6.1 | `flight_rules.py` deleted from `scripts/` | Phase 2 | Static file check |
| AC6.2 | All 4 existing flight rule entries appear in `using-promptgrimoire.md` | Phase 2 | Operational |
| AC6.3 | No imports or references to `flight_rules` remain in codebase | Phase 2 | Static grep |

---

## Automated Test Coverage Required

These criteria have automated tests that must exist and pass before the implementation is considered complete.

| Criterion | Test File | What the Test Verifies |
|-----------|-----------|------------------------|
| AC3.1 | `tests/unit/test_make_docs.py` | `"using-promptgrimoire.md"` present in `_GENERATED_GUIDE_MARKDOWN` tuple |
| AC3.4 | `tests/unit/test_make_docs.py` | Pandoc mock called exactly 4 times; `using-promptgrimoire.md` in pandoc arguments |
| AC3.5 | `tests/unit/test_make_docs.py` | Build function exits non-zero when expected guide markdown file is absent, with error message naming the missing file |
| AC4.1 | `tests/unit/test_help_config.py` | `HelpConfig` accepts all five fields; valid fully-specified config constructs without error |
| AC4.2 | `tests/unit/test_help_config.py` | `HelpConfig()` with no arguments has `help_enabled=False` |
| AC4.3 | `tests/unit/test_help_config.py` | `HelpConfig(help_enabled=True, help_backend="algolia")` with missing `algolia_app_id`, missing `algolia_search_api_key`, and missing `algolia_index_name` each raise `ValidationError`; disabled or mkdocs mode do not |
| AC5.1 | `tests/unit/test_help_button.py` | `_render_help_button()` calls a rendering function (not early-returns) when `help_enabled=True` |
| AC5.1 | `tests/e2e/test_help_button.py` | `page.get_by_test_id("help-btn")` is visible after navigating to any authenticated page |
| AC5.4 | `tests/unit/test_help_button.py` | `_render_help_button()` returns immediately without creating UI elements when `help_enabled=False` |
| AC5.4 | `tests/e2e/test_help_button.py` | `page.get_by_test_id("help-btn")` is not visible when `help_enabled=False` |
| Phase 2 DSL | `tests/unit/test_guide_dsl.py` | `Guide.section()` emits `## heading`; `guide.step(level=3)` emits `### heading`; `guide.subheading()` emits `### heading`; `guide.step()` default still emits `## heading` (backward compatible) |

**Note on AC5.3:** The E2E test for the MkDocs backend verifies the button is clickable and triggers navigation. Full tab-open verification depends on whether the E2E conftest parametrises env vars per test. If env vars are fixed, the enabled-state test covers AC5.3 by confirming the click does not error; new-tab destination is UAT-verified.

**Note on AC5.2:** DocSearch modal opening requires valid Algolia credentials and CDN access. It cannot be automated without a real index. This is UAT-only.

---

## Static Verification Required

These criteria are verified by grep or file-system checks, not by test suites. They are preconditions before the operational build runs.

| Criterion | Command | Expected Result |
|-----------|---------|-----------------|
| AC2.2 | `grep -r "_seed_template_tags\|_SEED_TEMPLATE_TAGS_SCRIPT\|_enrol_instructor" src/promptgrimoire/docs/scripts/instructor_setup.py` | No output (zero matches) |
| AC3.2 | `python -c "import yaml; nav = yaml.safe_load(open('mkdocs.yml'))['nav']; print(nav)"` | YAML parses without error; `nav` key present with "Getting Started" group and "Using the Application" entry |
| AC4.4 | `grep -r "write_api_key\|admin_api_key" src/ tests/ .env.example` | No output (zero matches) |
| AC6.1 | `ls src/promptgrimoire/docs/scripts/flight_rules.py` | "No such file or directory" |
| AC6.3 | `grep -r "flight_rules" src/ tests/` | No output (zero matches) |

---

## Human Verification Required

These criteria require a running application with seeded data and cannot be automated with unit or E2E tests.

| Criterion | Why Manual | Verification Method |
|-----------|------------|---------------------|
| AC1.1 | Requires `uv run grimoire docs build` against live server; output is generated markdown | Inspect `docs/guides/using-promptgrimoire.md` for `##`/`###` heading levels |
| AC1.2 | Screenshot presence in generated markdown depends on Playwright against live UI | Grep generated markdown for `![` image syntax per domain section |
| AC1.3 | Content accuracy of **Diagnosis:** and **Fix:** blocks is editorial | Read generated markdown; confirm both block types appear in problem entries |
| AC1.4 | Relative link anchors depend on exact heading text in generated output | Inspect cross-links; click them in rendered MkDocs site to confirm anchors resolve |
| AC2.1 | Guide script runs Playwright against live app; Step 5 navigation path is behavioral | Run `uv run grimoire docs build`; open `docs/guides/instructor-setup.md`; verify Step 5 references Unit Settings and template button, not Start button or Navigator |
| AC2.3 | Narrative accuracy (purple/blue chip distinction) is editorial | Read Step 5 text in generated markdown |
| AC2.4 | Screenshot content (highlighted template button) visible only in rendered image | View Step 5 screenshot; confirm purple chip or template button has red border highlight |
| AC3.3 | MkDocs navigation rendering requires `uv run grimoire docs serve` | Browse served site; confirm "Getting Started" and "Using the Application" sections appear in sidebar |
| AC5.2 | DocSearch modal requires valid Algolia credentials and live CDN | Set `HELP__HELP_BACKEND=algolia` with real credentials; click help button; confirm modal opens |
| AC5.5 | Narrow viewport layout is visual; no automated viewport-resize assertion in E2E suite | Resize browser to ~320px; confirm help button and logout button both visible and not overlapping |
| AC6.2 | Content equivalence of 4 absorbed flight-rule entries is editorial | Read `using-promptgrimoire.md`; confirm template vs instance, chip colours, start vs template, and tag import entries all present |

---

## Phase-by-Phase Test File Map

### Phase 1 — Instructor Guide Template Workflow

| Task | Implementation File | Test Coverage |
|------|---------------------|---------------|
| T1: Rewrite `_step_configure_tags()` | `docs/scripts/instructor_setup.py` | Static grep (AC2.2) + Operational UAT (AC2.1, AC2.3, AC2.4) |

No new test files. Verification is static analysis (`grep`, `ty check`, `ruff`) plus operational build.

### Phase 2 — Flight Rules Guide Script

| Task | Implementation File | Test Coverage |
|------|---------------------|---------------|
| T1: Extend Guide DSL | `docs/guide.py` | Unit: `tests/unit/test_guide_dsl.py` (AC1.1 DSL) |
| T2: Migrate `personal_grimoire.py` | `docs/scripts/personal_grimoire.py` | Static: `ty check`, `ruff` (no AC, infrastructure cleanup) |
| T3: Create `using_promptgrimoire.py` | `docs/scripts/using_promptgrimoire.py` | Operational UAT (AC1.1–AC1.4, AC6.2) |
| T4: Delete `flight_rules.py` | (deletion) | Static grep (AC6.1, AC6.3) |

### Phase 3 — Pipeline Integration

| Task | Implementation File | Test Coverage |
|------|---------------------|---------------|
| T1: Wire into `cli/docs.py` | `cli/docs.py` | Unit: `tests/unit/test_make_docs.py` (AC3.1, AC3.4) |
| T2: `mkdocs.yml` nav + `index.md` | `mkdocs.yml`, `docs/guides/index.md` | Static YAML parse (AC3.2) + Operational UAT (AC3.3) |
| T3: Update `test_make_docs.py` | `tests/unit/test_make_docs.py` | Unit: self-verifying (AC3.1, AC3.4, AC3.5) |

### Phase 4 — Algolia DocSearch Configuration

| Task | Implementation File | Test Coverage |
|------|---------------------|---------------|
| T1: `HelpConfig` sub-model | `config.py`, `.env.example`, `docs/configuration.md` | Unit: `tests/unit/test_help_config.py` (AC4.1–AC4.3) + static grep (AC4.4) |
| T2: `HelpConfig` unit tests | `tests/unit/test_help_config.py` | Unit: self-verifying (AC4.1–AC4.3) |

### Phase 5 — In-App Help Button

| Task | Implementation File | Test Coverage |
|------|---------------------|---------------|
| T1: Help button in `layout.py` | `pages/layout.py` | Unit: `tests/unit/test_help_button.py` (AC5.1, AC5.4 routing) + E2E: `tests/e2e/test_help_button.py` (AC5.1, AC5.3, AC5.4) |
| T2: Help button unit tests | `tests/unit/test_help_button.py` | Unit: self-verifying (AC5.1, AC5.2 routing, AC5.4) |
| T3: Help button E2E test | `tests/e2e/test_help_button.py` | E2E: self-verifying (AC5.1, AC5.3, AC5.4) |

---

## Run Order for Validation

```bash
# 1. Static checks (no server required)
grep -r "_seed_template_tags\|_SEED_TEMPLATE_TAGS_SCRIPT\|_enrol_instructor" \
    src/promptgrimoire/docs/scripts/instructor_setup.py
grep -r "flight_rules" src/ tests/
grep -r "write_api_key\|admin_api_key" src/ tests/ .env.example
ls src/promptgrimoire/docs/scripts/flight_rules.py
python -c "import yaml; yaml.safe_load(open('mkdocs.yml'))"

# 2. Type and lint checks
uvx ty check src/promptgrimoire/
uv run ruff check src/promptgrimoire/

# 3. Unit tests
uv run pytest tests/unit/test_guide_dsl.py -v
uv run pytest tests/unit/test_make_docs.py -v
uv run pytest tests/unit/test_help_config.py -v
uv run pytest tests/unit/test_help_button.py -v

# 4. E2E tests
uv run grimoire e2e run -k test_help_button

# 5. Operational build (requires seeded app server)
uv run grimoire docs build
# Then inspect: docs/guides/using-promptgrimoire.md
# Then inspect: docs/guides/instructor-setup.md (Step 5)

# 6. MkDocs serve (requires built docs)
uv run grimoire docs serve
# Verify nav in browser

# 7. UAT (requires running app + Algolia credentials for AC5.2)
# See UAT checklist below
```

---

## UAT Checklist

Complete this checklist after all automated tests pass and the operational build succeeds.

### AC1 — Flight-rules reference page structure
- [ ] Open `docs/guides/using-promptgrimoire.md` — confirm `##` domain headings (Getting Started, Workspaces, Tags, Annotating, Organising, Responding, Export, Unit Settings, Enrolment, Navigation, Sharing, File Upload)
- [ ] Confirm `###` first-person entry headings ("I want to...", "Why is...?")
- [ ] Confirm each domain section contains at least one `![screenshot]` image
- [ ] Confirm problem entries contain both `**Diagnosis:**` and `**Fix:**` blocks
- [ ] Confirm at least one cross-link in the form `[text](guide-name.md#anchor)` and that it resolves in the served MkDocs site

### AC2 — Template vs instance workflow
- [ ] Open `docs/guides/instructor-setup.md` — navigate to Step 5
- [ ] Confirm Step 5 heading reads "Configuring Tags in the Template"
- [ ] Confirm Step 5 narrative mentions "template workspace" (purple chip) and "instance workspace" (blue chip)
- [ ] Confirm Step 5 screenshot shows Unit Settings page with the template button visibly highlighted (red border)
- [ ] Confirm Step 5 contains no reference to the Start button or the Navigator

### AC3 — Pipeline generates and serves all guides
- [ ] Confirm `docs/guides/using-promptgrimoire.md` was generated (file exists, non-empty)
- [ ] Confirm `docs/guides/using-promptgrimoire.pdf` was generated by pandoc
- [ ] Run `uv run grimoire docs serve` — confirm sidebar shows "Getting Started" group (Instructor Setup, Student Workflow, Your Personal Grimoire) and "Using the Application" entry
- [ ] Confirm `docs/guides/index.md` links all 4 guides including "Your Personal Grimoire"

### AC4 — Algolia DocSearch configuration
- [ ] Run `uv run python -c "from promptgrimoire.config import Settings; s = Settings(); print(s.help)"` — confirm `help_enabled=False`, `help_backend='mkdocs'`
- [ ] Set `HELP__HELP_ENABLED=true HELP__HELP_BACKEND=algolia` without credentials — confirm startup fails with a clear error naming missing fields (`algolia_app_id`, `algolia_search_api_key`, `algolia_index_name`)
- [ ] Set `HELP__HELP_ENABLED=true HELP__HELP_BACKEND=mkdocs` — confirm startup succeeds without Algolia credentials
- [ ] Confirm `.env.example` has `HELP__` section with comment "use the SEARCH-ONLY API key"
- [ ] Confirm `docs/configuration.md` has `HELP__` row in the sub-model reference table

### AC5 — In-app help button
- [ ] Start app: `HELP__HELP_ENABLED=true HELP__HELP_BACKEND=mkdocs uv run run.py`
- [ ] Log in — confirm question-mark icon appears in header between flex spacer and user email
- [ ] Click the help button — confirm a new browser tab opens to the docs site URL
- [ ] Resize browser to ~320px width — confirm help button and logout button are both visible and non-overlapping
- [ ] Restart with `HELP__HELP_ENABLED=false` — confirm no help button appears in header
- [ ] **(Requires Algolia credentials — AC5.2):** Set `HELP__HELP_BACKEND=algolia` with valid `HELP__ALGOLIA_APP_ID`, `HELP__ALGOLIA_SEARCH_API_KEY`, `HELP__ALGOLIA_INDEX_NAME` — click help button and confirm DocSearch modal overlay opens

### AC6 — flight_rules.py absorbed
- [ ] `ls src/promptgrimoire/docs/scripts/flight_rules.py` returns "No such file or directory"
- [ ] In `docs/guides/using-promptgrimoire.md`: confirm entry "I configured tags but students can't see them" (absorbed from `_rule_template_vs_instance`)
- [ ] Confirm entry "How do I know if I'm in a template or instance?" (absorbed from `_rule_chip_colours`)
- [ ] Confirm entry "I clicked Start but wanted the template" (absorbed from `_rule_start_vs_template`)
- [ ] Confirm entry "Tag import from another activity shows nothing" (absorbed from `_rule_import_tags`)
- [ ] `grep -r "flight_rules" src/ tests/` returns no output
