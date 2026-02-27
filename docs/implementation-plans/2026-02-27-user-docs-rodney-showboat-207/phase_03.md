# Automated User Documentation — Phase 3: Student Workflow Guide Script

**Goal:** Replace the stub student script with the complete 9-step guide covering login, workspace creation, paste, annotate, comment, organise, respond, and export.

**Architecture:** A single bash script (`generate-student-workflow.sh`) drives the browser via Rodney, captures screenshots, and assembles a Showboat markdown document. A prerequisite task adds missing `data-testid` attributes to UI elements the script interacts with. The student script depends on the instructor script having already created the unit, week, activity, and tags — scripts run sequentially.

**Tech Stack:** Bash, Rodney (CLI browser automation), Showboat (CLI document assembly), NiceGUI (target UI)

**Scope:** Phase 3 of 4 from design plan

**Codebase verified:** 2026-02-27

---

## Acceptance Criteria Coverage

This phase implements and tests:

### user-docs-rodney-showboat-207.AC3: Student guide is complete and accurate
- **user-docs-rodney-showboat-207.AC3.1 Success:** Guide covers login, navigate, create workspace from activity, paste, annotate, comment, organise, respond, export
- **user-docs-rodney-showboat-207.AC3.2 Success:** Workspace inherits tags from instructor's activity configuration
- **user-docs-rodney-showboat-207.AC3.3 Success:** Each step has a corresponding screenshot
- **user-docs-rodney-showboat-207.AC3.4 Quality:** PDF is usable as a class handout — minimal jargon, task-oriented

### user-docs-rodney-showboat-207.AC1: CLI entry point works end-to-end (partial)
- **user-docs-rodney-showboat-207.AC1.3 Success:** Both PDFs are produced in `docs/guides/`
- **user-docs-rodney-showboat-207.AC1.6 Failure:** If a script fails mid-way, error output identifies the failing step

---

<!-- START_TASK_1 -->
### Task 1: Add missing `data-testid` attribute to Export PDF button

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/header.py` (line 122)

**Implementation:**

The Export PDF button in the annotation page header has no `data-testid`. The student guide script needs to click it. Add the attribute:

```python
export_btn = ui.button(
    "Export PDF",
    icon="picture_as_pdf",
).props('color=primary data-testid="export-pdf-btn"')
```

**Verification:**

Run: `uv run test-all`
Expected: All existing tests pass. The testid addition is purely additive.

Run: `uv run ruff check src/promptgrimoire/pages/annotation/header.py`
Expected: No lint errors.

**Commit:**

```bash
git add src/promptgrimoire/pages/annotation/header.py
git commit -m "chore: add data-testid to Export PDF button for doc generation"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement full student workflow guide script

**Verifies:** user-docs-rodney-showboat-207.AC3.1, user-docs-rodney-showboat-207.AC3.2, user-docs-rodney-showboat-207.AC3.3, user-docs-rodney-showboat-207.AC3.4, user-docs-rodney-showboat-207.AC1.3, user-docs-rodney-showboat-207.AC1.6

**Files:**
- Modify: `docs/guides/scripts/generate-student-workflow.sh` (replace stub from Phase 1)

**Implementation:**

Replace the Phase 1 stub with the full 9-step student guide. The script receives `$BASE_URL` as its first argument and uses helpers from `common.sh`.

**Prerequisites:** The instructor script (Phase 2) runs first, creating the unit (TRAN8034, S1 2026), week, activity, tags, and enrolling the demo student (`student-demo@test.example.edu.au`).

**Script structure (all 9 steps):**

```bash
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
rodney click --local '[data-testid="start-activity-btn"]'
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

rodney js --local "
  const html = $(printf '%s' "$SAMPLE_HTML" | sed "s/'/\\\\'/g");
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
rodney js --local "
  const container = document.querySelector('#doc-container');
  if (container) {
    const textNode = container.querySelector('p')?.firstChild;
    if (textNode) {
      const range = document.createRange();
      range.setStart(textNode, 0);
      range.setEnd(textNode, Math.min(textNode.length, 50));
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      // Trigger selectionchange event for NiceGUI handler
      document.dispatchEvent(new Event('selectionchange'));
    }
  }
"
sleep 1
rodney waitstable --local

# Click the first tag button in the highlight menu to create the highlight
rodney js --local "
  const btn = document.querySelector('[data-testid=\"highlight-menu\"] button');
  if (btn) btn.click();
"
sleep 1
rodney waitstable --local
take_screenshot "05_highlight_created"
add_image "05_highlight_created"
note "Select text and click a tag in the popup menu to create a highlight. The text is colour-coded by tag."

# ── Step 6: Add Comment to Highlight ─────────────────────────────
note "## Step 6: Adding a Comment"
note "Click on a highlighted section to select it, then type a comment in the sidebar."

# Click on an annotation card in the sidebar to select it,
# then type in the comment input
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
# Use rodney input (real keyboard events via CDP) — NOT rodney key, which dispatches
# key names like "Enter"/"Tab", not text characters.
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
```

**Key implementation notes for the executor:**

1. **Paste simulation**: The script uses `rodney js` to write HTML to the clipboard via `navigator.clipboard.write()`, then `rodney key --local "Control+v"` to trigger the paste event. This mirrors the E2E test pattern from `tests/e2e/test_html_paste_whitespace.py:78-111`. If Rodney's browser doesn't grant clipboard permissions, the fallback is to call the application's paste handler directly via `rodney js` (bypassing clipboard API).

2. **Text selection for highlighting**: The script uses `rodney js` to create a DOM Range and dispatch a `selectionchange` event. The annotation page's `document.py:36-44` (`on_selection`) handler responds to this event by showing the highlight menu. After the menu appears, the script clicks the first tag button inside `[data-testid="highlight-menu"]` via JS.

3. **Highlight menu tag buttons**: Individual tag buttons inside the highlight menu have no `data-testid` — they're dynamically generated with abbreviated tag names. The script targets them by querying `document.querySelector('[data-testid="highlight-menu"] button')`. Since the instructor configured tags in Phase 2, buttons will be present.

4. **Milkdown editor**: The Respond tab uses a Milkdown WYSIWYG editor rendered inside `[data-testid="milkdown-editor-container"]`. The actual editable element is a nested `[contenteditable]` div. The script focuses it via JS, then uses `rodney input` to type text via real CDP keyboard events. **Do NOT use `rodney key`** — it dispatches key names (e.g., `"Enter"`, `"Tab"`), not text characters. See `docs/rodney/cli-reference.md` for the distinction.

5. **Organise tab**: The script navigates to the Organise tab and takes a screenshot of the tag-column layout. It does NOT attempt to automate SortableJS drag-and-drop — the text explains the drag interaction, and the screenshot shows the starting layout with cards distributed by tag.

6. **Export**: The script clicks the Export PDF button and waits 3 seconds for the server-side LaTeX compilation. The screenshot captures the post-export state (success notification). The PDF itself is not verified by the script — this is a documentation guide, not a test.

7. **Sample HTML content**: The script includes a realistic translation studies conversation (matching the TRAN8034 unit created in Phase 2) as the paste content. This makes the guide screenshots contextually relevant.

8. **Error identification (AC1.6)**: `set -euo pipefail` means the script exits on the first failure. The `echo "✓"` at the end serves as a success indicator.

9. **Sequential dependency**: This script MUST run after the instructor script. The instructor creates the unit, week, activity, tags, and enrolls the student. The student script relies on all of these existing.

**Testing:**

Verification is operational — this is a bash script with no unit tests:
- AC3.1: Run `uv run make-docs`. Verify `docs/guides/student-workflow.pdf` contains screenshots for all 9 steps.
- AC3.2: Verify the workspace screenshot (step 3) shows the annotation page with tag configuration inherited from the activity.
- AC3.3: Verify the PDF contains at least 9 screenshots (one per step).
- AC3.4: Review the PDF text — it should use task-oriented language ("Click Start", "Select text", "Switch to the Organise tab"), not technical jargon.
- AC1.3: Verify both PDFs are produced.
- AC1.6: Deliberately introduce an error (e.g., wrong testid) and verify the orchestrator reports which script failed.

**Human verification (AC3.4 — quality criterion, cannot be automated):**

AC3.4 requires the PDF to be "usable as a class handout — minimal jargon, task-oriented." After running `uv run make-docs`, open `docs/guides/student-workflow.pdf` and verify:
- Language is task-oriented ("Click Start", "Select text", "Switch to the Organise tab"), not developer jargon
- Steps follow a logical student workflow (login → find activity → create workspace → paste → annotate → organise → respond → export)
- Screenshots match the text instructions they accompany
- No placeholder text, broken images, or technical artefacts visible

This is a human UAT gate — the executor should present the PDF for review.

**Verification:**

Run: `uv run make-docs`
Expected: Both PDFs produced. `docs/guides/student-workflow.pdf` has 9+ screenshots and explanatory text for all 9 steps.

Run: `ls -la docs/guides/instructor-setup.pdf docs/guides/student-workflow.pdf`
Expected: Both files exist and are non-empty.

**Commit:**

```bash
git add docs/guides/scripts/generate-student-workflow.sh
git commit -m "feat: implement full student workflow guide script (9 steps)"
```
<!-- END_TASK_2 -->
