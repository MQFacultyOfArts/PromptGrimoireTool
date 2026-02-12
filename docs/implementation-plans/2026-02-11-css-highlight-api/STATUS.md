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
