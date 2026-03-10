# LLM Playground Issue Hierarchy Implementation Plan

**Goal:** Create the complete GitHub issue hierarchy for the LLM Playground epic (#151) — 12 sub-issues in dependency order, 3 standalone post-MVP issues, and an updated epic body.

**Architecture:** All work is GitHub issue management via `gh` CLI. No application code. Each phase creates a batch of issues, links dependencies, and verifies correctness. Issue bodies follow the seam template from epic #92.

**Tech Stack:** `gh` CLI, GitHub issue dependency graph, GitHub labels/milestones

**Scope:** 6 phases from original design (phases 1-6)

**Codebase verified:** 2026-03-02

---

## Acceptance Criteria Coverage

This phase implements:

### playground-issues-151.AC2: Issue structure follows seam model
- **playground-issues-151.AC2.2 Success:** All 12 sub-issues have `domain:llm-playground` label

### playground-issues-151.AC4: Package architecture communicated
- **playground-issues-151.AC4.2 Success:** All issues reference the ~300 line threshold for package splitting

(Label must exist before any sub-issue can be tagged with it.)

---

<!-- START_TASK_1 -->
### Task 1: Create `domain:llm-playground` label

**Files:** None (GitHub API only)

**Step 1: Create the label**

```bash
gh label create "domain:llm-playground" --description "LLM Playground feature domain" --color "1D76DB" --force
```

**Step 2: Verify the label exists**

```bash
gh label list --search "domain:llm-playground"
```

Expected: One result showing `domain:llm-playground` with colour `#1D76DB`.

**Step 3: Add label to epic #151**

```bash
gh issue edit 151 --add-label "domain:llm-playground"
```

**Step 4: Verify epic #151 labels**

```bash
gh issue view 151 --json labels --jq '.labels[].name'
```

Expected output includes: `domain:llm-playground`, `type:epic`, `phase:post-mvp`, `implementation-planned`.

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Verify "LLM Playground" milestone exists

**Files:** None (GitHub API only)

**Step 1: List milestones and confirm**

```bash
gh api repos/{owner}/{repo}/milestones --jq '.[] | select(.title == "LLM Playground") | {number, title, due_on, state}'
```

Expected: Returns milestone #10 with title "LLM Playground", due 2026-03-12, state "open".

**Step 2: Record milestone number for subsequent phases**

The milestone number is **10**. All sub-issues in phases 2-4 will use `--milestone "LLM Playground"`.

<!-- END_TASK_2 -->
