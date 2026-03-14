# Multi-Document Tabbed Workspace Design

**GitHub Issue:** [#186](https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/186)

## Summary

PromptGrimoire currently shows one document at a time in the annotation workspace, under a three-tab layout (Annotate | Organise | Respond). This feature replaces that layout with a flat tab bar where each uploaded document gets its own "Source N: Title" tab, while Organise and Respond remain as shared aggregate views at the end. The result is that a student or instructor can work with several source texts side-by-side in the same workspace — switching between them without losing annotation state, and seeing all their highlights consolidated in Organise and Respond regardless of which document they came from.

The implementation is deliberately staged across 14 phases (including Phase 3b) because the current card-rendering code must be cleaned up before multi-document logic can be added safely. The first half (Phases 1–6) focuses on characterisation tests, unifying card display behaviour across tabs, sequentially extracting shared rendering utilities (cards.py first, then respond.py — stabilise one extraction before the next), replacing the current "clear and rebuild everything" card update with a surgical diff-based approach, and then pulling tab-management code out of the 865-line `workspace.py` into dedicated modules. Only once that refactoring is complete does the second half (Phases 7–13) add the visible new features: document rename, the "+" add-document tab, CRDT annotation purge on delete, source labels in Organise/Respond, cross-tab "locate in document" navigation, instructor upload controls, real-time cross-client tab sync, and documentation updates. Each phase delivers a stable, tested state. Throughout, the DB remains the authoritative source for the document list; the CRDT layer (which already stores `document_id` on every highlight) needs no structural changes.

## Definition of Done

The annotation workspace renders multiple documents as flat tabs (Source 1: Title | Source 2: Title | ... | Organise | Respond), replacing the current single-document view. Each source tab shows its own document content and annotation cards. Organise and Respond tabs remain shared across all sources, with highlight/tag cards labelled by source document. Documents can be added (respecting instructor max-tabs limit), renamed, reordered, and deleted (with existing warnings, plus annotation purge from CRDT). Workspace title is editable from within the annotation page. The `enable_multi_document` feature flag is removed — multi-document becomes the default behaviour. Tab overflow is handled gracefully for workspaces with many documents.

### Success Criteria

1. Flat tab bar: Source N: Title tabs + Organise + Respond
2. Each source tab renders its own document content and annotation cards
3. Organise and Respond tabs shared across all sources; tags labelled by source
4. "Add document" always available (instructor can disable or cap via `max_tabs` activity setting)
5. Document rename — new DB function and UI in management dialog
6. Workspace rename accessible from within the annotation page
7. Document management dialog updated for tab-awareness
8. Delete document purges its annotations from CRDT, with confirmation warning
9. `enable_multi_document` feature flag removed — multi-doc is default
10. Tab overflow handling for workspaces with many documents

## Acceptance Criteria

### multi-doc-tabs-186.AC1: Tab Bar Renders Document Tabs
- **multi-doc-tabs-186.AC1.1 Success:** Workspace with 3 documents shows "Source 1: Title | Source 2: Title | Source 3: Title | + | Organise | Respond"
- **multi-doc-tabs-186.AC1.2 Success:** Single-document workspace shows "Source 1: Title | + | Organise | Respond" (graceful single-doc degradation)
- **multi-doc-tabs-186.AC1.3 Success:** Tabs render in `order_index` sequence from DB
- **multi-doc-tabs-186.AC1.4 Success:** Quasar scroll arrows appear when tabs exceed container width
- **multi-doc-tabs-186.AC1.5 Edge:** Workspace with zero documents shows only "+ | Organise | Respond"
- **multi-doc-tabs-186.AC1.6 Edge:** Document with no title shows "Source N" (no trailing colon or empty string)

### multi-doc-tabs-186.AC2: Per-Document Content and Annotations
- **multi-doc-tabs-186.AC2.1 Success:** Each source tab renders its own document HTML content
- **multi-doc-tabs-186.AC2.2 Success:** Each source tab shows only that document's annotation cards (filtered by `document_id`)
- **multi-doc-tabs-186.AC2.3 Success:** Highlights created on Source 2 do not appear in Source 1's annotation cards
- **multi-doc-tabs-186.AC2.4 Success:** Tab content renders on first visit (deferred) and persists in DOM on subsequent visits (no re-render)
- **multi-doc-tabs-186.AC2.5 Edge:** Switching tabs rapidly does not cause duplicate content or orphaned elements

### multi-doc-tabs-186.AC3: Source Labelling in Organise and Respond
- **multi-doc-tabs-186.AC3.1 Success:** Organise tiles show "Document Title, [para N]" subtitle identifying source document
- **multi-doc-tabs-186.AC3.2 Success:** Respond reference cards show same "Document Title, [para N]" subtitle
- **multi-doc-tabs-186.AC3.3 Success:** Source label present even in single-document workspaces
- **multi-doc-tabs-186.AC3.4 Success:** Renaming a document updates source labels in Organise and Respond on next render

### multi-doc-tabs-186.AC4: Cross-Tab Locate
- **multi-doc-tabs-186.AC4.1 Success:** "Locate in document" from Organise switches to the correct source tab and scrolls to the highlight
- **multi-doc-tabs-186.AC4.2 Success:** "Locate in document" from Respond switches to the correct source tab and scrolls to the highlight
- **multi-doc-tabs-186.AC4.3 Success:** Locate to an unvisited tab triggers deferred rendering, then scrolls
- **multi-doc-tabs-186.AC4.4 Failure:** Locate for a deleted document's highlight does not crash (highlight should have been purged)

### multi-doc-tabs-186.AC5: Add Document
- **multi-doc-tabs-186.AC5.1 Success:** "+" tab opens content form (paste/upload); new document appears as new tab, auto-selected
- **multi-doc-tabs-186.AC5.2 Success:** New document's title defaults to uploaded filename (minus extension)
- **multi-doc-tabs-186.AC5.3 Success:** Pasted content with no filename defaults title to first 30 characters of plain text
- **multi-doc-tabs-186.AC5.4 Success:** New document gets next `order_index` and correct "Source N" numbering
- **multi-doc-tabs-186.AC5.5 Failure:** "+" tab hidden when `max_documents` limit reached
- **multi-doc-tabs-186.AC5.6 Failure:** "+" tab hidden for students when `allow_student_uploads` is false
- **multi-doc-tabs-186.AC5.7 Failure:** Server-side guard rejects document creation when limit reached (not just UI hiding)

### multi-doc-tabs-186.AC6: Document Rename
- **multi-doc-tabs-186.AC6.1 Success:** Document can be renamed via management dialog inline-edit
- **multi-doc-tabs-186.AC6.2 Success:** Tab label updates to "Source N: New Title" after rename
- **multi-doc-tabs-186.AC6.3 Success:** `search_dirty` set on workspace after rename (FTS reindex)
- **multi-doc-tabs-186.AC6.4 Failure:** Empty title rejected with validation error

### multi-doc-tabs-186.AC7: Workspace Rename from Annotation Page
- **multi-doc-tabs-186.AC7.1 Success:** Workspace title editable via pencil icon in annotation page header
- **multi-doc-tabs-186.AC7.2 Success:** Renamed title persists across page reload
- **multi-doc-tabs-186.AC7.3 Success:** Rename calls existing `update_workspace_title()` (sets `search_dirty`)

### multi-doc-tabs-186.AC8: Document Management Dialog
- **multi-doc-tabs-186.AC8.1 Success:** Pencil icon on source tab opens management dialog
- **multi-doc-tabs-186.AC8.2 Success:** Management dialog shows all documents with rename, reorder, and delete controls
- **multi-doc-tabs-186.AC8.3 Success:** Reordering documents changes Source N numbering and rebuilds tab bar

### multi-doc-tabs-186.AC9: Delete Document with CRDT Purge
- **multi-doc-tabs-186.AC9.1 Success:** Deleting a document removes all its highlights from the CRDT
- **multi-doc-tabs-186.AC9.2 Success:** Confirmation dialog shown before delete (existing pattern)
- **multi-doc-tabs-186.AC9.3 Success:** After delete, active tab switches to next remaining source tab
- **multi-doc-tabs-186.AC9.4 Success:** Deleted document's tab and panel removed from DOM
- **multi-doc-tabs-186.AC9.5 Edge:** Deleting last document leaves workspace with "+ | Organise | Respond" only
- **multi-doc-tabs-186.AC9.6 Failure:** Template-cloned documents still protected by `ProtectedDocumentError`

### multi-doc-tabs-186.AC10: Feature Flag Removal
- **multi-doc-tabs-186.AC10.1 Success:** Multi-document works without `enable_multi_document` config setting
- **multi-doc-tabs-186.AC10.2 Success:** Existing single-document workspaces continue to work unchanged

### multi-doc-tabs-186.AC11: Card Consistency
- **multi-doc-tabs-186.AC11.1 Success:** Organise cards use `_build_expandable_text()` (80-char truncate with toggle)
- **multi-doc-tabs-186.AC11.2 Success:** Respond cards use `_build_expandable_text()` (80-char truncate with toggle)
- **multi-doc-tabs-186.AC11.3 Success:** Respond cards use `anonymise_author()` for highlight authors
- **multi-doc-tabs-186.AC11.4 Success:** All three tabs use identical expandable text behaviour

### multi-doc-tabs-186.AC12: Diff-Based Card Updates
- **multi-doc-tabs-186.AC12.1 Success:** Adding a highlight inserts one card without destroying or rebuilding other cards
- **multi-doc-tabs-186.AC12.2 Success:** Removing a highlight deletes one card element without full container rebuild
- **multi-doc-tabs-186.AC12.3 Success:** New card inserted at correct position sorted by `start_char`
- **multi-doc-tabs-186.AC12.4 Success:** Tag or comment change on a highlight updates only that card
- **multi-doc-tabs-186.AC12.5 Edge:** Rapid successive CRDT updates (debounced) do not produce duplicate or missing cards

### multi-doc-tabs-186.AC13: Cross-Client Synchronisation
- **multi-doc-tabs-186.AC13.1 Success:** Document add by one client causes new tab to appear for other clients in same workspace
- **multi-doc-tabs-186.AC13.2 Success:** Document rename by one client updates tab label for other clients
- **multi-doc-tabs-186.AC13.3 Success:** Document delete by one client removes tab for other clients
- **multi-doc-tabs-186.AC13.4 Edge:** Client viewing a document that another client deletes is switched to next tab with notification

### multi-doc-tabs-186.AC14: Instructor Controls
- **multi-doc-tabs-186.AC14.1 Success:** `allow_student_uploads=False` hides "+" tab for students; editors/owners still see it
- **multi-doc-tabs-186.AC14.2 Success:** `max_documents=5` hides "+" tab when workspace has 5 documents
- **multi-doc-tabs-186.AC14.3 Success:** Settings configurable at activity level
- **multi-doc-tabs-186.AC14.4 Failure:** `max_documents=0` prevents any document uploads (edge: should this be valid?)

## Glossary

- **Annotation workspace**: The main page where users read source documents, create highlights, and write notes. Currently structured as three tabs (Annotate | Organise | Respond); this feature expands the tab bar to N source tabs.
- **CRDT (Conflict-free Replicated Data Type)**: A data structure that multiple clients can edit simultaneously and that always merges without conflicts. Implemented via `pycrdt`. Highlights, tags, and comments are stored in a CRDT document; the document list is stored in PostgreSQL, not the CRDT.
- **`AnnotationDoc`**: The project's CRDT document class (`crdt/annotation_doc.py`). Stores highlights keyed by ID, each with `document_id`, `start_char`, tags, and comments.
- **Highlight**: A user-selected text span within a source document. Stored in the CRDT with position (`start_char`), tags, and comments. The core unit of annotation.
- **Annotation card**: The UI element representing one highlight. Displays the highlighted text, tags, and comments. Cards in source tabs are per-document; cards in Organise and Respond aggregate across all documents.
- **`PageState`**: The server-side Python object that tracks all mutable UI state for one client's session on the annotation page — tab references, card registries, rendered flags, etc.
- **`DocumentTabState`**: A new dataclass proposed by this design. Holds per-document references: `ui.tab`, `ui.tab_panel`, document content container, annotation cards container, card registry dict, and rendered/epoch flags.
- **Diff-based card update**: An update strategy where only changed cards are added, removed, or repositioned — contrasted with the current "clear the container and rebuild all cards" approach. Prevents destroying in-flight UI interactions on other cards.
- **`@ui.refreshable`**: A NiceGUI decorator for incremental re-execution. Explicitly rejected here due to known NiceGUI bugs (#2535, #2502, #3392) that cause cross-session contamination and memory leaks in multi-user contexts.
- **NiceGUI**: The Python web UI framework used throughout the project. Renders server-side Python as a reactive browser UI over a WebSocket connection.
- **Quasar**: The Vue component library underlying NiceGUI. `QTabs` provides native scroll arrows when tabs overflow the container width.
- **`_RemotePresence`**: Existing WebSocket-based peer-awareness module. Tracks who else is viewing the same workspace. Extended by this design to carry a "documents changed" signal for cross-client tab bar sync.
- **`order_index`**: Integer column on `WorkspaceDocument` that determines display order within a workspace. Controls the "Source N" numbering.
- **`search_dirty`**: Boolean flag on `Workspace`. Set to true whenever content changes; the background `search_worker` re-extracts text for full-text search indexing.
- **`enable_multi_document`**: Existing feature flag (boolean, default false) in `config.py`. This feature removes it — multi-document becomes the unconditional default.
- **`max_documents`**: New activity-level integer setting (nullable, null = unlimited) that caps documents per workspace.
- **`allow_student_uploads`**: New activity-level boolean setting (default true) controlling whether students can add documents via the "+" tab.
- **Deferred tab rendering**: Pattern where tab panel content is not built until the user first visits that tab. Existing pattern for the Respond tab; extended here to all source document tabs.
- **All-in-DOM persistence**: Rendered tab panels stay in the browser DOM when not active (Quasar `keep-alive` default). Tab switching is CSS visibility only — no re-render.
- **`cards_epoch`**: Monotonic integer counter per document. Incremented after each card diff and broadcast to client-side JavaScript. Used by E2E tests to wait for card updates to settle.
- **`complexipy`**: Cyclomatic complexity checker used in CI hooks. File-level limits constrain how much logic can live in a single module — the reason Phases 3 and 5 extract shared utilities before adding new functionality.
- **`render_inline_title_edit()`**: Existing UI helper in `navigator/_cards.py` for read-only borderless input with pencil icon, switching to edit mode on click. Reused for workspace title editing in the annotation page header.

## Architecture

### Tab Bar Structure

The existing 3-tab layout (Annotate | Organise | Respond) becomes a flat bar:

```
Source 1: Title | Source 2: Title | ... | [+] | Organise | Respond
```

- Each source tab is a `ui.tab` generated dynamically from `list_documents(workspace_id)`, labelled "Source {order_index + 1}: {title}". Untitled documents show "Source {N}" only.
- The "+" pseudo-tab opens the content form (existing paste handler / file upload). Not a real tab — clicking it opens a dialog, does not navigate to a panel. Hidden when `allow_student_uploads` is false or `max_documents` is reached.
- Organise and Respond remain as fixed tabs at the end, unchanged in core behaviour.
- Quasar's native `QTabs` scroll arrows handle overflow when many document tabs exist.
- A pencil icon on each source tab opens the Manage Documents dialog for rename, reorder, and delete.

### Per-Document State

`PageState` gains a `document_tabs: dict[UUID, DocumentTabState]` mapping. Each `DocumentTabState` holds:

- `document_id: UUID`
- `tab: ui.tab` — reference for label updates and deletion
- `panel: ui.tab_panel` — reference for deletion
- `document_container: ui.column | None` — write-once, populated on first visit
- `cards_container: ui.column | None` — holds annotation cards
- `annotation_cards: dict[str, ui.element]` — live registry mapping `highlight_id` to card element
- `rendered: bool` — gate for deferred first-visit rendering
- `cards_epoch: int` — per-document monotonic counter for E2E test sync

### Diff-Based Card Updates (No `@ui.refreshable`)

`@ui.refreshable` is not used for card rendering. Known issues with multi-session cross-contamination (NiceGUI #2535), memory leaks (#2502), and lifecycle bugs (#3392) make it unsuitable for a multi-document, multi-user context.

Instead, cards are updated via diff against the `annotation_cards` registry:

1. On CRDT change, get current highlights for the affected document (sorted by `start_char`).
2. Diff highlight IDs against `annotation_cards.keys()`:
   - **Added**: `_build_annotation_card()` for the new highlight, then `card.move(cards_container, target_index=N)` to insert at correct `start_char` position.
   - **Removed**: `card.delete()` on the element, remove from dict.
   - **Changed** (tag/comment change): delete the old card element, rebuild single card, `.move()` to correct position.
3. Increment per-document `cards_epoch`, broadcast to client JS.

This preserves scroll position, does not destroy in-flight interactions on other cards, and avoids the session-tracking bugs of `@ui.refreshable`.

### Deferred Tab Rendering

Each source tab panel renders its content on first visit, not on page load. This follows the existing pattern used for the Respond tab (lazy Milkdown editor initialisation).

- Unvisited tabs have `rendered=False` and `None` container references.
- CRDT broadcasts for unvisited tabs are no-ops — the tab will render from current CRDT state when first visited.
- Document HTML content is immutable after upload — rendered once into `document_container`, never cleared.

### All-in-DOM Persistence

All rendered tab panels persist in DOM (Quasar `keep-alive` default). Tab switching is a CSS visibility change — no re-rendering. A 240-page document renders once and stays in DOM. If performance becomes a problem with many large documents, a future refactor can switch to active-tab-only rendering.

### Card Consistency Across Tabs

All three tab types (source, Organise, Respond) use the same card UX patterns:

- **Expandable text**: `_build_expandable_text()` from `cards.py` (80-char truncate with toggle). Currently missing from Organise (50-char static truncation) and Respond (same). Must be unified.
- **Anonymisation**: `anonymise_author()` applied consistently. Currently missing from Respond cards (`respond.py:155` uses raw author).

These are prerequisite fixes before multi-doc work begins.

### Source Labelling

In Organise and Respond tabs, each card shows a "Document Title, [para N]" subtitle indicating which source document the highlight came from. Always shown, even in single-document workspaces, for consistency.

Document title defaults:
- Uploaded file: filename minus extension
- Pasted content: first 30 characters of plain text
- User can rename via management dialog

### Cross-Tab Locate

"Locate in document" buttons in Organise and Respond switch to the correct source tab and scroll to the highlight position. Currently `_warp_to_highlight()` scrolls within the current document — it must also switch `tab_panels.value` to the target document's tab when the highlight is in a different document.

### Document Management

The existing `document_management.py` dialog is extended:

- **Rename**: New `rename_document(document_id, new_title)` DB function. Inline-editable title in the management dialog. Renaming updates the tab label.
- **Delete**: Existing flow plus CRDT annotation purge via new `remove_highlights_for_document(document_id)` helper on `AnnotationDoc`. Iterates `get_highlights_for_document()` and calls `remove_highlight()` for each.
- **Reorder**: Existing `reorder_documents()`. Reordering changes Source N numbering. Tab bar rebuilds.
- **Workspace rename**: Inline-editable title in the annotation page header (same pattern as navigator cards), calling existing `update_workspace_title()`.

### Instructor Controls

Two new activity-level settings:

- `allow_student_uploads: bool = True` — whether students can add documents via the "+" tab. When false, "+" is hidden for non-editors.
- `max_documents: int | None = None` — cap on documents per workspace. When reached, "+" is hidden. Null means unlimited.

Checked at render time (tab visibility) and at submission time (server-side guard in paste handler).

### Cross-Client Document Synchronisation

Document add/rename/delete is a DB operation, not a CRDT operation. When one client modifies the document list:

1. Broadcast a "documents changed" signal to all clients in the workspace via the existing `_RemotePresence` WebSocket channel.
2. Receiving clients re-fetch `list_documents()` from DB and rebuild the tab bar (≤8 elements, trivial).
3. If a client's active document was deleted, switch to the first remaining source tab with a notification.

No CRDT mirror of the document list — the DB is the source of truth. Document operations are infrequent (setup time, not real-time editing), so the broadcast overhead is minimal.

## Existing Patterns

### Tab Structure (`workspace.py:667-790`)
Current 3-tab layout uses `ui.tabs` + `ui.tab_panels` with `on_change` handler dispatching to tab-specific logic. Deferred rendering for Respond tab (lazy Milkdown init). This design extends the same pattern to N document tabs.

### Card Rendering (`cards.py:563-605`)
`_refresh_annotation_cards()` clears container and rebuilds from CRDT state. `state.annotation_cards: dict[str, ui.element]` already exists as a card registry but is rebuilt from scratch each time. This design repurposes the registry for diff-based updates.

### Document Filtering (`annotation_doc.py:365-377`, `highlights.py:86`)
CRDT already stores `document_id` on highlights. `get_highlights_for_document()` filters by document. `_build_highlight_json()` already uses this filter when `state.document_id` is set. Multi-document support is wired in the CRDT layer — the gap is UI only.

### Feature Flag (`config.py:87`)
`enable_multi_document: bool = False` gates the content form. Content form rendering (`workspace.py:557-588`) shows collapsible "Add Document" when enabled. This design removes the flag entirely.

### Remote Presence (`_RemotePresence`)
Existing WebSocket-based peer awareness within a workspace. Used for user count display and peer-left callbacks. This design extends it with a "documents changed" signal type.

### Inline Title Edit (`navigator/_cards.py:151-197`)
`render_inline_title_edit()` provides readonly borderless input with pencil icon, edit mode toggle, save on confirm/enter/blur. This design reuses the same pattern for workspace title in the annotation page header.

### Document Management Dialog (`document_management.py:140-168`)
Lists documents with edit/delete buttons. Clone protection warnings. This design adds rename capability and pencil-icon tab affordance to open the dialog.

### Divergence: `@ui.refreshable` Replacement
The current card rebuild uses `@ui.refreshable` semantics (clear + rebuild all). This design replaces it with diff-based updates — a new pattern in this codebase. Justified by known NiceGUI bugs (#2535, #2502, #3392) that multiply in a multi-document, multi-user context.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Characterisation Tests for Card Behaviour

**Goal:** Establish regression safety net for existing card rendering before any refactoring.

**Components:**
- Tests in `tests/` covering current `_refresh_annotation_cards()` behaviour — card creation, ordering by `start_char`, highlight text display, tag display, comment display, expandable text
- Tests covering Organise tile rendering — snippet display, locate button, drag-and-drop ordering
- Tests covering Respond reference card rendering — snippet display, locate button, comment display
- Identify gaps in current test coverage for card rendering paths

**Dependencies:** None (first phase)

**Done when:** Comprehensive tests exist for current card rendering behaviour across all three tabs; all tests pass against unmodified code
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Card Consistency Fixes

**Goal:** Unify card UX across Annotate, Organise, and Respond tabs

**Components:**
- `src/promptgrimoire/pages/annotation/organise.py` — replace 50-char static truncation with `_build_expandable_text()` from `cards.py`
- `src/promptgrimoire/pages/annotation/respond.py` — replace 50-char static truncation with `_build_expandable_text()`, add `anonymise_author()` call (currently missing at line 155)
- Shared card utilities extracted if needed to avoid duplication

**Dependencies:** Phase 1 (characterisation tests as safety net)

**Done when:** All three tabs use expandable text (80-char truncate with toggle); Respond cards use `anonymise_author()`; all Phase 1 tests still pass plus new tests for the fixed behaviour
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Extract Shared Utilities from cards.py

**Goal:** Extract common card rendering logic from `cards.py` (605 lines) into a shared module before adding diff logic.

**Components:**
- New `src/promptgrimoire/pages/annotation/card_shared.py` — shared card rendering functions extracted from `cards.py`: `_build_expandable_text()`, comment rendering, locate button rendering
- `src/promptgrimoire/pages/annotation/cards.py` — import shared utilities, reduce line count
- `src/promptgrimoire/pages/annotation/organise.py` — import shared utilities from `card_shared.py`

**Dependencies:** Phase 2 (card consistency — extract after unifying, not before)

**Done when:** Shared utilities in `card_shared.py`; `cards.py` and `organise.py` import from it; all tests pass; complexipy clean
<!-- END_PHASE_3 -->

<!-- START_PHASE_3B -->
### Phase 3b: Extract Shared Utilities from respond.py

**Goal:** Complete the extraction by migrating `respond.py` (624 lines) to use the shared module. Separated from Phase 3 to reduce blast radius — stabilise `cards.py` extraction before touching Respond.

**Components:**
- `src/promptgrimoire/pages/annotation/respond.py` — replace inline card rendering with imports from `card_shared.py`
- `src/promptgrimoire/pages/annotation/card_shared.py` — add any respond-specific shared logic discovered during extraction

**Dependencies:** Phase 3 (cards.py extraction stable)

**Done when:** `respond.py` imports from `card_shared.py`; no duplicated rendering logic across all three files; all tests pass; complexipy clean
<!-- END_PHASE_3B -->

<!-- START_PHASE_4 -->
### Phase 4: Diff-Based Card Updates

**Goal:** Replace `_refresh_annotation_cards()` clear+rebuild with diff-based add/remove/update of individual cards

**Components:**
- `src/promptgrimoire/pages/annotation/cards.py` — new `_diff_annotation_cards()` function that compares CRDT state against `state.annotation_cards` registry and applies targeted add/remove/update operations using `element.move(target_index=N)` for positional insertion
- `src/promptgrimoire/pages/annotation/cards.py` — `_add_card()`, `_remove_card()`, `_update_card()` helpers
- `src/promptgrimoire/crdt/annotation_doc.py` — `remove_highlights_for_document(document_id)` convenience method (iterates + removes)
- Per-document `cards_epoch` support in `PageState`

**Dependencies:** Phase 3 (shared utilities extracted)

**Done when:** Card updates are diff-based; adding a highlight inserts one card without destroying others; removing a highlight deletes one card; existing tests pass; no `container.clear()` in card update path
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Extract Tab Management from workspace.py

**Goal:** Reduce `workspace.py` (865 lines) before adding multi-doc tab logic that would push it well past complexity limits.

**Components:**
- New `src/promptgrimoire/pages/annotation/tab_bar.py` — tab creation, tab change handling, deferred rendering orchestration
- New `src/promptgrimoire/pages/annotation/tab_state.py` — `DocumentTabState` dataclass, `PageState.document_tabs` dict management
- `src/promptgrimoire/pages/annotation/workspace.py` — reduced to top-level page assembly, delegating tab logic to extracted modules
- `src/promptgrimoire/pages/annotation/__init__.py` — updated imports

**Dependencies:** Phase 4 (diff-based cards — extract before adding multi-doc, not after)

**Done when:** Tab rendering and management logic lives in dedicated modules; `workspace.py` reduced; all tests pass; complexipy clean
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Multi-Document Tab Infrastructure

**Goal:** Flat tab bar with per-document tab panels and deferred rendering

**Components:**
- `src/promptgrimoire/pages/annotation/tab_state.py` — `DocumentTabState` dataclass populated per document
- `src/promptgrimoire/pages/annotation/tab_bar.py` — dynamic tab generation from `list_documents()`, deferred per-tab rendering
- `src/promptgrimoire/pages/annotation/workspace.py` — wire up multi-doc tab bar, replace static 3-tab layout
- `src/promptgrimoire/config.py` — remove `enable_multi_document` feature flag

**Dependencies:** Phase 5 (tab management extracted)

**Done when:** Workspace with multiple documents shows flat tab bar; each source tab renders its document and annotation cards on first visit; Organise and Respond tabs work as before; single-document workspaces degrade gracefully (one source tab + Organise + Respond)
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Document Rename and Title Defaults

**Goal:** Documents can be renamed; new documents get meaningful default titles

**Components:**
- `src/promptgrimoire/db/workspace_documents.py` — `rename_document(document_id, new_title)` function (UPDATE title, set `search_dirty`)
- `src/promptgrimoire/pages/annotation/document_management.py` — inline-editable title in management dialog
- `src/promptgrimoire/pages/annotation/paste_handler.py` — document title defaults to filename (minus extension) or first 30 chars of plain text content
- Tab label updates after rename

**Dependencies:** Phase 6 (tab infrastructure exists)

**Done when:** Documents can be renamed via management dialog; new documents get meaningful titles; tab labels update after rename
<!-- END_PHASE_7 -->

<!-- START_PHASE_8 -->
### Phase 8: Add Document Tab and Delete with CRDT Purge

**Goal:** "+" pseudo-tab for adding documents; delete purges annotations from CRDT

**Components:**
- `src/promptgrimoire/pages/annotation/tab_bar.py` — "+" pseudo-tab that opens content form dialog
- `src/promptgrimoire/pages/annotation/workspace.py` — new document appears as new tab, auto-selected
- `src/promptgrimoire/crdt/annotation_doc.py` — `remove_highlights_for_document()` called on document delete
- `src/promptgrimoire/pages/annotation/document_management.py` — delete flow extended with CRDT purge
- Tab bar rebuild after add/reorder/delete
- Pencil icon on source tabs to open management dialog

**Dependencies:** Phase 7 (rename and titles)

**Done when:** "+" tab adds documents; delete purges CRDT highlights and removes tab; pencil icon on tabs opens management dialog; tab bar rebuilds correctly
<!-- END_PHASE_8 -->

<!-- START_PHASE_9 -->
### Phase 9: Workspace Rename from Annotation Page

**Goal:** Workspace title editable from within the annotation page

**Components:**
- `src/promptgrimoire/pages/annotation/header.py` — inline-editable workspace title using same pattern as navigator cards (`render_inline_title_edit`)
- Calls existing `update_workspace_title()` DB function

**Dependencies:** Phase 6 (annotation page has tab infrastructure)

**Done when:** Workspace title editable via pencil icon in annotation page header; persists across page reload
<!-- END_PHASE_9 -->

<!-- START_PHASE_10 -->
### Phase 10: Source Labelling and Cross-Tab Locate

**Goal:** Organise and Respond cards identify their source document; locate navigates across tabs

**Components:**
- `src/promptgrimoire/pages/annotation/organise.py` — "Document Title, [para N]" subtitle on each tile
- `src/promptgrimoire/pages/annotation/respond.py` — same subtitle on each reference card
- `src/promptgrimoire/pages/annotation/highlights.py` — `_warp_to_highlight()` extended to switch `tab_panels.value` to the target document's tab before scrolling
- Document title lookup via `PageState.document_tabs` (document_id → order index + title)

**Dependencies:** Phase 8 (document management complete, titles available)

**Done when:** Organise/Respond cards show source document title with paragraph reference; "Locate in document" from Organise/Respond switches to correct source tab and scrolls to highlight
<!-- END_PHASE_10 -->

<!-- START_PHASE_11 -->
### Phase 11: Instructor Controls

**Goal:** Activity-level settings for document upload permissions and limits

**Components:**
- Database migration adding `allow_student_uploads` (boolean, default true) and `max_documents` (integer, nullable) to Activity model
- `src/promptgrimoire/pages/annotation/tab_bar.py` — "+" tab visibility gated by settings
- `src/promptgrimoire/pages/annotation/paste_handler.py` — server-side guard rejecting uploads when limit reached
- Activity settings UI — controls for the two new settings

**Dependencies:** Phase 8 ("+" tab exists to gate)

**Done when:** Instructor can set upload permission and document cap; "+" tab respects limits; server-side enforcement
<!-- END_PHASE_11 -->

<!-- START_PHASE_12 -->
### Phase 12: Cross-Client Document Synchronisation

**Goal:** Real-time tab bar sync when documents are added, renamed, or deleted by another client

**Components:**
- `src/promptgrimoire/pages/annotation/workspace.py` — "documents changed" broadcast via `_RemotePresence` channel on document add/rename/delete
- Receiving clients re-fetch `list_documents()` and rebuild tab bar
- Active-document-deleted handling (switch to first remaining tab + notification)

**Dependencies:** Phase 8 (document management), Phase 6 (tab infrastructure)

**Done when:** Document changes by one client update other clients' tab bars; deleted-document-while-viewing handled gracefully
<!-- END_PHASE_12 -->

<!-- START_PHASE_13 -->
### Phase 13: Documentation

**Goal:** Update all four user-facing documentation routes to reflect multi-document workflow

**Components:**
- `src/promptgrimoire/docs/scripts/using_promptgrimoire.py` — general guide updated with multi-document concepts, tab navigation, document management
- `src/promptgrimoire/docs/scripts/student_workflow.py` — student perspective on working with multiple source documents, adding documents, navigating tabs
- `src/promptgrimoire/docs/scripts/instructor_setup.py` — activity configuration for `allow_student_uploads` and `max_documents`, document pre-loading workflow
- `src/promptgrimoire/docs/scripts/personal_grimoire.py` — personal workspace multi-document usage
- Screenshots of multi-document tab bar, management dialog (with rename), source labelling in Organise/Respond, workspace rename
- `uv run grimoire docs build` verification
- Use `add-docs-entry` skill for each new documentation entry

**Dependencies:** All prior phases complete

**Done when:** All four documentation routes updated; `uv run grimoire docs build` succeeds; screenshots reflect implemented UI
<!-- END_PHASE_13 -->

## Additional Considerations

**Implementation scoping:** This design has 14 phases (including Phase 3b). The writing-plans skill limits implementation plans to 8 phases. This design should be split into at least two implementation plans:
1. **Plan A (Phases 1–6):** Card fixes, shared utility extraction (sequential), diff-based updates, tab management extraction, multi-doc tab infrastructure
2. **Plan B (Phases 7–13):** Document management, source labelling, instructor controls, cross-client sync, documentation

**File size management:** `workspace.py` (865 lines), `cards.py` (605 lines), and `respond.py` (624 lines) are already near complexity limits. Phases 3 and 5 are explicit refactor stages that extract shared utilities and tab management before adding new functionality. Implementation plans must respect complexipy thresholds and should not skip these extractions.

**Performance boundary:** All-in-DOM with 5 documents (including a 240-page document) has been tested and works. If future use cases require significantly more documents or larger content, refactor to active-tab-only rendering. This is explicitly deferred — build for the known case, measure before optimising.

**Organise/Respond rebuild strategy:** These tabs aggregate across all documents. They do not use the diff-based card update pattern — their existing rebuild mechanisms are retained. If a CRDT change arrives while Organise/Respond is not the active tab, set a dirty flag and rebuild on next tab switch. This avoids rebuilding hidden aggregate views on every individual highlight change.

**E2E test epoch migration:** The current single `window.__annotationCardsEpoch` becomes a per-document map: `window.__cardEpochs["{doc_id}"]`. E2E tests capture the old epoch, perform an action, then `wait_for_function` until the specific document's epoch advances. Organise and Respond get separate epoch counters (`__organiseEpoch`, `__respondEpoch`).

**Alembic migration:** Phase 11 adds two columns to the Activity model. Standard Alembic migration with `op.add_column()`. No data migration needed — defaults (`allow_student_uploads=True`, `max_documents=None`) preserve current behaviour.

**Document change broadcasts do not touch cards.** The `_RemotePresence` "documents changed" signal (Phase 12) only rebuilds the tab bar — a separate DOM subtree from annotation card containers. It does NOT trigger card rebuilds, `container.clear()`, or any interaction with the CRDT card layer. This avoids the race condition class documented in `_RemotePresence.on_peer_left` where full rebuilds destroy in-flight user interactions.

**All-in-DOM memory for 5 documents.** Deferred rendering means only visited tabs have DOM content. If a student visits all 5 tabs, all 5 documents are in DOM simultaneously. Document HTML is static DOM (no event handlers, no reactive state) — browsers handle this efficiently. The 240-page document already works in the single-document case. Multi-doc multiplies the exposure but does not change the per-document DOM characteristics. Measure after Phase 6; if memory is a problem, refactor to active-tab-only rendering as noted above.

**Sequential extraction to reduce blast radius.** Phase 3 extracts shared utilities from `cards.py` and `organise.py` first. Phase 3b then migrates `respond.py` to the shared module. This avoids touching two large stable files simultaneously — stabilise one extraction before starting the next.
