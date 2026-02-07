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
- Workspace picker
- Sharing status display
- `/demo/live-annotation` removal

These stay in #98.

### Constraints Established

1. **Tag-agnostic**: Tabs accept a list of tags with names and colours,
   not the hardcoded `BriefTag` enum. Seam C (#95) can swap in
   configurable tags later without reworking the tab UI.

2. **Full interaction**: Drag-to-reorder in Tab 2, WYSIWYG editor in Tab 3,
   warp-to-Tab-1 navigation. All per #98's spec.

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

### Architecture Findings

From codebase investigation:
- `AnnotationDocument` (CRDT) is self-contained, holds highlights as
  `Map`, general_notes as `Text`. Can be extended with new fields.
- Existing broadcast via `_setup_client_sync` handles multi-client for Tab 1.
- UI layer has zero DB knowledge — all data passed through function params.
- `annotation.py` is 2285 lines, renders a single flat view.
- pycrdt `Text` supports `format()` for rich text attributes (Delta format).

### CRDT Extension Needed

New shared types in `AnnotationDocument`:
- `doc["tag_order"]` — Map of tag -> Array of highlight IDs (Tab 2 ordering)
- `doc["response_draft"]` — Text (Tab 3 markdown source)

## Phase 2: Exploration (In Progress)

### The Collaborative Editor Question

**Problem**: NiceGUI's `ui.editor()` (Quasar QEditor) syncs entire HTML
strings via value binding. pycrdt needs positional operations. Two concurrent
edits = last-write-wins, not merge.

**Solution identified**: Store markdown (plain text) in pycrdt `Text`.
Use [Milkdown](https://milkdown.dev/) as the WYSIWYG markdown editor.
Milkdown has native Yjs support via `@milkdown/plugin-collab`. pycrdt is
Yjs-compatible. So: markdown source in CRDT, Milkdown renders it, collab
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
- Highlights (Tab 1) — existing Map
- Tag ordering (Tab 2) — new Map of tag -> Array
- Response draft (Tab 3) — new Text, edited via Milkdown with collab plugin
- All three tabs observe same CRDT, all live
- Milkdown collab plugin handles the hard part (character-level sync)

## Phase 3: Design Presentation (Ready to Start)

Milkdown spike complete and merged. The approach is validated. Ready to
design the three-tab interface proper.

## Resolved Questions

1. ~~Should we bundle Milkdown locally or use CDN?~~
   **Resolved: local Vite bundle.** CDN breaks with Crepe's static imports.
   Bundle is an IIFE (~4.3MB) served as a static file. CSS injected by JS.

## Resolved Questions

1. ~~Should we bundle Milkdown locally or use CDN?~~
   **Resolved: local Vite bundle.** CDN breaks with Crepe's static imports.

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

2. How does the warp-to-Tab-1 navigation work when three different
   users might be on different tabs?
