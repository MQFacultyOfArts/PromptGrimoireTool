# Test Requirements: LLM Playground Issue Hierarchy

## Overview

This document maps each acceptance criterion to a verification method. Since all deliverables are GitHub issues created via `gh` CLI and GraphQL API, verification is either automated CLI commands (already present in the phase files) or human inspection of issue body content.

## Automated Verification

| AC | Criterion | Verification Command | Phase.Task |
|----|-----------|---------------------|------------|
| AC2.1 | All 12 sub-issues have `type:seam` label | `gh issue list --label "type:seam" --label "domain:llm-playground" --milestone "LLM Playground" --state open --limit 20` (expect exactly 12) | P6.T2 Step 1 |
| AC2.2 | All 12 sub-issues have `domain:llm-playground` label | Same command as AC2.1 — both labels are filter criteria, so 12 results confirms both present on all | P6.T2 Step 1 |
| AC2.3 | All 12 sub-issues assigned to "LLM Playground" milestone | Same command as AC2.1 — `--milestone` filter is applied, 12 results confirms all assigned | P6.T2 Step 1 |
| AC3.1 | All blocker relationships from the DAG table are established in GitHub's dependency graph | Spot-check via GraphQL `blockedBy` queries on Issues 5, 7, 11 (representative of each DAG path) | P6.T2 Step 2 |
| AC3.2 | No circular dependencies exist | `addBlockedBy` mutations reject cycles; successful execution is proof of acyclicity. Spot-checks provide additional confidence. | P4.T4 Step 4, P6.T2 Step 2 |
| AC4.1 | All 12 issues are linked as sub-issues of epic #151 | `gh api graphql` query on issue 151's `subIssues(first: 15)` — expect `totalCount: 12` | P6.T1 Step 3 |
| AC5.1 | Epic #151 body contains checklist with all 12 sub-issue numbers linked | `gh issue view 151 --json body --jq '.body' \| grep -c "^\- \["` (expect 12) | P6.T2 Step 4 |
| AC5.2 | "Related" section lists the 3 standalone issues | `gh issue view 151 --json body --jq '.body' \| grep "## Related" -A 5` (expect 3 issue refs) | P6.T2 Step 4 |
| AC6.1 | Direct Anthropic adapter, Usage dashboard, and Conversation forking exist as separate issues | `gh issue list --label "phase:post-mvp" --label "domain:llm-playground" --state open` (expect 3) | P5.T3 Step 4 |
| AC6.2 | All 3 have `phase:post-mvp` and `domain:llm-playground` labels | Same command as AC6.1 — both labels are filter criteria | P5.T3 Step 4 |
| AC6.3 | None assigned to a milestone | `gh issue view $STANDALONE_N_NUM --json milestone` for each (expect null) | P5.T1-T3 Step 4 |

## Human Verification

| AC | Criterion | Justification | Verification Approach |
|----|-----------|---------------|----------------------|
| AC1.1 | Each of the 38 PRD ACs (AC1.1-AC8.6) is assigned to at least one sub-issue | ACs are embedded as free-text markdown in issue bodies, not structured metadata — no CLI command can cross-reference | Open each of the 12 sub-issue bodies and confirm the ACs listed match the coverage table in the design plan |
| AC2.4 | Each issue body contains summary, ACs, architecture note, blocker references, and PRD/design doc links | Issue body structure is free-form markdown; CLI can confirm body is non-empty but cannot validate section presence without brittle text matching | For each of the 12 sub-issues, verify the body contains: (1) `## Summary`, (2) `## Acceptance Criteria`, (3) `## Architecture` with ~300 line threshold, (4) `## Blocked by`, (5) `## References` with PRD and design doc paths |
| AC3.1 | All blocker relationships from the DAG table are established (full verification beyond spot-checks) | Spot-checks cover 3 of 11 blocker relationships; full verification requires querying all 11 edges | Query `blockedBy` for each of Issues 2-12 and confirm against the DAG table. Could be scripted as a loop. |
| AC5.3 | Original context (PRD reference, provider approach, deferred items) preserved | Checking specific prose sections exist requires reading the body | Read epic #151 body and confirm: (1) `## Foundational PRD` with path to PRD, (2) `## Provider Approach` with OpenRouter/pydantic-ai strategy, (3) deferred items mentioned |

## Verification Execution Order

1. **After Phase 1** (P1.T1-T2): Verify label and milestone exist
2. **After Phase 2** (P2.T1-T4): Verify 4 issues with labels, milestone, blocking (Issues 2,3,4 blocked only by 1)
3. **After Phase 3** (P3.T1-T4): Verify 8 total issues, blocking relationships for Issues 5-8
4. **After Phase 4** (P4.T1-T4): Verify 12 total issues, all blocking relationships complete, no cycles
5. **After Phase 5** (P5.T1-T3): Verify 3 standalone issues with correct labels and no milestone
6. **After Phase 6** (P6.T1-T2): Full verification sweep — epic body, sub-issue links, all ACs

## Notes

- **AC3.1 partial automation**: Phase files include spot-checks for 3 representative dependency edges (P6.T2 Step 2). Full verification of all 11 edges is listed under Human Verification but could be scripted.
- **AC3.2 cycle detection**: GitHub's `addBlockedBy` mutation rejects cycles, so successful execution of all blocking mutations in Phases 2-4 is itself proof of acyclicity.
- **AC2.4 section validation**: Could be partially automated with grep for section headers, but is fragile and better done by human review during issue creation.
