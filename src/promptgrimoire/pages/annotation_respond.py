"""Tab 3 (Respond) rendering for the annotation page.

Embeds a Milkdown WYSIWYG editor bound to the ``response_draft`` XmlFragment
in the shared CRDT Doc, plus a read-only reference panel showing highlights
grouped by tag.

The Milkdown editor uses the same JS bundle as the spike page
(``static/milkdown/dist/milkdown-bundle.js``) but binds to a named
XmlFragment (``response_draft``) instead of the default Doc-level binding.
Yjs updates are Doc-level, so they flow through the existing annotation
broadcast mechanism without fragment-level routing.

This module imports TagInfo but NOT BriefTag -- the tag-agnostic abstraction
ensures Tab 3 rendering is decoupled from the domain enum.

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui/phase_05.md Tasks 2-3
- AC: three-tab-ui.AC4.1, AC4.2, AC4.3, AC4.4, AC4.5
"""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING, Any

from nicegui import ui

if TYPE_CHECKING:
    from promptgrimoire.crdt.annotation_doc import AnnotationDocument
    from promptgrimoire.pages.annotation_tags import TagInfo

logger = logging.getLogger(__name__)

# Maximum characters to show in highlight text snippet before truncation
_SNIPPET_MAX_CHARS = 100

# Milkdown editor container styling
_EDITOR_CONTAINER_STYLE = (
    "min-height: 300px; border: 1px solid #ddd; border-radius: 8px; padding: 16px;"
)

# Fragment name for the response draft in the shared CRDT Doc
_FRAGMENT_NAME = "response_draft"


def _build_reference_card(
    highlight: dict[str, Any],
    tag_colour: str,
    display_tag_name: str,
) -> None:
    """Render a single read-only highlight reference card.

    Args:
        highlight: Highlight data dict from CRDT.
        tag_colour: Hex colour for the left border.
        display_tag_name: Human-readable tag name.
    """
    author = highlight.get("author", "Unknown")
    full_text = highlight.get("text", "")
    snippet = full_text[:_SNIPPET_MAX_CHARS]
    if len(full_text) > _SNIPPET_MAX_CHARS:
        snippet += "..."

    with (
        ui.card()
        .classes("w-full mb-2")
        .style(f"border-left: 4px solid {tag_colour};")
        .props('data-testid="respond-reference-card"')
    ):
        ui.label(display_tag_name).classes("text-xs font-bold").style(
            f"color: {tag_colour};"
        )
        ui.label(f"by {author}").classes("text-xs text-gray-500")
        if snippet:
            ui.label(f'"{snippet}"').classes("text-sm italic mt-1")


def _build_reference_panel(
    tags: list[TagInfo],
    crdt_doc: AnnotationDocument,
) -> None:
    """Build the read-only highlight reference panel (right column).

    Shows highlights grouped by tag with coloured section headers.
    If no highlights exist, shows an empty-state message.

    Args:
        tags: List of TagInfo instances for grouping.
        crdt_doc: The CRDT annotation document.
    """
    all_highlights = crdt_doc.get_all_highlights()

    # Build raw tag value -> TagInfo lookup
    tag_raw_values: dict[str, TagInfo] = {tag.raw_key: tag for tag in tags}

    # Group highlights by tag
    tagged_highlights: dict[str, list[dict[str, Any]]] = {
        tag_info.name: [] for tag_info in tags
    }
    untagged_highlights: list[dict[str, Any]] = []

    for hl in all_highlights:
        raw_tag = hl.get("tag", "")
        if raw_tag and raw_tag in tag_raw_values:
            display_name = tag_raw_values[raw_tag].name
            tagged_highlights[display_name].append(hl)
        else:
            untagged_highlights.append(hl)

    has_any_highlights = bool(all_highlights)

    if not has_any_highlights:
        ui.label("No highlights yet").classes("text-gray-400 italic p-4").props(
            'data-testid="respond-no-highlights"'
        )
        return

    # Render grouped highlights
    for tag_info in tags:
        highlights_for_tag = tagged_highlights[tag_info.name]
        if not highlights_for_tag:
            continue

        with (
            ui.expansion(tag_info.name, value=True)
            .classes("w-full")
            .props(f'data-testid="respond-tag-group" data-tag-name="{tag_info.name}"')
        ):
            for hl in highlights_for_tag:
                _build_reference_card(hl, tag_info.colour, tag_info.name)

    # Untagged highlights
    if untagged_highlights:
        with (
            ui.expansion("Untagged", value=True)
            .classes("w-full")
            .props('data-testid="respond-tag-group" data-tag-name="Untagged"')
        ):
            for hl in untagged_highlights:
                _build_reference_card(hl, "#999999", "Untagged")


async def render_respond_tab(
    panel: ui.element,
    tags: list[TagInfo],
    crdt_doc: AnnotationDocument,
    workspace_key: str,
    client_id: str,
    on_yjs_update_broadcast: Any,
) -> None:
    """Populate the Respond tab panel with Milkdown editor and reference panel.

    Clears the placeholder content from the panel, then creates a two-column
    layout: Milkdown WYSIWYG editor on the left, read-only highlight reference
    cards on the right.

    The editor binds to the ``response_draft`` XmlFragment within the shared
    CRDT Doc. Yjs updates from local edits are forwarded to the broadcast
    function for relay to other connected clients. Full-state sync is sent
    to late-joining clients.

    Args:
        panel: The ui.tab_panel element to populate.
        tags: List of TagInfo instances for the reference panel.
        crdt_doc: The CRDT annotation document.
        workspace_key: String key for the workspace (for broadcast lookup).
        client_id: This client's unique ID (for echo prevention).
        on_yjs_update_broadcast: Callable(b64_update, origin_client_id) to
            broadcast Yjs updates to other clients.
    """
    panel.clear()

    with (
        panel,
        ui.row().classes("w-full gap-4 flex-nowrap").style("min-height: 400px;"),
    ):
        # Left column: Milkdown editor (flex: 2)
        with (
            ui.column()
            .classes("flex-grow")
            .style("flex: 2; min-width: 0;")
            .props('data-testid="respond-editor-column"')
        ):
            ui.label("Response Draft").classes("text-lg font-bold mb-2")
            editor_id = "milkdown-respond-editor"
            ui.html(
                f'<div id="{editor_id}" style="{_EDITOR_CONTAINER_STYLE}"'
                f' data-testid="milkdown-editor-container"></div>',
                sanitize=False,
            )

        # Right column: Reference panel (flex: 1)
        with (
            ui.column()
            .classes("flex-grow overflow-y-auto")
            .style("flex: 1; min-width: 200px; max-height: 80vh;")
            .props('data-testid="respond-reference-panel"')
        ):
            ui.label("Highlight Reference").classes("text-lg font-bold mb-2")
            _build_reference_panel(tags, crdt_doc)

    # Load the Milkdown JS bundle (idempotent if already loaded by spike)
    ui.add_body_html('<script src="/milkdown/milkdown-bundle.js"></script>')

    # Set up the Yjs update handler that relays edits to Python
    def on_yjs_update(e: object) -> None:
        """Receive a Yjs update from the JS Milkdown editor."""
        b64_update: str = e.args["update"]  # type: ignore[union-attr]
        raw = base64.b64decode(b64_update)
        # Apply to server-side CRDT Doc
        crdt_doc.apply_update(raw, origin_client_id=client_id)
        # Broadcast to other clients
        on_yjs_update_broadcast(b64_update, client_id)
        logger.debug(
            "RESPOND_YJS_UPDATE ws=%s client=%s bytes=%d",
            workspace_key,
            client_id[:8],
            len(raw),
        )

    ui.on("respond_yjs_update", on_yjs_update)

    # Wait for WebSocket, then initialize the editor
    await ui.context.client.connected()

    # Initialize Milkdown editor with response_draft fragment binding
    await ui.run_javascript(
        f"""
        const root = document.getElementById('{editor_id}');
        if (root && window._createMilkdownEditor) {{
            window._createMilkdownEditor(root, '', function(b64Update) {{
                emitEvent('respond_yjs_update', {{update: b64Update}});
            }}, '{_FRAGMENT_NAME}');
            'editor-init-started';
        }} else {{
            console.error(
                '[respond-tab] bundle not loaded or #{editor_id} missing'
            );
            'editor-init-failed';
        }}
        """,
        timeout=5.0,
    )

    # Full-state sync for late joiners (AC4.3)
    full_state = crdt_doc.get_full_state()
    if len(full_state) > 2:
        # >2 bytes means the doc has real content (empty doc is 2 bytes)
        b64_state = base64.b64encode(full_state).decode("ascii")
        ui.context.client.run_javascript(f"window._applyRemoteUpdate('{b64_state}')")
        logger.info(
            "RESPOND_FULL_STATE_SYNC ws=%s to_client=%s bytes=%d",
            workspace_key,
            client_id[:8],
            len(full_state),
        )
