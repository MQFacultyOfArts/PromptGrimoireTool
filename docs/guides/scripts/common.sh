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
  # Auth callback does ui.navigate.to("/") — a SPA navigation.
  # rodney waitload won't fire for SPA navigations (no browser load event).
  # Instead, wait for the home page element to appear after redirect.
  wait_for '.q-page' "Post-auth redirect for $email"
}

take_screenshot() {
  local name="$1"
  rodney sleep 0.5 --local
  rodney screenshot --local -w 1280 -h 800 "$SCREENSHOT_DIR/${name}.png"
}

note() {
  showboat note "$DOC_PATH" "$1"
}

add_image() {
  local name="$1"
  local caption="${2:-$name}"
  # Use a relative path from the markdown file to the screenshot so Pandoc
  # can resolve the image without relying on --resource-path or absolute paths.
  local rel_dir
  rel_dir=$(realpath --relative-to="$(dirname "$DOC_PATH")" "$SCREENSHOT_DIR")
  showboat note "$DOC_PATH" "![${caption}](${rel_dir}/${name}.png)"
}

step() {
  local name="$1"
  local heading="$2"
  local caption="${3:-$heading}"
  note "## $heading"
  take_screenshot "$name"
  add_image "$name" "$caption"
}

require_js() {
  local desc="$1"
  local js_expr="$2"
  local result
  result=$(rodney js --local "$js_expr")
  if [ -z "$result" ]; then
    echo "ERROR: $desc — JS query returned empty" >&2
    exit 1
  fi
  echo "$result"
}

# Wait for a specific element to appear and become visible.
# On failure, captures an error screenshot and prints context.
wait_for() {
  local selector="$1"
  local context="${2:-$selector}"
  if ! rodney wait --local "$selector"; then
    echo "FAILED waiting for: $context (selector: $selector)" >&2
    rodney screenshot --local -w 1280 -h 800 "$SCREENSHOT_DIR/ERROR_$(date +%s).png" 2>/dev/null || true
    return 1
  fi
}
