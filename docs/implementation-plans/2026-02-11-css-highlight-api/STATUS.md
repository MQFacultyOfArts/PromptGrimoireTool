# Implementation Plan Status

**Feature:** CSS Custom Highlight API Migration
**Branch:** css-highlight-api
**Worktree:** .worktrees/css-highlight-api
**Last updated:** 2026-02-13

## Execution Progress

| Phase | Status | UAT | Notes |
|-------|--------|-----|-------|
| 1. Browser Feature Gate | COMPLETE | Confirmed | |
| 2. JS Text Walker Module | COMPLETE | Confirmed | Parity tests pass |
| 3. Highlight Rendering Swap | COMPLETE | Confirmed | 3 bugfixes post-review |
| 4. Scroll-Sync and Card Interaction | COMPLETE | Confirmed | DOM replacement resilience fix |
| 5. Remote Presence | COMPLETE | Confirmed (AC3.1 deferred #149) | 3 review cycles, t-string refactor |
| 6. Cleanup and Verification | COMPLETE | Confirmed | Final code review passed |

### Phase 6 Execution Notes

All subcomponents complete and verified through code review:
- Subcomponent A (Task 1): Deleted `_process_text_to_char_spans` dead code
- Subcomponent B (Tasks 2-3): Verified no char-span CSS/JS references remain
- Subcomponent C (Tasks 4-5): Deleted obsolete tests, rewrote E2E helpers for mouse-based selection
- Subcomponent D (Tasks 6-7): Verified PDF export unchanged, updated CLAUDE.md documentation
- Task 8 (final sweep): Confirmed zero char-span references in source code

**Code review status:** Ready for merge. Minor issues addressed:
- Created `test_no_char_span_queries.py` static analysis guard for AC8.4/AC8.5
- Updated test-requirements.md to document AC8.1/AC8.2/AC8.3 as human-verification-only
- Created GitHub issue #156 tracking E2E test migration to text-walker helpers
- Updated STATUS.md and WIP-STATUS.md Phase 6 status to COMPLETE
- Migrated f-string JS to t-string format for consistency

### Phase 5 Execution Notes

All 9 tasks implemented across 4 subcomponents. Key additions beyond plan:
- `_render_js()` t-string function for safe JS interpolation (replaces json.dumps pattern)
- `_broadcast_js_to_others()` helper extracted during refactor step
- 21 adversarial security tests for `_render_js`
- AC3.1 (remote cursors) deferred to #149 — broadcast infra works but cursor events not emitted from clicks

Rebased onto main (2 commits: test optimisation, Serena removal). 2 trivial conflicts resolved.

### Phase 4 Execution Notes

All 5 tasks implemented. Key deviation from plan: discovered NiceGUI/Vue replaces the
entire Annotate tab panel DOM when the Respond tab initialises its Milkdown editor.
This required rewriting scroll-sync JS with dynamic `getElementById` lookups (no closured
DOM references), persistent `highlights-ready` event listener for MutationObserver
re-attachment, and document-level event delegation for card hover.

Planned E2E test files (`test_scroll_sync.py`, `test_card_interaction.py`) not created
as separate files — verified via diagnostic Playwright test + manual UAT. E2E test audit
doc move deferred to Phase 6.

## Planning Progress

| Phase | Design Read | Codebase Investigated | External Research | Plan Written | User Approved |
|-------|:-----------:|:---------------------:|:-----------------:|:------------:|:-------------:|
| 1. Browser Feature Gate | done | done | done | done | done |
| 2. JS Text Walker Module | done | done | done | done | done |
| 3. Highlight Rendering Swap | done | done | done | done | done |
| 4. Scroll-Sync and Card Interaction | done | done | done | done | done |
| 5. Remote Presence (in-memory, not Awareness) | done | done | done | done | done |
| 6. Cleanup and Verification | done | done | done | done | done |

**Finalization:** done (5 review rounds — round 5 APPROVED with 0 issues)
**Test Requirements:** done (30 sub-criteria mapped, 11 new test files, 5 human verification items)
**Execution Handoff:** ready — first phase: `phase_01.md`

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

### Phase 5
- **In-memory dict, NOT pycrdt Awareness** — server-hub architecture doesn't match Awareness's peer-to-peer model. `set_local_state()` only tracks one client; multi-client needs `apply_awareness_update()` with per-client encoding. Simpler dict approach matches NiceGUI's architecture.
- `_ClientState` → `_RemotePresence` dataclass, `_connected_clients` → `_workspace_presence`
- JS-targeted broadcast via `client.run_javascript()` (not CSS regeneration)
- Remote cursors as positioned DOM `<div>` elements (CSS Highlight API can't do borders/positioning)
- Remote selections as `CSS.highlights` entries with `priority = -1` (below annotation highlights)
- NiceGUI `client.on_disconnect` for cleanup (immediate, not 30s Awareness timeout)
- Delete unused Awareness helper methods (`update_cursor`, `update_selection`, `clear_cursor_and_selection`)
- Unit tests for JS rendering + one multi-context E2E smoke test

### Phase 6
- Delete `inject_char_spans`, `strip_char_spans`, `extract_chars_from_spans` (all dead code)
- Keep `extract_text_from_html` (PDF export pipeline dependency)
- E2E test helpers: **mouse events + JS coordinate lookup** (not full JS injection). `page.evaluate()` only for "where is char N on screen?" — actual selection via Playwright mouse API.
- Update CLAUDE.md only; leave historical implementation plan docs as archaeological record
- Final sweep: grep for all char-span references in `src/`, expect zero matches
