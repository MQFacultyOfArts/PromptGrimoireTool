# Personal Grimoire Guide Implementation Plan — Phase 1: Guide Script

**Goal:** Write the `personal_grimoire.py` guide script with all five pedagogical sections, producing narrative markdown and ~11 annotated screenshots.

**Architecture:** Single Python module following the established guide-script pattern from `instructor_setup.py` and `student_workflow.py`. Entry point function called by `make_docs()`, uses Guide DSL context managers for markdown emission and screenshot capture, subprocess helpers for DB seeding, `page.evaluate()` for HTML injection.

**Tech Stack:** Python 3.14, Playwright (sync API), Guide DSL (`promptgrimoire.docs`), `manage-users` CLI via subprocess

**Scope:** Phase 1 of 2 from original design

**Codebase verified:** 2026-03-01

---

## Acceptance Criteria Coverage

This phase implements:

### personal-grimoire-guide-208.AC1: Guide produces structured output
- **personal-grimoire-guide-208.AC1.1 Success:** Guide produces `your-personal-grimoire.md` in `docs/guides/`
- **personal-grimoire-guide-208.AC1.2 Success:** Guide produces ~11 screenshots in `docs/guides/screenshots/` with prefix `your-personal-grimoire-`
- **personal-grimoire-guide-208.AC1.3 Success:** Markdown contains 5 section headings matching the pedagogical arc
- **personal-grimoire-guide-208.AC1.4 Success:** All screenshot image references in the markdown resolve to files that exist on disk

### personal-grimoire-guide-208.AC2: Loose workspace created by enrolled student
- **personal-grimoire-guide-208.AC2.1 Success:** Student is enrolled in UNIT1234 but navigates to `/annotation` and clicks `create-workspace-btn` (bypassing the activity Start button)
- **personal-grimoire-guide-208.AC2.2 Success:** Created workspace has `activity_id=NULL` and `course_id=NULL`
- **personal-grimoire-guide-208.AC2.3 Success:** Navigator shows the workspace in the "Unsorted" section alongside the enrolled unit's activities

### personal-grimoire-guide-208.AC3: Emergent folksonomy — student creates own tags
- **personal-grimoire-guide-208.AC3.1 Success:** Tag management dialog opens on a workspace with zero pre-existing tags
- **personal-grimoire-guide-208.AC3.2 Success:** Student creates a tag group ("My Analysis") and three tags via the tag management dialog
- **personal-grimoire-guide-208.AC3.3 Success:** Created tags appear in the tag toolbar and can be applied to highlights

### personal-grimoire-guide-208.AC4: Placement dialog associates workspace with unit
- **personal-grimoire-guide-208.AC4.1 Success:** Placement dialog opens from the placement chip on the annotation header
- **personal-grimoire-guide-208.AC4.2 Success:** Cascading selects (Unit → Week → Activity) populate with UNIT1234 data
- **personal-grimoire-guide-208.AC4.3 Success:** After confirming placement, workspace is associated with the selected activity
- **personal-grimoire-guide-208.AC4.4 Success:** Student's enrolment in UNIT1234 causes it to appear in the placement dialog (enrolment is a precondition, not an edge case)

---

<!-- START_TASK_1 -->
### Task 1: Create personal_grimoire.py with module structure and setup helpers

**Verifies:** personal-grimoire-guide-208.AC2.1 (enrolled student setup)

**Files:**
- Create: `src/promptgrimoire/docs/scripts/personal_grimoire.py`

**Implementation:**

Create the module with imports, module-level constants, and setup helpers. Follow the pattern from `instructor_setup.py` and `student_workflow.py`.

**Module docstring and imports:**

```python
"""Personal grimoire guide -- produces markdown with annotated screenshots.

Drives a Playwright browser through the loose workspace flow: an enrolled
student chooses to create a personal workspace outside the activity
structure, builds their own tag vocabulary, annotates an AI conversation,
and associates the workspace with a course activity via the placement
dialog. Each section uses the Guide DSL to emit narrative markdown with
highlighted screenshots.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

from promptgrimoire.docs import Guide
from promptgrimoire.docs.helpers import select_chars, wait_for_text_walker

GUIDE_OUTPUT_DIR = Path("docs/guides")
```

**Sample HTML constant** — an AI conversation about cultural markers in Japanese legal text translation. Different from the student workflow guide's content to avoid duplication, but consistent with the UNIT1234 "AI in Professional Practice" domain:

```python
_SAMPLE_HTML = (
    '<div class="conversation">'
    '<div class="user"><p><strong>Human:</strong> I\'m translating a Japanese'
    " contract clause about \u4fe1\u7fa9\u8aa0\u5b9f\u306e\u539f\u5247 (shingi seijitsu no gensoku)."
    " The English term 'good faith' doesn't seem to capture the full"
    " meaning. What cultural factors should I consider?</p></div>"
    '<div class="assistant"><p><strong>Assistant:</strong> You\'ve identified'
    " a significant translation challenge. The Japanese principle of"
    " \u4fe1\u7fa9\u8aa0\u5b9f\u306e\u539f\u5247 carries cultural weight beyond the common law concept"
    " of 'good faith':</p>"
    "<ol>"
    "<li><strong>Relational obligation:</strong> In Japanese legal culture,"
    " this principle reflects an ongoing duty to maintain harmonious"
    " business relationships, not merely honest dealing at the point"
    " of contract.</li>"
    "<li><strong>Contextual interpretation:</strong> Japanese courts apply"
    " this principle more broadly than common law courts apply good faith,"
    " considering social context and the parties' relationship history.</li>"
    "<li><strong>Implied duties:</strong> The principle generates implied"
    " duties of cooperation and disclosure that go further than common"
    " law good faith typically requires.</li>"
    "</ol>"
    "<p>A translator might consider retaining the Japanese term with"
    " an explanatory gloss, or using 'good faith and fair dealing'"
    " with a translator's note explaining the broader scope.</p>"
    "</div></div>"
)
```

Note: The `page.evaluate()` call that uses this constant injects static, hardcoded HTML into a Quasar QEditor contenteditable div. This is the established pattern from `student_workflow.py` (line 123) and `instructor_setup.py` (line 296). Playwright's `fill()` does not support HTML content in contenteditable elements.

**Authenticate helper** (duplicated per script, consistent with existing practice):

```python
def _authenticate(page: Page, base_url: str, email: str) -> None:
    """Authenticate via mock token and wait for redirect."""
    page.goto(f"{base_url}/auth/callback?token=mock-token-{email}")
    page.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10000)
```

**Setup helper** — creates user and enrols in UNIT1234:

```python
def _setup_loose_student() -> None:
    """Create the loose-student user and enrol in UNIT1234."""
    for cmd in [
        [
            "uv", "run", "manage-users", "create",
            "loose-student@test.example.edu.au",
            "--name", "Loose Student",
        ],
        [
            "uv", "run", "manage-users", "enroll",
            "loose-student@test.example.edu.au",
            "UNIT1234", "S1 2026",
        ],
    ]:
        subprocess.run(cmd, capture_output=True, check=False)
```

**Prerequisite guard** — checks for UNIT1234 via Navigator, invokes instructor guide if missing:

```python
def _ensure_instructor_guide_ran(page: Page, base_url: str) -> None:
    """Ensure UNIT1234 exists; run instructor guide if not.

    Authenticates as a temporary user to check the Navigator for the
    unit. If UNIT1234 is not visible, invokes the instructor guide
    to create it. Re-authentication as the guide's own user happens
    in _section_enter_grimoire().
    """
    _setup_loose_student()
    _authenticate(page, base_url, "loose-student@test.example.edu.au")

    # Wait for Navigator to render, then check for UNIT1234.
    # Use wait_for on the start-activity-btn (present when units exist)
    # with a short timeout — if it times out, UNIT1234 is missing.
    try:
        page.locator('[data-testid^="start-activity-btn"]').first.wait_for(
            state="visible", timeout=5000,
        )
        unit_visible = page.locator("text=UNIT1234").count() > 0
    except Exception:
        unit_visible = False

    if not unit_visible:
        from promptgrimoire.docs.scripts.instructor_setup import (
            run_instructor_guide,
        )

        run_instructor_guide(page, base_url)
        # Re-setup the loose student (instructor guide may have reset state)
        _setup_loose_student()
```

**Verification:**

Run: `uv run ruff check src/promptgrimoire/docs/scripts/personal_grimoire.py`
Expected: No lint errors

Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: add personal_grimoire.py module structure and setup helpers`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement Section 1 — Enter the Grimoire

**Verifies:** personal-grimoire-guide-208.AC2.1, personal-grimoire-guide-208.AC2.2, personal-grimoire-guide-208.AC2.3

**Files:**
- Modify: `src/promptgrimoire/docs/scripts/personal_grimoire.py`

**Implementation:**

Add `_section_enter_grimoire()`. The student authenticates, sees the Navigator with enrolled units, then navigates to `/annotation` and clicks "Create Workspace" to create a loose workspace (bypassing the activity Start button). Screenshots: Navigator with enrolled unit visible, annotation page with Create Workspace button, newly created workspace.

```python
def _section_enter_grimoire(
    page: Page, base_url: str, guide: Guide,
) -> None:
    """Section 1: Enter the Grimoire.

    Login as enrolled student, show Navigator, navigate to /annotation,
    create a loose workspace (bypassing activity Start button).
    """
    with guide.step("Enter the Grimoire") as g:
        _authenticate(page, base_url, "loose-student@test.example.edu.au")

        # Navigator: show enrolled unit with Start button
        page.locator('[data-testid^="start-activity-btn"]').first.wait_for(
            state="visible", timeout=10000,
        )
        g.screenshot(
            "Navigator showing your enrolled unit and activities",
            highlight=["start-activity-btn"],
        )
        g.note(
            "After logging in, you see the Navigator with your enrolled "
            "units and activities. Instead of clicking Start on an "
            "activity, you will create your own workspace — your "
            "personal grimoire."
        )

        # Navigate to /annotation directly (bypassing Start button)
        page.goto(f"{base_url}/annotation")
        page.get_by_test_id("create-workspace-btn").wait_for(
            state="visible", timeout=10000,
        )
        g.screenshot(
            "Annotation page with Create Workspace button",
            highlight=["create-workspace-btn"],
        )
        g.note(
            "Navigate to the annotation page directly. The Create "
            "Workspace button lets you start a workspace outside any "
            "activity — a loose workspace that belongs only to you."
        )

        # Create the loose workspace
        page.get_by_test_id("create-workspace-btn").click()
        page.get_by_test_id("content-editor").wait_for(
            state="visible", timeout=15000,
        )
        g.screenshot(
            "Your new loose workspace on the annotation page",
            highlight=["content-editor"],
        )
        g.note(
            "Your workspace is created. Unlike activity-based workspaces, "
            "this one has no inherited tags and no course association. "
            "It is your blank slate — a grimoire waiting to be filled."
        )
```

**Verification:**

Run: `uv run ruff check src/promptgrimoire/docs/scripts/personal_grimoire.py`
Expected: No lint errors

**Commit:** `feat: add Section 1 — Enter the Grimoire`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Implement Section 2 — Bring Your Conversation

**Verifies:** personal-grimoire-guide-208.AC1.3 (section headings)

**Files:**
- Modify: `src/promptgrimoire/docs/scripts/personal_grimoire.py`

**Implementation:**

Add `_section_bring_conversation()`. Paste sample AI conversation via `page.evaluate()` (same pattern as `student_workflow.py`), click "Add Document", confirm content type, wait for text walker. Screenshots: editor with pasted content, processed conversation.

The `page.evaluate()` call injects the module-level `_SAMPLE_HTML` constant — static, hardcoded content — into the QEditor's contenteditable div. This is the established pattern from `student_workflow.py:123` and `instructor_setup.py:296`. Playwright's `fill()` does not support HTML in contenteditable elements.

```python
def _section_bring_conversation(page: Page, guide: Guide) -> None:
    """Section 2: Bring Your Conversation.

    Paste an AI conversation about cultural markers in Japanese legal
    text translation. Confirm content type.
    """
    with guide.step("Bring Your Conversation") as g:
        g.note(
            "Copy an AI conversation that you want to analyse. This could "
            "be from ChatGPT, Claude, or any other tool. Paste it into "
            "the editor to begin building your grimoire."
        )

        # Inject sample HTML into QEditor contenteditable div.
        # Uses .q-editor__content — known exception: Quasar renders this
        # div internally; our code cannot attach a data-testid to it.
        # Static, hardcoded content only (not user-supplied).
        page.evaluate(
            """(html) => {
                const el = document.querySelector(
                    '[data-testid="content-editor"] .q-editor__content'
                );
                el.focus();
                el.innerHTML = html;
                el.dispatchEvent(new Event('input', {bubbles: true}));
            }""",
            _SAMPLE_HTML,
        )
        g.screenshot(
            "AI conversation pasted into the editor",
            highlight=["content-editor"],
        )
        g.note(
            "Paste your AI conversation into the editor. This "
            "conversation about cultural markers in Japanese legal "
            "translation will be the artefact you annotate."
        )

        page.get_by_test_id("add-document-btn").click()

        confirm_btn = page.get_by_test_id("confirm-content-type-btn")
        confirm_btn.wait_for(state="visible", timeout=5000)
        confirm_btn.click()

        wait_for_text_walker(page, timeout=15000)
        g.screenshot("Processed conversation with formatted turns")
        g.note(
            "Your conversation is processed and displayed with formatted "
            "turns. The grimoire now holds your artefact — ready for "
            "annotation."
        )
```

**Verification:**

Run: `uv run ruff check src/promptgrimoire/docs/scripts/personal_grimoire.py`
Expected: No lint errors

**Commit:** `feat: add Section 2 — Bring Your Conversation`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Implement Section 3 — Make Meaning Through Tags

**Verifies:** personal-grimoire-guide-208.AC3.1, personal-grimoire-guide-208.AC3.2, personal-grimoire-guide-208.AC3.3

**Files:**
- Modify: `src/promptgrimoire/docs/scripts/personal_grimoire.py`

**Implementation:**

Add `_section_make_meaning()`. Open the tag management dialog (via `tag-settings-btn`), create a tag group "My Analysis", add three tags ("AI Assumption", "Cultural Gap", "Useful Insight"), close the dialog. Uses the same tag management dialog pattern as `instructor_setup.py:_create_tag_group_and_tags()`. Screenshots: empty tag management dialog, populated tag management dialog with group and tags.

```python
def _section_make_meaning(page: Page, guide: Guide) -> None:
    """Section 3: Make Meaning Through Tags.

    Open tag management, create a tag group and three tags from scratch
    (emergent folksonomy). This section mirrors the instructor guide's
    tag creation but from the student's perspective — no inherited tags.
    """
    with guide.step("Make Meaning Through Tags") as g:
        g.note(
            "Your workspace has no tags — unlike activity-based workspaces "
            "that inherit the instructor's tag vocabulary, your grimoire "
            "starts empty. You build your own analytical vocabulary: an "
            "emergent folksonomy that reflects how you see the conversation."
        )

        # Open tag management dialog
        page.get_by_test_id("tag-settings-btn").click()
        page.get_by_test_id("add-tag-group-btn").wait_for(
            state="visible", timeout=5000,
        )
        g.screenshot(
            "Tag management dialog with no existing tags",
            highlight=["add-tag-group-btn"],
        )
        g.note(
            "Open the tag settings to create your own tags. The dialog "
            "is empty — you are starting from scratch."
        )

        # Create tag group "My Analysis"
        page.get_by_test_id("add-tag-group-btn").click()
        page.wait_for_timeout(1000)

        group_header = page.locator(
            '[data-testid^="tag-group-header-"]'
        ).first
        group_header.wait_for(state="visible", timeout=5000)
        testid = group_header.get_attribute("data-testid") or ""
        group_id = testid.removeprefix("tag-group-header-")

        page.get_by_test_id(f"group-name-input-{group_id}").click()
        page.get_by_test_id(f"group-name-input-{group_id}").fill(
            "My Analysis"
        )
        # Commit the value by pressing Tab (triggers blur/change event)
        page.keyboard.press("Tab")
        page.wait_for_timeout(500)

        # Add three tags
        for tag_name in ["AI Assumption", "Cultural Gap", "Useful Insight"]:
            page.get_by_test_id(f"group-add-tag-btn-{group_id}").click()
            page.wait_for_timeout(1000)
            last_input = page.locator(
                '[data-testid^="tag-name-input-"]'
            ).last
            last_input.click()
            last_input.fill(tag_name)

        g.screenshot(
            "Tag group 'My Analysis' with three student-created tags",
            highlight=["add-tag-group-btn"],
        )
        g.note(
            "Create a tag group and tags that make sense for your "
            "analysis. These tags — 'AI Assumption', 'Cultural Gap', "
            "and 'Useful Insight' — reflect the student's own "
            "analytical categories, not the instructor's."
        )

        # Close tag management dialog
        page.get_by_test_id("tag-management-done-btn").click()
        page.wait_for_timeout(1000)
```

**Verification:**

Run: `uv run ruff check src/promptgrimoire/docs/scripts/personal_grimoire.py`
Expected: No lint errors

**Commit:** `feat: add Section 3 — Make Meaning Through Tags`

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Implement Section 4 — Annotate and Reflect

**Verifies:** personal-grimoire-guide-208.AC3.3 (tags applied to highlights), personal-grimoire-guide-208.AC1.3 (section headings)

**Files:**
- Modify: `src/promptgrimoire/docs/scripts/personal_grimoire.py`

**Implementation:**

Add `_section_annotate_and_reflect()`. Highlight text, apply a tag, add a comment, switch to Organise tab. Uses `select_chars()` from `promptgrimoire.docs.helpers`. Screenshots: text highlighted with tag, comment added, organise view.

```python
def _section_annotate_and_reflect(page: Page, guide: Guide) -> None:
    """Section 4: Annotate and Reflect.

    Highlight text, apply a tag, add a comment, view Organise tab.
    """
    with guide.step("Annotate and Reflect") as g:
        g.note(
            "With your tags ready, read through the conversation and "
            "annotate the parts that matter. Each highlight is a claim "
            "about the text — a moment where you assert that this "
            "passage is significant and why."
        )

        # Select text and apply first tag
        select_chars(page, 0, 50)
        page.wait_for_timeout(500)

        tag_button = page.locator(
            "[data-testid='tag-toolbar'] button"
        ).first
        tag_button.wait_for(state="visible", timeout=5000)
        tag_button.click()
        page.locator("[data-testid='annotation-card']").first.wait_for(
            state="visible", timeout=5000,
        )

        g.screenshot(
            "Text highlighted and tagged with your own category",
            highlight=["tag-toolbar", "annotation-card"],
        )
        g.note(
            "Select text and click a tag to create a highlight. "
            "Your tags — not the instructor's — categorise the "
            "annotation."
        )

        # Add a comment
        card = page.locator("[data-testid='annotation-card']").first
        comment_input = card.get_by_test_id("comment-input")
        comment_input.fill(
            "The AI assumes 'good faith' is a direct equivalent, "
            "but the Japanese concept carries relational obligations "
            "that common law lacks."
        )
        card.get_by_test_id("post-comment-btn").click()
        page.wait_for_timeout(1000)

        g.screenshot(
            "Comment reflecting on the AI's cultural assumption",
            highlight=["comment-input"],
        )
        g.note(
            "Add a comment explaining your annotation. This is where "
            "reflection happens — you are not just marking text, you "
            "are articulating why it matters."
        )

        # Organise tab
        page.get_by_test_id("tab-organise").click()
        page.get_by_test_id("organise-columns").wait_for(
            state="visible", timeout=10000,
        )
        page.wait_for_timeout(1000)

        g.screenshot(
            "Organise tab showing highlights grouped by your tags",
            highlight=["organise-columns"],
        )
        g.note(
            "The Organise tab groups your highlights by tag. Your "
            "emergent vocabulary becomes a lens for seeing patterns "
            "across the conversation."
        )
```

**Verification:**

Run: `uv run ruff check src/promptgrimoire/docs/scripts/personal_grimoire.py`
Expected: No lint errors

**Commit:** `feat: add Section 4 — Annotate and Reflect`

<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Implement Section 5 — Connect to Your Unit

**Verifies:** personal-grimoire-guide-208.AC4.1, personal-grimoire-guide-208.AC4.2, personal-grimoire-guide-208.AC4.3, personal-grimoire-guide-208.AC4.4

**Files:**
- Modify: `src/promptgrimoire/docs/scripts/personal_grimoire.py`

**Implementation:**

Add `_section_connect_to_unit()`. Switch back to Annotate tab, click the placement chip to open the placement dialog, select "Place in Activity" mode, cascade through Unit -> Week -> Activity selects using UNIT1234 data, confirm placement. Screenshots: placement dialog with mode selection, cascading selects populated, confirmed placement.

```python
def _section_connect_to_unit(page: Page, guide: Guide) -> None:
    """Section 5: Connect to Your Unit.

    Open the placement dialog, select UNIT1234 activity via cascading
    selects, confirm placement.
    """
    with guide.step("Connect to Your Unit") as g:
        g.note(
            "Your grimoire has grown from a blank slate into a structured "
            "analysis. Now you can connect it to your unit — associating "
            "your personal work with the course activity so your "
            "instructor can see it alongside the class work."
        )

        # Switch back to Annotate tab
        page.get_by_test_id("tab-annotate").click()
        page.wait_for_timeout(1000)

        # Open placement dialog via placement chip
        page.get_by_test_id("placement-chip").click()
        page.get_by_test_id("placement-mode").wait_for(
            state="visible", timeout=5000,
        )
        g.screenshot(
            "Placement dialog for associating workspace with a unit",
            highlight=["placement-mode"],
        )
        g.note(
            "Click the placement chip in the header to open the "
            "placement dialog. Your enrolled units appear in the "
            "cascading selects because you are already enrolled."
        )

        # Select "Place in Activity" mode
        page.locator(
            '[data-testid="placement-mode"]'
            ' label:has-text("Place in Activity")'
        ).click()
        page.wait_for_timeout(500)

        # Select unit from the course dropdown
        course_select = page.get_by_test_id("placement-course")
        course_select.wait_for(state="visible", timeout=5000)
        course_select.click()

        # Click the UNIT1234 option in the dropdown
        page.locator(
            '.q-menu .q-item:has-text("UNIT1234")'
        ).first.wait_for(state="visible", timeout=5000)
        page.locator(
            '.q-menu .q-item:has-text("UNIT1234")'
        ).first.click()
        page.wait_for_timeout(1000)

        # Select week
        week_select = page.get_by_test_id("placement-week")
        week_select.click()
        page.locator(".q-menu .q-item").first.wait_for(
            state="visible", timeout=5000,
        )
        page.locator(".q-menu .q-item").first.click()
        page.wait_for_timeout(1000)

        # Select activity
        activity_select = page.get_by_test_id("placement-activity")
        activity_select.click()
        page.locator(".q-menu .q-item").first.wait_for(
            state="visible", timeout=5000,
        )
        page.locator(".q-menu .q-item").first.click()
        page.wait_for_timeout(500)

        g.screenshot(
            "Cascading selects with UNIT1234, week, and activity selected",
            highlight=[
                "placement-course",
                "placement-week",
                "placement-activity",
            ],
        )
        g.note(
            "Select your unit, week, and activity from the cascading "
            "dropdowns. Your enrolment in UNIT1234 makes it available "
            "in the placement dialog."
        )

        # Confirm placement
        page.get_by_test_id("placement-confirm-btn").click()
        page.wait_for_timeout(2000)

        g.screenshot("Workspace now associated with the course activity")
        g.note(
            "Your personal grimoire is now connected to the course "
            "activity. It appears alongside other students' work in "
            "the unit, while retaining your personal tag vocabulary "
            "and annotations."
        )
```

**Verification:**

Run: `uv run ruff check src/promptgrimoire/docs/scripts/personal_grimoire.py`
Expected: No lint errors

**Commit:** `feat: add Section 5 — Connect to Your Unit`

<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Implement entry point and wire all sections

**Verifies:** personal-grimoire-guide-208.AC1.1, personal-grimoire-guide-208.AC1.2, personal-grimoire-guide-208.AC1.3, personal-grimoire-guide-208.AC1.4

**Files:**
- Modify: `src/promptgrimoire/docs/scripts/personal_grimoire.py`

**Implementation:**

Add the main entry point `run_personal_grimoire_guide()` that calls `_ensure_instructor_guide_ran()` then wraps all five sections in a `Guide` context manager.

```python
def run_personal_grimoire_guide(page: Page, base_url: str) -> None:
    """Run the personal grimoire guide, producing markdown and screenshots."""
    _ensure_instructor_guide_ran(page, base_url)

    with Guide("Your Personal Grimoire", GUIDE_OUTPUT_DIR, page) as guide:
        _section_enter_grimoire(page, base_url, guide)
        _section_bring_conversation(page, guide)
        _section_make_meaning(page, guide)
        _section_annotate_and_reflect(page, guide)
        _section_connect_to_unit(page, guide)
```

The `Guide("Your Personal Grimoire", ...)` title will produce slug `your-personal-grimoire`, generating:
- `docs/guides/your-personal-grimoire.md`
- `docs/guides/screenshots/your-personal-grimoire-01.png` through `your-personal-grimoire-NN.png`

Each `guide.step(heading)` call emits a markdown section heading (`## heading`) in the output file. The five section headings ("Enter the Grimoire", "Bring Your Conversation", "Make Meaning Through Tags", "Annotate and Reflect", "Connect to Your Unit") satisfy AC1.3's requirement for 5 section headings matching the pedagogical arc.

**Verification:**

Run: `uv run ruff check src/promptgrimoire/docs/scripts/personal_grimoire.py`
Expected: No lint errors

Run: `uvx ty check`
Expected: No type errors

**Commit:** `feat: wire entry point for personal grimoire guide`

<!-- END_TASK_7 -->
