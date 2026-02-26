"""Spike: Milkdown Crepe editor embedded in NiceGUI with CRDT sync.

Proves that Milkdown Crepe can be embedded in a NiceGUI page with:
- WYSIWYG toolbar (Bold, Italic, Heading, List, Blockquote, Code)
- Python read/write of markdown content
- Local Vite bundle (no CDN dependencies)
- Multi-client CRDT sync via Yjs + pycrdt relay

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
    from nicegui import Client

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

_SPIKE_DOC_ID = "spike-default"

# Module-level state for CRDT relay.
# Maps doc_id -> pycrdt Doc (server-side merge authority).
_documents: dict[str, Doc] = {}

# Maps doc_id -> {client_id: Client} for broadcasting updates.
_connected_clients: dict[str, dict[str, Client]] = {}


def _get_or_create_doc(doc_id: str) -> Doc:
    """Lazy-create a pycrdt Doc for the given document ID."""
    if doc_id not in _documents:
        _documents[doc_id] = Doc()
        _connected_clients.setdefault(doc_id, {})
        logger.debug("CRDT_DOC_CREATED doc_id=%s", doc_id)
    return _documents[doc_id]


def _broadcast_to_others(doc_id: str, origin_client_id: str, b64_update: str) -> None:
    """Send a Yjs update to all connected clients except the origin."""
    clients = _connected_clients.get(doc_id, {})
    for cid, client in clients.items():
        if cid == origin_client_id:
            continue
        # Fire-and-forget: don't await the JS execution
        client.run_javascript(f"window._applyRemoteUpdate('{b64_update}')")
        logger.debug("BROADCAST doc_id=%s from=%s to=%s", doc_id, origin_client_id, cid)


def _build_spike_ui() -> ui.label:
    """Build the spike page UI elements. Returns the markdown display label."""
    ui.add_body_html('<script src="/milkdown/milkdown-bundle.js"></script>')

    with ui.row().classes(
        "w-full bg-amber-100 border border-amber-400"
        " rounded p-3 mb-4 items-center gap-2"
    ):
        ui.icon("science").classes("text-amber-700 text-xl")
        ui.label("SPIKE / DEMO").classes("text-amber-800 font-bold")
        ui.label("Milkdown Crepe editor embedding test. Not production code.").classes(
            "text-amber-700 text-sm"
        )

    ui.label("Milkdown Editor Spike").classes("text-2xl font-bold mb-4")

    ui.html(
        f'<div id="milkdown-editor" style="{_EDITOR_CONTAINER_STYLE}"></div>',
        sanitize=False,
    )

    markdown_display = ui.label("").classes(
        "text-sm font-mono bg-gray-100 p-4 mt-4 whitespace-pre-wrap"
    )
    markdown_display.set_visibility(False)

    async def get_markdown() -> None:
        result = await ui.run_javascript("window._getMilkdownMarkdown()")
        markdown_display.text = result or "(empty)"
        markdown_display.set_visibility(True)

    async def set_markdown() -> None:
        sample = "# Injected Content\\n\\nThis was set from Python!"
        await ui.run_javascript(f"window._setMilkdownMarkdown(`{sample}`)")
        ui.notify("Set Markdown called (see console for spike limitation)")

    with ui.row().classes("mt-4 gap-2"):
        ui.button("Get Markdown", on_click=get_markdown)
        ui.button("Set Markdown", on_click=set_markdown)

    return markdown_display


@page_route(
    "/demo/milkdown-spike",
    title="Milkdown Spike",
    icon="edit_note",
    category="demo",
    requires_demo=True,
    order=90,
)
async def milkdown_spike_page() -> None:
    """Spike page: Milkdown Crepe editor with CRDT collaboration."""
    if not require_demo_enabled():
        return

    client_id = str(uuid4())
    client: Client = ui.context.client
    doc = _get_or_create_doc(_SPIKE_DOC_ID)

    # Register this client for broadcast
    _connected_clients.setdefault(_SPIKE_DOC_ID, {})[client_id] = client
    logger.debug(
        "CLIENT_REGISTERED doc_id=%s client_id=%s total=%d",
        _SPIKE_DOC_ID,
        client_id,
        len(_connected_clients[_SPIKE_DOC_ID]),
    )

    def on_disconnect(_disconnect_client: Client | None = None) -> None:
        """Clean up client from the broadcast registry on disconnect."""
        clients = _connected_clients.get(_SPIKE_DOC_ID, {})
        clients.pop(client_id, None)
        logger.debug(
            "CLIENT_DISCONNECTED doc_id=%s client_id=%s remaining=%d",
            _SPIKE_DOC_ID,
            client_id,
            len(clients),
        )

    client.on_disconnect(on_disconnect)

    # Handle Yjs updates from this client
    def on_yjs_update(e: object) -> None:
        """Receive a Yjs update from the JS client, apply to server doc, broadcast."""
        b64_update: str = e.args["update"]  # type: ignore[union-attr]
        raw = base64.b64decode(b64_update)
        doc.apply_update(raw)
        _broadcast_to_others(_SPIKE_DOC_ID, client_id, b64_update)
        logger.debug(
            "YJS_UPDATE doc_id=%s client_id=%s bytes=%d",
            _SPIKE_DOC_ID,
            client_id,
            len(raw),
        )

    ui.on("yjs_update", on_yjs_update)

    _build_spike_ui()

    # Wait for WebSocket, then initialize the editor
    await ui.context.client.connected()

    escaped_md = (
        _DEFAULT_MD.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    )

    # Initialize the editor with a Yjs update callback that emits to Python
    await ui.run_javascript(
        f"""
        const root = document.getElementById('milkdown-editor');
        if (root && window._createMilkdownEditor) {{
            window._createMilkdownEditor(root, `{escaped_md}`, function(b64Update) {{
                emitEvent('yjs_update', {{update: b64Update}});
            }});
            'editor-init-started';
        }} else {{
            console.error(
                '[spike] bundle not loaded or #milkdown-editor missing'
            );
            'editor-init-failed';
        }}
        """,
        timeout=5.0,
    )

    # Full state sync for late-joining clients
    other_clients = {
        cid: c
        for cid, c in _connected_clients.get(_SPIKE_DOC_ID, {}).items()
        if cid != client_id
    }
    if other_clients:
        # Server doc has accumulated state from prior clients — send to new joiner
        full_state = bytes(doc.get_update())
        b64_state = base64.b64encode(full_state).decode("ascii")
        if len(full_state) > 2:
            # >2 bytes means the doc has real content (empty doc is 2 bytes)
            client.run_javascript(f"window._applyRemoteUpdate('{b64_state}')")
            logger.debug(
                "FULL_STATE_SYNC doc_id=%s to_client=%s bytes=%d",
                _SPIKE_DOC_ID,
                client_id,
                len(full_state),
            )
