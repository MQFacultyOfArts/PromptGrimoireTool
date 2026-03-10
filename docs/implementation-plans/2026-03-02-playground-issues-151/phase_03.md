# LLM Playground Issue Hierarchy — Phase 3: Sub-Issues 5–8

**Goal:** Create the 4 core student experience issues (Core Chat UI, Persistence, Message Editing, JSONL Audit) with full bodies, labels, milestone, issue types, sub-issue links, and blocking relationships.

**Architecture:** Same pattern as Phase 2. Sequential `gh issue create` + GraphQL mutations. References real issue numbers from Phase 2 (substituted at runtime).

**Tech Stack:** `gh` CLI, GitHub GraphQL API

**Scope:** Phase 3 of 6

**Codebase verified:** 2026-03-02

---

## Acceptance Criteria Coverage

This phase implements and verifies:

### playground-issues-151.AC1: All PRD acceptance criteria covered
- **playground-issues-151.AC1.1 Success:** Each of the 38 PRD ACs (AC1.1–AC8.6) is assigned to at least one sub-issue
- **playground-issues-151.AC1.2 Success:** AC6.4 has primary ownership in Issue 7 (edit triggers audit write); Issue 8 provides the audit infrastructure and references AC6.4 in its architecture note

(Issues 5–8 carry ACs for transparency, provider switching, persistence, editing, and audit.)

### playground-issues-151.AC2: Issue structure follows seam model
- **playground-issues-151.AC2.1 Success:** All 12 sub-issues have `type:seam` label
- **playground-issues-151.AC2.2 Success:** All 12 sub-issues have `domain:llm-playground` label
- **playground-issues-151.AC2.3 Success:** All 12 sub-issues assigned to "LLM Playground" milestone
- **playground-issues-151.AC2.4 Success:** Each issue body contains summary, ACs, architecture note, blocker references, and PRD/design doc links

(Verified for issues 5–8 in this phase.)

### playground-issues-151.AC3: Dependency graph is correct
- **playground-issues-151.AC3.1 Success:** All blocker relationships from the DAG table are established in GitHub's dependency graph

(Issues 5–8 dependency relationships established in this phase.)

### playground-issues-151.AC4: Package architecture communicated
- **playground-issues-151.AC4.1 Success:** Issues 2 and 5 include package structure with suggested module breakdown in their architecture note

(Issue 5's architecture note includes package structure in this phase.)

---

**Prerequisite:** Phase 2 must have completed. Source persisted variables:

```bash
VARS_FILE="/tmp/playground-issues-151-vars.sh"
source "$VARS_FILE"
# Verify required variables are set:
echo "ISSUE_1_NUM=$ISSUE_1_NUM ISSUE_1_NODE=$ISSUE_1_NODE"
echo "ISSUE_2_NUM=$ISSUE_2_NUM ISSUE_2_NODE=$ISSUE_2_NODE"
echo "EPIC_NODE=$EPIC_NODE"
```

If `EPIC_NODE` is not set (e.g., fresh session), re-capture it:

```bash
EPIC_NODE=$(gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: 151) { id }
  }
}" --jq '.data.repository.issue.id')
echo "export EPIC_NODE=$EPIC_NODE" >> "$VARS_FILE"
```

<!-- START_TASK_1 -->
### Task 1: Create Issue 5 — Core Chat UI

**Files:** None (GitHub API only)

**Step 1: Create the issue**

```bash
gh issue create \
  --title "Core chat UI" \
  --label "type:seam,domain:llm-playground" \
  --milestone "LLM Playground" \
  --body "$(cat <<'ISSUE_BODY'
## Parent Epic

Part of #151 (LLM Playground)

## Summary

Build the NiceGUI page at `/playground` with system prompt textarea, message rendering, streaming display, parameter controls (temperature, max_tokens, thinking toggle), model picker (filtered by course allowlist), per-message metadata display, "Copy API JSON" button, and cancel generation.

## Acceptance Criteria

- **AC1.1** System prompt is displayed as an always-visible editable textarea at the top of the conversation
- **AC1.2** Each assistant message displays: model name, input/output/thinking token counts, estimated cost, and active parameters (temperature, max_tokens, thinking on/off)
- **AC1.3** Thinking blocks display in collapsible expansion panels with streaming content during generation
- **AC1.4** "Copy API request JSON" button on each assistant message shows the exact request payload sent to the provider
- **AC1.5** Temperature slider is disabled when a thinking-capable model has thinking enabled
- **AC1.6** Token count updates on system prompt textarea as user edits
- **AC3.4** Student can switch models between messages within the same conversation
- **AC3.6** Student model picker shows only models from the course allowlist

## Architecture

Implement as a package: `src/promptgrimoire/pages/playground/` (following `pages/annotation/` pattern)

Suggested modules:
- `__init__.py` — page route, page-level state
- `system_prompt.py` — system prompt card with token counter
- `message.py` — message rendering (user + assistant, metadata byline)
- `streaming.py` — live streaming display (thinking + text)
- `controls.py` — parameter controls, model picker
- `metadata.py` — token/cost/params byline, copy API JSON

If any module exceeds ~300 lines, split further.

## Blocked by

- #ISSUE_1_NUM Playground data model
- #ISSUE_2_NUM Provider abstraction

## Blocks

- Persistence & conversation history
- Message editing & regeneration

## References

- PRD: `docs/prds/2026-02-10-llm-playground.md`
- Design: `docs/design-plans/2026-03-02-playground-issues-151.md`
- Cached docs: `docs/annotation-architecture.md` (package pattern reference)
ISSUE_BODY
)"
```

Replace `#ISSUE_1_NUM` and `#ISSUE_2_NUM` with actual issue numbers from Phase 2.

**Step 2: Capture issue number as `ISSUE_5_NUM`**

```bash
ISSUE_5_NUM=NNN  # Replace NNN with actual number from URL
echo "export ISSUE_5_NUM=$ISSUE_5_NUM" >> "$VARS_FILE"
```

**Step 3: Set issue type, link as sub-issue, set blocking relationships**

```bash
ISSUE_5_NODE=$(gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $ISSUE_5_NUM) { id }
  }
}" --jq '.data.repository.issue.id')
echo "export ISSUE_5_NODE=$ISSUE_5_NODE" >> "$VARS_FILE"

# Set type = Task
gh api graphql -f query="
mutation {
  updateIssue(input: {
    id: \"$ISSUE_5_NODE\",
    issueTypeId: \"IT_kwDOAktGus4Ac3IQ\"
  }) { issue { number } }
}"

# Link as sub-issue of epic #151
gh api graphql -f query="
mutation {
  addSubIssue(input: {
    issueId: \"$EPIC_NODE\",
    subIssueId: \"$ISSUE_5_NODE\"
  }) { issue { id } }
}"

# Blocked by Issue 1 (data model) and Issue 2 (provider)
gh api graphql -f query="
mutation {
  a: addBlockedBy(input: {
    issueId: \"$ISSUE_5_NODE\",
    blockingIssueId: \"$ISSUE_1_NODE\"
  }) { blockedByItems { nodes { id } } }
  b: addBlockedBy(input: {
    issueId: \"$ISSUE_5_NODE\",
    blockingIssueId: \"$ISSUE_2_NODE\"
  }) { blockedByItems { nodes { id } } }
}"
```

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create Issue 6 — Persistence & Conversation History

**Files:** None (GitHub API only)

**Step 1: Create the issue**

```bash
gh issue create \
  --title "Persistence & conversation history" \
  --label "type:seam,domain:llm-playground" \
  --milestone "LLM Playground" \
  --body "$(cat <<'ISSUE_BODY'
## Parent Epic

Part of #151 (LLM Playground)

## Summary

Implement auto-save of conversations to PostgreSQL, a conversation list/browser UI, resume functionality for previous conversations, and automatic workspace creation for each conversation.

## Acceptance Criteria

- **AC4.1** Conversations persist in PostgreSQL (canonical store) and survive browser close/reopen
- **AC4.2** Student can browse conversation history and resume any previous conversation
- **AC4.5** Each conversation is linked to a Workspace

## Architecture

Implement across two locations:
- `src/promptgrimoire/db/` — persistence layer (CRUD for PlaygroundConversation, PlaygroundMessage)
- `src/promptgrimoire/pages/playground/` — conversation list UI component

Single modules in each location likely sufficient. If any module exceeds ~300 lines, split further.

## Blocked by

- #ISSUE_1_NUM Playground data model
- #ISSUE_5_NUM Core chat UI

## Blocks

- Message editing & regeneration
- File attachments
- Export to annotation
- Collaboration seams

## References

- PRD: `docs/prds/2026-02-10-llm-playground.md`
- Design: `docs/design-plans/2026-03-02-playground-issues-151.md`
ISSUE_BODY
)"
```

Replace `#ISSUE_1_NUM` and `#ISSUE_5_NUM` with actual issue numbers.

**Step 2: Capture issue number as `ISSUE_6_NUM`**

```bash
ISSUE_6_NUM=NNN  # Replace NNN with actual number from URL
echo "export ISSUE_6_NUM=$ISSUE_6_NUM" >> "$VARS_FILE"
```

**Step 3: Set issue type, link as sub-issue, set blocking relationships**

```bash
ISSUE_6_NODE=$(gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $ISSUE_6_NUM) { id }
  }
}" --jq '.data.repository.issue.id')
echo "export ISSUE_6_NODE=$ISSUE_6_NODE" >> "$VARS_FILE"

# Set type = Task
gh api graphql -f query="
mutation {
  updateIssue(input: {
    id: \"$ISSUE_6_NODE\",
    issueTypeId: \"IT_kwDOAktGus4Ac3IQ\"
  }) { issue { number } }
}"

# Link as sub-issue
gh api graphql -f query="
mutation {
  addSubIssue(input: {
    issueId: \"$EPIC_NODE\",
    subIssueId: \"$ISSUE_6_NODE\"
  }) { issue { id } }
}"

# Blocked by Issue 1 and Issue 5
gh api graphql -f query="
mutation {
  a: addBlockedBy(input: {
    issueId: \"$ISSUE_6_NODE\",
    blockingIssueId: \"$ISSUE_1_NODE\"
  }) { blockedByItems { nodes { id } } }
  b: addBlockedBy(input: {
    issueId: \"$ISSUE_6_NODE\",
    blockingIssueId: \"$ISSUE_5_NODE\"
  }) { blockedByItems { nodes { id } } }
}"
```

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create Issue 7 — Message Editing & Regeneration

**Files:** None (GitHub API only)

**Step 1: Create the issue**

```bash
gh issue create \
  --title "Message editing & regeneration" \
  --label "type:seam,domain:llm-playground" \
  --milestone "LLM Playground" \
  --body "$(cat <<'ISSUE_BODY'
## Parent Epic

Part of #151 (LLM Playground)

## Summary

Enable in-place editing of user and assistant messages, regeneration of assistant responses, and `@ui.refreshable` per-message rendering. Edits update the database record and trigger audit writes to the JSONL archive.

## Acceptance Criteria

- **AC6.1** Student can edit any user message text in place
- **AC6.2** Student can edit any assistant message text in place
- **AC6.3** Regenerate button on any assistant message re-runs that response (replaces the message content)
- **AC6.4** Edits update the database record; original content is preserved in the JSONL archive

**Note on AC6.4:** This issue is the primary owner. The edit triggers the audit write. Issue 8 (JSONL Audit) provides the audit log infrastructure that this issue calls into.

## Architecture

Implement as editing components within `src/promptgrimoire/pages/playground/` (adding to the package created by Issue 5).

If any module exceeds ~300 lines, split further.

**Key pattern:** `@ui.refreshable` decorator on per-message rendering functions for in-place updates without full page reload.

## Blocked by

- #ISSUE_5_NUM Core chat UI
- #ISSUE_6_NUM Persistence & conversation history

## Blocks

None (leaf node in DAG)

## References

- PRD: `docs/prds/2026-02-10-llm-playground.md`
- Design: `docs/design-plans/2026-03-02-playground-issues-151.md`
ISSUE_BODY
)"
```

Replace placeholders with actual issue numbers.

**Step 2: Capture issue number as `ISSUE_7_NUM`**

```bash
ISSUE_7_NUM=NNN  # Replace NNN with actual number from URL
echo "export ISSUE_7_NUM=$ISSUE_7_NUM" >> "$VARS_FILE"
```

**Step 3: Set issue type, link as sub-issue, set blocking relationships**

```bash
ISSUE_7_NODE=$(gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $ISSUE_7_NUM) { id }
  }
}" --jq '.data.repository.issue.id')
echo "export ISSUE_7_NODE=$ISSUE_7_NODE" >> "$VARS_FILE"

# Set type = Task
gh api graphql -f query="
mutation {
  updateIssue(input: {
    id: \"$ISSUE_7_NODE\",
    issueTypeId: \"IT_kwDOAktGus4Ac3IQ\"
  }) { issue { number } }
}"

# Link as sub-issue
gh api graphql -f query="
mutation {
  addSubIssue(input: {
    issueId: \"$EPIC_NODE\",
    subIssueId: \"$ISSUE_7_NODE\"
  }) { issue { id } }
}"

# Blocked by Issue 5 and Issue 6
gh api graphql -f query="
mutation {
  a: addBlockedBy(input: {
    issueId: \"$ISSUE_7_NODE\",
    blockingIssueId: \"$ISSUE_5_NODE\"
  }) { blockedByItems { nodes { id } } }
  b: addBlockedBy(input: {
    issueId: \"$ISSUE_7_NODE\",
    blockingIssueId: \"$ISSUE_6_NODE\"
  }) { blockedByItems { nodes { id } } }
}"
```

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Create Issue 8 — JSONL Audit Trail

**Files:** None (GitHub API only)

**Step 1: Create the issue**

```bash
gh issue create \
  --title "JSONL audit trail" \
  --label "type:seam,domain:llm-playground" \
  --milestone "LLM Playground" \
  --body "$(cat <<'ISSUE_BODY'
## Parent Epic

Part of #151 (LLM Playground)

## Summary

Extend `llm/log.py` to provide a full append-only JSONL audit trail with request, response, timing, cost, student ID, and course ID for every API call. The archive is immutable — edits to messages (AC6.4) preserve originals here.

## Acceptance Criteria

- **AC4.3** Every API call is logged to append-only JSONL archive with full request, response, timing, cost, student ID, and course ID
- **AC4.4** JSONL archive is immutable even when students edit messages in the DB

## Architecture

Extend existing `src/promptgrimoire/llm/log.py` (or create `src/promptgrimoire/llm/audit.py` if log.py is already substantial).

If any module exceeds ~300 lines, split further.

**AC6.4 cross-reference:** Issue 7 (Message Editing) is the primary owner of AC6.4. This issue provides the audit infrastructure that Issue 7 calls into when an edit occurs. The audit write preserves the original content before the database record is updated.

## Blocked by

- #ISSUE_1_NUM Playground data model
- #ISSUE_2_NUM Provider abstraction

## Blocks

None (leaf node in DAG)

## References

- PRD: `docs/prds/2026-02-10-llm-playground.md`
- Design: `docs/design-plans/2026-03-02-playground-issues-151.md`
ISSUE_BODY
)"
```

Replace placeholders with actual issue numbers.

**Step 2: Capture issue number as `ISSUE_8_NUM`**

```bash
ISSUE_8_NUM=NNN  # Replace NNN with actual number from URL
echo "export ISSUE_8_NUM=$ISSUE_8_NUM" >> "$VARS_FILE"
```

**Step 3: Set issue type, link as sub-issue, set blocking relationships**

```bash
ISSUE_8_NODE=$(gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $ISSUE_8_NUM) { id }
  }
}" --jq '.data.repository.issue.id')
echo "export ISSUE_8_NODE=$ISSUE_8_NODE" >> "$VARS_FILE"

# Set type = Task
gh api graphql -f query="
mutation {
  updateIssue(input: {
    id: \"$ISSUE_8_NODE\",
    issueTypeId: \"IT_kwDOAktGus4Ac3IQ\"
  }) { issue { number } }
}"

# Link as sub-issue
gh api graphql -f query="
mutation {
  addSubIssue(input: {
    issueId: \"$EPIC_NODE\",
    subIssueId: \"$ISSUE_8_NODE\"
  }) { issue { id } }
}"

# Blocked by Issue 1 and Issue 2
gh api graphql -f query="
mutation {
  a: addBlockedBy(input: {
    issueId: \"$ISSUE_8_NODE\",
    blockingIssueId: \"$ISSUE_1_NODE\"
  }) { blockedByItems { nodes { id } } }
  b: addBlockedBy(input: {
    issueId: \"$ISSUE_8_NODE\",
    blockingIssueId: \"$ISSUE_2_NODE\"
  }) { blockedByItems { nodes { id } } }
}"
```

**Step 4: Verify all Phase 3 issues**

```bash
gh issue list --label "type:seam" --label "domain:llm-playground" --milestone "LLM Playground" --state open
```

Expected: 8 issues (4 from Phase 2 + 4 from Phase 3).

<!-- END_TASK_4 -->
