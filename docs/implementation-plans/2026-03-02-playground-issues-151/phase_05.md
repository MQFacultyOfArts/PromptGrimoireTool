# LLM Playground Issue Hierarchy — Phase 5: Standalone Issues

**Goal:** Create 3 standalone issues outside the epic for deferred/cross-cutting concerns. Not assigned to any milestone.

**Architecture:** Same `gh issue create` + GraphQL pattern. These issues are NOT sub-issues of epic #151 — they are standalone with `phase:post-mvp` labels.

**Tech Stack:** `gh` CLI, GitHub GraphQL API

**Scope:** Phase 5 of 6

**Codebase verified:** 2026-03-02

---

## Acceptance Criteria Coverage

This phase implements and verifies:

### playground-issues-151.AC6: Standalone issues created
- **playground-issues-151.AC6.1 Success:** Direct Anthropic adapter, Usage dashboard, and Conversation forking exist as separate issues
- **playground-issues-151.AC6.2 Success:** All 3 have `phase:post-mvp` and `domain:llm-playground` labels
- **playground-issues-151.AC6.3 Success:** None assigned to a milestone

---

**Prerequisite:** Phase 2 must have completed. Source persisted variables:

```bash
VARS_FILE="/tmp/playground-issues-151-vars.sh"
source "$VARS_FILE"
echo "ISSUE_2_NUM=$ISSUE_2_NUM"
```

<!-- START_TASK_1 -->
### Task 1: Create Standalone Issue — Direct Anthropic Adapter

**Files:** None (GitHub API only)

**Step 1: Create the issue**

```bash
gh issue create \
  --title "Direct Anthropic adapter" \
  --label "type:seam,phase:post-mvp,domain:llm-playground" \
  --body "$(cat <<'ISSUE_BODY'
## Summary

Implement a direct Anthropic provider adapter for the playground's provider abstraction layer (defined in #ISSUE_2_NUM). This is the second provider after OpenRouter, enabling native Anthropic API access with first-class thinking support.

## Rationale

Second provider; depends on #ISSUE_2_NUM's interface but is an independent enhancement. Deferred from MVP because OpenRouter already supports Anthropic models — this adapter adds direct API access for lower latency and native feature support.

## Architecture

Implement as an additional module in `src/promptgrimoire/llm/playground/` (e.g., `anthropic.py`), implementing the N-provider protocol defined in Issue #ISSUE_2_NUM.

If the module exceeds ~300 lines, split further.

## Dependencies

- #ISSUE_2_NUM Provider abstraction (provides the protocol interface)

## References

- PRD: `docs/prds/2026-02-10-llm-playground.md`
- Design: `docs/design-plans/2026-03-02-playground-issues-151.md`
ISSUE_BODY
)"
```

Replace `#ISSUE_2_NUM` with actual issue number.

**Step 2: Capture issue number as `STANDALONE_1_NUM`**

```bash
STANDALONE_1_NUM=NNN  # Replace NNN with actual number from URL
echo "export STANDALONE_1_NUM=$STANDALONE_1_NUM" >> "$VARS_FILE"
```

**Step 3: Set issue type to Task**

```bash
STANDALONE_1_NODE=$(gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $STANDALONE_1_NUM) { id }
  }
}" --jq '.data.repository.issue.id')

gh api graphql -f query="
mutation {
  updateIssue(input: {
    id: \"$STANDALONE_1_NODE\",
    issueTypeId: \"IT_kwDOAktGus4Ac3IQ\"
  }) { issue { number } }
}"
```

**Step 4: Verify — no milestone, correct labels**

```bash
gh issue view $STANDALONE_1_NUM --json title,labels,milestone
```

Expected: Title "Direct Anthropic adapter", labels include `type:seam`, `phase:post-mvp`, `domain:llm-playground`. Milestone should be empty/null.

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create Standalone Issue — Usage Dashboard

**Files:** None (GitHub API only)

**Step 1: Create the issue**

```bash
gh issue create \
  --title "Usage dashboard" \
  --label "type:seam,phase:post-mvp,domain:llm-playground" \
  --body "$(cat <<'ISSUE_BODY'
## Summary

Build an instructor-facing usage dashboard showing aggregate and per-student API usage statistics: token counts, costs, model distribution, usage over time. Spans beyond the playground to provide a unified view of all LLM usage in a course.

## Rationale

Instructor analytics spanning beyond playground. Deferred from MVP because the JSONL audit trail (which provides the data) is implemented first, and dashboard design benefits from real usage data.

## Architecture

Location TBD — likely a new page route or a section within the courses admin UI. Will aggregate data from the JSONL audit trail and/or database.

If any module exceeds ~300 lines, split further.

## Dependencies

- JSONL audit trail (provides the usage data to aggregate)
- Persistence & conversation history (provides conversation metadata)

## References

- PRD: `docs/prds/2026-02-10-llm-playground.md`
- Design: `docs/design-plans/2026-03-02-playground-issues-151.md`
ISSUE_BODY
)"
```

**Step 2: Capture issue number as `STANDALONE_2_NUM`**

```bash
STANDALONE_2_NUM=NNN  # Replace NNN with actual number from URL
echo "export STANDALONE_2_NUM=$STANDALONE_2_NUM" >> "$VARS_FILE"
```

**Step 3: Set issue type to Task**

```bash
STANDALONE_2_NODE=$(gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $STANDALONE_2_NUM) { id }
  }
}" --jq '.data.repository.issue.id')

gh api graphql -f query="
mutation {
  updateIssue(input: {
    id: \"$STANDALONE_2_NODE\",
    issueTypeId: \"IT_kwDOAktGus4Ac3IQ\"
  }) { issue { number } }
}"
```

**Step 4: Verify**

```bash
gh issue view $STANDALONE_2_NUM --json title,labels,milestone
```

Expected: No milestone. Labels include `type:seam`, `phase:post-mvp`, `domain:llm-playground`.

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create Standalone Issue — Conversation Forking

**Files:** None (GitHub API only)

**Step 1: Create the issue**

```bash
gh issue create \
  --title "Conversation forking" \
  --label "type:prd,phase:post-mvp,domain:llm-playground" \
  --body "$(cat <<'ISSUE_BODY'
## Summary

Design and implement conversation forking: the ability to branch a conversation at any point, creating a new conversation that shares history up to the fork point but diverges afterwards.

## Rationale

Mentioned in PRD glossary but has no acceptance criteria — needs its own design work (PRD) before implementation. Deferred from MVP.

## Architecture

Needs own PRD and design plan. Key design questions:
- How does forking interact with the JSONL audit trail?
- Does the forked conversation share or copy message records?
- How is the fork relationship represented in the data model?
- How does forking interact with collaboration (shared workspaces)?

## Dependencies

- Playground data model (schema implications)
- Persistence & conversation history (fork mechanics)

## References

- PRD: `docs/prds/2026-02-10-llm-playground.md` (glossary mention only)
- Design: `docs/design-plans/2026-03-02-playground-issues-151.md`
ISSUE_BODY
)"
```

**Step 2: Capture issue number as `STANDALONE_3_NUM`**

```bash
STANDALONE_3_NUM=NNN  # Replace NNN with actual number from URL
echo "export STANDALONE_3_NUM=$STANDALONE_3_NUM" >> "$VARS_FILE"
```

**Step 3: Set issue type to Feature**

```bash
STANDALONE_3_NODE=$(gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $STANDALONE_3_NUM) { id }
  }
}" --jq '.data.repository.issue.id')

gh api graphql -f query="
mutation {
  updateIssue(input: {
    id: \"$STANDALONE_3_NODE\",
    issueTypeId: \"IT_kwDOAktGus4Ac3IX\"
  }) { issue { number } }
}"
```

**Step 4: Verify all 3 standalone issues**

```bash
# List all post-mvp playground issues (should include the 3 standalone ones)
gh issue list --label "phase:post-mvp" --label "domain:llm-playground" --state open
```

Expected: 3 issues, none with a milestone.

<!-- END_TASK_3 -->
