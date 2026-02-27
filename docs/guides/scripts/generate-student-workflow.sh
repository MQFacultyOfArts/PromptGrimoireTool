#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
BASE_URL="$1"
GUIDE_DIR="$(dirname "$SCRIPT_DIR")"
DOC_PATH="$GUIDE_DIR/student-workflow.md"
SCREENSHOT_DIR="$GUIDE_DIR/screenshots/student"

source "$SCRIPT_DIR/common.sh"

mkdir -p "$SCREENSHOT_DIR"

showboat init "$DOC_PATH" "Student Workflow Guide"
note "This guide walks through the student annotation workflow in PromptGrimoire."

# ── Step 1: Login ────────────────────────────────────────────────
authenticate_as "student-demo@test.example.edu.au"
rodney open --local "$BASE_URL"
rodney waitload --local
rodney waitstable --local
step "01_login" "Step 1: Logging In"
note "After logging in, you see the Navigator — your home page. Activities assigned by your instructor appear here."

# ── Step 2: Navigate to Activity ─────────────────────────────────
note "## Step 2: Finding Your Activity"
note "The Navigator shows activities available to you. Find the activity your instructor created."
take_screenshot "02_navigator_activity"
add_image "02_navigator_activity"
note "You can see the unit and activity on your Navigator."

# ── Step 3: Create Workspace ─────────────────────────────────────
note "## Step 3: Creating a Workspace"
note "Click Start on the activity to create your workspace. The workspace inherits the tag configuration set by your instructor."
# The testid includes the activity ID, so use prefix match
rodney click --local '[data-testid^="start-activity-btn"]'
rodney waitload --local
rodney waitstable --local
sleep 1  # Allow annotation page to fully render
take_screenshot "03_workspace_created"
add_image "03_workspace_created"
note "Your workspace is created. You are now on the annotation page with three tabs: Annotate, Organise, and Respond."

# ── Step 4: Paste AI Conversation ────────────────────────────────
note "## Step 4: Pasting Your AI Conversation"
note "Copy your AI conversation from ChatGPT, Claude, or another tool. Then paste it into the editor."

# Click the content editor to focus it
rodney click --local '[data-testid="content-editor"]'
rodney waitstable --local

# Simulate HTML paste using JS clipboard API
# This mirrors the E2E test pattern from test_html_paste_whitespace.py
SAMPLE_HTML='<div class="conversation"><div class="user"><p><strong>Human:</strong> What are the key challenges in translating legal documents between English and Japanese?</p></div><div class="assistant"><p><strong>Assistant:</strong> Legal translation between English and Japanese faces several key challenges:</p><ol><li><strong>Structural differences:</strong> Japanese legal writing uses longer sentences with nested clauses, while English prefers shorter, more direct constructions.</li><li><strong>Terminology gaps:</strong> Some legal concepts exist in one system but not the other. For example, the Japanese concept of <em>good faith</em> (信義誠実) has nuances that differ from common law interpretations.</li><li><strong>Formality registers:</strong> Japanese legal language uses highly formal registers (です/ます or である style) that have no direct English equivalent.</li></ol></div></div>'

# Escape backticks in the HTML so they don't break the JS template literal
ESCAPED_HTML=$(printf '%s' "$SAMPLE_HTML" | sed 's/`/\\`/g')

rodney js --local "
  const html = \`${ESCAPED_HTML}\`;
  const plain = html.replace(/<[^>]*>/g, '');
  await navigator.clipboard.write([
    new ClipboardItem({
      'text/html': new Blob([html], { type: 'text/html' }),
      'text/plain': new Blob([plain], { type: 'text/plain' })
    })
  ]);
"
rodney key --local "Control+v"
sleep 1
rodney waitstable --local
take_screenshot "04_content_pasted"
add_image "04_content_pasted"
note "After pasting, your conversation appears in the editor. PromptGrimoire automatically detects the conversation format."

# ── Step 5: Create Highlight and Assign Tag ──────────────────────
note "## Step 5: Annotating — Creating a Highlight"
note "Select text in the conversation to highlight it. A tag menu appears so you can categorise the highlight."

# Use JS to create a text selection in the document container.
# The annotation page listens for selectionchange events and shows
# the highlight menu when text is selected.
# First verify the doc container and text content exist.
require_js "doc container with text content" \
    'document.querySelector("#doc-container p")?.textContent ? "ok" : ""'

rodney js --local "
  const container = document.querySelector('#doc-container');
  const textNode = container.querySelector('p').firstChild;
  const range = document.createRange();
  range.setStart(textNode, 0);
  range.setEnd(textNode, Math.min(textNode.length, 50));
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  document.dispatchEvent(new Event('selectionchange'));
"
sleep 1
rodney waitstable --local

# Verify highlight menu appeared, then click the first tag button
require_js "highlight menu visible with tag buttons" \
    'document.querySelector("[data-testid=\"highlight-menu\"] button") ? "ok" : ""'

rodney js --local "
  document.querySelector('[data-testid=\"highlight-menu\"] button').click();
"
sleep 1
rodney waitstable --local
take_screenshot "05_highlight_created"
add_image "05_highlight_created"
note "Select text and click a tag in the popup menu to create a highlight. The text is colour-coded by tag."

# ── Step 6: Add Comment to Highlight ─────────────────────────────
note "## Step 6: Adding a Comment"
note "Click on a highlighted section to select it, then type a comment in the sidebar."

# Click on the comment input and type a comment
COMMENT_INPUT='[data-testid="comment-input"]'
rodney click --local "$COMMENT_INPUT"
rodney waitstable --local
rodney input --local "$COMMENT_INPUT" 'This passage highlights key structural differences between legal writing traditions.'
# Press Enter to submit the comment
rodney key --local "Enter"
sleep 0.5
rodney waitstable --local
take_screenshot "06_comment_added"
add_image "06_comment_added"
note "Comments appear below each highlight in the sidebar. Use comments to record your analysis."

# ── Step 7: Organise Tab ─────────────────────────────────────────
note "## Step 7: Organising by Tag"
note "Switch to the Organise tab to view your annotations grouped by tag."
rodney click --local '[data-testid="tab-organise"]'
rodney waitload --local
rodney waitstable --local
sleep 0.5
take_screenshot "07_organise_tab"
add_image "07_organise_tab"
note "The Organise tab shows your highlights in columns by tag. You can drag highlights between columns to reclassify them."

# ── Step 8: Respond Tab ──────────────────────────────────────────
note "## Step 8: Writing Your Response"
note "Switch to the Respond tab to write your analysis. Your highlights appear in the reference panel on the right."
rodney click --local '[data-testid="tab-respond"]'
rodney waitload --local
rodney waitstable --local
sleep 1  # Allow Milkdown editor to initialise

# Focus the Milkdown editor and type some content.
# Milkdown renders inside a contenteditable div within the container.
rodney js --local "
  const editor = document.querySelector('[data-testid=\"milkdown-editor-container\"] [contenteditable]');
  if (editor) {
    editor.focus();
  }
"
sleep 0.5
# Use rodney input (real keyboard events via CDP) — NOT rodney key
rodney input --local '[data-testid="milkdown-editor-container"] [contenteditable]' 'This analysis examines the translation challenges identified in the AI conversation. The key structural differences between English and Japanese legal writing highlight the importance of understanding both legal systems.'
rodney waitstable --local
take_screenshot "08_respond_tab"
add_image "08_respond_tab"
note "The Respond tab has a markdown editor on the left and your highlights as reference on the right. Write your analysis using the highlights as evidence."

# ── Step 9: Export PDF ───────────────────────────────────────────
note "## Step 9: Exporting to PDF"
note "Click Export PDF to generate a PDF of your complete annotation work."
rodney click --local '[data-testid="export-pdf-btn"]'
sleep 3  # Allow PDF generation to complete
rodney waitstable --local
take_screenshot "09_export"
add_image "09_export"
note "The exported PDF includes your pasted conversation with highlights, comments, organised notes, and your written response."

echo "✓ Student workflow guide generated: $DOC_PATH"
