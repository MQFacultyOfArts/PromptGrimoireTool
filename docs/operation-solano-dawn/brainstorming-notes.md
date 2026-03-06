# Operation Solano Dawn Brainstorming Notes

## Status

Revised 2026-03-06 from Codex draft. Original brainstorming validated and
amended against facilitator conversation.

The client PRD (`docs/prds/2026-03-04-operation-solano-dawn-wargame-prd.md`) is
source material and inspiration, not the internal spec. Historical run logs
(`~/people/Brian/Codes for Runthroughs .zip`, extracted to `/tmp/run_histories/`)
informed the interaction model.

## Core Framing

- This is a multi-tenant turn-processing system, not a free-chat roleplay tool.
- The feature should be specified in terms of workflows, state transitions, and projections, not page layouts.
- Wargame state lives in its own tables, not the existing Workspace/WorkspaceDocument model.
- One activity defines a class-wide run.
- Many team instances operate from that shared activity.

## Prompt Model

- The prompt architecture preserves the same separation used in last year's runs:
  - immutable GM system prompt
  - immutable scenario bootstrap
  - evolving canonical stream
- The system prompt is immutable across all team instances in a class run.
- The scenario bootstrap is immutable across all team instances in a class run.
- The bootstrap is the first canonical user message.
- Team codename is substituted into that first message.
- The first student-visible content is the assistant briefing response to that bootstrap.
- Briefings are canonical and vary by team.
- Divergence between teams is intentional product behavior.

## Team and Activity Model

- The activity template owns the immutable prompt pair.
- Team instances are the actual unit of play.
- Teams are the unit of organisation.
- A student belongs to zero or one team.
- Team membership is admin-managed from sets of student emails.
- Membership changes are operational/admin actions, not student actions.
- If a student moves teams, they immediately gain access to the destination team's prior history.

## Team-Side Resources

Each team instance needs three distinct collaboration surfaces:

- `canonical stream`
  - authoritative history for adjudication
  - contains bootstrap, cadet moves, assistant responses, and hidden operator material
- `move buffer`
  - turn-scoped collaborative Milkdown CRDT editor
  - used to compose the official team move
  - cleared after lock/submission
  - reopened only when the next round opens
- `team notes`
  - persistent collaborative document
  - non-canonical
  - never auto-submitted

## Round Lifecycle

- Rounds are cohort-level, not per-team rolling.
- A hard deadline locks all teams simultaneously ("the courier leaves").
- The deadline is either a timedelta from the last publish ("courier arrives") or a specific wall-clock time (if already past, it means tomorrow).
- At lock time, the underlying markdown source in each move buffer is snapshotted.
- That markdown source becomes the official cadet move.
- If the field is empty, the submission is a null move (`No move submitted`).
- There is at most one move per team per round.
- All teams in a round must be processed before the next round opens.
- The GM can override round timing.

## Facilitator / Privileged Operator Model

- Within this feature, GM and admin collapse into one `privileged operator` role.
- Privileged operators can do everything in the local feature context.
- There is exactly one active GM/editor for the exercise.
- NiceGUI bindings are sufficient for passive observation/live propagation.
- GM-side CRDT is out of scope.

## Processing Model

The turn cycle:

1. **Timer fires** — move buffers lock, snapshots taken for all teams.
2. **Pre-processing** — for each team (serial): AI call reads cadet orders + game-state artifact + turn history → generates draft response + updated game-state artifact.
3. **GM review** — GM works through the queue in any order. Can edit anything (including AI responses — discards thinking blob), inject hidden notes (XML-tagged GM content in user messages), regenerate.
4. **"Publish all"** — explicit GM action. All approved responses released to teams. "What the cadets know" summary generated and pushed to student document zone.
5. **Timer starts** — cadets read, discuss, draft in CRDT move buffer.
6. Back to step 1.

- AI calls use PydanticAI → Sonnet 4.6.
- Full turn history + latest game-state artifact (not accumulated artifacts).
- There should always be an LLM draft to riff on.
- GM steering is part of the actual historical interaction pattern (visible in run logs) and must be supported.
- Hidden GM content is persistent in canonical history unless removed by the GM.

## Canonical Stream Rules

- The GM works against the full canonical stream.
- Student clients never receive the full canonical stream.
- Student clients receive only projected content (tagged regions).
- The GM can edit any message in the pending response before publish.
- "Publish all" releases all pending responses into the canonical stream.
- The published stream is the authoritative history.

## Message Model

- Cadet moves are stored as underlying markdown source, not rendered HTML.
- There is just one canonical version of a cadet move at commit time.
- The facilitator can edit any canonical message.
- Edited messages should display an edited timestamp.
- Lightweight hidden per-message revision history is needed only for recovery/fat-finger prevention.
- Recovery scope is individual message, not full round rollback.
- Only the final selected assistant draft enters canon.
- Rejected drafts do not persist in canon.

## Turn Invariants

- One locked cadet move per team per round.
- One staged assistant response per team per round.
- One committed assistant response per team per round.
- The initial round is still user message -> assistant message:
  - bootstrap user message
  - canonical assistant briefing

## Visibility and Tagging Rules

- Explicit XML-ish tags are fed back to the model.
- Student projection is derived from tagged content, not heuristic parsing.
- Current hardcoded tags:
  - `<cadet_move>`
  - `<student_visible>`
- On facilitator-side/user-side messages:
  - only `<cadet_move>` is explicitly visible to students
  - all non-tagged content is hidden
- On assistant messages:
  - only `<student_visible>` is explicitly visible to students
  - all non-tagged content is hidden by default
- Student clients must not receive hidden content at all.
- Hidden content is excluded from the student payload, not merely hidden in the UI.
- Assistant messages are allowed to contain additional untagged hidden content.
- The logs do not support requiring mandatory structured hidden assistant regions on every turn.

## Thinking

- Preserve model thinking when emitted.
- Thinking is assistant-only.
- Thinking is collapsed in the UI.
- Thinking is immutable.
- No thinking history is required.
- Only the latest selected assistant draft's thinking survives.
- If an assistant message is manually edited later, attached thinking is removed.

## Evidence from Historical Logs

- Last year's chats show a real operator-to-Claude steering pattern, not just cadet move -> AI response.
- Historical assistant responses appear as one contiguous student-facing block per turn.
- The logs do not show multiple assistant messages per turn.
- The logs support separate operator steering messages.
- The logs do not justify mandatory `paths_to_victory` tagging on every assistant response.

## Relationship to Existing Infrastructure

**Resolved decisions:**

- Wargame state lives in its own tables, not the existing Workspace/WorkspaceDocument model.
- Auth uses the existing Stytch infrastructure.
- Team membership uses the existing ACL system — a "team" is a set of users who share access to the same team resources. The group table may just be the share relationship itself.
- The existing Activity/Week model is relevant for where the wargame activity lives in the course structure.
- Export to annotation workspace at end of run is an existing pattern to reuse.

## Game-State Artifacts

- **Game-state artifact** (GM-only): AI's running memory of the simulation state. Updated each turn during pre-processing. Fed back into the next AI call. Not shown to students.
- **"What the cadets know"** (student-visible): read-only blob overwritten each turn after publish. Lives in the student document zone alongside the turn panel and notes panel. Derived from a separate AI call.
- **Path to victory** (deferred): future feature. Subagent call with limited information for adversarial progression analysis.

## Student Document Zone

Each team has a student-facing area with:

- **Turn panel** (read-only): projected student-visible content from the canonical stream.
- **Notes panel** (CRDT, collaborative): persistent team notes, non-canonical, never auto-submitted.
- **Read-only artifact blobs**: "what the cadets know" and future artifacts. Overwritten each turn, not CRDT.

## Resolved Questions

All brainstorming questions from the original Codex draft are now resolved:

- The wargame uses its own tables, not the existing Workspace model.
- Team membership maps to ACL grants on team resources.
- The canonical stream, move buffer, and notes are distinct concerns within one team's state.
- GM access uses the existing privileged-user infrastructure.
