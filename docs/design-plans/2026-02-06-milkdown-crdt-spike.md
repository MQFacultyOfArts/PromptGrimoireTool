# Milkdown CRDT Spike Design

## Summary

This spike implements real-time collaborative markdown editing using Milkdown's Crepe editor with CRDT-based synchronization. The architecture connects browser-based Yjs CRDT documents to a Python pycrdt backend through NiceGUI's WebSocket infrastructure, enabling multiple users to edit the same document simultaneously without conflicts. The approach layers Milkdown's WYSIWYG interface over ProseMirror's document model, synchronized via the Yjs CRDT protocol, with Python serving as both a relay for client-to-client updates and the authoritative persistence point.

The implementation builds a local Vite bundle containing Milkdown Crepe and Yjs dependencies, served as static files to avoid external CDN dependencies. A custom NiceGUI provider bridges JavaScript and Python: client-side Yjs updates are base64-encoded and transmitted through WebSocket events, while Python applies them to its pycrdt document and broadcasts to other connected clients using the existing multi-client broadcast pattern from the annotation feature. Python can read and inject markdown content by calling JavaScript serialization functions, maintaining bidirectional interoperability between the editor and server-side processing.

## Definition of Done

1. **WYSIWYG toolbar**: Crepe editor renders with Bold, Italic, Heading, List, Blockquote, and Code formatting commands functional
2. **Multi-client CRDT sync**: Two browser tabs editing the same document — changes propagate live with character-level merge (not last-write-wins)
3. **Python read/write**: Python can read markdown from and inject markdown into the editor
4. **Demo page**: Available at `/demo/milkdown-spike` with `ENABLE_DEMO_PAGES=true`

## Glossary

- **CRDT (Conflict-free Replicated Data Type)**: A data structure that allows multiple clients to make concurrent edits that automatically merge without conflicts, ensuring eventual consistency across all replicas.
- **Yjs**: A JavaScript CRDT library implementing conflict-free data structures with efficient binary update encoding, commonly used for collaborative editing.
- **pycrdt**: Python implementation of Yjs-compatible CRDT data structures, allowing Python backends to participate in Yjs collaborative editing by speaking the same binary protocol.
- **Milkdown**: A plugin-driven WYSIWYG markdown editor framework built on ProseMirror.
- **Crepe**: A pre-configured Milkdown distribution providing a complete editor with toolbar and formatting commands.
- **ProseMirror**: A toolkit for building rich-text editors with a schema-driven document model, treating documents as structured trees rather than plain text.
- **y-prosemirror**: A binding library that synchronizes a ProseMirror editor's document state with a Yjs CRDT document, enabling collaborative editing at the document structure level.
- **Vite**: A modern JavaScript build tool used here to package Milkdown and its dependencies into a single file served as a static asset.
- **ContextVar**: Python's context-local state mechanism (from `contextvars`) used for tracking the origin client of CRDT updates to prevent echo loops.
- **Echo prevention**: Pattern where a client broadcasting an update skips re-sending it back to the originating client, preventing infinite feedback loops.

## Architecture

Three-layer architecture: Milkdown Crepe editor (browser) ↔ NiceGUI WebSocket ↔ pycrdt CRDT document (server).

```
Browser (per tab)                          Python server
┌─────────────────────────────┐           ┌──────────────────────────┐
│ Milkdown Crepe              │           │ pycrdt Doc               │
│   ↕ y-prosemirror           │  base64   │   - apply_update()       │
│ Yjs Y.Doc                   │◄─updates─►│   - get_update()         │
│   ↕ custom NiceGUI provider │  over WS  │   - observer → broadcast │
└─────────────────────────────┘           ├──────────────────────────┤
                                          │ Client registry          │
                                          │   - per-doc client dict  │
                                          │   - echo prevention      │
                                          └──────────────────────────┘
```

**Yjs on client, pycrdt on server.** Both speak the same binary CRDT protocol. ProseMirror-level CRDT gives structural merging (nodes and marks), not just text-level. `@milkdown/plugin-collab` binds Yjs Y.Doc to ProseMirror via y-prosemirror.

**NiceGUI WebSocket as transport.** No separate y-websocket server. Binary Yjs updates encoded as base64 strings, shuttled through NiceGUI's existing WebSocket. JS→Python via custom DOM events on a hidden element. Python→JS via `ui.run_javascript()` calling global functions.

**Server as relay + persistence point.** pycrdt Doc receives updates, applies them, broadcasts to other connected clients. Also serves as the authoritative state for save/load (persistence not in spike scope).

**Local Vite bundle for Milkdown.** Crepe + Yjs + y-prosemirror bundled with Vite into a single JS file. CodeMirror excluded — NiceGUI 3.6 already bundles CodeMirror for `ui.codemirror`, and loading a second copy causes version conflicts. Code blocks still work without syntax highlighting.

**Python reads markdown via JS.** Since the CRDT operates on ProseMirror structure, markdown extraction happens client-side via Milkdown's serializer. Python calls `window._getMilkdownMarkdown()` through `ui.run_javascript()`.

## Existing Patterns

### Multi-client broadcast

`src/promptgrimoire/pages/annotation.py` (`_setup_client_sync()`, lines 1464-1540) implements the pattern this design follows:

- Global registry: `_connected_clients[workspace_id][client_id] = callback`
- Each client registered on connect, removed on disconnect via `client.on_disconnect()`
- Broadcast iterates clients, skips origin to prevent echo
- All broadcast functions are async

### CRDT document wrapper

`src/promptgrimoire/crdt/sync.py` (`SharedDocument`) wraps pycrdt Doc + Text with:

- `apply_update(update, origin_client_id)` — apply binary update with origin tracking
- `set_broadcast_callback(callback)` — register function called on doc changes
- ContextVar-based echo prevention: `_origin_var` set before mutation, read in observer

### Echo prevention via ContextVar

Both `AnnotationDocument` and `SharedDocument` use the same pattern:

```python
_origin_var: ContextVar[str | None] = ContextVar("origin", default=None)

def apply_update(self, update: bytes, origin_client_id: str | None = None):
    _origin_var.set(origin_client_id)
    self.doc.apply_update(update)
    _origin_var.set(None)

def _on_update(self, event):
    origin = _origin_var.get()
    self._broadcast_callback(event.update, origin)
```

This design reuses the same pattern.

### Page registration

`src/promptgrimoire/pages/__init__.py` imports the spike module, triggering the `@page_route()` decorator. Route `/demo/milkdown-spike` with `requires_demo=True`. No change needed.

### JavaScript integration via body HTML

The existing spike (`milkdown_spike.py`) demonstrates the constraint: ES module imports must be in `<script type="module">` via `ui.add_body_html()`, not `ui.run_javascript()`. Subsequent calls to global functions via `ui.run_javascript()` work fine.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Vite Bundle Setup

**Goal:** Build a local JS bundle containing Milkdown Crepe + Yjs + collab plugin, served as NiceGUI static files.

**Components:**

- `src/promptgrimoire/static/milkdown/package.json` — declares dependencies: `@milkdown/crepe`, `@milkdown/plugin-collab`, `yjs`, `y-prosemirror`
- `src/promptgrimoire/static/milkdown/vite.config.js` — library mode build, CodeMirror externalized
- `src/promptgrimoire/static/milkdown/src/index.js` — entry point exporting editor factory and update functions as `window.*` globals
- `src/promptgrimoire/static/milkdown/dist/` — build output (committed)

**Dependencies:** None (first phase)

**Done when:** `npm install && npm run build` succeeds, `dist/milkdown-bundle.js` exists and is loadable in a browser without errors
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Crepe Editor with Python Interop

**Goal:** Replace the current kit-based Milkdown editor with Crepe from the local bundle, with toolbar and Python read/write.

**Components:**

- `src/promptgrimoire/pages/milkdown_spike.py` — rewrite to load bundle from static files instead of esm.sh import maps. Crepe initialization with toolbar. Python interop via `window._getMilkdownMarkdown()` and `window._setMilkdownMarkdown()`
- `src/promptgrimoire/static/milkdown/src/index.js` — `createEditor(rootEl, initialMd, onUpdate)` creates Crepe instance with `Feature.CodeMirror: false`. Exposes `getMarkdown()`, `setMarkdown(md)` as globals
- Static file serving via `app.add_static_files()` in the page module
- JS conflict detection — bundle init checks for conflicting ProseMirror instances and logs `console.error` if found. NiceGUI surfaces JS errors visibly.

**Dependencies:** Phase 1 (bundle exists)

**Done when:** Editor renders at `/demo/milkdown-spike` with working Bold, Italic, Heading, List, Blockquote, and Code toolbar buttons. Python `Get Markdown` button reads content back. Python can inject markdown via `Set Markdown`. Browser console shows no errors.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Multi-Client CRDT Sync

**Goal:** Two browser tabs editing the same document with live CRDT sync via pycrdt.

**Components:**

- `src/promptgrimoire/static/milkdown/src/index.js` — extend with Yjs integration: create Y.Doc, bind via `@milkdown/plugin-collab`, observe Y.Doc updates and call `onUpdate(base64)` callback, expose `applyRemoteUpdate(base64)` and `getFullState()` globals
- `src/promptgrimoire/pages/milkdown_spike.py` — add server-side CRDT document (pycrdt Doc), client registry, broadcast logic. Hidden UI element for JS→Python update channel. Connect/disconnect lifecycle. Full state sync for late-joining clients. Message chunking for updates exceeding WebSocket limits.

**JS→Python bridge contract:**

```javascript
// Bundle exposes:
window._applyRemoteUpdate(base64)  // Python pushes update to this client
window._getYjsUpdate()             // Returns base64 full state for new clients

// Bundle calls back:
onUpdate(base64)  // Called when local Y.Doc changes, triggers CustomEvent
```

**Server-side contract:**

```python
# Module-level state
_documents: dict[str, Doc]                              # doc_id → pycrdt Doc
_connected_clients: dict[str, dict[str, Callable]]      # doc_id → {client_id → push_fn}

# Per-client lifecycle
async def _on_client_connect(doc_id, client) -> None: ...
async def _on_yjs_update(doc_id, client_id, b64_update) -> None: ...
async def _broadcast_to_others(doc_id, origin_id, b64_update) -> None: ...
```

**Dependencies:** Phase 2 (editor renders and Python interop works)

**Done when:** Open two browser tabs to `/demo/milkdown-spike`. Type in one tab, text appears in the other within ~100ms. Both tabs can type simultaneously without data loss — changes merge at character level. A late-joining third tab receives full document state via chunked sync.
<!-- END_PHASE_3 -->

## Additional Considerations

**This is spike code.** No persistence, no auth, no error recovery, no tests beyond manual verification. The spike proves the integration path works. Production implementation will follow as a separate design.

**CodeMirror exclusion.** Crepe's CodeMirror feature is disabled at runtime (`Feature.CodeMirror: false`) and externalized at build time in Vite config. This means code blocks render as plain `<pre>` without syntax highlighting. Acceptable for a spike; production can re-enable by sharing NiceGUI's bundled CodeMirror.

**Bundle committed to git.** The `dist/` output is committed so deployment doesn't require Node.js. This matches NiceGUI 3.0's own pattern for bundled JS components.

**Single document for all clients.** The spike uses one hardcoded `doc_id`. All connected tabs edit the same document. Production will use workspace-scoped documents matching the `AnnotationDocument` registry pattern.

**WebSocket message chunking.** NiceGUI's Socket.IO transport has a 1 MB default `maxPayload`. Incremental Yjs updates are tiny (50-500 bytes), but full state sync for late-joining clients can exceed this limit on larger documents. Strategy: gzip compress before base64 encoding (2-4x savings), then chunk at ~500KB if still over limit. Each chunk carries an index and total count; receiver reassembles before applying. Both JS and Python sides implement this. This applies to the existing annotation sync code too — it currently has no size handling.

**JavaScript conflict detection.** The Vite bundle's init code checks for conflicting ProseMirror instances in the global scope and logs `console.error` if found. NiceGUI 3.2+ surfaces JS errors visibly. This ensures Milkdown's ProseMirror doesn't silently conflict with any other ProseMirror loaded by NiceGUI or other components.
