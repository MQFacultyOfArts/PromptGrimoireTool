# Operation Solano Dawn Internal Design Draft

## Summary

Revised 2026-03-06 from Codex draft.

Operation Solano Dawn is a wargame activity system inside PromptGrimoire with its own tables, not a variant of `/roleplay` or a reuse of annotation workspaces.

Two user-facing surfaces:

- **Wargame player room** — team-facing. Turn panel (read-only projected stream), CRDT move buffer, CRDT notes panel, read-only artifact blobs (student document zone).
- **Wargame control** — GM-facing. Review queue for all teams, edit/regenerate/inject, "publish all" action.

Each team has its own canonical stream, game-state artifact, and student summary. The model reflects the historical run logs:

- immutable system prompt
- immutable scenario bootstrap (codename substituted)
- canonical per-team stream (full history fed to model)
- projected student-visible stream (XML-tag derived)
- team move drafting in CRDT markdown
- GM edits pending responses directly (no separate staging copy)
- game-state artifact (GM-only) and student summary (read-only blob)

## Student Experience Narrative

The student experience begins when a team enters its `Wargame player room`. The room is already identified by a stable UUID URL, and membership has been assigned operationally rather than through self-service team formation.

The first thing the team sees is not the bootstrap prompt and not the hidden operator context. The first visible item is the generated briefing. This matches the historical pattern in the beta run, where the opening visible response is a formal wargame introduction that explains the exercise, gives framing instructions, and asks for concrete first decisions such as meeting location and leadership composition. In the historical logs, the opening assistant material then flows directly into the team's first actual move: choosing the abandoned warehouse and nominating the first leadership group.

Inside the player room, the team has three concerns at once:

- they read the projected student stream
- they compose the current move in the turn-scoped move buffer
- they maintain persistent notes in a separate shared document

The move buffer is the official source for the next cadet move. It is a Milkdown CRDT document, written as markdown source. The notes area is persistent but non-canonical. The stream is read-only from the team's perspective and contains only projected content extracted from canon. Hidden operator notes and non-student-visible content are not sent to the client at all.

The team experience is rhythmic rather than conversational. In the beta run, this is visible in the move/response cadence: the team chooses a meeting location, receives a command update, issues decisions about raids and intelligence priorities, and later receives operational reports, intelligence updates, and consequences. The same pattern appears in the more structured runs such as Operation Dingo Whiskey and Operation Greedy Fortune, where the team submits clearly formatted operational orders and receives a single coherent command update back.

At lock time, the room changes state. The move buffer stops being writable, whatever is in it is snapshotted as markdown source, and if it is empty the move becomes `No move submitted`. In product terms, this is the moment when orders are handed to the courier. The room enters processing. Students can still read their stream and notes, but they cannot continue writing the official move.

After processing, the team receives a single new projected response. That response itself is the marker that the previous round has concluded. No extra synthetic round separator is needed. When the next round opens, the move buffer becomes writable again and the cycle repeats.

At the end of the simulation, the player room stays visible but becomes read-only for team members. Students can still read the full projected stream and their notes as long as the activity remains visible to them.

## Privileged Operator Experience Narrative

The privileged operator works in `Wargame control`, one dashboard per wargame activity. The control surface manages all team instances for that activity and can deep-link into individual rooms using the same room UUID identity used on the player side.

The historical logs show that this role is not merely approving AI output. The operator actively steers the model. In the beta run, the operator shapes the opening experience by asking Claude to start the wargame, refine the player role, and later propose a clean ending once the exercise has run longer than intended. In the more mature runs, the operator asks for decision summaries, formatting adjustments, and early finalization. That behavior should be preserved as a first-class hidden part of the canonical history.

When a round locks, the system opens one GM draft for every team and immediately generates one initial assistant draft per team in serial. The operator does not start from an empty canvas. They start from a complete working draft stream for each team.

For any given team, the operator edits the pending response directly. This is not a separate copy of canon — it is the draft response waiting to be published. Reopening a team in the control view should resume where the GM left off.

The operator can:

- edit any message (including AI responses — discards thinking blob)
- edit the just-locked cadet move
- inject hidden GM notes as XML-tagged content in user messages
- regenerate the current draft assistant response
- repeat until satisfied

This reflects the historical pattern where the operator sometimes asks the model to change framing, summarize pending decisions, or change how the next output is structured. GM steering is normalised into hidden tagged content within user messages.

The operator may work through teams in any order. The queue is a backlog, not strict FIFO. When all teams are reviewed, the GM explicitly triggers "publish all" to release all responses simultaneously. The next round does not open until every team has a published response.

The operator can also end the simulation for all teams. This action closes all player rooms to read-only for team members. Export is a separate later action.

## Product Model

### Wargame Activity

The wargame exists as an activity in a week. One activity defines a class-wide run. That activity owns the immutable prompt pair:

- GM system prompt
- scenario bootstrap

The activity spawns many teams, each with its own codename, room URL, canonical stream, and collaboration surfaces.

### Team

Each team owns (in its own tables):

- codename
- room identity (stable UUID)
- canonical stream (turn log)
- game-state artifact (GM-only, updated per turn)
- student summary blob ("what the cadets know", overwritten per turn)
- round state
- CRDT move buffer (turn-scoped)
- CRDT notes document (persistent)

Teams are not modelled as the existing annotation `Workspace`.

### Wargame Control

The GM-facing dashboard for an activity run. Manages all teams, provides the review queue, and can navigate to any team by UUID.

## Prompt and History Model

The prompt model should preserve the same overall shape used in last year's runs:

1. immutable system prompt
2. immutable bootstrap user message
3. evolving conversation history

The key change is that hidden operator content is delineated by XML-like tags within user messages rather than being indistinguishable from cadet content. The model sees the full message; students see only tagged regions.

The bootstrap is the first canonical user message for every team instance. It includes codename substitution. Students do not see that bootstrap directly. They see the assistant briefing generated from it.

The full canonical stream is always available to the model. This follows your explicit preference and the historical pattern, where earlier context is carried forward rather than aggressively summarized away.

### Canonical Message Schema

Message persistence should preserve enough structure to reconstruct model calls (role, content, metadata). The exact schema (whether mirroring PydanticAI structures or using a simpler custom schema) is an implementation decision, not a design constraint.

## Game-State Artifacts

Two artifacts per team, updated each turn:

### Game-State Artifact (GM-only)

- AI's running memory of the simulation state.
- Updated during pre-processing (the AI call that generates the draft response).
- Fed back into the next AI call as context (latest version only, not accumulated).
- Not shown to students.

### Student Summary ("What the Cadets Know")

- Read-only blob overwritten each turn after publish.
- Generated from a separate AI call scoped to student-safe information.
- Delivered in the student document zone as a side panel (e.g. "Situation Update").
- Not part of the canonical chat log.

### Path to Victory (Deferred)

- Future feature: subagent call with limited information for adversarial progression analysis.
- Not in MVP scope.

## Projection Rules

Students do not get canonical history. They get a server-projected stream.

Current explicit tags:

- `<cadet_move>`
- `<student_visible>`

Rules:

- on the user/facilitator side, only `<cadet_move>` is projected to students
- on the assistant side, only `<student_visible>` is projected to students
- all other content is hidden by default
- hidden content is excluded from the student payload entirely

This lets the canonical stream remain rich while keeping the student client simple and safe.

Student summary output is intentionally not embedded in chat log messages and should be rendered through its own side-panel surface.

## Round and Timer Model

Rounds are cohort-level. The full cycle:

1. **"Publish all"** — GM releases all approved responses. Timer starts.
2. **Timer ticking** — cadets read, discuss, draft in CRDT move buffer. The deadline is either a timedelta from publish or a specific wall-clock time (if already past, rolls to next day).
3. **Timer fires** ("courier leaves") — all move buffers lock simultaneously. Snapshots taken. Empty buffers become `No move submitted`.
4. **Pre-processing** — for each team (serial): AI call with cadet orders + game-state artifact + full turn history → draft response + updated game-state artifact.
5. **GM review** — GM works the queue (any order), edits/injects/regenerates.
6. Back to step 1.

The draft lifecycle is minimal: a pending response exists after pre-processing, the GM edits it, and it gets published or regenerated. No formal FSM beyond "pending" and "published".

## Editing and Thinking

Canonical messages are editable by privileged operators. Edited messages should display an edited timestamp for transparency.

Per-message hidden revision history is needed only for recovery and fat-finger prevention, not for general browsing or time travel.

Thinking should be preserved only when emitted by the model, and only on the final selected assistant draft. It should remain collapsed in the UI and immutable. If a committed assistant message is manually edited later, the attached thinking should be removed so the stored thinking always remains an honest provider-authored artifact.

## ACL and Team Access

Teams should be ACLed to individuals, not to a new team principal type.

That means:

- team membership is a domain-level concept
- room access is still enforced through per-user ACL grants
- membership changes are operational actions that update those per-user grants

Team ACL policy is explicit for this feature: `viewer` is team-member read-only access (zero or more per team), and `editor` is collaborative write access (one or more per team).

## End of Run and Export

Ending the simulation is a distinct state transition.

When the operator chooses `end simulation for all`:

- all player rooms become read-only for team members
- team members retain read access
- privileged operators still retain edit and commit powers

Export is separate. At conclusion, the operator can generate one annotation workspace per student, individually owned, containing only the projected student-visible stream. Team notes are excluded. Hidden operator content is excluded. The existing export-to-annotation pattern in roleplay is relevant here, but the wargame runtime itself should not be forced into the annotation workspace model.

Post-end export should be idempotent and repeatable so operators can re-run export after cleanup edits when needed.

## Reuse Boundaries

This design should reuse code and patterns aggressively where they are defensible:

- Milkdown CRDT integration
- per-user ACL patterns
- route and layout conventions
- roleplay/playground-style transcript export patterns
- activity/template setup flows

But it should not pretend that the existing annotation `Workspace` is the same domain object as a wargame player room or team instance. The current workspace model is deeply entailed with annotation assumptions that do not cleanly match this feature's runtime invariants.

## Resolved Design Decisions

- Wargame state lives in its own tables, not the existing Workspace model.
- Teams are a single resource (not a 1:1 team-instance/player-room split).
- Auth uses existing Stytch. Team membership uses existing ACL grants.
- AI calls use PydanticAI → Sonnet 4.6 with full turn history + latest game-state artifact.
- One assistant response per team per round is a hard invariant.
- Lock-time generation is serial.
- The GM edits pending responses directly (no separate staging/draft copy model).
- Hidden content uses XML-like tags (`<cadet_move>`, `<student_visible>`). Untagged content is hidden by default.
- Student clients never receive hidden canonical content.
- Game-state artifact and student summary are separate by design.
- Student summary is not part of the chat log.
- Post-end export is idempotent and repeatable.
- Path to victory is deferred to post-MVP.
- Token budget guardrails and CLI stream editing are deferred to post-MVP.
