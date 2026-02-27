#!/bin/bash
# Common helpers for documentation generation scripts.
# Sourced by generate-*.sh scripts — not executed directly.
#
# Expects the following variables to be set before sourcing:
#   BASE_URL       — NiceGUI server URL (e.g. http://localhost:8123)
#   DOC_PATH       — output Markdown file path
#   SCREENSHOT_DIR — directory for screenshots

set -euo pipefail

authenticate_as() {
  local email="$1"
  rodney open --local "$BASE_URL/auth/callback?token=mock-token-${email}"
  rodney waitload --local
  # Wait for redirect away from /auth/callback
  sleep 1
  rodney waitstable --local
}

take_screenshot() {
  local name="$1"
  rodney waitstable --local
  rodney screenshot --local -w 1280 -h 800 "$SCREENSHOT_DIR/${name}.png"
}

note() {
  showboat note "$DOC_PATH" "$1"
}

add_image() {
  local name="$1"
  showboat image "$DOC_PATH" "$SCREENSHOT_DIR/${name}.png"
}

step() {
  local name="$1"
  local text="$2"
  note "## $text"
  take_screenshot "$name"
  add_image "$name"
}
