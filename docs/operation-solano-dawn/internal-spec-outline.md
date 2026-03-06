# Operation Solano Dawn Internal Spec Outline

## Purpose

Revised 2026-03-06 from Codex draft.

This document translates the client PRD into an internal product specification for PromptGrimoire. It defines the product model, core resources, and workflow invariants that implementation must respect.

## Product Framing

- This is a multi-tenant turn-processing system.
- It is not a free-chat roleplay product.
- It is specified in terms of state transitions, projections, and operator workflows rather than UI panels.
- Wargame state lives in its own tables, not the existing Workspace model.
- It integrates with the existing week/activity model for course structure.

## Working Terminology

These terms replace overloaded "turn/round" usage in this project context:

- `submission`: one team's locked move input
- `adjudication pass`: operator/model processing of one submission
- `cohort window`: shared lock/publish cycle across all teams

## Core Resources

Each team is a single resource (own tables, not the existing Workspace model).

### Team

A team owns:

- codename
- room identity (stable UUID)
- canonical stream (turn log)
- game-state artifact (GM-only, updated per turn)
- student summary blob ("what the cadets know", overwritten per turn)
- round state
- CRDT move buffer (turn-scoped)
- CRDT notes document (persistent)
- ACL grants (existing ACL system, per-user)

## Naming Model

User-facing terms:

- `Wargame activity`
- `Wargame player room` (team-facing)
- `Wargame control` (GM-facing)

Internal term: `team` (the data model resource).

## Routing Model

- Each `Wargame player room` has a stable opaque UUID route.
- The room URL is the identity of the room.
- The room URL remains stable for the life of the team.
- Team membership changes, round state changes, and simulation end state do not change the room URL.
- `Wargame control` exists as a top-level dashboard per activity run.
- `Wargame control` can deep-link to individual teams using the same room UUID.
- Multiple activities in different weeks/units can each have their own `Wargame control` dashboard.

## Class / Activity Model

- A single activity defines a class-wide run.
- The activity owns the immutable prompt pair.
- Many teams are created from that activity.
- Teams are the unit of organisation.
- Students belong to zero or one team.
- Team membership is managed operationally by the GM from sets of student emails.
- Membership changes update ACL grants on the existing team.

## Prompt Model

The prompt model preserves the same separation used in last year's runs.

### System Prompt

- One immutable GM system prompt per activity run
- Shared across all teams
- Stable behavioral and pedagogical instructions

### Scenario Bootstrap

- One immutable scenario bootstrap per activity run
- Shared across all teams
- Stored as the first canonical user message for each team
- Team codename is substituted into this message

### Canonical Stream

- Full evolving message history after bootstrap
- Includes cadet moves, assistant responses, and hidden GM content
- Fed back to the model as full history
- AI calls use PydanticAI → Sonnet 4.6

## Game-State Artifacts

### Game-State Artifact (GM-only)

- Per-team running memory of scenario state
- Updated during pre-processing (same AI call that generates draft response)
- Latest version only fed back into next AI call (not accumulated)
- Not shown to students

### Student Summary ("What the Cadets Know")

- Read-only blob overwritten each turn after publish
- Generated from a separate AI call scoped to student-safe information
- Delivered in the student document zone as a side panel
- Not part of the canonical chat log

### Path to Victory (Deferred)

- Future feature, not in MVP scope

## Roles

- `team member`: students assigned to a team via ACL grants
- `GM` (privileged operator): collapses GM and admin powers

The GM can:

- edit any message (discards thinking blob on AI responses)
- inject hidden notes (XML-tagged GM content in user messages)
- regenerate AI responses
- manage teams, timings, and deadlines
- publish all, end simulation, trigger exports

There is exactly one active GM for the exercise. NiceGUI propagation is sufficient for passive observation by others.

### Team ACL Mapping (existing ACL system)

- `viewer`: team member read-only access (zero or more per team)
- `editor`: collaborative write access to move buffer + notes (one or more per team)
- GM access uses existing privileged-user infrastructure

## Team-Side Authoring Model

Each team has two authoring surfaces and one read model:

### Move Buffer

- Milkdown CRDT document
- turn-scoped
- official source for the team's next move
- underlying markdown source is canonical at submission time
- cleared after lock
- reopened when the next round opens

### Team Notes

- persistent collaborative document
- never auto-submitted
- non-canonical
- remains readable as long as the activity is visible

### Projected Student Stream

- read model derived from canon
- only student-visible content is sent to the team client

## Round Lifecycle and Timer Model

Rounds are cohort-level. The full cycle:

1. **"Publish all"** — GM releases all approved responses. Timer starts.
2. **Timer ticking** — cadets read, discuss, draft in CRDT move buffer. Deadline is either a timedelta from publish or a specific wall-clock time (if already past, rolls to next day).
3. **Timer fires** ("courier leaves") — hard deadline. All move buffers lock simultaneously. Markdown snapshots taken. Empty buffers become `No move submitted`.
4. **Pre-processing** — for each team (serial): AI call with cadet orders + game-state artifact + full turn history → draft response + updated game-state artifact.
5. **GM review** — GM works the queue in any order. Edits, injects hidden notes, regenerates as needed.
6. Back to step 1.

### Invariants

- One locked cadet move per team per round.
- One assistant response per team per round (hard invariant, no exceptions).
- Next round does not open until all teams have published responses.
- Pre-processing always produces a draft — GM never starts from empty.
- GM steering is a first-class hidden part of canonical history (visible in run logs).

## Canonical Stream Model

The canonical stream is the authoritative gameplay record.

### Included Content

- bootstrap user message
- cadet moves
- assistant responses
- hidden operator content

### Editing Rules

- privileged operators can edit any canonical message
- edited messages show an edited timestamp
- lightweight hidden per-message revision history exists only for recovery/fat-finger prevention
- revision recovery is per-message, not full-run rollback

## Message Rules

### Cadet-Side Message Rule

- cadet submissions are stored as markdown source
- GM can edit any message before or after publish

### Assistant Message Rule

- one and only one assistant response per team per round
- quality iteration happens through editing/regeneration before publish
- only the final version enters canon

### Canonical Message Schema

- Message persistence should preserve enough structure to reconstruct model calls (role, content, metadata)
- The exact schema is an implementation decision, not a design constraint

### Thinking Rule

- preserve raw model thinking only when emitted
- thinking is assistant-only
- thinking is immutable
- thinking is collapsed in the UI
- only the final selected draft's thinking is retained
- if a committed assistant message is manually edited later, attached thinking is removed

## Projection Rules

Student clients receive a server-projected stream, not canonical history.

### Visibility Rule

- student clients receive only extracted visible regions
- hidden content must not be sent to the student client at all

### Tagging Rule

Current hardcoded prompt-visible tags are:

- `<cadet_move>`
- `<student_visible>`

Rules:

- on facilitator-side/user-side messages, only `<cadet_move>` is student-visible
- on assistant messages, only `<student_visible>` is student-visible
- all non-tagged content is hidden by default
- tags are fed back to the model as part of prompt history

The first canonical bootstrap message is not separately tagged. It is identified by message role/origin and position in history.

## End-of-Run Model

The simulation ends through an explicit GM action.

### End Simulation for All

When the GM ends the simulation:

- all player rooms become read-only for team members
- team members retain read access
- GM retains full edit/publish powers

This action does not itself trigger export.

## Export Model

Export is a separate post-run operator action.

### Export Output

- one annotation workspace per student
- individual ownership
- content is only the projected student-visible stream
- no team notes
- no hidden operator content
- no multi-document bundle

### Export Timing

- export happens only after the run concludes
- export is not continuously regenerated during the run

## Existing Pattern Reuse

Reuse code and patterns, not the domain model:

- per-user ACL grant/check patterns
- Milkdown/NiceGUI CRDT integration
- page routing and layout conventions
- roleplay/playground-style transcript export patterns
- activity/week model for course structure

The existing Workspace model is not reused as the runtime resource.

## Resolved Decisions

- Wargame state lives in its own tables, not the existing Workspace model.
- Teams are a single resource (no team-instance/player-room split).
- Auth uses existing Stytch. Team membership uses existing ACL grants.
- AI calls use PydanticAI → Sonnet 4.6 with full turn history + latest game-state artifact.
- One assistant response per team per round is a hard invariant.
- Lock-time generation is serial.
- GM edits pending responses directly (no separate staging/draft copy).
- Hidden content uses XML-like tags. Untagged content is hidden by default.
- Student clients never receive hidden canonical content.
- Game-state artifact and student summary are separate by design.
- Student summary is not part of the chat log.
- Post-end export is idempotent and repeatable.
- Path to victory deferred to post-MVP.
- Token budget guardrails and CLI stream editing deferred to post-MVP.
