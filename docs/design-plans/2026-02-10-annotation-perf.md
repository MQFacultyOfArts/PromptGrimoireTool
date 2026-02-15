# Annotation Page Performance Design

## Summary

This design optimizes the annotation page's hot path for adding and managing highlights. Currently, adding highlight #51 to a document triggers three compounding bottlenecks: a synchronous database write that blocks the UI until the round-trip completes, a full rebuild of all 50 existing annotation cards (destroying and recreating them from scratch), and complete CSS regeneration for every character-range selector. This design eliminates the first two bottlenecks by introducing debounced persistence (database writes happen asynchronously after a configurable delay) and CRDT-driven incremental card updates (only the changed annotation card is added, removed, or rebuilt). The solution builds entirely on existing patterns in the codebase: the persistence manager already implements debounce timers but the annotation page bypasses them, NiceGUI cards already support individual deletion, and the CRDT layer already uses observers for broadcasting updates.

The work is split into four phases across two pull requests. Phase 1 (separate PR) mechanically refactors the monolithic 2,302-line `annotation.py` into a focused module structure under `pages/annotation/`. Phases 2-4 (single PR) then introduce debounced persistence, register a CRDT Map observer on the highlights collection to detect add/remove/modify events, and wire that observer to drive incremental card updates for both local and remote changes. CSS optimization is explicitly deferred to a follow-up PR but the observer pattern introduced here makes incremental CSS append a natural next step.

## Definition of Done

1. Annotation-add path does not block on database write
2. Adding/removing a highlight updates only the affected card(s), not all cards
3. CRDT Map observers drive card updates for both local and remote changes
4. `annotation.py` is split into focused modules under `pages/annotation/`
5. Test suite passes at current baseline (2263 passed, 1 xfail `chinese_wikipedia`, 2 xfail cross-heading — xfails likely resolved by #134/#101)
6. No regressions in multi-client broadcast behaviour

## Acceptance Criteria

### annotation-perf.AC1: Persistence does not block UI
- **annotation-perf.AC1.1 Success:** Adding a highlight returns control to the UI before any database write completes
- **annotation-perf.AC1.2 Success:** Dirty workspace is persisted within debounce window (5s production, 0s test)
- **annotation-perf.AC1.3 Success:** Client disconnect triggers immediate flush of dirty state
- **annotation-perf.AC1.4 Success:** App shutdown flushes all dirty workspaces
- **annotation-perf.AC1.5 Success:** PDF export calls force_persist before reading state
- **annotation-perf.AC1.6 Edge:** Rapid highlight additions (5 in 2 seconds) result in at most 1 DB write in production

### annotation-perf.AC2: Incremental card updates
- **annotation-perf.AC2.1 Success:** Adding highlight #N+1 appends one card without destroying existing N cards
- **annotation-perf.AC2.2 Success:** Removing a highlight deletes only that card from the DOM
- **annotation-perf.AC2.3 Success:** Changing a highlight's tag rebuilds only that card (border colour, dropdown)
- **annotation-perf.AC2.4 Success:** Adding a comment to a highlight rebuilds only that card
- **annotation-perf.AC2.5 Success:** Initial page load still renders all cards (full build fallback)
- **annotation-perf.AC2.6 Edge:** Tab switch to Annotate re-renders cards correctly from current CRDT state

### annotation-perf.AC3: CRDT observer drives updates
- **annotation-perf.AC3.1 Success:** Local highlight add fires observer with 'add' action and highlight data
- **annotation-perf.AC3.2 Success:** Local highlight remove fires observer with 'remove' action and highlight ID
- **annotation-perf.AC3.3 Success:** Remote update via apply_update() fires observer on receiving client
- **annotation-perf.AC3.4 Success:** Tag change fires observer with 'modify' action
- **annotation-perf.AC3.5 Success:** Comment add fires observer (via observe_deep) with highlight ID
- **annotation-perf.AC3.6 Failure:** Observer does not fire for the originating client's own broadcast echo

### annotation-perf.AC4: Module split
- **annotation-perf.AC4.1 Success:** annotation.py replaced by pages/annotation/ package with focused modules
- **annotation-perf.AC4.2 Success:** All existing tests pass without modification (except import paths if needed)
- **annotation-perf.AC4.3 Success:** No logic changes — pure mechanical move

> **Addressed by:** Issue #120 (annotation-split). See `docs/design-plans/2026-02-14-120-annotation-split.md`.

## Glossary

- **CRDT (Conflict-free Replicated Data Type)**: A data structure that enables multiple clients to make concurrent edits without coordination, automatically merging changes without conflicts. PromptGrimoire uses pycrdt to sync annotations in real-time across browsers.
- **pycrdt**: Python library implementing CRDTs. Provides `Doc` (CRDT document), `Map` (dictionary-like CRDT), and observer pattern for change notifications.
- **Observer pattern**: A design pattern where objects (observers) register callbacks to be notified when another object (observable) changes state. pycrdt's `Map.observe()` fires events when keys are added, removed, or modified.
- **MapEvent**: pycrdt's event object passed to `Map.observe()` callbacks, containing details about which keys changed and how (add/remove/modify).
- **Debounce**: A technique that delays an action until a period of inactivity. Adding 5 highlights in 2 seconds results in only 1 database write after the 5-second quiet period.
- **Hot path**: The most frequently executed code path in an application. For annotation, this is the add-highlight flow triggered by pressing number keys.
- **NiceGUI**: Python web framework used for PromptGrimoire's UI. Components like `.card()` and `.label()` create reactive DOM elements.
- **Char span**: A `<span class="char" data-char-index="N">` wrapper around each text character, enabling character-level selection targeting for highlights.
- **Annotation card**: A NiceGUI card component displaying a single highlight's metadata (tag, comment, text range).
- **Origin tracking**: Mechanism to prevent update loops where a client's broadcast would trigger its own observer. Uses Python's `ContextVar` to mark "I originated this change."
- **ContextVar**: Python's context-local storage mechanism (like thread-local but for async tasks). Used to track which client originated a CRDT change to prevent echo.

## Architecture

Three independent bottlenecks compound on the annotation-add hot path:

1. **Synchronous persistence** — `force_persist_workspace()` serializes the entire CRDT doc to PostgreSQL and awaits the round-trip before updating the UI.
2. **Full card rebuild** — `_refresh_annotation_cards()` calls `.clear()` on the container then rebuilds every annotation card. Adding highlight #51 destroys and recreates all 50 existing cards.
3. **O(n×m) CSS generation** — `_build_highlight_css()` generates one CSS selector per character per highlight, rebuilding from scratch on every mutation.

The design addresses (1) and (2) in a single performance PR, preceded by a mechanical refactor of the 2,302-line `annotation.py`. CSS optimization (3) is deferred to a follow-up PR but the observer pattern introduced here enables incremental CSS append as a natural extension.

### Debounced Persistence

The persistence manager (`src/promptgrimoire/crdt/persistence.py`) already implements a 5-second debounce timer via `mark_dirty_workspace()` → `_schedule_debounced_workspace_save()`. The annotation page bypasses this by calling `force_persist_workspace()` after every mutation "for test observability."

The fix: mutation handlers call only `mark_dirty_workspace()`. `force_persist_workspace()` is retained for lifecycle events (client disconnect, app shutdown, before PDF export). Test configuration sets `debounce_seconds=0` so the timer fires effectively immediately during tests.

### CRDT-Driven Incremental Card Updates

pycrdt's `Map.observe(callback)` fires a `MapEvent` when keys are added, removed, or modified — for both local and remote changes. Registering an observer on `doc["highlights"]` provides a single code path that replaces both the local `_refresh_annotation_cards()` call and the remote `handle_update_from_other()` card rebuild.

Observer reactions:
- **Key added** → build one new card, append to `annotations_container`
- **Key removed** → call `.delete()` on `state.annotation_cards[hl_id]`
- **Key modified** (tag change, comment add) → delete and rebuild that one card

`_refresh_annotation_cards()` becomes a fallback for bulk operations: initial page load and tab switches.

### Data Flow

```
User presses number key
  → _add_highlight() adds to CRDT Map
  → mark_dirty_workspace() schedules debounced DB write
  → Map.observe() fires MapEvent (key added)
  → _on_highlight_change() appends one card + appends CSS for new range
  → CRDT broadcasts update to other clients
  → Remote client's Map.observe() fires same MapEvent
  → Remote client's _on_highlight_change() appends same card
```

No explicit `broadcast_update()` call needed for card rebuilds — the CRDT sync layer triggers the observer on remote clients automatically.

## Existing Patterns

### Persistence Manager Debounce

`mark_dirty_workspace()` at `persistence.py:59-80` already schedules saves via `_schedule_debounced_workspace_save()`. Each new edit resets the 5-second timer. `force_persist_workspace()` at `persistence.py:140-157` cancels the pending task and writes immediately. The debounce infrastructure is fully built; the annotation page simply doesn't use it.

### Individual Element Deletion

NiceGUI's `.delete()` method is already used in `_delete_highlight()` at `annotation.py:703` to remove a single card without clearing the container. The `state.annotation_cards` dict already tracks cards by highlight ID. The incremental approach extends this existing pattern.

### CRDT Observer Pattern

`AnnotationDocument` at `annotation_doc.py` already registers `Doc.observe(self._on_update)` for broadcasting binary updates. The design adds a `Map.observe()` on `doc["highlights"]` for structured change notifications. Origin tracking uses the existing `ContextVar` pattern (`_origin_var`) to prevent echo.

### No Divergence

All three optimizations follow patterns already present in the codebase. No new architectural patterns are introduced.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Mechanical Refactor of annotation.py

**Goal:** Split the 2,302-line `annotation.py` into a `pages/annotation/` package for manageable file sizes.

**Components (actual structure after #120):**
- `src/promptgrimoire/pages/annotation/__init__.py` — Core types (PageState, _RemotePresence), globals, route entry point
- `src/promptgrimoire/pages/annotation/broadcast.py` — Multi-client sync, remote presence, Yjs update relay
- `src/promptgrimoire/pages/annotation/cards.py` — Annotation card UI (build, expand, comments, refresh)
- `src/promptgrimoire/pages/annotation/content_form.py` — Content paste/upload form with platform detection
- `src/promptgrimoire/pages/annotation/css.py` — CSS constants (_PAGE_CSS), tag toolbar, highlight pseudo-CSS
- `src/promptgrimoire/pages/annotation/document.py` — Document rendering with CSS Highlight API, selection handlers
- `src/promptgrimoire/pages/annotation/highlights.py` — Highlight CRUD, JSON serialisation, push-to-client, warp
- `src/promptgrimoire/pages/annotation/organise.py` — Tab 2: organise highlights by tag (drag-and-drop columns)
- `src/promptgrimoire/pages/annotation/pdf_export.py` — PDF export orchestration with loading notification
- `src/promptgrimoire/pages/annotation/respond.py` — Tab 3: respond with reference panel and CRDT markdown
- `src/promptgrimoire/pages/annotation/tags.py` — Tag abstractions (TagInfo, brief_tags_to_tag_info)
- `src/promptgrimoire/pages/annotation/workspace.py` — Workspace view orchestrator, header, placement, copy protection

**Dependencies:** None (first phase, separate PR)

**Done when:** All existing tests pass at current baseline. No logic changes — pure mechanical move. Imports updated throughout codebase.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Debounce Persistence

**Goal:** Remove database round-trip from the annotation-add hot path.

**Components:**
- Mutation handlers in `pages/annotation/highlights.py` — replace `force_persist_workspace()` with `mark_dirty_workspace()`
- Comment handlers in `pages/annotation/cards.py` — same replacement
- Tag change handlers in `pages/annotation/cards.py` — same replacement
- Test configuration — set `debounce_seconds=0` on persistence manager in test fixtures
- Lifecycle handlers — verify `force_persist_workspace()` retained in `on_disconnect()` and `app.on_shutdown`

**Dependencies:** Phase 1 (file split)

**Done when:** Annotation add/remove/comment/tag-change no longer awaits DB write. `force_persist_workspace()` only called in lifecycle events and before export. Tests pass with `debounce_seconds=0`.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: CRDT Highlight Observer

**Goal:** Register `Map.observe()` on `doc["highlights"]` and expose structured change events to the annotation page.

**Components:**
- `src/promptgrimoire/crdt/annotation_doc.py` — add `observe_highlights(callback)` method wrapping `Map.observe()` and `Map.observe_deep()`, parse `MapEvent` into add/remove/modify actions
- Observer callback contract — callback receives structured change info: action type (add/remove/modify), highlight ID, highlight data (for add/modify)

**Dependencies:** Phase 1 (file split)

**Done when:** Observer fires correctly for local add, local remove, local modify (tag change, comment add), and remote updates applied via `apply_update()`. Unit tests verify each case.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Incremental Card Updates

**Goal:** Wire the CRDT observer to drive incremental card add/remove/rebuild instead of full container clear.

**Components:**
- `pages/annotation/cards.py` — new `_on_highlight_change(event)` handler that dispatches to add/remove/rebuild-one based on action type
- `pages/annotation/cards.py` — `_refresh_annotation_cards()` retained as fallback for initial load and tab switch
- `pages/annotation/broadcast.py` — remove card rebuild from `handle_update_from_other()` (observer handles it)
- `pages/annotation/highlights.py` — remove explicit `state.refresh_annotations()` call from `_add_highlight()` (observer handles it)

**Dependencies:** Phase 3 (observer), Phase 2 (debounce)

**Done when:** Adding highlight #51 does not destroy the existing 50 cards. Removing a highlight deletes only that card. Tag change rebuilds only the affected card. Remote updates from other clients trigger incremental updates via the observer, not full rebuild. Manual QA confirms no visual glitches with 10+ rapid highlight additions.
<!-- END_PHASE_4 -->

## Additional Considerations

**CSS optimization (future — #141):** The observer pattern enables incremental CSS append as a natural next step. On highlight add, only the new highlight's char-range CSS rules need appending. This is deferred to a separate PR to keep the current scope focused.

**Lazy char span injection (future — #137):** Paragraph-level `IntersectionObserver` for DOM reduction on large documents. Independent of this design. Detailed design already exists in issue #137.

**Persistence failure visibility:** The current `_persist_workspace()` swallows exceptions with `logger.exception()`. The workspace stays in `_workspace_dirty` so subsequent lifecycle flushes (disconnect, shutdown) will retry. However, a sustained DB outage would be invisible to the user. Phase 2 should add a UI toast on background write failure so the user knows to save their work externally.

**Implementation scoping:** This design has 4 phases across 2 PRs (Phase 1 = PR 0, Phases 2-4 = PR 1). Well within the 8-phase limit.
