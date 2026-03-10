# LLM Playground Issue Hierarchy — Phase 4: Sub-Issues 9–12

**Goal:** Create the 4 advanced feature issues (File Attachments, Export to Annotation, Course Admin UI, Collaboration Seams) with full bodies, labels, milestone, issue types, sub-issue links, and blocking relationships. Complete the 12-issue dependency graph.

**Architecture:** Same pattern as Phases 2–3. Sequential `gh issue create` + GraphQL mutations.

**Tech Stack:** `gh` CLI, GitHub GraphQL API

**Scope:** Phase 4 of 6

**Codebase verified:** 2026-03-02

---

## Acceptance Criteria Coverage

This phase implements and verifies:

### playground-issues-151.AC1: All PRD acceptance criteria covered
- **playground-issues-151.AC1.1 Success:** Each of the 38 PRD ACs (AC1.1–AC8.6) is assigned to at least one sub-issue

(Issues 9–12 carry ACs for file attachments, export, instructor admin, and collaboration — completing full coverage.)

### playground-issues-151.AC2: Issue structure follows seam model
- **playground-issues-151.AC2.1 Success:** All 12 sub-issues have `type:seam` label
- **playground-issues-151.AC2.2 Success:** All 12 sub-issues have `domain:llm-playground` label
- **playground-issues-151.AC2.3 Success:** All 12 sub-issues assigned to "LLM Playground" milestone
- **playground-issues-151.AC2.4 Success:** Each issue body contains summary, ACs, architecture note, blocker references, and PRD/design doc links

(Verified for issues 9–12 in this phase.)

### playground-issues-151.AC3: Dependency graph is correct
- **playground-issues-151.AC3.1 Success:** All blocker relationships from the DAG table are established in GitHub's dependency graph
- **playground-issues-151.AC3.2 Success:** No circular dependencies exist

(All 12 issues' dependency relationships complete after this phase.)

---

**Prerequisite:** Phases 2–3 must have completed. Source persisted variables:

```bash
VARS_FILE="/tmp/playground-issues-151-vars.sh"
source "$VARS_FILE"
# Verify required variables are set:
echo "ISSUE_3_NUM=$ISSUE_3_NUM ISSUE_4_NUM=$ISSUE_4_NUM ISSUE_6_NUM=$ISSUE_6_NUM"
echo "EPIC_NODE=$EPIC_NODE"
```

If `EPIC_NODE` is not set, re-capture:

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
### Task 1: Create Issue 9 — File Attachments

**Files:** None (GitHub API only)

**Step 1: Create the issue**

```bash
gh issue create \
  --title "File attachments" \
  --label "type:seam,domain:llm-playground" \
  --milestone "LLM Playground" \
  --body "$(cat <<'ISSUE_BODY'
## Parent Epic

Part of #151 (LLM Playground)

## Summary

Implement file attachment support: `ui.upload` with drag-and-drop, workspace file storage, reference chips on messages, base64 image encoding for vision-capable models, and capability gating that disables attachments for non-vision models.

## Acceptance Criteria

- **AC7.1** Student can attach files via upload button or drag-and-drop in the input area
- **AC7.2** Multiple files can be attached to a single message
- **AC7.3** Attached files display as reference chips (filename + size) on the message, not as image previews
- **AC7.4** Images are sent as base64 to vision-capable models
- **AC7.5** File attach button is disabled for models that don't support file/vision input
- **AC7.6** Attached files are stored in workspace file storage and referenced by message metadata

## Architecture

Implement across two locations:
- `src/promptgrimoire/pages/playground/` — upload UI component, reference chips
- `src/promptgrimoire/db/` — workspace file storage operations

Single modules in each location likely sufficient. If any module exceeds ~300 lines, split further.

## Blocked by

- #ISSUE_6_NUM Persistence & conversation history

## Blocks

None (leaf node in DAG)

## References

- PRD: `docs/prds/2026-02-10-llm-playground.md`
- Design: `docs/design-plans/2026-03-02-playground-issues-151.md`
ISSUE_BODY
)"
```

Replace `#ISSUE_6_NUM` with actual issue number.

**Step 2: Capture issue number as `ISSUE_9_NUM`**

```bash
ISSUE_9_NUM=NNN  # Replace NNN with actual number from URL
echo "export ISSUE_9_NUM=$ISSUE_9_NUM" >> "$VARS_FILE"
```

**Step 3: Set issue type, link as sub-issue, set blocking relationship**

```bash
ISSUE_9_NODE=$(gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $ISSUE_9_NUM) { id }
  }
}" --jq '.data.repository.issue.id')
echo "export ISSUE_9_NODE=$ISSUE_9_NODE" >> "$VARS_FILE"

gh api graphql -f query="
mutation {
  updateIssue(input: {
    id: \"$ISSUE_9_NODE\",
    issueTypeId: \"IT_kwDOAktGus4Ac3IQ\"
  }) { issue { number } }
}"

gh api graphql -f query="
mutation {
  addSubIssue(input: {
    issueId: \"$EPIC_NODE\",
    subIssueId: \"$ISSUE_9_NODE\"
  }) { issue { id } }
}"

# Blocked by Issue 6 only
gh api graphql -f query="
mutation {
  addBlockedBy(input: {
    issueId: \"$ISSUE_9_NODE\",
    blockingIssueId: \"$ISSUE_6_NODE\"
  }) { blockedByItems { nodes { id } } }
}"
```

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create Issue 10 — Export to Annotation

**Files:** None (GitHub API only)

**Step 1: Create the issue**

```bash
gh issue create \
  --title "Export to annotation" \
  --label "type:seam,domain:llm-playground" \
  --milestone "LLM Playground" \
  --body "$(cat <<'ISSUE_BODY'
## Parent Epic

Part of #151 (LLM Playground)

## Summary

Implement conversation export: serialize a playground conversation to structured HTML, create a `WorkspaceDocument(source_type="playground")`, and feed it into the existing input pipeline for annotation.

## Acceptance Criteria

- **AC5.1** "Annotate this conversation" creates a `WorkspaceDocument(source_type="playground")` that the annotation page can render
- **AC5.2** Exported HTML includes speaker labels and per-message metadata (model, tokens, cost)
- **AC5.3** Thinking blocks are included as collapsible sections in the exported HTML

## Architecture

Implement as a serialiser in `src/promptgrimoire/export/` or `src/promptgrimoire/pages/playground/` (whichever fits better with the existing export pipeline pattern).

Single module likely sufficient. If it exceeds ~300 lines, split further.

## Blocked by

- #ISSUE_6_NUM Persistence & conversation history

## Blocks

None (leaf node in DAG)

## References

- PRD: `docs/prds/2026-02-10-llm-playground.md`
- Design: `docs/design-plans/2026-03-02-playground-issues-151.md`
- Cached docs: `docs/input-pipeline.md`, `docs/export.md`
ISSUE_BODY
)"
```

Replace `#ISSUE_6_NUM` with actual issue number.

**Step 2: Capture issue number as `ISSUE_10_NUM`**

```bash
ISSUE_10_NUM=NNN  # Replace NNN with actual number from URL
echo "export ISSUE_10_NUM=$ISSUE_10_NUM" >> "$VARS_FILE"
```

**Step 3: Set issue type, link as sub-issue, set blocking relationship**

```bash
ISSUE_10_NODE=$(gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $ISSUE_10_NUM) { id }
  }
}" --jq '.data.repository.issue.id')
echo "export ISSUE_10_NODE=$ISSUE_10_NODE" >> "$VARS_FILE"

gh api graphql -f query="
mutation {
  updateIssue(input: {
    id: \"$ISSUE_10_NODE\",
    issueTypeId: \"IT_kwDOAktGus4Ac3IQ\"
  }) { issue { number } }
}"

gh api graphql -f query="
mutation {
  addSubIssue(input: {
    issueId: \"$EPIC_NODE\",
    subIssueId: \"$ISSUE_10_NODE\"
  }) { issue { id } }
}"

gh api graphql -f query="
mutation {
  addBlockedBy(input: {
    issueId: \"$ISSUE_10_NODE\",
    blockingIssueId: \"$ISSUE_6_NODE\"
  }) { blockedByItems { nodes { id } } }
}"
```

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create Issue 11 — Course Admin UI

**Files:** None (GitHub API only)

**Step 1: Create the issue**

```bash
gh issue create \
  --title "Course admin UI" \
  --label "type:seam,domain:llm-playground" \
  --milestone "LLM Playground" \
  --body "$(cat <<'ISSUE_BODY'
## Parent Epic

Part of #151 (LLM Playground)

## Summary

Build the instructor-facing UI for model configuration, key provisioning, and read-only conversation viewing. This integrates into the existing courses page (which may already be a package by implementation time — check current state of `src/promptgrimoire/pages/courses/`).

## Acceptance Criteria

- **AC2.6** Instructor can view student conversations read-only

## Architecture

Add to `src/promptgrimoire/pages/courses/` (check current structure — may be a single file or already refactored to a package).

Components:
- Model configuration UI (add/enable/disable models on course allowlist)
- Key provisioning UI (mint/revoke per-student API keys)
- Instructor read-only conversation viewer

If `courses.py` is still a single file and adding these components would exceed ~300 lines, refactor to a package first. If already a package, add modules to it.

## Blocked by

- #ISSUE_3_NUM OpenRouter key provisioning
- #ISSUE_4_NUM Model allowlist

## Blocks

None (leaf node in DAG)

## References

- PRD: `docs/prds/2026-02-10-llm-playground.md`
- Design: `docs/design-plans/2026-03-02-playground-issues-151.md`
ISSUE_BODY
)"
```

Replace `#ISSUE_3_NUM` and `#ISSUE_4_NUM` with actual issue numbers.

**Step 2: Capture issue number as `ISSUE_11_NUM`**

```bash
ISSUE_11_NUM=NNN  # Replace NNN with actual number from URL
echo "export ISSUE_11_NUM=$ISSUE_11_NUM" >> "$VARS_FILE"
```

**Step 3: Set issue type, link as sub-issue, set blocking relationships**

```bash
ISSUE_11_NODE=$(gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $ISSUE_11_NUM) { id }
  }
}" --jq '.data.repository.issue.id')
echo "export ISSUE_11_NODE=$ISSUE_11_NODE" >> "$VARS_FILE"

gh api graphql -f query="
mutation {
  updateIssue(input: {
    id: \"$ISSUE_11_NODE\",
    issueTypeId: \"IT_kwDOAktGus4Ac3IQ\"
  }) { issue { number } }
}"

gh api graphql -f query="
mutation {
  addSubIssue(input: {
    issueId: \"$EPIC_NODE\",
    subIssueId: \"$ISSUE_11_NODE\"
  }) { issue { id } }
}"

# Blocked by Issue 3 and Issue 4
gh api graphql -f query="
mutation {
  a: addBlockedBy(input: {
    issueId: \"$ISSUE_11_NODE\",
    blockingIssueId: \"$ISSUE_3_NODE\"
  }) { blockedByItems { nodes { id } } }
  b: addBlockedBy(input: {
    issueId: \"$ISSUE_11_NODE\",
    blockingIssueId: \"$ISSUE_4_NODE\"
  }) { blockedByItems { nodes { id } } }
}"
```

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Create Issue 12 — Collaboration Seams

**Files:** None (GitHub API only)

**Step 1: Create the issue**

```bash
gh issue create \
  --title "Collaboration seams" \
  --label "type:seam,domain:llm-playground" \
  --milestone "LLM Playground" \
  --body "$(cat <<'ISSUE_BODY'
## Parent Epic

Part of #151 (LLM Playground)

## Summary

Implement shared workspace access for conversations, real-time stream sharing so two users see AI output arriving simultaneously, user identification (username/first name passed to AI), instructor sharing to class, and CRDT integration documentation for future full collaboration.

## Acceptance Criteria

- **AC8.1** Two students accessing the same workspace see the same conversation list
- **AC8.2** Two tabs/users in the same workspace can see the same AI stream arriving in real time
- **AC8.3** Each user in a shared workspace is identified by username; first name is passed to the AI so it can differentiate messages from different users
- **AC8.4** Instructor can share a conversation to the class (creates read-only copies for enrolled students)
- **AC8.5** CRDT integration points are documented for future implementation
- **AC8.6** Shared workspace access respects future ACL (architecture does not bypass Workspace-level access)

## Architecture

Implement across two locations:
- `src/promptgrimoire/pages/playground/` — sharing UI, real-time stream sharing
- `docs/` — CRDT integration documentation (AC8.5)

The `PlaygroundConversation.shared_with` field is already in the data model (Issue 1), so this issue builds UI and server-push logic on top of existing schema.

If any module exceeds ~300 lines, split further.

## Blocked by

- #ISSUE_6_NUM Persistence & conversation history

## Blocks

None (leaf node in DAG)

## References

- PRD: `docs/prds/2026-02-10-llm-playground.md`
- Design: `docs/design-plans/2026-03-02-playground-issues-151.md`
- Cached docs: `docs/annotation-architecture.md` (CRDT patterns)
ISSUE_BODY
)"
```

Replace `#ISSUE_6_NUM` with actual issue number.

**Step 2: Capture issue number as `ISSUE_12_NUM`**

```bash
ISSUE_12_NUM=NNN  # Replace NNN with actual number from URL
echo "export ISSUE_12_NUM=$ISSUE_12_NUM" >> "$VARS_FILE"
```

**Step 3: Set issue type, link as sub-issue, set blocking relationship**

```bash
ISSUE_12_NODE=$(gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $ISSUE_12_NUM) { id }
  }
}" --jq '.data.repository.issue.id')
echo "export ISSUE_12_NODE=$ISSUE_12_NODE" >> "$VARS_FILE"

gh api graphql -f query="
mutation {
  updateIssue(input: {
    id: \"$ISSUE_12_NODE\",
    issueTypeId: \"IT_kwDOAktGus4Ac3IQ\"
  }) { issue { number } }
}"

gh api graphql -f query="
mutation {
  addSubIssue(input: {
    issueId: \"$EPIC_NODE\",
    subIssueId: \"$ISSUE_12_NODE\"
  }) { issue { id } }
}"

gh api graphql -f query="
mutation {
  addBlockedBy(input: {
    issueId: \"$ISSUE_12_NODE\",
    blockingIssueId: \"$ISSUE_6_NODE\"
  }) { blockedByItems { nodes { id } } }
}"
```

**Step 4: Verify all 12 sub-issues**

```bash
# Count all seam issues in the playground domain
gh issue list --label "type:seam" --label "domain:llm-playground" --milestone "LLM Playground" --state open --limit 20
```

Expected: 12 issues listed.

```bash
# Spot-check a blocking relationship (e.g., Issue 7 blocked by 5 and 6)
echo "Verifying Issue 7 blockers..."
gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $ISSUE_7_NUM) {
      title
      blockedBy(first: 5) {
        nodes { number title }
      }
    }
  }
}" --jq '.data.repository.issue'
```

Expected: Issue 7 shows blocked by Issue 5 (Core chat UI) and Issue 6 (Persistence).

<!-- END_TASK_4 -->
