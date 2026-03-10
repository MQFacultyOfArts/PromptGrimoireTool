# LLM Playground Issue Hierarchy — Phase 2: Sub-Issues 1–4

**Goal:** Create the 4 foundation issues (Data Model, Provider Abstraction, Key Provisioning, Model Allowlist) with full bodies, labels, milestone, issue types, sub-issue links, and blocking relationships.

**Architecture:** Sequential `gh issue create` commands, followed by GraphQL mutations for issue type, blocking, and sub-issue relationships. Issue 1 created first (others depend on it), then 2–4.

**Tech Stack:** `gh` CLI, GitHub GraphQL API

**Scope:** Phase 2 of 6

**Codebase verified:** 2026-03-02

---

## Acceptance Criteria Coverage

This phase implements and verifies:

### playground-issues-151.AC1: All PRD acceptance criteria covered
- **playground-issues-151.AC1.1 Success:** Each of the 38 PRD ACs (AC1.1–AC8.6) is assigned to at least one sub-issue

(Issues 1–4 carry ACs for data model, provider abstraction, instructor config, and persistence/audit foundations.)

### playground-issues-151.AC2: Issue structure follows seam model
- **playground-issues-151.AC2.1 Success:** All 12 sub-issues have `type:seam` label
- **playground-issues-151.AC2.2 Success:** All 12 sub-issues have `domain:llm-playground` label
- **playground-issues-151.AC2.3 Success:** All 12 sub-issues assigned to "LLM Playground" milestone
- **playground-issues-151.AC2.4 Success:** Each issue body contains summary, ACs, architecture note, blocker references, and PRD/design doc links

(Verified for issues 1–4 in this phase.)

### playground-issues-151.AC3: Dependency graph is correct
- **playground-issues-151.AC3.3 Success:** Issues 2, 3, 4 are blocked only by issue 1 (maximum initial parallelism)

### playground-issues-151.AC4: Package architecture communicated
- **playground-issues-151.AC4.1 Success:** Issues 2 and 5 include package structure with suggested module breakdown in their architecture note
- **playground-issues-151.AC4.2 Success:** All issues reference the ~300 line threshold for package splitting

(Issue 2's architecture note includes package structure in this phase.)

---

## Variable Persistence

All phases share issue numbers and node IDs via a variables file. Each phase appends to this file; subsequent phases source it.

```bash
VARS_FILE="/tmp/playground-issues-151-vars.sh"
```

After capturing any variable (e.g., `ISSUE_1_NUM`, `ISSUE_1_NODE`), immediately record it:

```bash
echo "export ISSUE_1_NUM=$ISSUE_1_NUM" >> "$VARS_FILE"
```

At the start of each subsequent phase, source the file:

```bash
source "$VARS_FILE"
```

## GraphQL Error Checking

After every GraphQL mutation, check for errors. The `gh api graphql` command returns errors in the response body, not via exit code. Add `--jq '.errors'` to verify:

```bash
# If this returns null, the mutation succeeded. If it returns an array, inspect the error messages.
```

The `addBlockedBy` and `addSubIssue` mutations are documented in the project's `.claude/skills/manage-issues/SKILL.md` and verified working in this repository.

---

<!-- START_TASK_1 -->
### Task 1: Create Issue 1 — Playground Data Model

**Files:** None (GitHub API only)

**Step 1: Create the issue**

```bash
gh issue create \
  --title "Playground data model" \
  --label "type:seam,domain:llm-playground" \
  --milestone "LLM Playground" \
  --body "$(cat <<'ISSUE_BODY'
## Parent Epic

Part of #151 (LLM Playground)

## Summary

Create the SQLModel tables for the playground feature: `CourseModelConfig`, `StudentAPIKey` (full column set including `openrouter_key_hash`, `budget_limit`, `budget_reset`, `expires_at`), `PlaygroundConversation` (including `shared_with` for future collaboration), and `PlaygroundMessage`. Generate an Alembic migration for all tables.

## Acceptance Criteria

This issue provides the data foundation. No PRD ACs are directly tested here — the schema enables all downstream issues to implement their ACs.

## Architecture

Implement as additions to `src/promptgrimoire/db/models.py` (single file — models are centralised). Migration in `alembic/versions/`.

If `models.py` exceeds ~300 lines after these additions, split into a package with focused modules.

**Tables:**

- `CourseModelConfig` — links a model identifier to a course with display name, privacy notes, hosting region, cost tier, enabled flag
- `StudentAPIKey` — per-student-per-course API key record with `openrouter_key_hash`, `budget_limit`, `budget_reset`, `expires_at`, Fernet-encrypted key blob
- `PlaygroundConversation` — conversation metadata: title, student, course, workspace link, model, system prompt, parameters, `shared_with: list[UUID] | None`
- `PlaygroundMessage` — individual messages: role, content, token counts, cost, model, thinking content, attachments metadata

**Key design decisions:**

1. `shared_with` included in `PlaygroundConversation` now (not deferred to Issue 12) to avoid mid-sprint migration
2. `StudentAPIKey` includes full column set derived from OpenRouter Management API docs to avoid Issue 3 needing a follow-on migration
3. All tables use UUID primary keys consistent with existing models

## Blocked by

None (foundation issue)

## Blocks

- Provider abstraction
- OpenRouter key provisioning
- Model allowlist
- Core chat UI
- Persistence & conversation history
- JSONL audit trail

## References

- PRD: `docs/prds/2026-02-10-llm-playground.md`
- Design: `docs/design-plans/2026-03-02-playground-issues-151.md`
- Cached docs: `docs/openrouter/key-management-api.md`
ISSUE_BODY
)"
```

**Step 2: Capture the issue number**

The `gh issue create` command outputs the issue URL. Extract the issue number (e.g., from `https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/NNN`).

Record this as `ISSUE_1_NUM`:

```bash
VARS_FILE="/tmp/playground-issues-151-vars.sh"
ISSUE_1_NUM=NNN  # Replace NNN with actual number from URL
echo "export ISSUE_1_NUM=$ISSUE_1_NUM" >> "$VARS_FILE"
```

**Step 3: Set issue type to Task**

```bash
# Get node ID (double-quoted so $ISSUE_1_NUM expands)
ISSUE_1_NODE=$(gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $ISSUE_1_NUM) { id }
  }
}" --jq '.data.repository.issue.id')
echo "export ISSUE_1_NODE=$ISSUE_1_NODE" >> "$VARS_FILE"

# Set type = Task
gh api graphql -f query="
mutation {
  updateIssue(input: {
    id: \"$ISSUE_1_NODE\",
    issueTypeId: \"IT_kwDOAktGus4Ac3IQ\"
  }) { issue { number } }
}"
```

**Step 4: Link as sub-issue of epic #151**

```bash
# Get epic #151 node ID
EPIC_NODE=$(gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: 151) { id }
  }
}" --jq '.data.repository.issue.id')
echo "export EPIC_NODE=$EPIC_NODE" >> "$VARS_FILE"

# Add as sub-issue
gh api graphql -f query="
mutation {
  addSubIssue(input: {
    issueId: \"$EPIC_NODE\",
    subIssueId: \"$ISSUE_1_NODE\"
  }) { issue { id } }
}"
```

**Step 5: Verify**

```bash
gh issue view $ISSUE_1_NUM --json title,labels,milestone
```

Expected: Title "Playground data model", labels include `type:seam` and `domain:llm-playground`, milestone "LLM Playground".

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create Issue 2 — Provider Abstraction

**Files:** None (GitHub API only)

**Step 1: Create the issue**

```bash
gh issue create \
  --title "Provider abstraction" \
  --label "type:seam,domain:llm-playground" \
  --milestone "LLM Playground" \
  --body "$(cat <<'ISSUE_BODY'
## Parent Epic

Part of #151 (LLM Playground)

## Summary

Create an N-provider protocol layer, the OpenRouter adapter implementation, a pydantic-ai Agent factory, and a streaming event handler that emits uniform event types (ThinkingPart, TextPart deltas) regardless of provider.

## Acceptance Criteria

- **AC3.1** Direct Anthropic provider creates `AnthropicModel` agents with native thinking support
- **AC3.2** OpenRouter provider creates `OpenRouterModel` agents for non-Anthropic models
- **AC3.3** Both providers emit the same streaming event types (ThinkingPart, TextPart deltas) to the UI handler
- **AC3.5** Conversation `message_history` carries forward across model switches (pydantic-ai handles serialization)

## Architecture

Implement as a package: `src/promptgrimoire/llm/playground/`

Suggested modules:
- `__init__.py` — public exports
- `provider.py` — N-provider protocol (abstract interface)
- `openrouter.py` — OpenRouter adapter (first implementation)
- `streaming.py` — streaming event handler (thinking/text/metadata)

Follow the `pages/annotation/` pattern. If any module exceeds ~300 lines, split further.

**Note:** AC3.1 (Direct Anthropic provider) is scoped here as an interface definition. The full Anthropic adapter implementation is a standalone post-MVP issue.

## Blocked by

- #ISSUE_1_NUM Playground data model

## Blocks

- Core chat UI
- JSONL audit trail

## References

- PRD: `docs/prds/2026-02-10-llm-playground.md`
- Design: `docs/design-plans/2026-03-02-playground-issues-151.md`
- Cached docs: `docs/pydantic-ai/` (if available)
ISSUE_BODY
)"
```

Replace `#ISSUE_1_NUM` with the actual issue number from Task 1.

**Step 2: Capture issue number as `ISSUE_2_NUM`**

```bash
ISSUE_2_NUM=NNN  # Replace NNN with actual number from URL
echo "export ISSUE_2_NUM=$ISSUE_2_NUM" >> "$VARS_FILE"
```

**Step 3: Set issue type to Task and link as sub-issue**

```bash
ISSUE_2_NODE=$(gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $ISSUE_2_NUM) { id }
  }
}" --jq '.data.repository.issue.id')
echo "export ISSUE_2_NODE=$ISSUE_2_NODE" >> "$VARS_FILE"

gh api graphql -f query="
mutation {
  updateIssue(input: {
    id: \"$ISSUE_2_NODE\",
    issueTypeId: \"IT_kwDOAktGus4Ac3IQ\"
  }) { issue { number } }
}"

gh api graphql -f query="
mutation {
  addSubIssue(input: {
    issueId: \"$EPIC_NODE\",
    subIssueId: \"$ISSUE_2_NODE\"
  }) { issue { id } }
}"
```

**Step 4: Set blocking relationship (Issue 1 blocks Issue 2)**

```bash
gh api graphql -f query="
mutation {
  addBlockedBy(input: {
    issueId: \"$ISSUE_2_NODE\",
    blockingIssueId: \"$ISSUE_1_NODE\"
  }) { blockedByItems { nodes { id } } }
}"
```

**Step 5: Verify**

```bash
gh issue view $ISSUE_2_NUM --json title,labels,milestone
```

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create Issue 3 — OpenRouter Key Provisioning

**Files:** None (GitHub API only)

**Step 1: Create the issue**

```bash
gh issue create \
  --title "OpenRouter key provisioning" \
  --label "type:seam,domain:llm-playground" \
  --milestone "LLM Playground" \
  --body "$(cat <<'ISSUE_BODY'
## Parent Epic

Part of #151 (LLM Playground)

## Summary

Integrate with the OpenRouter Management API to auto-mint and revoke per-student API keys. Implement Fernet encryption for key storage at rest, and server-side key resolution so keys are never exposed to the client.

## Acceptance Criteria

- **AC2.3** Instructor provisions per-student-per-unit API keys (one per provider per student per course); students cannot add their own keys
- **AC2.4** API keys are encrypted at rest and never exposed in any UI (including to students)
- **AC2.5** Per-student keys give instructor per-student budget control via the provider's own billing

## Architecture

Implement as a module within `src/promptgrimoire/llm/playground/` (key management module). Single module likely sufficient given focused scope.

If the module exceeds ~300 lines, split further.

**Key components:**
- OpenRouter Management API client (mint, revoke, list keys)
- Fernet encryption wrapper for key storage/retrieval
- Server-side key resolution (student requests → server injects key → API call)

## Blocked by

- #ISSUE_1_NUM Playground data model

## Blocks

- Course admin UI

## References

- PRD: `docs/prds/2026-02-10-llm-playground.md`
- Design: `docs/design-plans/2026-03-02-playground-issues-151.md`
- Cached docs: `docs/openrouter/key-management-api.md`
ISSUE_BODY
)"
```

Replace `#ISSUE_1_NUM` with the actual issue number.

**Step 2: Capture issue number as `ISSUE_3_NUM`**

```bash
ISSUE_3_NUM=NNN  # Replace NNN with actual number from URL
echo "export ISSUE_3_NUM=$ISSUE_3_NUM" >> "$VARS_FILE"
```

**Step 3: Set issue type to Task and link as sub-issue**

```bash
ISSUE_3_NODE=$(gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $ISSUE_3_NUM) { id }
  }
}" --jq '.data.repository.issue.id')
echo "export ISSUE_3_NODE=$ISSUE_3_NODE" >> "$VARS_FILE"

gh api graphql -f query="
mutation {
  updateIssue(input: {
    id: \"$ISSUE_3_NODE\",
    issueTypeId: \"IT_kwDOAktGus4Ac3IQ\"
  }) { issue { number } }
}"

gh api graphql -f query="
mutation {
  addSubIssue(input: {
    issueId: \"$EPIC_NODE\",
    subIssueId: \"$ISSUE_3_NODE\"
  }) { issue { id } }
}"
```

**Step 4: Set blocking relationship (Issue 1 blocks Issue 3)**

```bash
gh api graphql -f query="
mutation {
  addBlockedBy(input: {
    issueId: \"$ISSUE_3_NODE\",
    blockingIssueId: \"$ISSUE_1_NODE\"
  }) { blockedByItems { nodes { id } } }
}"
```

**Step 5: Verify**

```bash
gh issue view $ISSUE_3_NUM --json title,labels,milestone
```

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Create Issue 4 — Model Allowlist

**Files:** None (GitHub API only)

**Step 1: Create the issue**

```bash
gh issue create \
  --title "Model allowlist" \
  --label "type:seam,domain:llm-playground" \
  --milestone "LLM Playground" \
  --body "$(cat <<'ISSUE_BODY'
## Parent Epic

Part of #151 (LLM Playground)

## Summary

Implement CourseModelConfig CRUD operations, integration with OpenRouter's `/api/v1/models` endpoint to fetch model metadata, and enable/disable toggle for individual models on a per-course basis.

## Acceptance Criteria

- **AC2.1** Instructor can add models to a course allowlist with display name, privacy notes, hosting region, and cost tier
- **AC2.2** Instructor can enable/disable individual models without deleting them

## Architecture

Implement across two locations:
- `src/promptgrimoire/db/` — CRUD operations for CourseModelConfig
- `src/promptgrimoire/llm/playground/` — OpenRouter API fetch for model metadata

Single modules in each location likely sufficient. If any module exceeds ~300 lines, split further.

## Blocked by

- #ISSUE_1_NUM Playground data model

## Blocks

- Course admin UI

## References

- PRD: `docs/prds/2026-02-10-llm-playground.md`
- Design: `docs/design-plans/2026-03-02-playground-issues-151.md`
ISSUE_BODY
)"
```

Replace `#ISSUE_1_NUM` with the actual issue number.

**Step 2: Capture issue number as `ISSUE_4_NUM`**

```bash
ISSUE_4_NUM=NNN  # Replace NNN with actual number from URL
echo "export ISSUE_4_NUM=$ISSUE_4_NUM" >> "$VARS_FILE"
```

**Step 3: Set issue type to Task and link as sub-issue**

```bash
ISSUE_4_NODE=$(gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $ISSUE_4_NUM) { id }
  }
}" --jq '.data.repository.issue.id')
echo "export ISSUE_4_NODE=$ISSUE_4_NODE" >> "$VARS_FILE"

gh api graphql -f query="
mutation {
  updateIssue(input: {
    id: \"$ISSUE_4_NODE\",
    issueTypeId: \"IT_kwDOAktGus4Ac3IQ\"
  }) { issue { number } }
}"

gh api graphql -f query="
mutation {
  addSubIssue(input: {
    issueId: \"$EPIC_NODE\",
    subIssueId: \"$ISSUE_4_NODE\"
  }) { issue { id } }
}"
```

**Step 4: Set blocking relationship (Issue 1 blocks Issue 4)**

```bash
gh api graphql -f query="
mutation {
  addBlockedBy(input: {
    issueId: \"$ISSUE_4_NODE\",
    blockingIssueId: \"$ISSUE_1_NODE\"
  }) { blockedByItems { nodes { id } } }
}"
```

**Step 5: Verify all 4 issues**

```bash
# List all issues with our labels
gh issue list --label "type:seam" --label "domain:llm-playground" --milestone "LLM Playground" --state open

# Verify blocking relationships exist
echo "Issue 2 blocked by:"
gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $ISSUE_2_NUM) {
      title
      blockedBy(first: 5) { nodes { number title } }
    }
  }
}" --jq '.data.repository.issue'
```

**Step 6: Commit the phase plan (if running in a branch)**

This phase creates no local files — all work is GitHub API calls. No commit needed.

<!-- END_TASK_4 -->
