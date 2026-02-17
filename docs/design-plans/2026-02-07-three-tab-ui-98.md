# Three-Tab Annotation Interface Design

## Summary

This design extends the `/annotation` page with a three-tab interface for
collaborative document annotation. Tab 1 ("Annotate") preserves the current
two-column layout where users highlight text and add comments. Tab 2
("Organise") introduces a kanban-style view where highlights appear as
draggable cards grouped by tag — users can reorder highlights within a tag
column or drag cards between columns to change tags. Tab 3 ("Respond") embeds
a collaborative WYSIWYG markdown editor (Milkdown) alongside a read-only
reference panel of highlights, enabling teams to draft a shared response while
consulting their annotations.

All three tabs share a single CRDT document (pycrdt `Doc`), extending the
existing `AnnotationDocument` with two new fields: a `tag_order` Map for
persisting drag-reorder operations and a `response_draft` XmlFragment for
real-time collaborative editing. The WebSocket broadcast mechanism propagates
changes across tabs and clients: a highlight created in Tab 1 appears
immediately in Tab 2's columns and Tab 3's reference panel; reordering in
Tab 2 persists via CRDT; edits in Tab 3 merge character-by-character across
simultaneous editors. NiceGUI's lazy tab rendering defers Tab 2 and Tab 3
initialisation until first visit, avoiding upfront performance cost for the
Milkdown bundle (~4.3MB) and drag UI setup.

## Definition of Done

The existing `/annotation` page (`annotation.py:2264`, flat two-column layout
at `annotation.py:1192-1290`) gains a three-tab interface:

- **Tab 1 (Annotate)**: The current annotation view — document with highlights
  and sidebar — becomes the first tab. No functional change to Tab 1 itself;
  it's a restructuring of the existing flat layout into a tab container.
- **Tab 2 (Organise)**: A new view showing highlights grouped by tag in
  columns. Drag to reorder within a column; drag between columns to change a
  highlight's tag. CRDT-persisted ordering via a new `tag_order` Map in
  `AnnotationDocument`. Tag-agnostic — accepts a list of `{name, colour}` tags,
  not `BriefTag` directly.
- **Tab 3 (Respond)**: A Milkdown WYSIWYG editor for a shared response draft,
  collaboratively edited via CRDT (XmlFragment in the same `AnnotationDocument`
  Doc). Includes a reference panel showing highlight summaries and PDF export of
  the draft.

All three tabs backed by one CRDT document. Three users on three tabs
simultaneously see each other's changes propagate live. Lazy-render Tabs 2 and
3 on first visit. Warp-to-Tab-1 is per-user only.

**Excluded**: Save-as-draft, routing changes, workspace picker redesign,
sharing display. Design must not preclude these.

## Acceptance Criteria

### three-tab-ui.AC1: Tab container wraps existing functionality
- **three-tab-ui.AC1.1 Success:** Annotation page renders three tab headers (Annotate, Organise, Respond) with Annotate selected by default
- **three-tab-ui.AC1.2 Success:** All existing annotation functionality (highlight create/edit/delete, multi-client sync, cursor/selection awareness) works identically within Tab 1
- **three-tab-ui.AC1.3 Success:** Tabs 2 and 3 lazy-render — no content created until first visit
- **three-tab-ui.AC1.4 Failure:** Switching tabs does not destroy Tab 1 state (highlights, scroll position preserved)

### three-tab-ui.AC2: Tab 2 organises highlights by tag
- **three-tab-ui.AC2.1 Success:** Tab 2 shows one column per tag with the tag's name and colour
- **three-tab-ui.AC2.2 Success:** Highlight cards appear in the correct tag column, showing text snippet, tag, and author
- **three-tab-ui.AC2.3 Success:** Dragging a card within a column reorders it; order persists in CRDT
- **three-tab-ui.AC2.4 Success:** Dragging a card to a different column changes its tag; change persists in CRDT and updates Tab 1's sidebar
- **three-tab-ui.AC2.5 Success:** Two users dragging simultaneously produces a consistent merged result (no lost moves)
- **three-tab-ui.AC2.6 Edge:** A highlight with no tag appears in an "Untagged" section or column

### three-tab-ui.AC3: CRDT extended with new shared types
- **three-tab-ui.AC3.1 Success:** `tag_order` Map stores ordered highlight IDs per tag; survives server restart via persistence
- **three-tab-ui.AC3.2 Success:** `response_draft` XmlFragment coexists with existing highlights/client_meta/general_notes in the same Doc
- **three-tab-ui.AC3.3 Failure:** Adding new fields does not break existing highlight operations or broadcast

### three-tab-ui.AC4: Tab 3 collaborative editor
- **three-tab-ui.AC4.1 Success:** Milkdown WYSIWYG editor renders in Tab 3 with full toolbar
- **three-tab-ui.AC4.2 Success:** Two clients editing Tab 3 see character-level merged changes in real time
- **three-tab-ui.AC4.3 Success:** Client opening Tab 3 after others have edited receives full state sync
- **three-tab-ui.AC4.4 Success:** Reference panel shows highlights grouped by tag (read-only)
- **three-tab-ui.AC4.5 Edge:** Tab 3 visited before any highlights exist shows empty reference panel and functional editor

### three-tab-ui.AC5: Cross-tab navigation and reactivity
- **three-tab-ui.AC5.1 Success:** "Locate" button on a highlight card in Tab 2 or Tab 3 switches to Tab 1 and scrolls the viewport to the highlighted phrase in the document
- **three-tab-ui.AC5.2 Success:** Creating a highlight in Tab 1 appears in Tab 2 columns and Tab 3 reference panel without manual refresh
- **three-tab-ui.AC5.3 Success:** Changing a highlight's tag via Tab 2 drag updates the tag colour in Tab 1's sidebar card
- **three-tab-ui.AC5.4 Failure:** Warp-to-Tab-1 does not affect other users' active tab
- **three-tab-ui.AC5.5 Success:** After warping to Tab 1 from a highlight card, user can return to their previous tab and scroll position

### three-tab-ui.AC6: PDF export includes response draft
- **three-tab-ui.AC6.1 Success:** "Export PDF" includes response draft content below annotated document
- **three-tab-ui.AC6.2 Edge:** Empty response draft produces no extra section in the PDF
- **three-tab-ui.AC6.3 Success:** Export works regardless of whether the exporting user has visited Tab 3

## Glossary

- **CRDT (Conflict-free Replicated Data Type)**: A data structure for
  distributed systems where multiple users can concurrently edit shared state
  and the system automatically merges changes without conflicts. pycrdt
  provides the CRDT implementation.
- **pycrdt**: A Python binding for the Yjs CRDT library. Manages shared types
  (Map, Text, XmlFragment) and handles binary state synchronisation between
  clients via WebSocket.
- **XmlFragment**: A CRDT shared type representing a tree-structured document
  (like ProseMirror's document model). Milkdown binds to this type for
  collaborative rich-text editing.
- **Milkdown**: A WYSIWYG markdown editor framework built on ProseMirror.
  Provides a rich-text interface with toolbar and markdown shortcuts.
- **ProseMirror**: An open-source rich-text editing toolkit that Milkdown is
  built on. Uses a document model (schema + tree) for structured editing.
- **NiceGUI**: A Python web UI framework wrapping Vue/Quasar components.
  Provides declarative UI construction and client-server synchronisation.
- **IIFE bundle**: "Immediately Invoked Function Expression" — a JavaScript
  bundle format that executes immediately when loaded, exposing APIs via global
  variables (e.g., `window._createMilkdownEditor`).
- **CollabService**: A Milkdown plugin API for binding the editor to a Yjs
  CRDT document. `bindXmlFragment(fragment)` connects to a named XmlFragment
  within the Doc.
- **TagInfo**: A tag-agnostic data structure used by Tab 2 and Tab 3 to render
  tag metadata without coupling to the `BriefTag` enum.
- **BriefTag**: An enum defining the current hardcoded tag set used in the
  annotation system. Seam C (#95) will replace this with configurable tags.
- **Warp-to-Tab-1**: A UI pattern where clicking "locate" on a highlight card
  in Tab 2 or Tab 3 switches the user to Tab 1 and scrolls to the highlighted
  text. Per-user only.

## Architecture

### Single CRDT Document

All tab state lives in one `AnnotationDocument` (`crdt/annotation_doc.py`).
The existing pycrdt `Doc` gains two new root-level shared types:

```
Doc
├── highlights    (Map)        — existing, line 62
├── client_meta   (Map)        — existing, line 63
├── general_notes (Text)       — existing, line 64
├── tag_order     (Map)        — NEW: {tag_name: [highlight_id, ...]}
└── response_draft (XmlFragment) — NEW: Milkdown/ProseMirror document
```

**tag_order** maps tag names (strings, not `BriefTag` values) to ordered
arrays of highlight IDs. Highlights absent from all arrays appear at the
bottom of their tag's column in Tab 2. When a highlight is dragged between
columns, its ID is removed from the source array and inserted into the target.

**response_draft** is a pycrdt `XmlFragment`, not `Text`. Milkdown's collab
plugin binds to XmlFragment internally — `CollabService.bindXmlFragment()`
is the public API (verified in spike investigation). pycrdt relays binary Yjs
updates without needing to understand ProseMirror document structure.

### Tab Container

NiceGUI's built-in `ui.tabs()` + `ui.tab_panels()` wraps the existing layout.

```
annotation_page()
└── ui.column
    ├── ui.label ("Annotation Workspace")
    ├── ui.row — Header: save status, user count (shared across tabs)
    ├── ui.tabs()
    │   ├── ui.tab("Annotate")
    │   ├── ui.tab("Organise")
    │   └── ui.tab("Respond")
    └── ui.tab_panels(tabs)
        ├── ui.tab_panel("Annotate")
        │   └── existing two-column layout (extracted from _render_workspace_view)
        ├── ui.tab_panel("Organise")
        │   └── tag columns with draggable highlight cards
        └── ui.tab_panel("Respond")
            └── Milkdown editor + reference panel + export button
```

NiceGUI lazy-renders tab panels — content is only created when a tab is first
visited. After first visit, content persists in the DOM (hidden via CSS when
inactive). This means:

- Tab 1 renders immediately (it's the default tab).
- Tabs 2 and 3 only initialise on first click. No performance cost upfront.
- The Milkdown editor binds to the XmlFragment on first Tab 3 visit.
  Late-joiner full-state sync (proven in spike) handles content that was
  edited before this client opened Tab 3.

Programmatic tab switching for warp-to-Tab-1:
`tab_panels.set_value("Annotate")` — per-user, does not affect other clients.

### Tab 1: Annotate

The existing flat two-column layout moves inside `ui.tab_panel("Annotate")`
with no functional changes. The current `_render_workspace_view` function
(`annotation.py`) is extracted/refactored to render inside the panel.

The "Export PDF" button stays in the header row (shared across all tabs) since
export applies to the whole workspace, not just the current tab.

### Tab 2: Organise

Tag-agnostic column layout. Accepts `list[TagInfo]` where
`TagInfo = namedtuple("TagInfo", ["name", "colour"])` or equivalent.
`BriefTag` is mapped to `TagInfo` at the call site — Tab 2 never imports
`BriefTag`.

**Column layout**: One column per tag, each containing draggable highlight
cards. Each column has a coloured header showing the tag name.

**Drag-and-drop**: Reimplemented from scratch, inspired by
[zigai/nicegui-extensions](https://github.com/zigai/nicegui-extensions)
`draggable.py` (HTML5 drag events, ~150 lines). Key differences from that
library:

1. **Cross-column drops**: Columns are drop targets (not just cards). Dropping
   a card on a column changes the highlight's tag and appends to that column.
   Dropping on a specific card within a column inserts at that position.
2. **Per-client drag state**: Uses NiceGUI client storage or closure scope,
   not a module-level global. Multiple users can drag simultaneously.
3. **CRDT sync on drop**: Each drop updates `tag_order` Map in the CRDT doc.
   The broadcast mechanism propagates the change to all connected clients,
   which re-render their columns.

**Warp-to-Tab-1**: Each highlight card has a "locate" button. Clicking it
switches that user's tab to "Annotate" and scrolls to the highlight.

### Tab 3: Respond

Two-column layout mirroring Tab 1's proportions (editor flex:2, reference
panel flex:1):

- **Left (wide, scrollable)**: Milkdown WYSIWYG editor. The editor container
  fills the available height (`min-height: 70vh`, grows with content) and
  scrolls independently — not a cramped textarea. Bound to `response_draft`
  XmlFragment via `CollabService.bindXmlFragment(fragment)`. Uses the same
  Vite IIFE bundle from the spike (`static/milkdown/dist/milkdown-bundle.js`,
  ~4.3MB). The JS `_createMilkdownEditor` function is extended to accept a
  named XmlFragment (currently uses default `'prosemirror'` name).
- **Right (narrow)**: Read-only reference panel showing highlight cards
  grouped by tag. Same data as Tab 2 but non-interactive — a quick reference
  while writing.

**PDF export**: A "Export Draft" button in Tab 3 exports the Milkdown
markdown through the existing PDF pipeline. This replaces the hardcoded
`general_notes=""` at `annotation.py:1601` — the response draft content
is read via `window._getMilkdownMarkdown()` and passed as the
`general_notes` parameter to `export_annotation_pdf()`.

**CRDT binding**: One-line change from spike code. The spike uses
`collabService.bindDoc(ydoc)` which internally calls
`ydoc.getXmlFragment('prosemirror')`. For the three-tab interface, the JS
creates a named fragment (`ydoc.getXmlFragment('response_draft')`) and calls
`collabService.bindXmlFragment(fragment)` directly.

### Broadcast and Sync

The existing `_setup_client_sync` pattern (`annotation.py:1464-1553`)
extends to cover new CRDT fields:

- **Tab 1 changes** (highlight create/edit/delete): Existing broadcast →
  all tabs' highlight lists update. Tab 2 columns and Tab 3 reference panel
  reactively reflect new/changed/deleted highlights.
- **Tab 2 changes** (drag reorder/reassign): Update `tag_order` Map →
  broadcast → Tab 2 columns re-render on all clients. Tab 1 sidebar card
  order does not change (sidebar is sorted by document position, not tag
  order).
- **Tab 3 changes** (editor content): Yjs update → pycrdt relay → broadcast
  to other clients' Milkdown instances via `_applyRemoteUpdate()`. Same
  pattern as spike, different XmlFragment name.

Echo prevention remains unchanged: JS-side `origin === "remote"` skip +
Python-side `client_id != origin_client_id` in broadcast.

## Existing Patterns

Investigation confirmed these existing patterns that this design follows:

- **CRDT document as single source of truth**: `AnnotationDocument` already
  holds all shared state. Adding `tag_order` and `response_draft` follows the
  same pattern — new root-level shared types in the same Doc.
- **Callback-based broadcast**: `_setup_client_sync` registers per-client
  callbacks. Tab 2 and Tab 3 add their own refresh callbacks to the same
  registry.
- **UI builds from CRDT state**: The existing annotation cards are rendered
  from `crdt_doc.get_highlights()`. Tab 2 columns and Tab 3 reference panel
  follow the same pattern — read from CRDT, render UI, re-render on change.
- **Static JS bundles**: The Milkdown bundle is served from
  `static/milkdown/dist/` via `app.add_static_files()`. Tab 3 reuses this
  bundle.
- **`PageState` dataclass**: Holds per-client state including UI element
  references and broadcast callables (`annotation.py:296-326`). Extended
  with references to Tab 2 columns and Tab 3 editor.

**New pattern introduced**: Tag-agnostic `TagInfo` interface. This is the
first place in the codebase where tags are not hardcoded to `BriefTag`. The
mapping from `BriefTag` → `TagInfo` happens at the page level, keeping the
tab components decoupled.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Tab Container Shell

**Goal:** Wrap the existing annotation view in a NiceGUI tab container
without changing any functionality.

**Components:**
- `annotation.py` — refactor `_render_workspace_view` to render inside
  `ui.tab_panel("Annotate")`. Add empty panels for "Organise" and "Respond"
  with placeholder labels.
- Header row (save status, user count, export) moves above tab panels.

**Dependencies:** None (first phase).

**Done when:** `/annotation?workspace_id=<UUID>` renders with three tab
headers. Clicking "Annotate" shows the existing two-column view unchanged.
Clicking "Organise" or "Respond" shows placeholder text. All existing
annotation functionality (highlight, edit, delete, export, multi-client sync)
works identically.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: CRDT Extension

**Goal:** Add `tag_order` and `response_draft` fields to
`AnnotationDocument`.

**Components:**
- `crdt/annotation_doc.py` — add `doc["tag_order"]` (Map) and
  `doc["response_draft"]` (XmlFragment) in `__init__`. Add properties and
  helper methods: `get_tag_order(tag)`, `set_tag_order(tag, ids)`,
  `move_highlight_to_tag(highlight_id, from_tag, to_tag, position)`.

**Dependencies:** Phase 1.

**Done when:** Unit tests verify: tag_order Map can store and retrieve ordered
highlight IDs per tag; highlights can be moved between tags; response_draft
XmlFragment can be created and accessed; existing highlights/client_meta/
general_notes functionality unaffected.

**ACs covered:** three-tab-ui.AC3.1, three-tab-ui.AC3.2
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Tag-Agnostic Interface

**Goal:** Create the `TagInfo` abstraction and wire it to Tab 2's column
rendering.

**Components:**
- New module (e.g., `pages/annotation_tags.py`) — `TagInfo` type,
  `brief_tags_to_tag_info()` mapper that converts `BriefTag` + `TAG_COLORS`
  to `list[TagInfo]`.
- Tab 2 panel in `annotation.py` — renders one column per tag using
  `TagInfo.name` and `TagInfo.colour`. Columns populated from CRDT
  `highlights` Map grouped by tag, ordered by `tag_order` Map.
- No drag-and-drop yet — static read-only columns.

**Dependencies:** Phase 2.

**Done when:** Tab 2 shows highlight cards grouped by tag in coloured columns.
Cards show text snippet, tag name, author. Columns use `TagInfo` interface,
not `BriefTag`. Adding a highlight in Tab 1 appears in the correct column in
Tab 2 (via CRDT broadcast).

**ACs covered:** three-tab-ui.AC2.1, three-tab-ui.AC2.2
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Drag-and-Drop

**Goal:** Implement drag-to-reorder within columns and drag-to-reassign
between columns.

**Components:**
- New module (e.g., `pages/annotation_drag.py`) — `DraggableHighlightCard`
  (extends `ui.card`, HTML5 drag events), `TagColumn` (extends `ui.column`,
  drop target). Per-client drag state via closure scope.
- Wire drop events to CRDT: reorder updates `tag_order` array positions;
  cross-column drop updates both the highlight's `tag` field in `highlights`
  Map and moves the ID between `tag_order` arrays.
- Broadcast on drop → all clients re-render columns.

**Dependencies:** Phase 3.

**Done when:** Dragging a card within a column reorders it (persisted in
CRDT). Dragging a card to a different column changes its tag (persisted in
CRDT). Both operations propagate live to other connected clients. Two users
can drag simultaneously without conflict.

**ACs covered:** three-tab-ui.AC2.3, three-tab-ui.AC2.4, three-tab-ui.AC2.5
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Milkdown Editor in Tab 3

**Goal:** Embed the collaborative Milkdown editor in Tab 3 with
`response_draft` XmlFragment binding.

**Components:**
- Tab 3 panel in `annotation.py` — left panel with Milkdown editor container,
  right panel with read-only highlight reference cards.
- JS bundle extension — `_createMilkdownEditor` accepts optional
  `fragmentName` parameter (default `'prosemirror'`, Tab 3 passes
  `'response_draft'`). `CollabService.bindXmlFragment()` used instead of
  `bindDoc()`.
- Python CRDT relay extended to handle Yjs updates targeting the
  `response_draft` XmlFragment within the shared Doc.

**Dependencies:** Phase 2 (CRDT extension), Phase 1 (tab container).

**Done when:** Tab 3 shows a Milkdown WYSIWYG editor. Two clients editing
Tab 3 see each other's changes in real time with character-level merging.
A client opening Tab 3 after others have edited sees the current content
(full-state sync). Reference panel shows highlights grouped by tag.

**ACs covered:** three-tab-ui.AC4.1, three-tab-ui.AC4.2, three-tab-ui.AC4.3
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Warp Navigation and Cross-Tab Reactivity

**Goal:** Wire up warp-to-Tab-1 from Tabs 2 and 3, and ensure all tabs
react to changes from other tabs.

**Components:**
- Highlight cards in Tab 2 and Tab 3 get a "locate" button that calls
  `tab_panels.set_value("Annotate")` and scrolls to the highlight position
  in the document.
- Tab 1 highlight changes (create/edit/delete) → Tab 2 columns and Tab 3
  reference panel update via CRDT broadcast callbacks.
- Tab 2 tag reassignment → Tab 1 sidebar annotation card updates its tag
  colour/label.

**Dependencies:** Phases 4 and 5.

**Done when:** Clicking "locate" on a highlight in Tab 2 or Tab 3 switches
to Tab 1 and scrolls to the highlight. Creating a highlight in Tab 1
appears in Tab 2 columns and Tab 3 reference panel. Changing a tag in Tab 2
updates the tag colour in Tab 1's sidebar.

**ACs covered:** three-tab-ui.AC5.1, three-tab-ui.AC5.2, three-tab-ui.AC5.3
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: PDF Export Integration

**Goal:** Extend PDF export to include the response draft from Tab 3.

**Components:**
- `annotation.py` `_handle_pdf_export` — read Milkdown markdown via
  `window._getMilkdownMarkdown()` (if Tab 3 has been visited) or from
  pycrdt XmlFragment serialisation (if not visited). Pass as
  `general_notes` parameter to `export_annotation_pdf()`.
- `export/pdf_export.py` — the existing `general_notes` parameter and
  `_build_general_notes_section()` already support this content. No changes
  needed to the export pipeline itself.

**Dependencies:** Phase 5.

**Done when:** "Export PDF" produces a PDF that includes the response draft
content below the annotated document. Empty draft produces no extra section.
Export works regardless of whether the exporting user has visited Tab 3.

**ACs covered:** three-tab-ui.AC6.1, three-tab-ui.AC6.2
<!-- END_PHASE_7 -->

## Additional Considerations

**Tag-agnostic boundary**: The `TagInfo` interface is the contract between
the page layer (which knows about `BriefTag`) and the tab components (which
don't). When Seam C (#95) introduces configurable tags, only the mapper
function changes — Tab 2 and Tab 3 components are untouched.

**annotation.py size**: At ~2302 lines, the file is already large. Phases 3
and 4 introduce new modules (`annotation_tags.py`, `annotation_drag.py`) to
keep tab-specific logic out of the main file. Tab 3's Milkdown integration
may warrant a similar extraction.
