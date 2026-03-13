# Documentation Flight Rules — Phase 2: Flight Rules Guide Script

**Goal:** Create the "Using the Application" guide script with flight-rules-style entries, absorb and delete the standalone `flight_rules.py`.

**Architecture:** Extend the Guide DSL with a `section()` method and `level` parameter on `step()` to support `##` domain sections with `###` entry headings. Create `using_promptgrimoire.py` with ~19 entries across 10 domains, reusing data state from prior guides. Delete `flight_rules.py` and clean up references. Migrate `personal_grimoire.py`'s private `_append("### ...")` calls to use the new public API.

**Tech Stack:** Playwright, Guide DSL, Python

**Scope:** 2 of 5 phases from original design

**Codebase verified:** 2026-03-12

---

## Acceptance Criteria Coverage

This phase implements and tests:

### docs-flight-rules-230.AC1: Flight-rules reference page exists with correct structure
- **docs-flight-rules-230.AC1.1 Success:** `uv run grimoire docs build` generates `docs/guides/using-promptgrimoire.md` with `##` domain headings and `###` first-person entry headings
- **docs-flight-rules-230.AC1.2 Success:** Each domain section contains at least one entry with a screenshot
- **docs-flight-rules-230.AC1.3 Success:** Problem/diagnosis entries include **Diagnosis:** and **Fix:** blocks
- **docs-flight-rules-230.AC1.4 Success:** Cross-links to sequential guides use relative markdown links with anchor fragments

### docs-flight-rules-230.AC6: `flight_rules.py` absorbed
- **docs-flight-rules-230.AC6.1 Success:** `flight_rules.py` is deleted from `src/promptgrimoire/docs/scripts/`
- **docs-flight-rules-230.AC6.2 Success:** All 4 existing flight rule entries (template vs instance, chip colours, start vs template, import tags) appear in `using-promptgrimoire.md`
- **docs-flight-rules-230.AC6.3 Failure:** No imports or references to `flight_rules` remain in the codebase

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Extend Guide DSL with `section()` and `level` parameter

**Verifies:** docs-flight-rules-230.AC1.1 (supports `##` domain / `###` entry heading hierarchy)

**Files:**
- Modify: `src/promptgrimoire/docs/guide.py` (lines 93-95 for `step()`, new method after line 103)
- Test: `tests/unit/test_guide_dsl.py` (unit)

**Context:**

Read these files before starting:
- `src/promptgrimoire/docs/guide.py` — current Guide DSL implementation
- `src/promptgrimoire/docs/scripts/personal_grimoire.py:405-494` — existing private `_append("### ...")` usage that needs migrating

**Implementation:**

The current Guide DSL hierarchy:
- `Guide.__enter__()` → `# Title` (line 80)
- `guide.step(heading)` → `## heading` (line 166)
- Private `_append("### subhead\n")` used in personal_grimoire.py (lines 405, 416, 456, 494) — no public API

Add two features:

**1. `section()` method on Guide** (after line 103):

```python
def section(self, heading: str) -> None:
    """Emit a ``## section`` heading for grouping steps."""
    self._append(f"## {heading}\n")
```

**2. `level` parameter on `step()` and `Step`:**

Modify `Guide.step()` (line 93-95):
```python
def step(self, heading: str, *, level: int = 2) -> Step:
    """Create a ``Step`` context manager bound to this guide."""
    return Step(self, heading, level=level)
```

Modify `Step.__init__()` (line 160-162):
```python
def __init__(self, guide: Guide, heading: str, *, level: int = 2) -> None:
    self._guide = guide
    self._heading = heading
    self._level = level
    self._screenshot_count_at_entry: int = 0
```

Modify `Step.__enter__()` (line 165-167):
```python
def __enter__(self) -> Guide:
    prefix = "#" * self._level
    self._guide._append(f"{prefix} {self._heading}\n")
    self._screenshot_count_at_entry = self._guide._screenshot_counter
    return self._guide
```

Update the `Step` docstring (line 148-157) to mention the `level` parameter.

**3. Add `subheading()` method on Guide** (convenience for sub-step headings):

```python
def subheading(self, heading: str, *, level: int = 3) -> None:
    """Emit a sub-heading within a step (default ``###``)."""
    prefix = "#" * level
    self._append(f"{prefix} {heading}\n")
```

**Testing:**

Tests must verify:
- docs-flight-rules-230.AC1.1: `guide.section("Domain")` emits `## Domain`, `guide.step("Entry", level=3)` emits `### Entry`

Write unit tests verifying:
- `Guide.section()` appends `## heading` to buffer
- `Guide.step()` with default level appends `## heading` (backward compatible)
- `Guide.step(level=3)` appends `### heading`
- `Guide.subheading()` appends `### heading`
- `Guide.subheading(level=4)` appends `#### heading`

Use a mock Page object (guide needs a Page for screenshot capability but these tests won't take screenshots).

**Verification:**
```bash
uv run pytest tests/unit/test_guide_dsl.py -v
# Expected: all tests pass

uvx ty check src/promptgrimoire/docs/guide.py
# Expected: no errors

uv run ruff check src/promptgrimoire/docs/guide.py
# Expected: no errors

uv run complexipy src/promptgrimoire/docs/guide.py
# Expected: no functions > 15

uvx ty check tests/unit/test_guide_dsl.py
# Expected: no errors

uv run ruff check tests/unit/test_guide_dsl.py
# Expected: no errors

uv run complexipy tests/unit/test_guide_dsl.py
# Expected: no functions > 15
```

**Commit:** `feat: extend Guide DSL with section() and level parameter`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Migrate personal_grimoire.py to use `subheading()` API

**Verifies:** None (infrastructure cleanup, no ACs — backward-compatible refactor)

**Files:**
- Modify: `src/promptgrimoire/docs/scripts/personal_grimoire.py` (lines 405, 416, 456, 494)

**Context:**

Read `src/promptgrimoire/docs/scripts/personal_grimoire.py` — the existing script that uses private `g._append("### ...")` calls.

**Implementation:**

Replace 4 private `_append` calls with public `subheading()`:

Line 405: `g._append("### Viewing Your Tags\n")` → `g.subheading("Viewing Your Tags")`
Line 416: `g._append("### Reordering Within a Column\n")` → `g.subheading("Reordering Within a Column")`
Line 456: `g._append("### Writing Your Response\n")` → `g.subheading("Writing Your Response")`
Line 494: `g._append("### Locating Source Text\n")` → `g.subheading("Locating Source Text")`

**Verification:**
```bash
uvx ty check src/promptgrimoire/docs/scripts/personal_grimoire.py
# Expected: no errors

uv run ruff check src/promptgrimoire/docs/scripts/personal_grimoire.py
# Expected: no errors

uv run complexipy src/promptgrimoire/docs/scripts/personal_grimoire.py
# Expected: no functions > 15
```

**Commit:** `refactor: migrate personal_grimoire.py to public subheading() API`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Create `using_promptgrimoire.py` guide script

**Verifies:** docs-flight-rules-230.AC1.1, docs-flight-rules-230.AC1.2, docs-flight-rules-230.AC1.3, docs-flight-rules-230.AC1.4, docs-flight-rules-230.AC6.2

**Files:**
- Create: `src/promptgrimoire/docs/scripts/using_promptgrimoire.py`

**Context:**

Read these files before starting:
- `src/promptgrimoire/docs/guide.py` — Guide DSL (with new `section()`, `level`, `subheading()` from Task 1)
- `src/promptgrimoire/docs/scripts/flight_rules.py` — 4 entries to absorb (lines 97-208)
- `src/promptgrimoire/docs/scripts/instructor_setup.py` — data state created (UNIT1234, activity, tags)
- `src/promptgrimoire/docs/scripts/student_workflow.py` — data state created (student workspace)
- `src/promptgrimoire/docs/scripts/personal_grimoire.py` — prerequisite pattern (`_ensure_instructor_guide_ran`)
- `src/promptgrimoire/docs/helpers.py` — `select_chars()`, `wait_for_text_walker()` helpers

**Implementation:**

Create `src/promptgrimoire/docs/scripts/using_promptgrimoire.py` with entry point `run_using_promptgrimoire_guide(page: Page, base_url: str) -> None`.

**Structure:**
```python
"""Using PromptGrimoire flight-rules guide.

Generates a single-page reference document organised by feature domain.
Each entry answers a first-person question ("I want to..." or "Why is...?")
with screenshots captured from a live application instance.

Requires data state from instructor + student guides (UNIT1234, activity,
workspace, tags). Runs after all sequential guides in the build pipeline.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page  # annotation-only; safe with PEP 563

from promptgrimoire.docs import Guide
from promptgrimoire.docs.helpers import select_chars, wait_for_text_walker

GUIDE_OUTPUT_DIR = Path("docs/guides")
```

**Prerequisite validation:** Follow the `_ensure_instructor_guide_ran` pattern from `personal_grimoire.py`. Authenticate as the instructor, navigate to the Navigator, and check that UNIT1234 exists. If not, run the instructor guide. This ensures the script can be tested in isolation during development.

`_ensure_prerequisites()` must return a `course_url: str` — the URL of the UNIT1234 course detail page (e.g., `{base_url}/courses/{course_id}`). This URL is needed by several entries that navigate to Unit Settings (e.g., `_entry_tags_not_visible`, `_entry_chip_colours`). Extract it by finding the UNIT1234 course link on the Navigator or by querying the course detail page directly, following the same pattern as `instructor_setup.py`'s `_step_create_unit()` which returns `course_url`.

**Domain sections and entries:**

Use `guide.section("Domain Name")` for domain sections (emits `## Domain Name`) and `guide.step("I want to...", level=3)` for entries (emits `### I want to...`).

The 10 domains and ~19 entries from the design plan:

| Domain | Entry | Type | Screenshots needed |
|--------|-------|------|-------------------|
| Getting Started | I want to log in for the first time | Happy path | Login page, Navigator |
| Getting Started | I don't see any activities after logging in | Problem | Empty Navigator |
| Workspaces | I want to create a workspace for an activity | Happy path | Start button, workspace |
| Workspaces | I configured tags but students can't see them | Problem | Unit Settings + template btn (from flight_rules) |
| Workspaces | I clicked Start but wanted the template | Problem | Navigator Start btn (from flight_rules) |
| Tags | I want to create a tag group for my activity | Happy path | Tag management dialog |
| Tags | Tag import from another activity shows nothing | Problem | (narrative only, from flight_rules) |
| Annotating | I want to highlight text and apply a tag | Happy path | Tag toolbar, highlighted text |
| Annotating | I want to add a comment to my highlight | Happy path | Comment input, posted comment |
| Organising | I want to view my highlights grouped by tag | Happy path | Organise tab columns |
| Responding | I want to write a response using my highlights as reference | Happy path | Respond tab, editor + references |
| Export | I want to export my work as PDF | Happy path | Export button |
| Unit Settings | I want to create a unit and activity | Happy path | Course creation form |
| Unit Settings | How do I know if I'm in a template or instance? | Orientation | Purple vs blue chip (from flight_rules) |
| Enrolment | I want to enrol students in my unit | Happy path | Enrollment page |
| Navigation | I want to find my workspace | Happy path | Navigator with workspaces |
| Navigation | I want to search across my workspaces | Happy path | Search input |
| Sharing | I want to share my workspace with someone | Happy path | Share dialog |
| File Upload | I want to upload a document instead of pasting | Happy path | Upload button/dialog |

**Entry implementation pattern:**

Each entry function follows this pattern:
```python
def _entry_log_in(page: Page, base_url: str, guide: Guide) -> None:
    """I want to log in for the first time."""
    with guide.step("I want to log in for the first time", level=3) as g:
        g.note(
            "Navigate to the application URL. You will be prompted to "
            "enter your email address for a magic link login."
        )
        # ... Playwright navigation and screenshot capture ...
        g.screenshot("Login page", highlight=["login-email-input"])
        g.note(
            "See [Student Workflow § Step 1](student-workflow.md#step-1-logging-in) "
            "for a step-by-step walkthrough."
        )
```

**Problem/diagnosis entries** (AC1.3) must include `**Diagnosis:**` and `**Fix:**` blocks:
```python
def _entry_tags_not_visible(page: Page, course_url: str, guide: Guide) -> None:
    """I configured tags but students can't see them."""
    with guide.step("I configured tags but students can't see them", level=3) as g:
        g.note(
            "**Diagnosis:** You configured tags in your own workspace "
            "(a student instance), not the template. Tags set on instances "
            "only affect that workspace."
        )
        g.note(
            "**Fix:** Go to **Unit Settings** and click the **Create Template** "
            "or **Edit Template** button next to the activity. This opens the "
            "template workspace (purple chip). Configure tags there — students "
            "will inherit them when they start the activity."
        )
        # ... screenshot of Unit Settings with template button highlighted ...
```

**Cross-links** (AC1.4) use relative markdown links with anchor fragments:
```python
g.note(
    "See [Instructor Setup § Step 5](instructor-setup.md#step-5-configuring-tags-in-the-template) "
    "for a complete walkthrough."
)
```

**Main entry point:**
```python
def run_using_promptgrimoire_guide(page: Page, base_url: str) -> None:
    """Run the Using PromptGrimoire flight-rules guide."""
    course_url = _ensure_prerequisites(page, base_url)

    with Guide("Using PromptGrimoire", GUIDE_OUTPUT_DIR, page) as guide:
        guide.note(
            "Quick answers to common tasks and problems. "
            "Each entry shows you exactly what to click, with screenshots "
            "from the live application."
        )

        guide.section("Getting Started")
        _entry_log_in(page, base_url, guide)
        _entry_no_activities(page, base_url, guide)

        guide.section("Workspaces")
        _entry_create_workspace(page, base_url, guide)
        _entry_tags_not_visible(page, course_url, guide)
        _entry_start_vs_template(page, base_url, guide)

        # ... remaining domain sections ...
```

**Data state assumptions:** This script runs after instructor, student, and personal grimoire guides. The following data exists:
- Unit `UNIT1234` with semester `S1 2026`
- Week 3 "Source Text Analysis" with published state
- Activity "Source Text Analysis with AI" with template workspace
- Enrolled instructor (`instructor@uni.edu`) and student (`student-demo@test.example.edu.au`)
- Student workspace with content, highlights, and comments
- Tags in template workspace: "Translation Analysis" group with 3 tags

Some entries may need to authenticate as different users (instructor vs student) using the same `_authenticate()` pattern from existing scripts.

**Absorbing flight_rules entries (AC6.2):**

The 4 existing entries from `flight_rules.py` map to:
1. `_rule_template_vs_instance` → Workspaces: "I configured tags but students can't see them"
2. `_rule_chip_colours` → Unit Settings: "How do I know if I'm in a template or instance?"
3. `_rule_start_vs_template` → Workspaces: "I clicked Start but wanted the template"
4. `_rule_import_tags` → Tags: "Tag import from another activity shows nothing"

Adapt the content from `flight_rules.py` lines 97-208, but:
- Remove the TODO comments (template-btn testid now exists from Phase 1)
- Add `highlight=["template-btn"]` to screenshots that reference the template button
- Use `guide.step("...", level=3)` instead of `guide.step("...")`

**Testing:**

This is an infrastructure/guide-script task. Verification is operational:
- AC1.1: Generated markdown has `##` domain headings and `###` entry headings
- AC1.2: Each domain section has at least one screenshot
- AC1.3: Problem entries have `**Diagnosis:**` and `**Fix:**` blocks
- AC1.4: Cross-links use relative markdown links (e.g., `[text](instructor-setup.md#anchor)`)
- AC6.2: All 4 flight rule entries appear in the output

**Verification:**
```bash
uvx ty check src/promptgrimoire/docs/scripts/using_promptgrimoire.py
# Expected: no errors

uv run ruff check src/promptgrimoire/docs/scripts/using_promptgrimoire.py
# Expected: no errors

uv run complexipy src/promptgrimoire/docs/scripts/using_promptgrimoire.py
# Expected: no functions > 15
```

**UAT Steps (Phase 2 — after Tasks 1-4 complete):**
1. [ ] Run `uv run grimoire docs build` (requires seeded app server)
2. [ ] Open generated `docs/guides/using-promptgrimoire.md`
3. [ ] Verify `##` domain headings (Getting Started, Workspaces, Tags, etc.)
4. [ ] Verify `###` first-person entry headings ("I want to...", "Why is...?")
5. [ ] Verify each domain section has at least one screenshot
6. [ ] Verify problem/diagnosis entries have **Diagnosis:** and **Fix:** blocks
7. [ ] Verify cross-links use relative markdown links (e.g., `[text](instructor-setup.md#anchor)`)
8. [ ] Verify all 4 absorbed flight-rules entries appear: template vs instance, chip colours, start vs template, import tags
9. [ ] Verify `flight_rules.py` is deleted: `ls src/promptgrimoire/docs/scripts/flight_rules.py` → "No such file"
10. [ ] Verify no dangling references: `grep -r "flight_rules" src/ tests/` → no output
11. [ ] Verify `personal_grimoire.py` uses `g.subheading()` not `g._append("### ...")`

**Commit:** `feat: create using_promptgrimoire.py flight-rules guide script (#230)`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Delete `flight_rules.py` and remove all references

**Verifies:** docs-flight-rules-230.AC6.1, docs-flight-rules-230.AC6.3

**Files:**
- Delete: `src/promptgrimoire/docs/scripts/flight_rules.py`
- Modify: Any file that imports or references `flight_rules` (check with grep)

**Context:**

Read `src/promptgrimoire/docs/scripts/__init__.py` — currently empty, no exports to clean up.
Check `src/promptgrimoire/cli/docs.py` — scripts are imported directly here (lines 71-75).

**Implementation:**

**Step 1: Verify no imports exist**

Search the codebase for any references to `flight_rules`:
```bash
grep -r "flight_rules" src/ tests/
```

The `__init__.py` is empty so there are no exports to remove. If `cli/docs.py` imports `flight_rules`, remove that import. If any test file references `flight_rules`, remove those references.

**Step 2: Delete the file**

```bash
rm src/promptgrimoire/docs/scripts/flight_rules.py
```

**Step 3: Verify no dangling references**

```bash
grep -r "flight_rules" src/ tests/
# Expected: no output
```

**Verification:**
```bash
# Confirm file is deleted
ls src/promptgrimoire/docs/scripts/flight_rules.py
# Expected: No such file or directory

# Confirm no references remain
grep -r "flight_rules" src/ tests/
# Expected: no output

# Type check the scripts package
uvx ty check src/promptgrimoire/docs/scripts/
# Expected: no errors
```

**Commit:** `chore: delete absorbed flight_rules.py (#230)`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->
