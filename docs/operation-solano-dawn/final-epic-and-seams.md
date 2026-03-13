# Operation Solano Dawn: Final Epic and Seam Issues

## Status

Revised 2026-03-06 from Codex draft. Validated against facilitator conversation
and historical run logs.

This document is the canonical handoff for implementation planning.

## Product Summary

Operation Solano Dawn is a multi-tenant wargame turn-processing system built as an activity type in PromptGrimoire.

It is not a free-chat roleplay feature. Wargame state lives in its own tables, not the existing Workspace model. The core loop is:

1. GM triggers "publish all" — approved responses released to all teams. Timer starts.
2. Teams draft moves in CRDT move buffer until hard deadline.
3. Timer fires ("courier leaves") — all move buffers lock, snapshots taken.
4. System generates one draft assistant response per team (serial) + updates game-state artifact.
5. GM reviews queue — edits, injects hidden notes, regenerates as needed.
6. Back to step 1.

## Terminology

- `submission`: one team’s locked move input for a cohort window
- `adjudication pass`: operator/model processing of one submission
- `cohort window`: shared lock/publish cycle across all teams

## Scope Boundaries

### In Scope (MVP)

- Team-based wargame runtime with one canonical stream per team
- Team collaborative move buffer (Milkdown CRDT) and persistent team notes
- Hard-deadline timer with lock/snapshot/pre-processing pipeline
- GM control workflow: review queue, edit/inject/regenerate, "publish all"
- Game-state artifact (GM-only) and student summary ("what cadets know")
- Student projection model (XML-tag-bounded visibility)
- Student document zone (read-only artifact blobs)
- End-of-run freeze and post-run per-student export
- AI calls via PydanticAI → Sonnet 4.6

### Out of Scope (MVP)

- Path to victory (OpFor subagent analysis)
- Token budget guardrails and CLI stream editing
- Automatic context summarization/compression
- Bounded concurrency generation workers
- Additional hidden tagging schema beyond current two tags
- New ACL subsystem or dedicated wargame ACL table

## Stakeholder Narratives

### Student Team Narrative

- Team enters `Wargame player room` via stable UUID route.
- Team sees projected student-visible stream, "what the cadets know" summary panel, and persistent notes.
- Team drafts in turn-scoped move buffer (CRDT, collaborative among editors).
- Timer counts down to deadline. When it fires, buffer locks and snapshot is taken.
- Empty snapshot becomes `No move submitted`.
- During processing, team cannot edit the move buffer. Notes remain editable.
- After publish, team receives one new projected assistant response and updated summary.
- At simulation end, room becomes read-only for team members but remains readable.

### GM Narrative

- GM uses `Wargame control` dashboard for one activity run.
- After timer fires, pre-processing generates one draft per team (serial AI calls).
- GM works the queue in any order: edit any message (discards thinking on AI responses), inject hidden XML-tagged notes, regenerate.
- Hidden GM content is canonical but never sent to student clients.
- When all teams are reviewed, GM triggers "publish all" to release responses and start the next timer.
- GM can trigger `end simulation for all` and run repeatable export passes.

## Core Resources and Identity

### Wargame Activity

- Owns immutable system prompt and immutable scenario bootstrap template.
- Spawns many teams.

### Team

A single resource (own tables, not the existing Workspace model). Owns:

- codename
- room identity (stable UUID, unchanged across membership/round/end-state changes)
- canonical stream (turn log)
- game-state artifact (GM-only, updated per turn)
- student summary blob ("what the cadets know", overwritten per turn)
- round state
- CRDT move buffer (turn-scoped)
- CRDT notes document (persistent)
- ACL grants (existing ACL system, per-user)

### User-Facing Surfaces

- **Wargame player room**: team-facing. Turn panel, move buffer, notes, student document zone.
- **Wargame control**: GM-facing. Review queue, edit/regenerate/inject, "publish all".

## Prompt, History, and Message Model

### Prompt Pair

- Immutable system prompt per activity run.
- Immutable scenario bootstrap (first canonical user message) with codename substitution.
- Codename generation occurs during template expansion and is random-on-create (not deterministic).
- Codename format is single-word operation style (for example, ANODE/HEDGEROW/CATALYST style), then persisted as immutable for that team.

### Canonical History

- Full canonical history is sent to model calls in MVP.
- No automatic summarization seam in MVP.
- AI calls use PydanticAI → Sonnet 4.6 with full turn history + latest game-state artifact.

### Canonical Message Schema

- Message persistence must preserve enough structure to reconstruct model calls (role, content, metadata).
- The exact schema (PydanticAI mirroring vs simpler custom schema) is an implementation decision.
- Canonical order is maintained by per-team monotonic `sequence_no` (not timestamp ordering).
- `sequence_no` is append-only and never reused/resequenced.

### Assistant Response Invariant

- Exactly one committed assistant response per team per cohort window.
- No exception path; quality iteration occurs via edit/regenerate before commit.

### Thinking Invariant

- Preserve only emitted assistant thinking on the final selected draft.
- Thinking is immutable, collapsed, and assistant-only.
- If assistant message is manually edited later, attached thinking is removed.

## Projection and Visibility Rules

### Student Projection

- Student clients receive server-projected stream only.
- Hidden canonical content is never sent to student clients.

### Tags (MVP)

- `<cadet_move>`
- `<student_visible>`

Rules:

- User/facilitator side: only `<cadet_move>` projects to students.
- Assistant side: only `<student_visible>` projects to students.
- Non-tagged content is hidden by default.
- Tags remain in prompt history sent to model.

### Student Document Zone

- Student summary (“what the cadets know”) is separate from chat log.
- Rendered in player-room side panel (e.g. “Situation Update”).
- Read-only blob, overwritten each turn. Extensible for future artifacts.

## Game-State Artifacts (MVP)

Two artifacts per team, updated each turn:

### Game-State Artifact (GM-only)

- AI's running memory of the simulation state.
- Updated during pre-processing (same AI call that generates draft response).
- Latest version only fed into next AI call (not accumulated).
- Not shown to students.

### Student Summary (“What the Cadets Know”)

- Read-only blob overwritten each turn after publish.
- Generated from a separate AI call scoped to student-safe information.
- Delivered in the student document zone.
- Not part of the canonical chat log.
- Not fed back to the model.

### Path to Victory (Deferred)

- Future feature: OpFor subagent analysis with limited information.
- Not in MVP scope.

## ACL Policy (MVP)

- Reuse existing ACL subsystem and per-user grants.
- No separate `wargame_acl_entry` table.
- Team ACL mapping:
  - `viewer`: team-member read-only access (zero or more per team)
  - `editor`: move-buffer + notes write access (one or more per team)
  - GM access uses existing privileged-user infrastructure

## Round Lifecycle and Timer

The full cycle:

1. **"Publish all"** — GM releases all approved responses. Timer starts.
2. **Timer ticking** — cadets draft in CRDT move buffer. Deadline is either a timedelta from publish or a specific wall-clock time (if already past, rolls to next day).
3. **Timer fires** ("courier leaves") — hard deadline. All move buffers lock. Snapshots taken. Empty buffers become `No move submitted`.
4. **Pre-processing** — for each team (serial): AI call with cadet orders + game-state artifact + full turn history → draft response + updated game-state artifact.
5. **GM review** — GM works queue in any order, edits/injects/regenerates.
6. Back to step 1.

### Team Round State

- `drafting` — move buffer writable, timer ticking
- `locked` — timer fired, pre-processing and GM review in progress
- `simulation_ended` — read-only for team members

No formal draft FSM. A pending response exists after pre-processing; the GM edits it and publishes.

## End State and Export

- `end simulation for all` sets all player rooms read-only for team members.
- GM retains full edit/publish powers after end.
- Export is a separate action.
- Export output:
  - one annotation workspace per student
  - projected student-visible stream only
  - excludes team notes and hidden content
- Export is idempotent and repeatable.

## Seam Issue Breakdown

These seams are intended as implementation issues under one epic.

### Seam 1: Data Model and Migrations

Deliver:

- Wargame activity table (owns immutable system prompt + scenario bootstrap).
- Team table (codename, room UUID, round state, simulation state).
- Canonical message table (role, content, metadata, per-team monotonic `sequence_no`).
- Game-state artifact column/table (GM-only blob, updated in place per turn).
- Student summary column/table (read-only blob, overwritten per turn).
- Timer/deadline configuration (timedelta or wall-clock per activity).
- Alembic migrations for all new tables.

Dependencies:

- None (foundation seam).

### Seam 2: Team Management and ACL

Deliver:

- Team creation from activity (codename generation, room UUID assignment).
- Team membership ingestion/update from email sets.
- ACL grants using existing ACL tables and resolution logic.
- Role mapping: `viewer` (read-only, zero or more), `editor` (move-buffer + notes write, one or more).
- Membership updates rejected if they would leave a team with zero editors.
- Bulk membership import is additive/update-only; removals require explicit operations.

Dependencies:

- Seam 1.

### Seam 3: Turn Cycle Engine

Deliver:

- Timer management: start timer on publish, deadline as timedelta or wall-clock.
- Hard-deadline lock: all move buffers lock simultaneously when timer fires.
- Snapshot pipeline: extract markdown from each team's CRDT move buffer. Empty/whitespace → `No move submitted`.
- Serial pre-processing: for each team, PydanticAI call with cadet orders + game-state artifact + full turn history → draft response + updated game-state artifact.
- "Publish all": explicit GM action that releases all approved responses, generates student summaries (separate AI call), and starts the next timer.
- Completion gating: next round does not open until all teams have published responses.
- One assistant response per team per round (hard invariant, enforced in service logic).

Dependencies:

- Seam 1.

### Seam 4: Player Room

Deliver:

- CRDT move buffer lifecycle (writable during drafting, locked on timer fire, cleared on publish).
- Persistent CRDT team notes document (editable by editors throughout simulation, including during lock).
- Projected stream rendering (read-only turn panel showing student-visible content).
- Student document zone: student summary side panel + extensible area for future read-only artifact blobs.
- Read-only behaviour after simulation end.

Design note: Consider using Anthropic Batch API for turn cycle AI calls
(turn_agent, summary_agent). All per-team calls are independent — ideal
batch candidates. 50% cost reduction. Changes flow from "call and await"
to "submit batch → poll → collect", so deadline worker needs redesign.
PydanticAI has no built-in batch support; use anthropic SDK directly and
map results back to TurnResult/StudentSummary structured types.

Dependencies:

- Seams 1, 2, 3.

### Seam 5: GM Control

Deliver:

- Review queue UI: list of all teams with pending drafts, work in any order.
- Per-team review: view full canonical stream, edit any message (edited timestamp shown; editing AI response discards thinking blob).
- Hidden GM note injection: XML-tagged content within user messages.
- Regenerate: re-run AI call for a team's pending response.
- "Publish all" button (triggers Seam 3 publish pipeline).
- One-assistant-response invariant visible in UI (cannot publish until every team has exactly one pending response).

Dependencies:

- Seams 1, 3.

### Seam 6: Projection and Tagging

Deliver:

- XML tag extraction from canonical messages.
- Projection rules: `<cadet_move>` on user-side messages → student-visible; `<student_visible>` on assistant messages → student-visible; all else hidden.
- Hidden-content exclusion guarantee: student clients never receive untagged content.
- Tags remain in prompt history sent to model.
- Malformed/missing tags surface explicit GM error with action to regenerate.

Dependencies:

- Seam 1.

### Seam 7: End Simulation and Export

Deliver:

- `end simulation for all`: sets all player rooms read-only for team members. GM retains full edit/publish powers.
- Idempotent repeatable export pipeline: one annotation workspace per student, containing projected student-visible stream only. Excludes team notes and hidden content.

Dependencies:

- Seams 4, 5, 6.

## Dependency Order (Suggested)

1. Seam 1 (data model)
2. Seam 2 (team management + ACL)
3. Seam 6 (projection + tagging — pure logic, no UI dependency)
4. Seam 3 (turn cycle engine)
5. Seam 5 (GM control)
6. Seam 4 (player room)
7. Seam 7 (end simulation + export)

## MVP Acceptance Contract (Cross-cutting)

- Exactly one assistant response per team per round (hard invariant, enforced in service logic).
- Hard-deadline timer locks all teams simultaneously.
- Pre-processing generates one draft per team (serial) — GM never starts from empty.
- "Publish all" is an explicit GM action that releases all responses at once.
- Student clients never receive hidden canonical content.
- Projection parse failures surface explicit GM error with regenerate action.
- Full-history canonical context + latest game-state artifact used for model calls.
- Lock-time initial generation is serial.
- Team ACL mapping enforced (`viewer` read-only, `editor` move+notes-write).
- End-simulation sets team-member read-only without blocking GM edits.
- Export is repeatable and emits projected student-visible stream only.

## Outstanding Questions

- None at design level.
- Remaining work is implementation decomposition and execution.
