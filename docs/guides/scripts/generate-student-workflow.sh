#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_URL="$1"
GUIDE_DIR="$(dirname "$SCRIPT_DIR")"
DOC_PATH="$GUIDE_DIR/student-workflow.md"
SCREENSHOT_DIR="$GUIDE_DIR/screenshots/student"

source "$SCRIPT_DIR/common.sh"

mkdir -p "$SCREENSHOT_DIR"

showboat init "$DOC_PATH" "Student Workflow Guide"
note "This guide walks through using PromptGrimoire for annotation."

authenticate_as "student-demo@test.example.edu.au"
step "01_login" "Step 1: Logging In"

echo "✓ Student workflow guide generated: $DOC_PATH"
