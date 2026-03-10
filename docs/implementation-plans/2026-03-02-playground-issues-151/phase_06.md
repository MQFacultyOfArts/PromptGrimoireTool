# LLM Playground Issue Hierarchy — Phase 6: Update Epic #151 Body

**Goal:** Rewrite the epic #151 body with a structured checklist linking all 12 sub-issues (following the #92 pattern), a Related section for standalone issues, and preserved original context.

**Architecture:** Single `gh issue edit` command with the new body content.

**Tech Stack:** `gh` CLI

**Scope:** Phase 6 of 6

**Codebase verified:** 2026-03-02

---

## Acceptance Criteria Coverage

This phase implements and verifies:

### playground-issues-151.AC5: Epic body updated
- **playground-issues-151.AC5.1 Success:** Epic #151 body contains checklist with all 12 sub-issue numbers linked
- **playground-issues-151.AC5.2 Success:** "Related" section lists the 3 standalone issues
- **playground-issues-151.AC5.3 Success:** Original context (PRD reference, provider approach, deferred items) preserved

---

**Prerequisite:** All phases 2–5 must have completed. Source persisted variables:

```bash
VARS_FILE="/tmp/playground-issues-151-vars.sh"
source "$VARS_FILE"
# Verify all 15 issue numbers are set:
echo "Issues 1-12: $ISSUE_1_NUM $ISSUE_2_NUM $ISSUE_3_NUM $ISSUE_4_NUM $ISSUE_5_NUM $ISSUE_6_NUM $ISSUE_7_NUM $ISSUE_8_NUM $ISSUE_9_NUM $ISSUE_10_NUM $ISSUE_11_NUM $ISSUE_12_NUM"
echo "Standalone: $STANDALONE_1_NUM $STANDALONE_2_NUM $STANDALONE_3_NUM"
```

<!-- START_TASK_1 -->
### Task 1: Update Epic #151 Body

**Files:** None (GitHub API only)

**Step 1: Update the epic body**

```bash
gh issue edit 151 --body "$(cat <<EPIC_BODY
## Summary

A transparent, pedagogical chat interface that exposes the full LLM machinery (parameters, tokens, costs, thinking blocks) for teaching AI literacy. Inspired by chatcraft.org with educational focus.

## Progress

- [ ] #$ISSUE_1_NUM Playground data model
- [ ] #$ISSUE_2_NUM Provider abstraction
- [ ] #$ISSUE_3_NUM OpenRouter key provisioning
- [ ] #$ISSUE_4_NUM Model allowlist
- [ ] #$ISSUE_5_NUM Core chat UI
- [ ] #$ISSUE_6_NUM Persistence & conversation history
- [ ] #$ISSUE_7_NUM Message editing & regeneration
- [ ] #$ISSUE_8_NUM JSONL audit trail
- [ ] #$ISSUE_9_NUM File attachments
- [ ] #$ISSUE_10_NUM Export to annotation
- [ ] #$ISSUE_11_NUM Course admin UI
- [ ] #$ISSUE_12_NUM Collaboration seams

## Seam Dependencies

| Seam | Issue | Blocked by |
|------|-------|-----------|
| 1. Data Model | #$ISSUE_1_NUM | None |
| 2. Provider Abstraction | #$ISSUE_2_NUM | 1 |
| 3. Key Provisioning | #$ISSUE_3_NUM | 1 |
| 4. Model Allowlist | #$ISSUE_4_NUM | 1 |
| 5. Core Chat UI | #$ISSUE_5_NUM | 1, 2 |
| 6. Persistence & History | #$ISSUE_6_NUM | 1, 5 |
| 7. Message Editing | #$ISSUE_7_NUM | 5, 6 |
| 8. JSONL Audit | #$ISSUE_8_NUM | 1, 2 |
| 9. File Attachments | #$ISSUE_9_NUM | 6 |
| 10. Export to Annotation | #$ISSUE_10_NUM | 6 |
| 11. Course Admin UI | #$ISSUE_11_NUM | 3, 4 |
| 12. Collaboration Seams | #$ISSUE_12_NUM | 6 |

## Recommended Order

1. **#$ISSUE_1_NUM (1)** — foundation
2. **#$ISSUE_2_NUM (2), #$ISSUE_3_NUM (3), #$ISSUE_4_NUM (4)** — in parallel (independent, all need only 1)
3. **#$ISSUE_5_NUM (5), #$ISSUE_8_NUM (8)** — Chat UI needs 2; Audit needs 2 (parallel to each other)
4. **#$ISSUE_6_NUM (6)** — needs 5
5. **#$ISSUE_7_NUM (7), #$ISSUE_9_NUM (9), #$ISSUE_10_NUM (10), #$ISSUE_12_NUM (12)** — all need 6 (parallel)
6. **#$ISSUE_11_NUM (11)** — needs 3 and 4

## Related

Standalone issues outside this epic:

- #$STANDALONE_1_NUM Direct Anthropic adapter (`phase:post-mvp`)
- #$STANDALONE_2_NUM Usage dashboard (`phase:post-mvp`)
- #$STANDALONE_3_NUM Conversation forking (`phase:post-mvp`)

## Foundational PRD

`docs/prds/2026-02-10-llm-playground.md` — full 8-phase design with 38 acceptance criteria (AC1–AC8).

## Provider Approach

**pydantic-ai via OpenRouter** (single provider path for MVP):
- `OpenAIModel` with `base_url="https://openrouter.ai/api/v1"` and per-student API key
- Streaming via `run_stream_events()` — thinking blocks as `ThinkingPart`, text as `TextPartDelta`
- Direct Anthropic provider deferred to post-MVP standalone issue
- Docs cached: `docs/openrouter/pydantic-ai-integration.md`

## Status

Design plan: `docs/design-plans/2026-03-02-playground-issues-151.md`
Implementation plan: `docs/implementation-plans/2026-03-02-playground-issues-151/`
Issue hierarchy created with 12 sub-issues + 3 standalone post-MVP issues.
EPIC_BODY
)"
```

**Step 2: Verify the epic body**

```bash
gh issue view 151 --json body --jq '.body' | head -30
```

Expected: Body starts with "## Summary" and includes the Progress checklist with real issue numbers.

**Step 3: Verify sub-issue count in GitHub UI**

```bash
# Check that sub-issues are linked (from earlier addSubIssue mutations)
gh api graphql -f query='
{
  repository(owner: "MQFacultyOfArts", name: "PromptGrimoireTool") {
    issue(number: 151) {
      subIssues(first: 15) {
        nodes { number title }
        totalCount
      }
    }
  }
}' --jq '.data.repository.issue.subIssues'
```

Expected: 12 sub-issues listed.

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Final Verification — All Acceptance Criteria

**Step 1: Verify AC2 — Issue structure**

```bash
# All 12 sub-issues have correct labels and milestone
gh issue list --label "type:seam" --label "domain:llm-playground" --milestone "LLM Playground" --state open --limit 20
```

Expected: Exactly 12 issues.

**Step 2: Verify AC3 — Dependency graph**

Spot-check 3 dependency relationships:

```bash
# Issue 5 should be blocked by 1 and 2
gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $ISSUE_5_NUM) {
      title
      blockedBy(first: 5) { nodes { number title } }
    }
  }
}" --jq '.data.repository.issue'

# Issue 11 should be blocked by 3 and 4
gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $ISSUE_11_NUM) {
      title
      blockedBy(first: 5) { nodes { number title } }
    }
  }
}" --jq '.data.repository.issue'

# Issue 7 should be blocked by 5 and 6
gh api graphql -f query="
{
  repository(owner: \"MQFacultyOfArts\", name: \"PromptGrimoireTool\") {
    issue(number: $ISSUE_7_NUM) {
      title
      blockedBy(first: 5) { nodes { number title } }
    }
  }
}" --jq '.data.repository.issue'
```

**Step 3: Verify AC6 — Standalone issues**

```bash
# All 3 standalone issues have correct labels and no milestone
gh issue list --label "phase:post-mvp" --label "domain:llm-playground" --state open
```

Expected: 3 issues, none with a milestone.

**Step 4: Verify AC5 — Epic body**

```bash
# Check epic body has checklist and related section
gh issue view 151 --json body --jq '.body' | grep -c "^\- \["
```

Expected: 12 (checklist items).

```bash
gh issue view 151 --json body --jq '.body' | grep "## Related" -A 5
```

Expected: Related section with 3 standalone issue references.

<!-- END_TASK_2 -->
