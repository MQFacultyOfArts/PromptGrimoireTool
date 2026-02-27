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
note "This guide walks through setting up a unit in PromptGrimoire."

authenticate_as "instructor@uni.edu"
step "01_navigator" "Step 1: The Navigator (Home Page)"

echo "✓ Instructor setup guide generated: $DOC_PATH"
