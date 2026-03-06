# Operation Solano Dawn Planning

This directory holds internal planning notes derived from the client PRD for Operation Solano Dawn. All documents revised 2026-03-06.

## Source Documents

- **Implementation handoff**: [final-epic-and-seams.md](final-epic-and-seams.md) — 7 seams under one epic
- Client PRD (inspiration): [../prds/2026-03-04-operation-solano-dawn-wargame-prd.md](../prds/2026-03-04-operation-solano-dawn-wargame-prd.md)
- Planning copy of client PRD: [client-prd.md](client-prd.md)
- Brainstorming notes: [brainstorming-notes.md](brainstorming-notes.md)
- Internal spec outline: [internal-spec-outline.md](internal-spec-outline.md)
- Internal design draft: [internal-design-draft.md](internal-design-draft.md)

Historical run logs: `~/people/Brian/Codes for Runthroughs .zip` (not in repo).
Extraction script: `scripts/extract_anthropic_console_to_json.py`.

## Core Framing

- Multi-tenant turn-processing system, not free-chat roleplay.
- Wargame state in own tables, not the existing Workspace model.
- Auth via existing Stytch. Team membership via existing ACL.
- AI calls via PydanticAI → Sonnet 4.6.

## Turn Cycle

1. GM triggers "publish all" → timer starts
2. Teams draft in CRDT move buffer until hard deadline
3. Timer fires ("courier leaves") → buffers lock, snapshots taken
4. Pre-processing: serial AI calls → draft responses + game-state updates
5. GM reviews queue → edits/injects/regenerates
6. Back to step 1

## Status

- Design questions resolved. Documents validated against facilitator conversation.
- Remaining work: create GitHub epic + seam issues, then implementation.
