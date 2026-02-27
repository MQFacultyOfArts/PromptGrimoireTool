# Automated User Documentation — Phase 2: Instructor Setup Guide Script

**Goal:** Replace the stub instructor script with the complete 7-step guide covering unit creation, week/activity setup, tag configuration, and student verification.

**Architecture:** A single bash script (`generate-instructor-setup.sh`) drives the browser via Rodney, captures screenshots, and assembles a Showboat markdown document. A prerequisite task adds missing `data-testid` attributes to UI elements the script interacts with. Tag configuration requires navigating from the courses page to the annotation page (tag management lives on the annotation page toolbar, not the courses page).

**Tech Stack:** Bash, Rodney (CLI browser automation), Showboat (CLI document assembly), NiceGUI (target UI)

**Scope:** Phase 2 of 4 from design plan

**Codebase verified:** 2026-02-27

---

## Acceptance Criteria Coverage

This phase implements and tests:

### user-docs-rodney-showboat-207.AC2: Instructor guide is complete and accurate
- **user-docs-rodney-showboat-207.AC2.1 Success:** Guide starts from empty database and creates unit, week, activity through the UI
- **user-docs-rodney-showboat-207.AC2.2 Success:** Activity tag configuration (groups + tags) is documented with screenshots
- **user-docs-rodney-showboat-207.AC2.3 Success:** Guide includes enrollment instruction (provide list to admin)
- **user-docs-rodney-showboat-207.AC2.4 Success:** Guide verifies student view by re-authenticating as a student

### user-docs-rodney-showboat-207.AC1: CLI entry point works end-to-end (partial)
- **user-docs-rodney-showboat-207.AC1.3 Success:** Both PDFs are produced in `docs/guides/`
- **user-docs-rodney-showboat-207.AC1.6 Failure:** If a script fails mid-way, error output identifies the failing step

---

<!-- START_TASK_1 -->
### Task 1: Add missing `data-testid` attributes to UI elements

**Files:**
- Modify: `src/promptgrimoire/pages/courses.py` (lines 339, 354, 538)
- Modify: `src/promptgrimoire/pages/annotation/css.py` (line 419)
- Modify: `src/promptgrimoire/pages/annotation/tag_management_rows.py` (lines 459, 466)
- Modify: `src/promptgrimoire/pages/navigator/_cards.py` (line 305)

**Implementation:**

The project convention (CLAUDE.md) requires all interactable UI elements to have `data-testid` attributes. Seven elements used by the instructor guide script are missing them. Add each:

1. **"New Unit" button** (`courses.py:339`):
   ```python
   ui.button("New Unit", on_click=lambda: ui.navigate.to("/courses/new")).classes(
       "mb-4"
   ).props('data-testid="new-unit-btn"')
   ```

2. **Course card rows** (`courses.py:354`):
   Add `data-testid` with the course ID to make each card uniquely targetable:
   ```python
   ui.card()
   .classes("w-full cursor-pointer hover:bg-gray-50")
   .on("click", lambda c=course: ui.navigate.to(f"/courses/{c.id}"))
   .props(f'data-testid="course-card-{course.id}"')
   ```

3. **Activity rows** (`courses.py:538`):
   Add `data-testid` to the activity row container:
   ```python
   with ui.row().classes("items-center gap-2").props(
       f'data-testid="activity-row-{act.id}"'
   ):
   ```

4. **Tag toolbar settings icon** (`annotation/css.py:419`):
   ```python
   ui.button(
       icon="settings",
       on_click=on_manage_click,
   ).classes("compact-btn").props(
       'round dense flat color=grey-7 data-testid="tag-settings-btn"',
   ).tooltip("Manage tags")
   ```

5. **Ungrouped "+ Add tag" button** (`tag_management_rows.py:459`):
   ```python
   ui.button(
       "+ Add tag",
       on_click=lambda _e: on_add_tag(None),
   ).props('flat dense data-testid="add-ungrouped-tag-btn"').classes("text-xs ml-8 mt-1")
   ```

6. **"+ Add group" button** (`tag_management_rows.py:466`):
   ```python
   ui.button("+ Add group", on_click=on_add_group).props(
       'flat dense data-testid="add-tag-group-btn"'
   ).classes("text-xs")
   ```

7. **"Start" button on navigator** (`navigator/_cards.py:305`):
   The button needs a unique testid per activity. Check what identifier is available in the rendering context (likely `activity.id` or similar) and add:
   ```python
   ui.button("Start", on_click=_start_activity).props(
       f'flat dense size=sm color=primary data-testid="start-activity-btn"'
   ).classes("navigator-start-btn")
   ```
   If multiple unstarted activities could appear, include the activity ID for uniqueness.

**Verification:**

Run: `uv run test-all`
Expected: All existing tests pass. The testid additions are purely additive.

Run: `uv run ruff check src/promptgrimoire/pages/`
Expected: No lint errors.

**Commit:**

```bash
git add src/promptgrimoire/pages/courses.py src/promptgrimoire/pages/annotation/css.py src/promptgrimoire/pages/annotation/tag_management_rows.py src/promptgrimoire/pages/navigator/_cards.py
git commit -m "chore: add missing data-testid attributes for doc generation scripts"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement full instructor guide script

**Verifies:** user-docs-rodney-showboat-207.AC2.1, user-docs-rodney-showboat-207.AC2.2, user-docs-rodney-showboat-207.AC2.3, user-docs-rodney-showboat-207.AC2.4, user-docs-rodney-showboat-207.AC1.3, user-docs-rodney-showboat-207.AC1.6

**Files:**
- Modify: `docs/guides/scripts/generate-instructor-setup.sh` (replace stub from Phase 1)

**Implementation:**

Replace the Phase 1 stub with the full 7-step instructor guide. The script receives `$BASE_URL` as its first argument and uses helpers from `common.sh`.

**Script structure (all 7 steps):**

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
note "This guide walks through setting up a unit in PromptGrimoire for your class."

# ── Step 1: Login and Navigator ──────────────────────────────────
authenticate_as "instructor@uni.edu"
rodney open --local "$BASE_URL"
rodney waitload --local
rodney waitstable --local
step "01_navigator" "Step 1: The Navigator (Home Page)"
note "After logging in, you see the Navigator. As a new instructor with no units configured, it will be empty."

# ── Step 2: Create Unit ──────────────────────────────────────────
note "## Step 2: Creating a Unit"
note "Navigate to Units and create a new unit for your class."
rodney open --local "$BASE_URL/courses/new"
rodney waitload --local
rodney waitstable --local
rodney input --local '[data-testid="course-code-input"]' 'TRAN8034'
rodney input --local '[data-testid="course-name-input"]' 'Translation Technologies'
rodney input --local '[data-testid="course-semester-input"]' 'S1 2026'
take_screenshot "02a_create_unit_form"
add_image "02a_create_unit_form"
note "Enter the unit code, name, and semester, then click Create."

rodney click --local '[data-testid="create-course-btn"]'
rodney waitload --local
rodney waitstable --local
take_screenshot "02b_unit_created"
add_image "02b_unit_created"
note "After creating the unit, you are taken to the unit detail page."

# ── Step 3: Create Week and Publish ──────────────────────────────
note "## Step 3: Adding a Week"
rodney click --local '[data-testid="add-week-btn"]'
rodney waitload --local
rodney waitstable --local
rodney input --local '[data-testid="week-number-input"]' '3'
rodney input --local '[data-testid="week-title-input"]' 'Source Text Analysis'
rodney click --local '[data-testid="create-week-btn"]'
rodney waitload --local
rodney waitstable --local
note "Create a week by entering the week number and title."

rodney click --local '[data-testid="publish-week-btn"]'
rodney waitstable --local
take_screenshot "03_week_published"
add_image "03_week_published"
note "Publish the week to make it visible to students."

# ── Step 4: Create Activity ──────────────────────────────────────
note "## Step 4: Creating an Activity"
rodney click --local '[data-testid="add-activity-btn"]'
rodney waitload --local
rodney waitstable --local
rodney input --local '[data-testid="activity-title-input"]' 'Source Text Analysis with AI'
rodney input --local '[data-testid="activity-description-input"]' 'Analyse a source text using AI conversation tools, then annotate your conversation in the Grimoire.'
rodney click --local '[data-testid="create-activity-btn"]'
rodney waitload --local
rodney waitstable --local
take_screenshot "04_activity_created"
add_image "04_activity_created"
note "Create an activity within the week. Students will create workspaces from this activity."

# ── Step 5: Configure Tags ───────────────────────────────────────
# Tag management is on the annotation page, not the courses page.
# Navigate to the home page, start the activity to create a workspace,
# then configure tags via the tag management dialog.
note "## Step 5: Configuring Tags"
note "Tags help students categorise their annotations. Configure tag groups and tags for the activity."

rodney open --local "$BASE_URL"
rodney waitload --local
rodney waitstable --local
# Click "Start" on the unstarted activity to create a workspace
rodney click --local '[data-testid="start-activity-btn"]'
rodney waitload --local
rodney waitstable --local
sleep 1  # Allow annotation page to fully render

# Open tag management dialog from the toolbar
rodney click --local '[data-testid="tag-settings-btn"]'
sleep 0.5
rodney waitstable --local

# Add a tag group: "Translation Analysis"
rodney click --local '[data-testid="add-tag-group-btn"]'
rodney waitstable --local
# Find the newly created group's name input and type the group name.
# Since we start from empty, the first group header is the only one.
# Use JS to locate the editable group name field within the new group.
GROUP_HEADER=$(rodney js --local 'document.querySelector("[data-testid^=\"tag-group-header-\"]")?.getAttribute("data-testid")' 2>/dev/null || echo "")
if [ -n "$GROUP_HEADER" ]; then
    GROUP_ID="${GROUP_HEADER#tag-group-header-}"
    # Add tags to this group
    rodney click --local "[data-testid=\"group-add-tag-btn-${GROUP_ID}\"]"
    rodney waitstable --local
    # Find the new tag's name input and fill it
    TAG_INPUT=$(rodney js --local 'document.querySelector("[data-testid^=\"tag-name-input-\"]")?.getAttribute("data-testid")' 2>/dev/null || echo "")
    if [ -n "$TAG_INPUT" ]; then
        rodney click --local "[data-testid=\"${TAG_INPUT}\"]"
        rodney input --local "[data-testid=\"${TAG_INPUT}\"]" 'Source Text Features'
    fi

    # Add more tags to the group (repeat pattern)
    rodney click --local "[data-testid=\"group-add-tag-btn-${GROUP_ID}\"]"
    rodney waitstable --local
    # Find the newest tag input (last one)
    TAG_INPUT2=$(rodney js --local '[...document.querySelectorAll("[data-testid^=\"tag-name-input-\"]")].pop()?.getAttribute("data-testid")' 2>/dev/null || echo "")
    if [ -n "$TAG_INPUT2" ]; then
        rodney click --local "[data-testid=\"${TAG_INPUT2}\"]"
        rodney input --local "[data-testid=\"${TAG_INPUT2}\"]" 'Translation Strategy'
    fi

    # Add third tag
    rodney click --local "[data-testid=\"group-add-tag-btn-${GROUP_ID}\"]"
    rodney waitstable --local
    TAG_INPUT3=$(rodney js --local '[...document.querySelectorAll("[data-testid^=\"tag-name-input-\"]")].pop()?.getAttribute("data-testid")' 2>/dev/null || echo "")
    if [ -n "$TAG_INPUT3" ]; then
        rodney click --local "[data-testid=\"${TAG_INPUT3}\"]"
        rodney input --local "[data-testid=\"${TAG_INPUT3}\"]" 'Cultural Adaptation'
    fi
fi

take_screenshot "05_tags_configured"
add_image "05_tags_configured"
note "Configure tag groups and tags. Students' workspaces will inherit this tag configuration."

# Close the tag management dialog
rodney click --local '[data-testid="tag-management-done-btn"]'
rodney waitstable --local

# ── Step 6: Enrollment Note ──────────────────────────────────────
note "## Step 6: Enrolling Students"
note "Provide your student email list to the PromptGrimoire administrator. They will enrol students in your unit using the management tools. Students will see the unit and its activities on their Navigator after enrolment."

# Programmatically enrol the demo student for verification in step 7.
# manage-users create + enroll both operate on the shared database.
uv run manage-users create "student-demo@test.example.edu.au" --name "Demo Student" 2>/dev/null || true
uv run manage-users enroll "student-demo@test.example.edu.au" "TRAN8034" "S1 2026" 2>/dev/null || true

# ── Step 7: Verify Student View ──────────────────────────────────
note "## Step 7: Verifying the Student View"
note "Re-authenticate as a student to verify the activity is visible."
authenticate_as "student-demo@test.example.edu.au"
rodney open --local "$BASE_URL"
rodney waitload --local
rodney waitstable --local
take_screenshot "07_student_navigator"
add_image "07_student_navigator"
note "The student can see the unit and activity on their Navigator. They can click Start to create a workspace."

echo "✓ Instructor setup guide generated: $DOC_PATH"
```

**Key implementation notes for the executor:**

1. **Tag management flow**: Tags are configured on the annotation page, NOT the courses page. The script navigates to the home page, clicks "Start" on the activity (creating a workspace), then opens the tag management dialog from the annotation toolbar.

2. **Dynamic element IDs**: Tag groups and tags have auto-generated IDs. The script uses `rodney js` to query the DOM for testid values of newly created elements. Since we start from an empty tag configuration, the first group/tag is always the only one (or the last one when adding multiple).

3. **Enrollment**: Step 6 is a text note for the guide. The programmatic enrollment (`manage-users create` + `manage-users enroll`) makes the demo student visible for step 7's verification. The `2>/dev/null || true` suppresses "already exists" warnings on re-runs. **cwd guarantee:** These `uv run` commands require `pyproject.toml` to be findable. The orchestrator in `cli.py` must pass `cwd` pointing to the project root when invoking scripts (see Phase 1, Task 2). Since `uv` walks up directories to find `pyproject.toml`, this works as long as the script inherits a cwd within the project tree.

4. **Wait patterns**: After every `rodney click` or page navigation, use `rodney waitstable --local`. Before dialog interactions, add `sleep 0.5` for NiceGUI dialog animation. Phase 4 will harden these patterns.

5. **Error identification (AC1.6)**: `set -euo pipefail` means the script exits on the first failure. The last echo line serves as a success indicator — if absent from output, the orchestrator knows the script failed. The error will show the failing Rodney command with line number.

6. **Group name editing**: The investigation shows tag group headers have `tag-group-header-{id}` testids. The group name may be edited via a separate input field within the header. The executor should verify the exact interaction pattern — it may require clicking on the group header to reveal an edit field, or the name may be editable inline. Check `tag_management_rows.py` for the group name editing mechanism.

**Testing:**

Verification is operational — this is a bash script with no unit tests:
- AC2.1: Run `uv run make-docs`. Verify `docs/guides/instructor-setup.pdf` contains screenshots of unit creation, week creation, and activity creation.
- AC2.2: Verify the PDF contains a screenshot of the tag management dialog with configured groups and tags.
- AC2.3: Verify the PDF contains the enrollment instruction text.
- AC2.4: Verify the PDF contains a screenshot of the student's navigator showing the activity.
- AC1.3: Verify both PDFs are produced (instructor + student stub).
- AC1.6: Deliberately introduce an error (e.g., wrong testid) and verify the orchestrator reports which script failed.

**Human verification (PDF quality — cannot be automated):**

After running `uv run make-docs`, open `docs/guides/instructor-setup.pdf` and verify:
- Guide reads as coherent instructor instructions (not developer notes)
- Screenshots match the described steps (unit creation, week, activity, tags, student view)
- Tag configuration screenshot (step 5) shows the tag management dialog with groups and tags
- Student navigator screenshot (step 7) shows the activity visible to the enrolled student
- No placeholder text, broken images, or technical artefacts visible

This is a human UAT gate — the executor should present the PDF for review.

**Verification:**

Run: `uv run make-docs`
Expected: Both PDFs produced. `docs/guides/instructor-setup.pdf` has 7+ screenshots and explanatory text for all 7 steps.

Run: `ls -la docs/guides/instructor-setup.pdf docs/guides/student-workflow.pdf`
Expected: Both files exist and are non-empty.

**Commit:**

```bash
git add docs/guides/scripts/generate-instructor-setup.sh
git commit -m "feat: implement full instructor setup guide script (7 steps)"
```
<!-- END_TASK_2 -->
