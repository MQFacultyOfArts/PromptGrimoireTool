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

### Milkdown Spike (In Progress)

**File**: `src/promptgrimoire/pages/milkdown_spike.py`
**Route**: `/demo/milkdown-spike` (requires `ENABLE_DEMO_PAGES=true`)

**Status**:
- Milkdown renders via `@milkdown/kit` (low-level Editor + commonmark preset)
- `@milkdown/crepe` (high-level wrapper with toolbar) breaks on esm.sh CDN
  due to static CodeMirror import
- Import maps must be in `<script type="module">`, not `ui.run_javascript()`
  (which uses indirect execution that can't resolve bare specifiers)
- Multi-client sync not yet wired
- No toolbar/formatting buttons in current low-level setup

**Key learning**: `ui.run_javascript()` cannot use ES module import maps.
Must put Milkdown init in `<script type="module">` via `ui.add_body_html()`.

**Next steps for spike**:
1. Verify `<script type="module">` approach works (current version)
2. Wire multi-client broadcast (sync_demo.py pattern)
3. For toolbar: either bundle Milkdown locally with esbuild (best),
   or import Crepe feature plugins individually
4. Test `@milkdown/plugin-collab` with pycrdt websocket

### Approach Selected

**CRDT Hub with Milkdown** (Approach A revised):
- All tab state in single CRDT document
- Highlights (Tab 1) — existing Map
- Tag ordering (Tab 2) — new Map of tag -> Array
- Response draft (Tab 3) — new Text, edited via Milkdown with collab plugin
- All three tabs observe same CRDT, all live
- Milkdown collab plugin handles the hard part (character-level sync)

## Phase 3: Design Presentation (Not Started)

Pending completion of Milkdown spike to validate the approach.

## Open Questions

1. Should we bundle Milkdown locally (esbuild) or use CDN?
   - Local: toolbar works, no CDN dependency, version pinned
   - CDN: simpler setup, but Crepe wrapper breaks
   - **Leaning**: local bundle

2. Tab lifecycle — performance is a known issue on Tab 1. Lazy-render
   Tabs 2/3 on first visit, or render all upfront?

3. How does the warp-to-Tab-1 navigation work when three different
   users might be on different tabs?
