#!/bin/bash
# Debug script: runs instructor setup rodney commands one at a time.
# Usage: bash docs/guides/scripts/debug-instructor.sh <BASE_URL>
# Requires: rodney already started (rodney start --local), server already running.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BASE_URL="$1"
SCREENSHOT_DIR="$(dirname "$SCRIPT_DIR")/screenshots/instructor"
export ROD_TIMEOUT=15

mkdir -p "$SCREENSHOT_DIR"

step=0
run() {
  step=$((step + 1))
  echo "--- step $step: $1"
  shift
  if "$@"; then
    echo "    ok"
  else
    local rc=$?
    echo "    FAILED (exit $rc)"
    rodney screenshot --local -w 1280 -h 800 "$SCREENSHOT_DIR/FAIL_step${step}.png" 2>/dev/null || true
    echo "    Screenshot: $SCREENSHOT_DIR/FAIL_step${step}.png"
    exit $rc
  fi
}

js_check() {
  local desc="$1"
  local expr="$2"
  echo "--- js: $desc"
  local result
  result=$(rodney js --local "$expr" 2>&1) || true
  echo "    => $result"
  echo "$result"
}

# Step 1: Login
run "auth instructor" rodney open --local "$BASE_URL/auth/callback?token=mock-token-instructor@uni.edu"
run "wait .q-page" rodney wait --local ".q-page"
run "screenshot nav" rodney screenshot --local -w 1280 -h 800 "$SCREENSHOT_DIR/d01_nav.png"

# Step 2: Create Unit
run "open /courses/new" rodney open --local "$BASE_URL/courses/new"
run "wait course-code-input" rodney wait --local '[data-testid="course-code-input"]'
run "input code" rodney input --local '[data-testid="course-code-input"]' 'TRAN8034'
run "input name" rodney input --local '[data-testid="course-name-input"]' 'Translation Technologies'
run "input semester" rodney input --local '[data-testid="course-semester-input"]' 'S1 2026'
run "click create" rodney click --local '[data-testid="create-course-btn"]'
run "wait add-week-btn" rodney wait --local '[data-testid="add-week-btn"]'

# Step 3: Create Week and Publish
run "click add-week" rodney click --local '[data-testid="add-week-btn"]'
run "wait week-number" rodney wait --local '[data-testid="week-number-input"]'
run "input week#" rodney input --local '[data-testid="week-number-input"]' '3'
run "input week title" rodney input --local '[data-testid="week-title-input"]' 'Source Text Analysis'
run "click create-week" rodney click --local '[data-testid="create-week-btn"]'
run "wait publish-btn" rodney wait --local '[data-testid="publish-week-btn"]'
run "click publish" rodney click --local '[data-testid="publish-week-btn"]'
run "sleep 1" rodney sleep 1 --local

# Step 4: Create Activity
run "click add-activity" rodney click --local '[data-testid="add-activity-btn"]'
run "wait activity-title" rodney wait --local '[data-testid="activity-title-input"]'
run "input activity title" rodney input --local '[data-testid="activity-title-input"]' 'Source Text Analysis with AI'
run "input activity desc" rodney input --local '[data-testid="activity-description-input"]' 'Analyse a source text.'
run "click create-activity" rodney click --local '[data-testid="create-activity-btn"]'
run "sleep 1" rodney sleep 1 --local

# Enrol instructor
echo "--- enrolling instructor..."
(cd "$PROJECT_ROOT" && uv run manage-users enroll "instructor@uni.edu" "TRAN8034" "S1 2026") 2>&1 || true
echo "    done"

# Step 5: Navigate home, click Start
run "open home" rodney open --local "$BASE_URL"
run "wait .q-page" rodney wait --local ".q-page"
run "sleep 2 for render" rodney sleep 2 --local

# Diagnostic: what does the page look like?
run "screenshot before-start" rodney screenshot --local -w 1280 -h 800 "$SCREENSHOT_DIR/d05_before_start.png"

# Check if start button exists
FOUND=$(js_check "start-activity-btn exists?" \
  'document.querySelector("[data-testid^=\"start-activity-btn\"]")?.getAttribute("data-testid") || "NOT_FOUND"')
echo "    start-activity-btn result: $FOUND"

if [ "$FOUND" = "NOT_FOUND" ]; then
  echo ""
  echo "=== DIAGNOSIS: start-activity-btn not found on navigator ==="
  # Check what IS on the page
  js_check "page title" 'document.title'
  js_check "q-page exists?" 'document.querySelector(".q-page") ? "yes" : "no"'
  js_check "any buttons?" 'JSON.stringify([...document.querySelectorAll("button")].map(b => b.textContent?.trim()).filter(Boolean).slice(0, 10))'
  js_check "any data-testid?" 'JSON.stringify([...document.querySelectorAll("[data-testid]")].map(e => e.getAttribute("data-testid")).slice(0, 20))'
  echo "    Check screenshot: $SCREENSHOT_DIR/d05_before_start.png"
  exit 1
fi

run "click start" rodney click --local '[data-testid^="start-activity-btn"]'
run "wait content-editor" rodney wait --local '[data-testid="content-editor"]'

# Tag management
run "click tag-settings" rodney click --local '[data-testid="tag-settings-btn"]'
run "wait add-tag-group" rodney wait --local '[data-testid="add-tag-group-btn"]'
run "click add-tag-group" rodney click --local '[data-testid="add-tag-group-btn"]'
run "sleep 1" rodney sleep 1 --local

GROUP_HEADER=$(js_check "tag group header" \
  'document.querySelector("[data-testid^=\"tag-group-header-\"]")?.getAttribute("data-testid")')
if [ -z "$GROUP_HEADER" ]; then
  echo "    FAILED: no group header"
  exit 1
fi
GROUP_ID="${GROUP_HEADER#tag-group-header-}"
echo "    GROUP_ID=$GROUP_ID"

run "click group-name-input" rodney click --local "[data-testid=\"group-name-input-${GROUP_ID}\"]"
run "input group name" rodney input --local "[data-testid=\"group-name-input-${GROUP_ID}\"]" 'Translation Analysis'
run "sleep 0.5" rodney sleep 0.5 --local

# Tag 1
run "click add-tag-1" rodney click --local "[data-testid=\"group-add-tag-btn-${GROUP_ID}\"]"
run "sleep 1" rodney sleep 1 --local
TAG1=$(js_check "tag input 1" \
  'document.querySelector("[data-testid^=\"tag-name-input-\"]")?.getAttribute("data-testid")')
run "click tag1" rodney click --local "[data-testid=\"${TAG1}\"]"
run "input tag1" rodney input --local "[data-testid=\"${TAG1}\"]" 'Source Text Features'

# Tag 2
run "click add-tag-2" rodney click --local "[data-testid=\"group-add-tag-btn-${GROUP_ID}\"]"
run "sleep 1" rodney sleep 1 --local
TAG2=$(js_check "tag input 2" \
  '[...document.querySelectorAll("[data-testid^=\"tag-name-input-\"]")].pop()?.getAttribute("data-testid")')
run "click tag2" rodney click --local "[data-testid=\"${TAG2}\"]"
run "input tag2" rodney input --local "[data-testid=\"${TAG2}\"]" 'Translation Strategy'

# Tag 3
run "click add-tag-3" rodney click --local "[data-testid=\"group-add-tag-btn-${GROUP_ID}\"]"
run "sleep 1" rodney sleep 1 --local
TAG3=$(js_check "tag input 3" \
  '[...document.querySelectorAll("[data-testid^=\"tag-name-input-\"]")].pop()?.getAttribute("data-testid")')
run "click tag3" rodney click --local "[data-testid=\"${TAG3}\"]"
run "input tag3" rodney input --local "[data-testid=\"${TAG3}\"]" 'Cultural Adaptation'

run "click done" rodney click --local '[data-testid="tag-management-done-btn"]'
run "sleep 1" rodney sleep 1 --local

# Step 6+7: Student enrol & verify
echo "--- creating & enrolling student..."
(cd "$PROJECT_ROOT" && uv run manage-users create "student-demo@test.example.edu.au" --name "Demo Student") 2>&1 || true
(cd "$PROJECT_ROOT" && uv run manage-users enroll "student-demo@test.example.edu.au" "TRAN8034" "S1 2026") 2>&1 || true
echo "    done"

run "auth student" rodney open --local "$BASE_URL/auth/callback?token=mock-token-student-demo@test.example.edu.au"
run "wait .q-page" rodney wait --local ".q-page"
run "screenshot student nav" rodney screenshot --local -w 1280 -h 800 "$SCREENSHOT_DIR/d07_student.png"

echo ""
echo "✓ All instructor steps passed!"
