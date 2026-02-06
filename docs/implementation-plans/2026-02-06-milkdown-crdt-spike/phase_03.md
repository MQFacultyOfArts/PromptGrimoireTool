# Phase 3: Multi-Client CRDT Sync

**Goal:** Two browser tabs editing the same document with live CRDT sync via pycrdt.

**Type:** Infrastructure + functionality (verified manually — spike code, no automated tests)

**Dependencies:** Phase 1 (bundle exists), Phase 2 (editor renders with Python interop)

**Design deviations (justified for spike):**
- **Echo prevention:** Design specifies ContextVar-based echo prevention matching `SharedDocument`. This implementation uses a simpler approach: JS-side `origin === "remote"` skip on Y.Doc updates, Python-side `client_id != origin_client_id` in broadcast loop. Functionally equivalent and avoids unnecessary ContextVar complexity for a spike. Production can adopt ContextVar if needed.
- **WebSocket chunking:** Design mentions chunking for full state sync exceeding NiceGUI's 1MB `maxPayload`. Deferred for spike — spike documents will be <10KB (manual editing in a demo), well under the 500KB threshold where chunking becomes necessary. Production implementation should add chunking for large documents.
- **Does not reuse `SharedDocument`:** Design references `SharedDocument` from `crdt/sync.py`. This implementation uses bare `pycrdt.Doc` because Milkdown collab operates on full Doc binary updates, not the Text-specific API that `SharedDocument` wraps.

---

<!-- START_TASK_1 -->
### Task 1: Rebuild JS bundle with Yjs + collab integration

**Files:**
- Modify: `src/promptgrimoire/static/milkdown/src/index.js` (full rewrite — extends Phase 1 entry point)

**Step 1: Rewrite the entry point**

Replace the entire contents of `src/promptgrimoire/static/milkdown/src/index.js` with:

```javascript
import { Crepe } from "@milkdown/crepe";
import { collab, collabServiceCtx } from "@milkdown/plugin-collab";
import "@milkdown/crepe/theme/common/style.css";
// NOTE: Verify exact theme CSS path after npm install. If frame.css does not
// exist, check node_modules/@milkdown/crepe/theme/ for available theme files.
import "@milkdown/crepe/theme/frame.css";
import * as Y from "yjs";

/**
 * Create a Milkdown Crepe editor with Yjs CRDT collaboration.
 *
 * @param {HTMLElement} rootEl - DOM element to mount the editor in.
 * @param {string} initialMd - Initial markdown (used only if no CRDT state received).
 * @param {function} onYjsUpdate - Callback with (base64EncodedUpdate: string) on local changes.
 * @returns {Promise<Crepe>} The Crepe editor instance.
 */
async function createEditor(rootEl, initialMd, onYjsUpdate) {
  if (window.__milkdownCrepe) {
    console.error("[milkdown-bundle] Crepe already initialized.");
    return window.__milkdownCrepe;
  }

  if (document.querySelector(".ProseMirror")) {
    console.error("[milkdown-bundle] Existing ProseMirror detected.");
  }

  // Create Yjs document for CRDT collaboration
  const ydoc = new Y.Doc();
  window.__milkdownYDoc = ydoc;

  const crepe = new Crepe({
    root: rootEl,
    defaultValue: initialMd || "",
    features: { [Crepe.Feature.CodeMirror]: false },
  });

  // Register collab plugin before creation
  crepe.editor.use(collab);
  await crepe.create();
  console.log("[milkdown-bundle] Crepe editor created");

  // Bind Yjs doc to editor via collab service (must be after create)
  crepe.editor.action((ctx) => {
    const service = ctx.get(collabServiceCtx);
    service.bindDoc(ydoc).connect();
  });
  console.log("[milkdown-bundle] Yjs collab bound");

  // Observe local Y.Doc changes and call back with base64
  ydoc.on("update", (update, origin) => {
    // Skip updates that came from remote (applied via _applyRemoteUpdate)
    if (origin === "remote") return;
    if (onYjsUpdate) {
      onYjsUpdate(uint8ArrayToBase64(update));
    }
  });

  window.__milkdownCrepe = crepe;
  return crepe;
}

/**
 * Apply a remote CRDT update received from the server.
 * @param {string} b64Update - Base64-encoded Yjs update.
 */
function applyRemoteUpdate(b64Update) {
  const ydoc = window.__milkdownYDoc;
  if (!ydoc) {
    console.error("[milkdown-bundle] No Y.Doc initialized");
    return;
  }
  const update = base64ToUint8Array(b64Update);
  Y.applyUpdate(ydoc, update, "remote");
}

/**
 * Get the full Yjs document state as base64 for syncing new clients.
 * @returns {string} Base64-encoded full state.
 */
function getYjsFullState() {
  const ydoc = window.__milkdownYDoc;
  if (!ydoc) return "";
  return uint8ArrayToBase64(Y.encodeStateAsUpdate(ydoc));
}

// --- Base64 helpers ---

function uint8ArrayToBase64(arr) {
  let bin = "";
  for (let i = 0; i < arr.length; i++) bin += String.fromCharCode(arr[i]);
  return btoa(bin);
}

function base64ToUint8Array(b64) {
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return arr;
}

// Expose globals for Python interop via ui.run_javascript()
window._createMilkdownEditor = createEditor;

window._getMilkdownMarkdown = function () {
  if (!window.__milkdownCrepe) return "";
  return window.__milkdownCrepe.getMarkdown();
};

window._setMilkdownMarkdown = function () {
  console.warn("[milkdown-bundle] setMarkdown: spike limitation");
};

window._applyRemoteUpdate = applyRemoteUpdate;
window._getYjsFullState = getYjsFullState;
```

**Step 2: Rebuild the bundle**

```bash
cd src/promptgrimoire/static/milkdown
npm run build
```

Expected: `dist/milkdown-bundle.js` rebuilt. Should be slightly larger than Phase 1 build due to Yjs inclusion.

**Step 3: Verify bundle contains new globals**

```bash
grep -c "_applyRemoteUpdate" src/promptgrimoire/static/milkdown/dist/milkdown-bundle.js
grep -c "_getYjsFullState" src/promptgrimoire/static/milkdown/dist/milkdown-bundle.js
# Both should output 1 or more
```

**Step 4: Commit**

```bash
git add src/promptgrimoire/static/milkdown/src/index.js src/promptgrimoire/static/milkdown/dist/
git commit -m "feat: add Yjs CRDT integration to Milkdown bundle with collab plugin"
```

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add server-side CRDT relay to milkdown_spike.py

**Files:**
- Modify: `src/promptgrimoire/pages/milkdown_spike.py` (full rewrite — replaces Phase 2 version)

**Step 1: Rewrite the page module**

Replace the entire contents of `src/promptgrimoire/pages/milkdown_spike.py` with:

```python
"""Spike: Milkdown Crepe editor with multi-client CRDT sync.

Proves Milkdown Crepe + Yjs can sync via pycrdt through NiceGUI WebSockets:
- WYSIWYG toolbar (Bold, Italic, Heading, List, Blockquote, Code)
- Python read/write of markdown content
- Multi-client CRDT sync (two tabs editing the same document)
- Local Vite bundle (no CDN dependencies)

Not production code — delete after spike evaluation.

Route: /demo/milkdown-spike (requires ENABLE_DEMO_PAGES=true)
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from nicegui import app, ui
from pycrdt import Doc

from promptgrimoire.pages.layout import require_demo_enabled
from promptgrimoire.pages.registry import page_route

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# Serve the Milkdown bundle from static files
_BUNDLE_DIR = Path(__file__).parent.parent / "static" / "milkdown" / "dist"
app.add_static_files("/milkdown", str(_BUNDLE_DIR))

_EDITOR_CONTAINER_STYLE = (
    "min-height: 300px; border: 1px solid #ddd; border-radius: 8px; padding: 16px;"
)

_DEFAULT_MD = """\
# Response Draft

Start writing your reflection here.

- Use **bold** and *italic*
- Create lists
- Add headings
"""

# --- Server-side CRDT state ---

# Single document for all clients (spike simplification)
_SPIKE_DOC_ID = "milkdown-spike-doc"

# doc_id -> pycrdt Doc
_documents: dict[str, Doc] = {}

# doc_id -> {client_id -> push_fn}
_connected_clients: dict[str, dict[str, Callable]] = {}


def _get_or_create_doc(doc_id: str) -> Doc:
    """Get or create a pycrdt Doc for the given document ID."""
    if doc_id not in _documents:
        _documents[doc_id] = Doc()
    return _documents[doc_id]


async def _broadcast_to_others(
    doc_id: str, origin_client_id: str, b64_update: str
) -> None:
    """Send a CRDT update to all connected clients except the origin."""
    clients = _connected_clients.get(doc_id, {})
    for cid, push_fn in list(clients.items()):
        if cid != origin_client_id:
            try:
                await push_fn(b64_update)
            except Exception:
                logger.debug("PUSH_FAILED: doc=%s client=%s", doc_id, cid[:8])


@page_route(
    "/demo/milkdown-spike",
    title="Milkdown Spike",
    icon="edit_note",
    category="demo",
    requires_demo=True,
    order=90,
)
async def milkdown_spike_page() -> None:
    """Spike page: Milkdown Crepe editor with CRDT sync."""
    if not require_demo_enabled():
        return

    # Load the IIFE bundle (not an ES module — no type="module" needed)
    ui.add_body_html('<script src="/milkdown/milkdown-bundle.js"></script>')

    # Demo banner
    with ui.row().classes(
        "w-full bg-amber-100 border border-amber-400"
        " rounded p-3 mb-4 items-center gap-2"
    ):
        ui.icon("science").classes("text-amber-700 text-xl")
        ui.label("SPIKE / DEMO").classes("text-amber-800 font-bold")
        ui.label(
            "Milkdown Crepe + CRDT sync. Open two tabs to test."
        ).classes("text-amber-700 text-sm")

    ui.label("Milkdown Editor Spike").classes("text-2xl font-bold mb-4")

    # Editor container
    ui.html(
        f'<div id="milkdown-editor" style="{_EDITOR_CONTAINER_STYLE}"></div>',
        sanitize=False,
    )

    # Markdown display area (hidden until "Get Markdown" is clicked)
    markdown_display = ui.label("").classes(
        "text-sm font-mono bg-gray-100 p-4 mt-4 whitespace-pre-wrap"
    )
    markdown_display.set_visibility(False)

    async def get_markdown() -> None:
        """Read markdown content from the editor via JS global."""
        result = await ui.run_javascript("window._getMilkdownMarkdown()")
        markdown_display.text = result or "(empty)"
        markdown_display.set_visibility(True)

    async def set_markdown() -> None:
        """Inject sample markdown into the editor."""
        sample = "# Injected Content\\n\\nThis was set from Python!"
        await ui.run_javascript(f"window._setMilkdownMarkdown(`{sample}`)")
        ui.notify("Set Markdown called (see console for spike limitation)")

    with ui.row().classes("mt-4 gap-2"):
        ui.button("Get Markdown", on_click=get_markdown)
        ui.button("Set Markdown", on_click=set_markdown)

    # Wait for WebSocket connection before setting up sync
    await ui.context.client.connected()

    # --- CRDT sync setup ---
    client = ui.context.client
    client_id = str(uuid4())
    doc_id = _SPIKE_DOC_ID
    doc = _get_or_create_doc(doc_id)

    # Register this client's push function
    if doc_id not in _connected_clients:
        _connected_clients[doc_id] = {}

    async def push_update_to_client(b64_update: str) -> None:
        """Push a CRDT update to this client's browser."""
        await ui.run_javascript(
            f"window._applyRemoteUpdate('{b64_update}')"
        )

    _connected_clients[doc_id][client_id] = push_update_to_client

    logger.info(
        "CLIENT_REGISTERED: doc=%s client=%s total=%d",
        doc_id, client_id[:8], len(_connected_clients[doc_id]),
    )

    # JS→Python bridge: receive Yjs updates via emitEvent
    # (follows annotation.py pattern: emitEvent on JS side, ui.on on Python side)
    async def on_yjs_update(e) -> None:
        """Handle a Yjs update from the browser."""
        b64_update = e.args.get("update", "")
        if not b64_update:
            return
        # Apply to server-side pycrdt Doc
        try:
            update_bytes = base64.b64decode(b64_update)
            doc.apply_update(update_bytes)
        except Exception:
            logger.exception("APPLY_UPDATE_FAILED: doc=%s", doc_id)
            return
        # Broadcast to other connected clients
        await _broadcast_to_others(doc_id, client_id, b64_update)

    ui.on("yjs_update", on_yjs_update)

    # Disconnect cleanup
    async def on_disconnect() -> None:
        if doc_id in _connected_clients:
            _connected_clients[doc_id].pop(client_id, None)
            logger.info(
                "CLIENT_DISCONNECTED: doc=%s client=%s remaining=%d",
                doc_id, client_id[:8],
                len(_connected_clients.get(doc_id, {})),
            )

    client.on_disconnect(on_disconnect)

    # Initialize editor with CRDT sync callback
    escaped_md = _DEFAULT_MD.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")

    await ui.run_javascript(f"""
        const root = document.getElementById('milkdown-editor');
        if (root && window._createMilkdownEditor) {{
            window._createMilkdownEditor(root, `{escaped_md}`, function(b64Update) {{
                emitEvent('yjs_update', {{ update: b64Update }});
            }});
        }} else {{
            console.error('[spike] milkdown-bundle.js not loaded or #milkdown-editor not found');
        }}
    """)

    # Full state sync for late-joining clients
    if len(_connected_clients.get(doc_id, {})) > 1:
        full_state = base64.b64encode(doc.get_update()).decode("ascii")
        if full_state:
            await ui.run_javascript(
                f"window._applyRemoteUpdate('{full_state}')"
            )
            logger.info(
                "FULL_STATE_SYNC: doc=%s client=%s bytes=%d",
                doc_id, client_id[:8], len(full_state),
            )
```

**Step 2: Verify the editor still renders**

```bash
ENABLE_DEMO_PAGES=true uv run python -m promptgrimoire
```

Navigate to `http://localhost:8080/demo/milkdown-spike`.

Expected:
- Crepe editor renders with toolbar
- Default markdown content visible
- Browser console shows `[milkdown-bundle] Crepe editor created` and `[milkdown-bundle] Yjs collab bound`
- No JS errors in console

**Step 3: Test multi-client sync**

- Open Tab A at `/demo/milkdown-spike`
- Open Tab B at `/demo/milkdown-spike`
- Type in Tab A — text appears in Tab B
- Type in Tab B — text appears in Tab A
- Both typing simultaneously — changes merge without data loss
- Server logs show CLIENT_REGISTERED for both tabs

**Step 4: Commit**

```bash
git add src/promptgrimoire/pages/milkdown_spike.py
git commit -m "feat: add multi-client CRDT sync to milkdown spike via pycrdt"
```

<!-- END_TASK_2 -->

---

## UAT Steps (requires human judgment)

1. [ ] Start the app: `ENABLE_DEMO_PAGES=true uv run python -m promptgrimoire`
2. [ ] Open Tab A: `/demo/milkdown-spike`
3. [ ] Verify: Crepe editor renders with working toolbar (Bold, Italic, Heading, List, Blockquote, Code)
4. [ ] Open Tab B: `/demo/milkdown-spike`
5. [ ] Type text in Tab A — text appears in Tab B within ~1 second
6. [ ] Type text in Tab B — text appears in Tab A within ~1 second
7. [ ] Both tabs typing simultaneously — changes merge at character level, no data loss
8. [ ] Open Tab C (late joiner) — receives full document state on load
9. [ ] Click "Get Markdown" in any tab — shows current merged content accurately
10. [ ] Browser console in all tabs shows no errors (especially no ProseMirror conflicts)
11. [ ] Server logs show CLIENT_REGISTERED, update propagation, FULL_STATE_SYNC for late joiners

**Evidence Required:**
- [ ] Screenshot or recording of two tabs syncing text in real time
- [ ] Screenshot of "Get Markdown" showing merged content from both tabs
- [ ] Server log excerpt showing CLIENT_REGISTERED and FULL_STATE_SYNC messages
