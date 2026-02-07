# Three-Tab Annotation Interface — Brainstorming WIP

## Context

Splitting the 3-tab annotation interface out of Seam F (#98) as a standalone
issue. Seam F bundles routing, workspace picker, sharing display, AND the tab
UI. The tab UI only needs Seam A (workspace model, done), not Seams B/D/E.

Parent epic: #92 (Annotation Workspace Platform)

## Phase 1: Understanding (Complete)

### Scope

The 3-tab interface as a self-contained issue, split from:
- Routing (`/annotation`, `/annotation/{workspace_id}`, etc.)
- Workspace picker (currently query-param + create button, `annotation.py:2281-2302`)
- Sharing status display

These stay in #98.

### Constraints Established

1. **Tag-agnostic**: Tabs accept a list of tags with names and colours,
   not the hardcoded `BriefTag` enum. Seam C (#95) can swap in
   configurable tags later without reworking the tab UI.

2. **Full interaction**: Drag-to-reorder within a tag column in Tab 2,
   drag between columns to change tag type, WYSIWYG editor in Tab 3,
   warp-to-Tab-1 navigation (per-user). All per #98's spec.

3. **Excluded from scope**: Save-as-draft (creates WorkspaceDocument),
   routing, workspace picker, sharing. Design must not preclude these.

4. **Concurrency model (CRITICAL)**: Three people on three tabs
   simultaneously, all backed by one CRDT. Alice annotating in Tab 1,
   Bob organising in Tab 2, Candy writing the response in Tab 3.
   Changes propagate live across tabs.

5. **Tab 3 draft**: Single shared document, co-authored via CRDT.
   Not per-user — one response per workspace, collaboratively edited.

6. **Building on**: Branch 106 (HTML paste-in), so Tab 1 has real
   HTML content to annotate.

7. **Dependencies**: Only Seam A (workspace model, already done).

### Verified Codebase State (2026-02-07)

All claims below verified against actual code with file:line citations.

**Routes:**
- `/annotation` is the live route — `annotation.py:2264`,
  `@page_route("/annotation", category="main")`
- `/demo/live-annotation` does NOT exist. Fully removed from production code.
  Only references are in `tests/e2e/deprecated/` files.

**Annotation page structure (`annotation.py`, ~2302 lines):**
- Flat two-column layout (document left flex:2, sidebar right flex:1)
  — `annotation.py:1192-1290`
- NO tab UI — full-file search: zero `ui.tabs` / `QTab` components
- Workspace via query param `?workspace_id=<UUID>` — `annotation.py:2281-2302`
- Minimal workspace picker: "Create Workspace" button if no workspace_id

**Tag system:**
- `BriefTag` is a `StrEnum` with 10 legal case brief tags
  — `models/case.py:12-24`
- `TAG_COLORS`: hardcoded dict `BriefTag → hex colour`
  — `models/case.py:28-39`
- `TAG_SHORTCUTS`: hardcoded keyboard shortcuts 1-9, 0
  — `models/case.py:42-53`
- NO tag-agnostic abstraction — all UI iterates `BriefTag` directly
  — `annotation.py:566`: `for i, tag in enumerate(BriefTag):`
- NO `tag_order` anywhere in codebase (grep: zero matches)

**CRDT document (`crdt/annotation_doc.py`):**
- `highlights` Map — `annotation_doc.py:62`
- `client_meta` Map — `annotation_doc.py:63`
- `general_notes` Text — `annotation_doc.py:64`
- NO `tag_order`, NO `response_draft`, NO `XmlFragment`
  (grep: zero matches for all three)

**Broadcast (`annotation.py:1464-1553`):**
- `_setup_client_sync` registers clients in
  `_connected_clients[workspace_key][client_id]`
- Callback-based broadcast with ContextVar for echo prevention
- Three broadcast types: update, cursor, selection

**PDF export:**
- "Export PDF" button in header — `annotation.py:2233-2247`
- Handler `_handle_pdf_export` — `annotation.py:1556-1614`
- Pipeline: `pdf_export.py` → `latex.py` (Pandoc+Lark) → `pdf.py` (LuaLaTeX)
- `general_notes` hardcoded as `""` — `annotation.py:1601`
- NO general_notes editor in UI
- NO response draft editor in UI
- NO save-as-draft (only `type="source"` documents created)

**PageState dataclass** — `annotation.py:296-326`:
- Holds workspace_id, client_id, document_id, selection range, user name/color,
  UI element references, CRDT doc reference, broadcast callables

### CRDT Extension Needed

New shared types in `AnnotationDocument` (`crdt/annotation_doc.py`):
- `doc["tag_order"]` — Map of tag -> Array of highlight IDs (Tab 2 ordering)
- `doc["response_draft"]` — XmlFragment (Tab 3, bound via
  `CollabService.bindXmlFragment()`)

Note: `response_draft` is XmlFragment, NOT Text. Milkdown/ProseMirror uses
XmlFragment internally. `CollabService.bindDoc(doc)` just calls
`doc.getXmlFragment('prosemirror')` — `bindXmlFragment(fragment)` allows
binding a named fragment within the shared Doc. One Doc, one sync channel.

## Phase 2: Exploration (Complete)

### The Collaborative Editor Question

**Problem**: NiceGUI's `ui.editor()` (Quasar QEditor) syncs entire HTML
strings via value binding. pycrdt needs positional operations. Two concurrent
edits = last-write-wins, not merge.

**Solution identified**: Store ProseMirror document structure in pycrdt
XmlFragment. Use [Milkdown](https://milkdown.dev/) as the WYSIWYG markdown
editor. Milkdown has native Yjs support via `@milkdown/plugin-collab`. pycrdt
is Yjs-compatible. So: XmlFragment in CRDT, Milkdown renders it, collab
plugin syncs it — character-level merging for free.

### Milkdown Spike (Complete — merged to main 2026-02-07)

**File**: `src/promptgrimoire/pages/milkdown_spike.py`
**Route**: `/demo/milkdown-spike` (requires `ENABLE_DEMO_PAGES=true`)
**Design plan**: `docs/design-plans/2026-02-06-milkdown-crdt-spike.md`
**Implementation notes**: `docs/implementation-plans/2026-02-06-milkdown-crdt-spike/phase_03.md`

**Result**: All three phases passed UAT. The spike validates the full
collaborative editing stack:

- **Phase 1**: Vite IIFE bundle of Milkdown Crepe + Yjs + y-prosemirror,
  served as a static file. CSS injected by JS (no separate stylesheet).
  Bundle is ~4.3MB (includes CodeMirror for code blocks).
- **Phase 2**: Crepe editor renders in NiceGUI with full toolbar (Bold,
  Italic, Heading, List, Blockquote, Code). Python reads markdown via
  `window._getMilkdownMarkdown()` through `ui.run_javascript()`.
- **Phase 3**: Multi-client CRDT sync. Two browser tabs editing the same
  document with character-level merging. pycrdt Doc on the server relays
  base64-encoded Yjs updates between clients via NiceGUI WebSocket events.
  Late joiners receive full state sync.

**Key findings**:
- Local Vite bundle is the only viable approach. CDN/esm.sh breaks with
  Crepe's static CodeMirror imports.
- `@milkdown/plugin-collab` + `collabServiceCtx` binds a Y.Doc to
  ProseMirror via y-prosemirror. Register plugin before `crepe.create()`,
  bind doc after.
- pycrdt Doc acts as a pure binary relay — it doesn't need to understand
  ProseMirror document structure. Receives Yjs updates, applies them,
  forwards to other clients.
- NiceGUI `ui.on()` is per-client scoped (registers on that client's
  Vue layout element), so each client's event handler fires independently.
- Echo prevention: JS-side `origin === "remote"` skip + Python-side
  `client_id != origin_client_id` in broadcast. No ContextVar needed.
- Do NOT disable `Crepe.Feature.CodeMirror` — triggers a Milkdown 7.x bug
  where disabled feature configs still execute.

### Approach Selected

**CRDT Hub with Milkdown** (Approach A revised):
- All tab state in single CRDT document
- Highlights (Tab 1) — existing Map (`annotation_doc.py:62`)
- Tag ordering (Tab 2) — new Map of tag -> Array
- Response draft (Tab 3) — new XmlFragment, edited via Milkdown with
  collab plugin. Bound via `CollabService.bindXmlFragment(fragment)`.
- All three tabs observe same CRDT, all live
- Milkdown collab plugin handles the hard part (character-level sync)

### Clarification Answers (from design conversation 2026-02-07)

1. **Workspace model**: One workspace, all tabs in one thing, no multi-sync
   and catchup. Everyone connected to a workspace is managed together.

2. **Tab 3 scope**: Editor + reference panel + PDF export. Save-as-draft
   excluded (creates WorkspaceDocument — separate concern).

3. **Tags**: Tag-agnostic from day one. Tabs accept list of tags with
   names and colours; BriefTag is just one consumer.

4. **Tab 2 interaction**: CRDT-persisted ordering. Drag to reorder within
   a tag column. Drag between columns to change tag type. Think Alice,
   Ben, Candy working collaboratively — all see each other's changes.

5. **Tab lifecycle**: Lazy-render Tabs 2 and 3 on first visit.
   Tab 1 (annotation) has known performance concerns.

6. **Warp-to-Tab-1**: Per-user only. Each user controls their own tab
   navigation. Clicking a highlight reference in Tab 2 or Tab 3 warps
   THAT user to Tab 1, not everyone.

## Phase 3: Design Presentation (Ready to Start)

Milkdown spike complete and merged. The approach is validated. Ready to
design the three-tab interface proper.

## Resolved Questions

1. ~~Should we bundle Milkdown locally or use CDN?~~
   **Resolved: local Vite bundle.** CDN breaks with Crepe's static imports.
   Bundle is an IIFE (~4.3MB) served as a static file. CSS injected by JS.

2. ~~How to integrate Milkdown collab into AnnotationDocument's CRDT?~~
   **Resolved: single Doc with named XmlFragment.** Investigation confirmed:
   - `CollabService.bindXmlFragment(fragment)` exists as public API
   - `bindDoc(doc)` internally just calls `doc.getXmlFragment('prosemirror')`
     — both converge to the same codepath
   - pycrdt `Doc.get_or_insert_xml_fragment(txn, 'response_draft')` works
     alongside `get_or_insert_map(txn, 'highlights')` in the same Doc
   - One Doc, one sync channel. No spike needed — one-line change from
     spike's working code.

## Open Questions

1. Tab lifecycle — performance is a known issue on Tab 1. Lazy-render
   Tabs 2/3 on first visit, or render all upfront?
   **Leaning**: Lazy-render (per clarification answer #5).

2. How does the warp-to-Tab-1 navigation work when three different
   users might be on different tabs?
   **Leaning**: Per-user only (per clarification answer #6).
