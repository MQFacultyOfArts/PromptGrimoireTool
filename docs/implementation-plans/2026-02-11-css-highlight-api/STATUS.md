# Implementation Plan Status

**Feature:** CSS Custom Highlight API Migration
**Branch:** css-highlight-api
**Worktree:** .worktrees/css-highlight-api
**Last updated:** 2026-02-12

## Progress

| Phase | Design Read | Codebase Investigated | External Research | Plan Written | User Approved |
|-------|:-----------:|:---------------------:|:-----------------:|:------------:|:-------------:|
| 1. Browser Feature Gate | done | done | done | done | done |
| 2. JS Text Walker Module | done | done | done | done | done |
| 3. Highlight Rendering Swap | done | done | done | done | done |
| 4. Scroll-Sync and Card Interaction | done | done | done | done | done |
| 5. Remote Presence via pycrdt Awareness | done | done | **stalled** | pending | pending |
| 6. Cleanup and Verification | pending | pending | pending | pending | pending |

**Finalization:** pending (blocked by phases 5D, 6D)
**Test Requirements:** pending (blocked by finalization)
**Execution Handoff:** pending

## Phase 5 Investigation Findings (completed, not yet written to plan)

Codebase investigation completed successfully. Key findings for when resuming:

- `update_cursor()` (L511), `update_selection()` (L531), `clear_cursor_and_selection()` (L561) confirmed in `crdt/annotation_doc.py` — all **uncalled**
- `_ClientState` class (L75-111): stores cursor_char, selection_start/end, color, name, callback
- `_connected_clients` dict (L115): `workspace_id -> {client_id -> _ClientState}`
- `_build_remote_cursor_css()` (L568-595): generates `box-shadow` on `[data-char-index]` + `::before` label
- `_build_remote_selection_css()` (L598-634): generates `background-color` on char range + `::before` label
- `_update_cursor_css()` / `_update_selection_css()` (L1520-1541): inject CSS on broadcast
- **Critical:** Awareness methods exist but are completely bypassed — current system uses in-memory `_ClientState` objects with NiceGUI callbacks, not pycrdt Awareness
- Awareness schema confirmed: `{client_id, name, color, cursor: int|None, selection: {start_char, end_char}|None}`
- `self.awareness = Awareness(self.doc)` at L70 — created but never read
- **Zero E2E tests** for remote cursor/selection visibility

External research on pycrdt Awareness API stalled (user rejected web fetch). Resume with internet-researcher or cached docs.

## Design Decisions Made

### Phase 1
- Gate at **login page** (not annotation) — annotation will require auth
- Client-side JS feature detection (`'highlights' in CSS`)
- Simple text message with browser version requirements

### Phase 2
- Single `annotation-highlight.js` file (not multiple modules)
- Playwright for parity tests (not Node/jsdom)
- Create edge-case fixtures for AC7.2/AC7.3 alongside existing workspace fixture

### Phase 3
- Full CSS Custom Highlight API: JS `Highlight` objects + `::highlight()` pseudo-elements (not per-char CSS rules)
- `ui.run_javascript()` for server-to-client highlight data transport
- Delete char-span functions entirely (not just hide from `__all__`)

### Phase 4
- `charOffsetToRect()` wrapper for scroll-sync coordinates
- Temporary `CSS.highlights` entry for card hover (replaces per-char class toggle)
- Flash on/off for go-to throb (`::highlight()` doesn't support transitions)
- E2E tests completely rewritten, old ones nuked
- E2E test audit doc moved from buried location to `docs/e2e-test-audit.md`

## To Resume

Run `/denubis-plan-and-execute:start-implementation-plan` with this design plan and pick up from Phase 5C (pycrdt Awareness research). Or continue manually:

1. Research pycrdt Awareness API (Phase 5C)
2. Present Phase 5 design decisions for approval
3. Write phase_05.md (Phase 5D)
4. Phase 6: investigate, design decisions, write phase_06.md
5. Finalization: code-reviewer over all 6 phases
6. Test Requirements: generate test-requirements.md
7. Execution handoff
