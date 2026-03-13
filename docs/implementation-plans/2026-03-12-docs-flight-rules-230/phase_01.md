# Documentation Flight Rules — Phase 1: Instructor Guide Template Workflow

**Goal:** Rewrite instructor guide Step 5 to use the template button in Unit Settings instead of the Start button + DB workaround.

**Architecture:** Remove the database seeding workaround (`_seed_template_tags`, `_SEED_TEMPLATE_TAGS_SCRIPT`, `_enrol_instructor`) from `instructor_setup.py`. Rewrite `_step_configure_tags()` to navigate to the course detail page and click the `template-btn-{act.id}` button, opening the template workspace directly. Add narrative explaining the template (purple chip) vs instance (blue chip) distinction.

**Tech Stack:** Playwright (browser automation), Guide DSL (screenshot + markdown generation)

**Scope:** 1 of 5 phases from original design

**Codebase verified:** 2026-03-12

---

## Acceptance Criteria Coverage

This phase implements and tests:

### docs-flight-rules-230.AC2: Template vs instance workflow is correct
- **docs-flight-rules-230.AC2.1 Success:** Instructor guide Step 5 navigates to template workspace via Unit Settings → `template-btn-{act.id}`, not via Navigator → Start
- **docs-flight-rules-230.AC2.2 Success:** `_seed_template_tags()` and `_SEED_TEMPLATE_TAGS_SCRIPT` are removed from `instructor_setup.py`
- **docs-flight-rules-230.AC2.3 Success:** Step 5 narrative explains template (purple chip) vs instance (blue chip) distinction
- **docs-flight-rules-230.AC2.4 Success:** Screenshot in Step 5 shows the purple chip highlighted

---

<!-- START_TASK_1 -->
### Task 1: Rewrite `_step_configure_tags()` and remove DB workaround

**Verifies:** docs-flight-rules-230.AC2.1, docs-flight-rules-230.AC2.2, docs-flight-rules-230.AC2.3, docs-flight-rules-230.AC2.4

**Files:**
- Modify: `src/promptgrimoire/docs/scripts/instructor_setup.py`

**Context:**

Read these files before starting:
- `src/promptgrimoire/docs/scripts/instructor_setup.py` — the file being modified
- `src/promptgrimoire/docs/guide.py` — the Guide DSL API
- `src/promptgrimoire/pages/courses.py:330-351` — template button rendering and testid pattern

**Implementation:**

The current `_step_configure_tags()` (lines 218-247) uses this workflow:
1. Enrol instructor via CLI subprocess
2. Navigate to Navigator (home page)
3. Click Start button → creates a student instance workspace
4. Add sample content + configure tags in the instance
5. Call `_seed_template_tags()` to copy tags into the template workspace via DB

Replace with:
1. Navigate to the course detail page (Unit Settings) using the `course_url` parameter
2. Click the template button (`[data-testid^="template-btn-"]`)
3. Wait for annotation page to load
4. Add sample content + configure tags directly in the template workspace
5. No DB workaround needed

**Step 1: Delete the DB workaround code**

Remove these three items from `instructor_setup.py`:

1. `_enrol_instructor()` function (lines 30-49) — only called by the old `_step_configure_tags()` workflow
2. `_SEED_TEMPLATE_TAGS_SCRIPT` constant (lines 52-97) — the DB seeding SQL script
3. `_seed_template_tags()` function (lines 100-112) — the subprocess wrapper

**Step 2: Update `_step_configure_tags()` signature and implementation**

Change the function signature to accept `course_url` instead of `base_url`:

```python
def _step_configure_tags(page: Page, course_url: str, guide: Guide) -> None:
    """Step 5: Open template workspace via Unit Settings and configure tags."""
```

Replace the function body with:

```python
    with guide.step("Step 5: Configuring Tags in the Template") as g:
        g.note(
            "Each activity has a **template workspace** (shown with a purple chip) "
            "that holds the canonical tag configuration. When students start the "
            "activity, they receive a cloned **instance workspace** (blue chip) "
            "that inherits the template's tags.\n\n"
            "Navigate to Unit Settings and click the template button to open "
            "the template workspace directly."
        )

        # Navigate to Unit Settings (course detail page)
        page.goto(course_url)
        page.wait_for_timeout(2000)

        # Click the template button for the activity
        template_btn = page.locator('[data-testid^="template-btn-"]').first
        template_btn.wait_for(state="visible", timeout=10000)
        g.screenshot(
            "Unit Settings page showing the template button for the activity",
            highlight=["template-btn"],
        )
        template_btn.click()

        # Wait for annotation page (template workspace)
        page.wait_for_url(re.compile(r"/annotation\?workspace_id="), timeout=15000)

        _add_sample_content(page)
        _create_tag_group_and_tags(page, g)

        # Close tag management dialog
        page.get_by_test_id("tag-management-done-btn").click()
        page.wait_for_timeout(1000)
```

Note: The highlight parameter `"template-btn"` uses a prefix match — the Guide DSL's `screenshot()` method highlights elements where `data-testid` starts with the given string.

**Step 3: Update the call site in `run_instructor_guide()`**

At line 374, change:
```python
_step_configure_tags(page, base_url, guide)
```
to:
```python
_step_configure_tags(page, course_url, guide)
```

`course_url` is already captured at line 371 from `_step_create_unit()`.

**Testing:**

This is an infrastructure/guide-script task — verification is operational, not unit-test-based. The guide script drives a live browser; correctness is verified by running the build.

- docs-flight-rules-230.AC2.1: Run `uv run grimoire docs build`. Inspect generated `docs/guides/instructor-setup.md` — Step 5 should show navigation to Unit Settings and clicking the template button. No reference to Start button or Navigator in Step 5.
- docs-flight-rules-230.AC2.2: Search `instructor_setup.py` for `_seed_template_tags` and `_SEED_TEMPLATE_TAGS_SCRIPT` — neither should exist.
- docs-flight-rules-230.AC2.3: Read the Step 5 narrative in the generated markdown — it should mention template (purple chip) vs instance (blue chip).
- docs-flight-rules-230.AC2.4: Inspect the Step 5 screenshot — it should show the Unit Settings page with the template button highlighted (red border from the Guide DSL).

**Verification:**

```bash
# Verify DB workaround code is removed
grep -r "_seed_template_tags\|_SEED_TEMPLATE_TAGS_SCRIPT\|_enrol_instructor" src/promptgrimoire/docs/scripts/instructor_setup.py
# Expected: no output (no matches)

# Run type checker on modified file
uvx ty check src/promptgrimoire/docs/scripts/instructor_setup.py
# Expected: no errors

# Run linter
uv run ruff check src/promptgrimoire/docs/scripts/instructor_setup.py
# Expected: no errors

# Complexity check
uv run complexipy src/promptgrimoire/docs/scripts/instructor_setup.py
# Expected: no functions > 15
```

Full build verification (`uv run grimoire docs build`) requires a running app server with seeded data — this is tested during E2E/integration runs, not as a quick unit check.

**UAT Steps:**
1. [ ] Run `uv run grimoire docs build` (requires seeded app server)
2. [ ] Open generated `docs/guides/instructor-setup.md`
3. [ ] Verify Step 5 heading says "Configuring Tags in the Template"
4. [ ] Verify Step 5 narrative mentions template (purple chip) vs instance (blue chip)
5. [ ] Verify Step 5 screenshot shows Unit Settings page with template button highlighted (red border)
6. [ ] Verify no reference to "Start" button or "Navigator" in Step 5
7. [ ] Search `instructor_setup.py` for `_seed_template_tags`, `_SEED_TEMPLATE_TAGS_SCRIPT`, `_enrol_instructor` — none should exist

**Commit:** `docs: rewrite instructor guide Step 5 to use template workflow (#230)`
<!-- END_TASK_1 -->
