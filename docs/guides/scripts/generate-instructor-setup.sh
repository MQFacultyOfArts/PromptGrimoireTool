#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
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
# Navigate to home, start the activity to create a workspace,
# then configure tags via the tag management dialog.
note "## Step 5: Configuring Tags"
note "Tags help students categorise their annotations. Configure tag groups and tags for the activity."

rodney open --local "$BASE_URL"
rodney waitload --local
rodney waitstable --local
# Click "Start" on the unstarted activity to create a workspace
# The testid includes the activity ID, so use prefix match
rodney click --local '[data-testid^="start-activity-btn"]'
rodney waitload --local
rodney waitstable --local
sleep 1  # Allow annotation page to fully render

# Open tag management dialog from the toolbar
rodney click --local '[data-testid="tag-settings-btn"]'
sleep 0.5
rodney waitstable --local

# Add a tag group
rodney click --local '[data-testid="add-tag-group-btn"]'
rodney waitstable --local

# Find the newly created group's header testid via JS
GROUP_HEADER=$(require_js "tag group header after add-tag-group-btn click" \
    'document.querySelector("[data-testid^=\"tag-group-header-\"]")?.getAttribute("data-testid")')
GROUP_ID="${GROUP_HEADER#tag-group-header-}"

# Name the group
rodney click --local "[data-testid=\"group-name-input-${GROUP_ID}\"]"
rodney input --local "[data-testid=\"group-name-input-${GROUP_ID}\"]" 'Translation Analysis'
rodney waitstable --local

# Add first tag to this group
rodney click --local "[data-testid=\"group-add-tag-btn-${GROUP_ID}\"]"
rodney waitstable --local
TAG_INPUT=$(require_js "first tag name input" \
    'document.querySelector("[data-testid^=\"tag-name-input-\"]")?.getAttribute("data-testid")')
rodney click --local "[data-testid=\"${TAG_INPUT}\"]"
rodney input --local "[data-testid=\"${TAG_INPUT}\"]" 'Source Text Features'

# Add second tag
rodney click --local "[data-testid=\"group-add-tag-btn-${GROUP_ID}\"]"
rodney waitstable --local
TAG_INPUT2=$(require_js "second tag name input" \
    '[...document.querySelectorAll("[data-testid^=\"tag-name-input-\"]")].pop()?.getAttribute("data-testid")')
rodney click --local "[data-testid=\"${TAG_INPUT2}\"]"
rodney input --local "[data-testid=\"${TAG_INPUT2}\"]" 'Translation Strategy'

# Add third tag
rodney click --local "[data-testid=\"group-add-tag-btn-${GROUP_ID}\"]"
rodney waitstable --local
TAG_INPUT3=$(require_js "third tag name input" \
    '[...document.querySelectorAll("[data-testid^=\"tag-name-input-\"]")].pop()?.getAttribute("data-testid")')
rodney click --local "[data-testid=\"${TAG_INPUT3}\"]"
rodney input --local "[data-testid=\"${TAG_INPUT3}\"]" 'Cultural Adaptation'

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
(cd "$PROJECT_ROOT" && uv run manage-users create "student-demo@test.example.edu.au" --name "Demo Student") 2>/dev/null || true
(cd "$PROJECT_ROOT" && uv run manage-users enroll "student-demo@test.example.edu.au" "TRAN8034" "S1 2026") 2>/dev/null || true

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
