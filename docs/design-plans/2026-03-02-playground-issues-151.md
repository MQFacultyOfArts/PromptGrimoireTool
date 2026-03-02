# LLM Playground Issue Hierarchy Design

**GitHub Issue:** #151

## Summary

This document designs the GitHub issue hierarchy for the LLM Playground feature (epic #151). The playground will allow students to interact with AI language models directly within PromptGrimoire — choosing from an instructor-approved model list, sending messages with file attachments, editing and regenerating responses, and exporting conversations to the annotation workspace. Instructors control which models are available per course, provision API keys through OpenRouter, and can review student conversations. The work spans 12 independently implementable components (seams), plus 3 standalone issues for deferred concerns.

The design task is not to build the playground — it is to decompose the playground PRD into a correctly structured issue hierarchy on GitHub before implementation begins. The 12 sub-issues are arranged in a dependency DAG: a single data model issue (seam 1) unlocks two parallel tracks, one for the student-facing chat experience and one for instructor configuration. Each issue is written to a standard template and labelled, milestoned, and dependency-linked according to conventions established by an earlier epic (#92). The output of this design work is a set of GitHub issues that any developer can claim and implement without needing to read the full PRD.

## Definition of Done

- Complete hierarchy of GitHub issues under epic #151, each an independently implementable architectural component (seam model from #92)
- Provider abstraction designed for N providers; OpenRouter is first implementation, direct Anthropic is a future adapter issue
- All issues assigned to "LLM Playground" milestone; user redistributes to "6 Mar" as needed
- Every PRD acceptance criterion (AC1–AC8) covered by at least one issue
- Blocker/dependency relationships established via GitHub's dependency graph
- Epic #151 body updated with linked checklist of all sub-issues
- Usage dashboard created as standalone issue outside the epic

## Acceptance Criteria

### playground-issues-151.AC1: All PRD acceptance criteria covered
- **playground-issues-151.AC1.1 Success:** Each of the 38 PRD ACs (AC1.1–AC8.6) is assigned to at least one sub-issue
- **playground-issues-151.AC1.2 Success:** AC6.4 has primary ownership in Issue 7 (edit triggers audit write); Issue 8 provides the audit infrastructure and references AC6.4 in its architecture note
- **playground-issues-151.AC1.3 Failure:** An AC appears in zero issues → gap in coverage

### playground-issues-151.AC2: Issue structure follows seam model
- **playground-issues-151.AC2.1 Success:** All 12 sub-issues have `type:seam` label
- **playground-issues-151.AC2.2 Success:** All 12 sub-issues have `domain:llm-playground` label
- **playground-issues-151.AC2.3 Success:** All 12 sub-issues assigned to "LLM Playground" milestone
- **playground-issues-151.AC2.4 Success:** Each issue body contains summary, ACs, architecture note, blocker references, and PRD/design doc links

### playground-issues-151.AC3: Dependency graph is correct
- **playground-issues-151.AC3.1 Success:** All blocker relationships from the DAG table are established in GitHub's dependency graph
- **playground-issues-151.AC3.2 Success:** No circular dependencies exist
- **playground-issues-151.AC3.3 Success:** Issues 2, 3, 4 are blocked only by issue 1 (maximum initial parallelism)
- **playground-issues-151.AC3.4 Failure:** An issue has a missing blocker relationship → dependency not tracked

### playground-issues-151.AC4: Package architecture communicated
- **playground-issues-151.AC4.1 Success:** Issues 2 and 5 include package structure with suggested module breakdown in their architecture note
- **playground-issues-151.AC4.2 Success:** All issues reference the ~300 line threshold for package splitting

### playground-issues-151.AC5: Epic body updated
- **playground-issues-151.AC5.1 Success:** Epic #151 body contains checklist with all 12 sub-issue numbers linked
- **playground-issues-151.AC5.2 Success:** "Related" section lists the 3 standalone issues
- **playground-issues-151.AC5.3 Success:** Original context (PRD reference, provider approach, deferred items) preserved

### playground-issues-151.AC6: Standalone issues created
- **playground-issues-151.AC6.1 Success:** Direct Anthropic adapter, Usage dashboard, and Conversation forking exist as separate issues
- **playground-issues-151.AC6.2 Success:** All 3 have `phase:post-mvp` and `domain:llm-playground` labels
- **playground-issues-151.AC6.3 Success:** None assigned to a milestone

## Glossary

- **Epic**: A GitHub issue used as a parent container, tracking a large feature through a checklist of linked sub-issues. Epic #151 is the LLM Playground epic.
- **Seam**: An architectural boundary where one independently implementable component meets another. Seams are the unit of work decomposition in this project's issue model; each sub-issue corresponds to one seam.
- **PRD (Product Requirements Document)**: A document specifying what a feature must do. The referenced PRD is `docs/prds/2026-02-10-llm-playground.md` and contains 38 acceptance criteria (AC1.1–AC8.6).
- **DAG (Directed Acyclic Graph)**: A dependency graph with no cycles. Used here to describe which issues must complete before others can begin.
- **Dependency graph**: GitHub's built-in mechanism for expressing blocker relationships between issues via "Blocked by" / "Blocks" links.
- **OpenRouter**: A third-party API aggregation service that routes requests to many language model providers under a single API key. Used here so the application does not need direct integrations with each provider.
- **Provider abstraction**: A protocol (interface) layer that decouples the chat UI from any specific LLM API. Designed to support N providers; OpenRouter is the first implementation.
- **pydantic-ai**: A Python library for building AI-powered applications with structured, type-safe agent workflows. Used to wrap the provider API calls.
- **Fernet encryption**: Symmetric authenticated encryption from the Python `cryptography` package. Used to store OpenRouter API keys at rest.
- **JSONL audit trail**: A newline-delimited JSON log where each line records one event (request, response, timing, cost, student, course). Append-only.
- **CRDT**: Conflict-free Replicated Data Type. A data structure that supports concurrent edits without coordination. Used in PromptGrimoire's annotation workspace for real-time collaboration.
- **`@ui.refreshable`**: A NiceGUI decorator that marks a function as re-renderable in place without a full page reload. Referenced in the message editing issue as the mechanism for in-place message updates.
- **WorkspaceDocument**: The application's core model for a piece of annotatable content. Playground conversations are exported into this form to enter the annotation pipeline.
- **Alembic**: A database schema migration tool for SQLAlchemy/SQLModel. All schema changes must go through Alembic migrations, never `create_all()`.
- **Milestone**: A GitHub construct grouping issues by delivery target. "LLM Playground" is the milestone for all 12 sub-issues; weekly milestones are assigned by the user separately.
- **`type:seam` / `domain:llm-playground`**: GitHub label taxonomy conventions used in this project. Labels use colon-prefixed namespaces (`type:`, `phase:`, `domain:`) to categorise issues by kind, delivery phase, and feature domain.
- **Vision capability gating**: Conditionally enabling image attachment features only when the selected model supports vision input.

## Architecture

12 sub-issues under epic #151, each an independently implementable architectural component (`type:seam`). 3 standalone issues outside the epic for deferred/cross-cutting concerns. All sub-issues assigned to "LLM Playground" milestone with `domain:llm-playground` label.

### Component List

| # | Issue Title | Scope | Package Path |
|---|------------|-------|-------------|
| 1 | Playground data model | CourseModelConfig, StudentAPIKey (full column set incl. `openrouter_key_hash`, `budget_limit`, `budget_reset`, `expires_at`), PlaygroundConversation (incl. `shared_with` for future collaboration), PlaygroundMessage tables + Alembic migration | `src/promptgrimoire/db/models.py` (models), `alembic/versions/` (migration) |
| 2 | Provider abstraction | N-provider protocol, OpenRouter adapter, pydantic-ai Agent factory, streaming event handler | `src/promptgrimoire/llm/playground/` |
| 3 | OpenRouter key provisioning | Management API integration, auto-mint/revoke lifecycle, Fernet encryption, server-side resolution | `src/promptgrimoire/llm/playground/` (key management module) |
| 4 | Model allowlist | CourseModelConfig CRUD, OpenRouter `/api/v1/models` metadata fetch, enable/disable | `src/promptgrimoire/db/` (CRUD), `src/promptgrimoire/llm/playground/` (API fetch) |
| 5 | Core chat UI | NiceGUI page at `/playground`, system prompt, message rendering, streaming, parameter controls, model picker, metadata, "Copy API JSON", cancel | `src/promptgrimoire/pages/playground/` |
| 6 | Persistence & conversation history | Auto-save, conversation list, resume, workspace auto-creation | `src/promptgrimoire/db/` (persistence), `src/promptgrimoire/pages/playground/` (list UI) |
| 7 | Message editing & regeneration | Edit user/assistant messages in place, regenerate responses, `@ui.refreshable` per message | `src/promptgrimoire/pages/playground/` (editing components) |
| 8 | JSONL audit trail | Extend `llm/log.py`, full request/response/timing/cost/student/course logging, append-only | `src/promptgrimoire/llm/` (log extension) |
| 9 | File attachments | `ui.upload`, workspace file storage, reference chips, base64 images for vision, capability gating | `src/promptgrimoire/pages/playground/` (upload UI), `src/promptgrimoire/db/` (storage) |
| 10 | Export to annotation | Conversation → structured HTML → `WorkspaceDocument(source_type="playground")` → input pipeline | `src/promptgrimoire/export/` or `src/promptgrimoire/pages/playground/` (serialiser) |
| 11 | Course admin UI | Model config UI on courses page, key provisioning UI, instructor read-only conversation view | `src/promptgrimoire/pages/courses/` (refactor to package if needed) |
| 12 | Collaboration seams | Shared workspace access, real-time stream sharing, user identification, instructor sharing, CRDT integration docs | `src/promptgrimoire/pages/playground/` (sharing), `docs/` (CRDT docs) |

**Standalone issues (outside epic):**

| Title | Type | Rationale |
|-------|------|-----------|
| Direct Anthropic adapter | `type:seam` | Second provider; depends on #2's interface but independent enhancement |
| Usage dashboard | `type:seam` | Instructor analytics spanning beyond playground |
| Conversation forking | `type:prd` | Mentioned in PRD glossary, no ACs; needs own design work |

### Package Architecture Constraint

Each issue body includes an architecture note specifying whether the implementation should be a package (directory with `__init__.py` and focused modules) or a single module. The threshold: if a component is likely to exceed ~300 lines, it must be a package.

Issues requiring package structure:

- **Issue 2 (Provider Abstraction)** → `src/promptgrimoire/llm/playground/`
  - `__init__.py` — public exports
  - `provider.py` — N-provider protocol
  - `openrouter.py` — OpenRouter adapter
  - `streaming.py` — event handler (thinking/text/metadata)

- **Issue 5 (Core Chat UI)** → `src/promptgrimoire/pages/playground/` (following `pages/annotation/` pattern)
  - `__init__.py` — page route, page-level state
  - `system_prompt.py` — system prompt card
  - `message.py` — message rendering (user + assistant)
  - `streaming.py` — live streaming display
  - `controls.py` — parameter controls, model picker
  - `metadata.py` — token/cost/params byline, copy API JSON

Issues where a single module suffices: 1, 3, 4, 8, 10. Issues 6, 7, 9, 11, 12 add modules to existing packages.

### Dependency DAG

Two parallel tracks share only the data model as common root:

```
Track A (student-facing):
  1. Data Model
    → 2. Provider Abstraction → 5. Core Chat UI → 7. Message Editing
                                    ↓
                              6. Persistence → 9. File Attachments
                                    ↓         → 10. Export to Annotation
                                    ↓         → 12. Collaboration Seams
    → 8. JSONL Audit (parallel, branches off data model + provider)

Track B (instructor-facing):
  1. Data Model
    → 3. Key Provisioning  ──→ 11. Course Admin UI
    → 4. Model Allowlist   ──→ 11. Course Admin UI
```

Explicit blocker relationships (for GitHub dependency graph):

| Issue | Blocked by |
|-------|-----------|
| 2. Provider Abstraction | 1 |
| 3. Key Provisioning | 1 |
| 4. Model Allowlist | 1 |
| 5. Core Chat UI | 1, 2 |
| 6. Persistence & History | 1, 5 |
| 7. Message Editing | 5, 6 |
| 8. JSONL Audit | 1, 2 |
| 9. File Attachments | 6 |
| 10. Export to Annotation | 6 |
| 11. Course Admin UI | 3, 4 |
| 12. Collaboration Seams | 6 |

Maximum parallelism after Data Model: issues 2, 3, 4 can start simultaneously. Issue 8 can start once 2 completes (parallel to Chat UI work).

### PRD Acceptance Criteria Coverage

Every AC from the PRD (`docs/prds/2026-02-10-llm-playground.md`) maps to at least one issue:

- **AC1** (transparency): all 6 criteria → Issue 5
- **AC2** (instructor config): AC2.1–2.2 → Issue 4; AC2.3–2.5 → Issue 3; AC2.6 → Issue 11
- **AC3** (provider abstraction): AC3.1–3.3, AC3.5 → Issue 2; AC3.4, AC3.6 → Issue 5
- **AC4** (persistence/audit): AC4.1–4.2, AC4.5 → Issue 6; AC4.3–4.4 → Issue 8
- **AC5** (export): all 3 criteria → Issue 10
- **AC6** (editing): AC6.1–6.3 → Issue 7; AC6.4 primary owner Issue 7, Issue 8 provides audit infrastructure
- **AC7** (file attachments): all 6 criteria → Issue 9
- **AC8** (collaboration): all 6 criteria → Issue 12

### Issue Body Template

Each sub-issue follows this structure:

```markdown
## Summary
[1-2 sentence scope description]

## Acceptance Criteria
[PRD ACs assigned to this issue, copied verbatim]

## Architecture
Implement as `path/to/package/` (not a single file). Suggested modules:
- `module.py` — responsibility

Follow the `pages/annotation/` pattern. If any module exceeds ~300 lines, split further.

## Blocked by
- #NNN [issue title]

## Blocks
- #NNN [issue title]

## References
- PRD: `docs/prds/2026-02-10-llm-playground.md`
- Design: `docs/design-plans/2026-03-02-playground-issues-151.md`
- Cached docs: [relevant docs/ files]
```

## Existing Patterns

Investigation found the following patterns in the codebase that this design follows:

**Epic #92 seam model.** Epic #92 (Annotation Workspace Platform) used 8 seams (A–H) as sub-issues, each independently implementable with explicit dependencies noted in the epic body as a checklist. This design follows the same pattern with 12 seams.

**Label taxonomy.** Existing labels use `type:`, `phase:`, and `domain:` prefixes. This design adds `domain:llm-playground` following the established convention.

**Milestone structure.** "LLM Playground" milestone already exists (due 2026-03-12). All sub-issues are assigned to it; the user redistributes to weekly milestones as needed.

**No divergence from existing patterns.** The issue hierarchy follows established conventions exactly.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Label and Milestone Setup

**Goal:** Create the `domain:llm-playground` label so all issues can be labelled consistently.

**Components:**
- `domain:llm-playground` label via `gh label create`
- Verify "LLM Playground" milestone exists

**Dependencies:** None

**Done when:** Label exists, milestone confirmed.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Create Sub-Issues 1–4 (Foundation + Instructor Backend)

**Goal:** Create the data model issue and the three issues that depend only on it (provider, key provisioning, model allowlist). These form the widest parallelism point.

**Components:**
- Issue: Playground data model (seam 1)
- Issue: Provider abstraction (seam 2)
- Issue: OpenRouter key provisioning (seam 3)
- Issue: Model allowlist (seam 4)

Each issue created with full body (summary, ACs, architecture note, blocker references, PRD/design doc links).

**Dependencies:** Phase 1 (label exists)

**Done when:** 4 issues created with correct labels, milestone, and dependency relationships in GitHub's graph.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Create Sub-Issues 5–8 (Core Student Experience)

**Goal:** Create the chat UI, persistence, message editing, and JSONL audit issues. Set up dependency graph links to Phase 2 issues.

**Components:**
- Issue: Core chat UI (seam 5) — blocked by 1, 2
- Issue: Persistence & conversation history (seam 6) — blocked by 1, 5
- Issue: Message editing & regeneration (seam 7) — blocked by 5, 6
- Issue: JSONL audit trail (seam 8) — blocked by 1, 2

**Dependencies:** Phase 2 (issues 1–4 exist for cross-referencing)

**Done when:** 4 issues created with correct dependency graph relationships.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Create Sub-Issues 9–12 (Advanced Features)

**Goal:** Create file attachments, export, course admin UI, and collaboration seams issues. Complete the dependency graph.

**Components:**
- Issue: File attachments (seam 9) — blocked by 6
- Issue: Export to annotation (seam 10) — blocked by 6
- Issue: Course admin UI (seam 11) — blocked by 3, 4
- Issue: Collaboration seams (seam 12) — blocked by 6

**Dependencies:** Phase 3 (issues 5–8 exist for cross-referencing)

**Done when:** 4 issues created. All 12 sub-issues have correct dependency graph relationships.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Create Standalone Issues

**Goal:** Create the 3 issues outside the epic for deferred/cross-cutting concerns.

**Components:**
- Issue: Direct Anthropic adapter (`type:seam`, `phase:post-mvp`, `domain:llm-playground`)
- Issue: Usage dashboard (`type:seam`, `phase:post-mvp`, `domain:llm-playground`)
- Issue: Conversation forking (`type:prd`, `phase:post-mvp`, `domain:llm-playground`)

**Dependencies:** Phase 2 (Anthropic adapter references issue 2's provider interface)

**Done when:** 3 standalone issues created with correct labels. Not assigned to any milestone.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Update Epic #151 Body

**Goal:** Replace the epic body with a structured checklist linking all sub-issues (following #92 pattern) while preserving the PRD reference and provider approach context.

**Components:**
- Epic #151 body rewrite with linked checklist
- "Related" section for standalone issues
- Preserve foundational PRD reference and deferred items list

**Dependencies:** Phases 2–5 (all issues exist with real numbers)

**Done when:** Epic #151 body shows all 12 sub-issues as a checklist with issue numbers, plus related standalone issues.
<!-- END_PHASE_6 -->

## Additional Considerations

**Issue creation order matters.** GitHub's dependency graph requires issues to exist before they can be linked. Phases 2–4 create issues in dependency order so blockers can reference real issue numbers.

**Epic body preservation.** The current epic body contains valuable context (MVP scope, provider approach, deferred items). Phase 6 should preserve this context while adding the checklist structure, not replace it entirely.

**Collaboration schema in Issue 1.** `PlaygroundConversation.shared_with: list[UUID] | None` is included in the data model migration (Issue 1) so Issue 12 (Collaboration Seams) only needs to build UI and server-push logic, not alter the schema. This was surfaced by proleptic challenge — placing schema additions late in the DAG risks mid-sprint migrations.

**StudentAPIKey full column set in Issue 1.** The data model includes the full column set for `StudentAPIKey` (including `openrouter_key_hash`, `budget_limit`, `budget_reset`, `expires_at`) derived from the cached OpenRouter Management API docs (`docs/openrouter/key-management-api.md`). This avoids Issue 3 needing a follow-on migration. If the Management API surprises us, Issue 3 can still add columns, but the risk is much lower.

**AC6.4 ownership.** AC6.4 ("Edits update the database record; original content is preserved in the JSONL archive") has primary ownership in Issue 7 (Message Editing), which triggers the audit write. Issue 8 (JSONL Audit) provides the audit log infrastructure and references AC6.4 in its architecture note. This resolves the dual-ownership concern from proleptic challenge.
