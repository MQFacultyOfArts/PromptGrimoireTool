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

# Clean previous run artifacts so the script is re-runnable
rm -f "$DOC_PATH"
rm -rf "$SCREENSHOT_DIR"
mkdir -p "$SCREENSHOT_DIR"

showboat init "$DOC_PATH" "Student Workflow Guide"
note "This guide walks through the student annotation workflow in PromptGrimoire."

# ── Step 1: Login ────────────────────────────────────────────────
authenticate_as "student-demo@test.example.edu.au"
wait_for '.q-page' 'Navigator after login'
step "01_login" "Step 1: Logging In"
note "After logging in, you see the Navigator — your home page. Activities assigned by your instructor appear here."

# ── Step 2: Navigate to Activity ─────────────────────────────────
note "## Step 2: Finding Your Activity"
note "The Navigator shows activities available to you. Find the activity your instructor created."
take_screenshot "02_navigator_activity"
add_image "02_navigator_activity" "Navigator showing the unit and activity"
note "You can see the unit and activity on your Navigator."

# ── Step 3: Create Workspace ─────────────────────────────────────
note "## Step 3: Creating a Workspace"
note "Click Start on the activity to create your workspace. The workspace inherits the tag configuration set by your instructor."
# The testid includes the activity ID, so use prefix match
rodney click --local '[data-testid^="start-activity-btn"]'
wait_for '[data-testid="content-editor"]' 'Annotation page loaded'
take_screenshot "03_workspace_created"
add_image "03_workspace_created" "New workspace on the annotation page"
note "Your workspace is created. You are now on the annotation page with three tabs: Annotate, Organise, and Respond."

# ── Step 4: Paste AI Conversation ────────────────────────────────
note "## Step 4: Pasting Your AI Conversation"
note "Copy your AI conversation from ChatGPT, Claude, or another tool. Then paste it into the editor."

# Insert sample content into the Quasar editor via JS.
# rodney has no keyboard command, so we set innerHTML directly on the
# contenteditable element and use the Add Document button flow.
SAMPLE_HTML='<div class="conversation"><div class="user"><p><strong>Human:</strong> What are the key challenges in translating legal documents between English and Japanese?</p></div><div class="assistant"><p><strong>Assistant:</strong> Legal translation between English and Japanese faces several key challenges:</p><ol><li><strong>Structural differences:</strong> Japanese legal writing uses longer sentences with nested clauses, while English prefers shorter, more direct constructions.</li><li><strong>Terminology gaps:</strong> Some legal concepts exist in one system but not the other. For example, the Japanese concept of <em>good faith</em> (信義誠実) has nuances that differ from common law interpretations.</li><li><strong>Formality registers:</strong> Japanese legal language uses highly formal registers (です/ます or である style) that have no direct English equivalent.</li></ol></div></div>'
ESCAPED_HTML=$(printf '%s' "$SAMPLE_HTML" | sed "s/'/\\\\'/g")

rodney js --local "(() => { let el = document.querySelector('[data-testid=\"content-editor\"] .q-editor__content'); el.focus(); el.innerHTML = '${ESCAPED_HTML}'; el.dispatchEvent(new Event('input', {bubbles: true})); return 'done'; })()"
take_screenshot "04a_content_pasted"
add_image "04a_content_pasted" "AI conversation pasted into the editor"
note "Paste your AI conversation into the editor. PromptGrimoire accepts content from ChatGPT, Claude, and other tools."

# Click Add Document to process the pasted content through the input pipeline
rodney click --local '[data-testid="add-document-btn"]'
wait_for '[data-testid="confirm-content-type-btn"]' 'Content type confirmation'
take_screenshot "04b_confirm_type"
add_image "04b_confirm_type" "Content type confirmation dialog"
note "PromptGrimoire detects the content type. Confirm the detected type or change it, then click Confirm."
rodney click --local '[data-testid="confirm-content-type-btn"]'
rodney sleep 2 --local
take_screenshot "04c_content_processed"
add_image "04c_content_processed" "Processed conversation with formatted turns"
note "Your conversation is now processed and displayed with formatted turns."

# ── Step 5: Create Highlight and Assign Tag ──────────────────────
note "## Step 5: Annotating — Creating a Highlight"
note "Select text in the conversation to highlight it. A tag menu appears so you can categorise the highlight."

# Use JS to create a text selection in the document container.
# The annotation page listens for mouseup events and shows
# the highlight menu when text is selected.
# First verify the doc container, text content, and annotation handler exist.
require_js "doc container with text content" \
    'document.querySelector("#doc-container p")?.textContent ? "ok" : ""'
require_js "annotation selection handler bound" \
    'window._annotSelectionBound ? "ok" : ""'

# Create a text selection and dispatch mouseup to trigger the highlight menu.
# The selection callback sends a WebSocket event to the NiceGUI server
# which then makes the highlight menu visible.
# Use TreeWalker to find actual text nodes (input pipeline wraps content
# in <strong> tags, so p.firstChild may be an element, not a text node).
rodney js --local "(() => { let c = document.getElementById('doc-container'); let tw = document.createTreeWalker(c, NodeFilter.SHOW_TEXT); let tn = tw.nextNode(); while (tn && !tn.textContent.trim()) tn = tw.nextNode(); if (!tn) return 'no text node'; let end = Math.min(tn.length, 50); let r = document.createRange(); r.setStart(tn, 0); r.setEnd(tn, end); window.getSelection().removeAllRanges(); window.getSelection().addRange(r); document.dispatchEvent(new MouseEvent('mouseup', {bubbles:true})); return 'selected ' + end + ' chars'; })()"
wait_for '[data-testid="highlight-menu"]' 'Highlight tag menu appeared'

# Click the first tag button in the highlight menu
rodney js --local "(() => { let btn = document.querySelector('[data-testid=\"highlight-menu\"] button'); if (!btn) return 'no button'; btn.click(); return 'ok'; })()"
rodney sleep 1 --local
take_screenshot "05_highlight_created"
add_image "05_highlight_created" "Text highlighted and tagged with colour coding"
note "Select text and click a tag in the popup menu to create a highlight. The text is colour-coded by tag."

# ── Step 6: Add Comment to Highlight ─────────────────────────────
note "## Step 6: Adding a Comment"
note "Click on a highlighted section to select it, then type a comment in the sidebar."

# Click on the comment input and type a comment
COMMENT_INPUT='[data-testid="comment-input"]'
rodney click --local "$COMMENT_INPUT"
rodney sleep 0.5 --local
rodney input --local "$COMMENT_INPUT" 'This passage highlights key structural differences between legal writing traditions.'
# Click the Post button to submit the comment
rodney click --local '[data-testid="post-comment-btn"]'
rodney sleep 1 --local
take_screenshot "06_comment_added"
add_image "06_comment_added" "Comment added to a highlight in the sidebar"
note "Comments appear below each highlight in the sidebar. Use comments to record your analysis."

# ── Step 7: Organise Tab ─────────────────────────────────────────
note "## Step 7: Organising by Tag"
note "Switch to the Organise tab to view your annotations grouped by tag."
rodney click --local '[data-testid="tab-organise"]'
wait_for '[data-testid="organise-columns"]' 'Organise tab loaded'
rodney sleep 1 --local
take_screenshot "07_organise_tab"
add_image "07_organise_tab" "Organise tab with highlights grouped by tag"
note "The Organise tab shows your highlights in columns by tag. You can drag highlights between columns to reclassify them."

# ── Step 8: Respond Tab ──────────────────────────────────────────
note "## Step 8: Writing Your Response"
note "Switch to the Respond tab to write your analysis. Your highlights appear in the reference panel on the right."
rodney click --local '[data-testid="tab-respond"]'
wait_for '[data-testid="milkdown-editor-container"]' 'Respond tab editor loaded'

# Insert content into the Milkdown editor via JS.
# rodney input panics on contenteditable divs (.select() unsupported),
# so we set textContent directly and dispatch an input event.
wait_for '[data-testid="milkdown-editor-container"] [contenteditable]' 'Milkdown editor ready'
rodney js --local "(() => { let editor = document.querySelector('[data-testid=\"milkdown-editor-container\"] [contenteditable]'); if (!editor) return 'no editor'; editor.focus(); editor.innerHTML = '<p>This analysis examines the translation challenges identified in the AI conversation. The key structural differences between English and Japanese legal writing highlight the importance of understanding both legal systems.</p>'; editor.dispatchEvent(new Event('input', {bubbles: true})); return 'done'; })()"
rodney sleep 1 --local
take_screenshot "08_respond_tab"
add_image "08_respond_tab" "Respond tab with markdown editor and highlight references"
note "The Respond tab has a markdown editor on the left and your highlights as reference on the right. Write your analysis using the highlights as evidence."

# ── Step 9: Export PDF ───────────────────────────────────────────
note "## Step 9: Exporting to PDF"
note "Click Export PDF to generate a PDF of your complete annotation work."
rodney click --local '[data-testid="export-pdf-btn"]'
rodney sleep 3 --local
take_screenshot "09_export"
add_image "09_export" "Exported PDF with conversation, highlights, and response"
note "The exported PDF includes your pasted conversation with highlights, comments, organised notes, and your written response."

echo "✓ Student workflow guide generated: $DOC_PATH"
