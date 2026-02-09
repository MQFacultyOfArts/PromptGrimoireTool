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

from promptgrimoire.crdt.persistence import get_persistence_manager

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from promptgrimoire.crdt.annotation_doc import AnnotationDocument
    from promptgrimoire.pages.annotation_tags import TagInfo

logger = logging.getLogger(__name__)

# Maximum characters to show in highlight text snippet before truncation
_SNIPPET_MAX_CHARS = 100

# Initial split percentage for the reference panel (left side of splitter)
_REFERENCE_PANEL_SPLIT = 25

# Split value when the reference panel is collapsed
_REFERENCE_PANEL_COLLAPSED = 0

# Fragment name for the response draft in the shared CRDT Doc
_FRAGMENT_NAME = "response_draft"

# Override Milkdown's default ProseMirror padding (60px 120px) for constrained layouts.
# Asymmetric: generous left for Crepe's block-handle controls (~66px for two 32px
# operation-items + gap), minimal right so the right margin collapses first when
# the splitter is narrow.  No overflow-x:hidden — that clips the absolutely-
# positioned block handles and floating toolbar.
_EDITOR_CSS = """
    #milkdown-respond-editor .milkdown .ProseMirror {
        padding: 24px 0 24px 82px;
    }
"""


def group_highlights_by_tag(
    tags: list[TagInfo],
    crdt_doc: AnnotationDocument,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], bool]:
    """Pure function to group highlights by tag for reference panel rendering.

    Extracts all highlights from the CRDT doc and organizes them by tag,
    with untagged highlights in a separate list. This logic is decoupled
    from UI rendering to enable unit testing.

    Args:
        tags: List of TagInfo instances for grouping.
        crdt_doc: The CRDT annotation document.

    Returns:
        A tuple of:
        - tagged_highlights: dict mapping tag display name to list of highlights
        - untagged_highlights: list of highlights without a recognized tag
        - has_any_highlights: boolean indicating if any highlights exist
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

    return tagged_highlights, untagged_highlights, has_any_highlights


def _build_reference_card(
    highlight: dict[str, Any],
    tag_colour: str,
    display_tag_name: str,
    on_locate: Callable[..., Any] | None = None,
) -> None:
    """Render a single read-only highlight reference card.

    Args:
        highlight: Highlight data dict from CRDT.
        tag_colour: Hex colour for the left border.
        display_tag_name: Human-readable tag name.
        on_locate: Optional async callback(start_char, end_char) to warp to
            the highlight in Tab 1.
    """
    author = highlight.get("author", "Unknown")
    start_char: int = highlight.get("start_char", 0)
    end_char: int = highlight.get("end_char", 0)
    full_text = highlight.get("text", "")
    snippet = full_text[:_SNIPPET_MAX_CHARS]
    if len(full_text) > _SNIPPET_MAX_CHARS:
        snippet += "..."
    comments: list[dict[str, Any]] = highlight.get("comments", [])

    with (
        ui.card()
        .classes("w-full mb-2")
        .style(f"border-left: 4px solid {tag_colour};")
        .props('data-testid="respond-reference-card"')
    ):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(display_tag_name).classes("text-xs font-bold").style(
                f"color: {tag_colour};"
            )
            if on_locate is not None:

                async def _do_locate(sc: int = start_char, ec: int = end_char) -> None:
                    await on_locate(sc, ec)

                ui.button(icon="my_location", on_click=_do_locate).props(
                    "flat dense size=xs"
                ).tooltip("Locate in document")

        ui.label(f"by {author}").classes("text-xs text-gray-500")
        if snippet:
            ui.label(f'"{snippet}"').classes("text-sm italic mt-1")
        for comment in comments:
            comment_author = comment.get("author", "")
            comment_text = comment.get("text", "")
            if comment_text:
                with (
                    ui.row()
                    .classes("w-full items-start gap-1 mt-1 pl-2")
                    .style("border-left: 2px solid #e0e0e0;")
                ):
                    ui.label(f"{comment_author}:").classes(
                        "text-xs text-gray-500 font-medium shrink-0"
                    )
                    ui.label(comment_text).classes("text-xs text-gray-700")


def _matches_filter(highlight: dict[str, Any], filter_text: str) -> bool:
    """Check if a highlight matches the search filter (case-insensitive)."""
    needle = filter_text.lower()
    text = highlight.get("text", "").lower()
    author = highlight.get("author", "").lower()
    if needle in text or needle in author:
        return True
    for comment in highlight.get("comments", []):
        if needle in comment.get("text", "").lower():
            return True
        if needle in comment.get("author", "").lower():
            return True
    return False


def _build_reference_panel(
    tags: list[TagInfo],
    crdt_doc: AnnotationDocument,
    filter_text: str | None = None,
    accordion_state: dict[str, bool] | None = None,
    on_locate: Callable[..., Any] | None = None,
) -> None:
    """Build the read-only highlight reference panel (left column).

    Shows highlights grouped by tag with coloured section headers.
    If no highlights exist, shows an empty-state message.

    Args:
        tags: List of TagInfo instances for grouping.
        crdt_doc: The CRDT annotation document.
        filter_text: Optional search string to filter highlights by text or author.
        accordion_state: Dict mapping tag name to open/closed state. Mutated in
            place via ``on_value_change`` callbacks so the caller's dict stays
            in sync across rebuilds.
        on_locate: Optional async callback(start_char, end_char) to warp to
            a highlight in Tab 1.
    """
    tagged_highlights, untagged_highlights, has_any_highlights = (
        group_highlights_by_tag(tags, crdt_doc)
    )

    if not has_any_highlights:
        ui.label("No highlights yet").classes("text-gray-400 italic p-4").props(
            'data-testid="respond-no-highlights"'
        )
        return

    # Apply text filter if provided
    active_filter = filter_text.strip() if filter_text else ""

    def _expansion_for(tag_name: str) -> ui.expansion:
        """Create an expansion panel that tracks its open/closed state."""
        is_open = accordion_state.get(tag_name, True) if accordion_state else True
        exp = (
            ui.expansion(tag_name, value=is_open)
            .classes("w-full")
            .props(f'data-testid="respond-tag-group" data-tag-name="{tag_name}"')
        )
        if accordion_state is not None:

            def _track(e: Any, name: str = tag_name) -> None:
                accordion_state[name] = bool(e.value)

            exp.on_value_change(_track)
        return exp

    # Render grouped highlights
    for tag_info in tags:
        highlights_for_tag = tagged_highlights[tag_info.name]
        if active_filter:
            highlights_for_tag = [
                hl
                for hl in highlights_for_tag
                if _matches_filter(hl, active_filter)
                or active_filter.lower() in tag_info.name.lower()
            ]
        if not highlights_for_tag:
            continue

        with _expansion_for(tag_info.name):
            for hl in highlights_for_tag:
                _build_reference_card(hl, tag_info.colour, tag_info.name, on_locate)

    # Untagged highlights
    if active_filter:
        untagged_highlights = [
            hl for hl in untagged_highlights if _matches_filter(hl, active_filter)
        ]
    if untagged_highlights:
        with _expansion_for("Untagged"):
            for hl in untagged_highlights:
                _build_reference_card(hl, "#999999", "Untagged", on_locate)


def _build_reference_column(
    splitter: ui.splitter,
    tags: list[TagInfo],
    crdt_doc: AnnotationDocument,
    accordion_state: dict[str, bool],
    on_locate: Callable[..., Any] | None = None,
) -> tuple[ui.element, ui.input]:
    """Build the reference panel column inside the splitter's 'before' slot.

    Returns the reference_container and search_input elements so the caller
    can wire up refresh and filter callbacks.
    """
    with (
        splitter.before,
        ui.column()
        .classes("w-full p-2 overflow-y-auto")
        .style("max-height: 80vh;")
        .props('id="respond-ref-scroll" data-testid="respond-reference-panel"'),
    ):
        with ui.row().classes("w-full items-center justify-between mb-2"):
            ui.label("Highlight Reference").classes("text-lg font-bold")
            ui.button(
                icon="chevron_left",
                on_click=lambda: splitter.set_value(_REFERENCE_PANEL_COLLAPSED),
            ).props("flat dense round size=sm")

        search_input = (
            ui.input(placeholder="Filter highlights...")
            .classes("w-full mb-2")
            .props("dense clearable outlined")
        )

        reference_container = ui.column().classes("w-full")
        with reference_container:
            _build_reference_panel(
                tags, crdt_doc, accordion_state=accordion_state, on_locate=on_locate
            )

    return reference_container, search_input


async def _sync_markdown_to_crdt(
    crdt_doc: AnnotationDocument,
    workspace_key: str,
    client_id: str,
) -> None:
    """Extract markdown from Milkdown and write to the CRDT Text field.

    Called after Yjs updates and on tab-leave to keep the server-side
    ``response_draft_markdown`` Text field in sync with the editor content.
    This enables PDF export from clients that never visited Tab 3 (AC6.3).

    Args:
        crdt_doc: The CRDT annotation document.
        workspace_key: Workspace identifier for logging.
        client_id: Client identifier for logging.
    """
    try:
        md: str = await ui.run_javascript("window._getMilkdownMarkdown()", timeout=3.0)
        if md is None:
            md = ""
    except (TimeoutError, OSError) as exc:
        logger.debug(
            "RESPOND_MD_SYNC_SKIP ws=%s (JS call failed: %s)",
            workspace_key,
            type(exc).__name__,
        )
        return

    # Replace the entire Text field content atomically
    text_field = crdt_doc.response_draft_markdown
    current = str(text_field)
    if current != md:
        with crdt_doc.doc.transaction():
            current_len = len(text_field)
            if current_len > 0:
                del text_field[:current_len]
            if md:
                text_field += md
        logger.debug(
            "RESPOND_MD_SYNC ws=%s client=%s len=%d",
            workspace_key,
            client_id[:8],
            len(md),
        )


def _setup_yjs_event_handler(
    crdt_doc: AnnotationDocument,
    workspace_key: str,
    workspace_id: UUID,
    client_id: str,
    on_yjs_update_broadcast: Any,
) -> None:
    """Register the NiceGUI event handler for Yjs updates from the Milkdown editor.

    Receives base64-encoded Yjs updates from the browser, applies them to the
    server-side CRDT Doc, broadcasts to other clients, and syncs the markdown
    mirror to the CRDT Text field.

    Args:
        crdt_doc: The CRDT annotation document.
        workspace_key: Workspace identifier for broadcast lookup.
        workspace_id: Workspace UUID for persistence.
        client_id: This client's unique ID (for echo prevention).
        on_yjs_update_broadcast: Callable(b64_update, origin_client_id) to
            broadcast Yjs updates to other clients.
    """

    async def on_yjs_update(e: object) -> None:
        """Receive a Yjs update from the JS Milkdown editor."""
        b64_update: str = e.args["update"]  # type: ignore[union-attr]  # NiceGUI GenericEventArguments.args is untyped
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
        # Sync markdown mirror to CRDT Text field for server-side access
        await _sync_markdown_to_crdt(crdt_doc, workspace_key, client_id)
        # Persist CRDT state to database (debounced by persistence manager)
        pm = get_persistence_manager()
        pm.mark_dirty_workspace(
            workspace_id,
            crdt_doc.doc_id,
            last_editor=client_id,
        )

    ui.on("respond_yjs_update", on_yjs_update)


async def render_respond_tab(
    panel: ui.element,
    tags: list[TagInfo],
    crdt_doc: AnnotationDocument,
    workspace_key: str,
    workspace_id: UUID,
    client_id: str,
    on_yjs_update_broadcast: Any,
    on_locate: Callable[..., Any] | None = None,
) -> tuple[Callable[[], None], Callable[[], Any]]:
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
        on_locate: Optional async callback(start_char, end_char) to warp to
            a highlight in Tab 1.

    Returns:
        A tuple of (refresh_references, sync_markdown):
        - refresh_references: Callable that refreshes the reference panel.
        - sync_markdown: Async callable that syncs editor markdown to the
          CRDT Text field for server-side access (PDF export fallback).
    """
    panel.clear()
    editor_id = "milkdown-respond-editor"

    # Tracks which tag accordions are open/closed across rebuilds.
    # Mutated in place by on_value_change callbacks inside _build_reference_panel.
    accordion_state: dict[str, bool] = {}

    def _toggle_reference() -> None:
        """Toggle the reference panel between collapsed and expanded."""
        if splitter.value <= _REFERENCE_PANEL_COLLAPSED:
            splitter.set_value(_REFERENCE_PANEL_SPLIT)
        else:
            splitter.set_value(_REFERENCE_PANEL_COLLAPSED)

    with panel:
        ui.add_css(_EDITOR_CSS)

        splitter = (
            ui.splitter(value=_REFERENCE_PANEL_SPLIT)
            .classes("w-full")
            .style("min-height: 70vh;")
            .props(
                f':limits="[{_REFERENCE_PANEL_COLLAPSED}, 40]"'
                ' data-testid="respond-splitter"'
            )
        )

        reference_container, search_input = _build_reference_column(
            splitter, tags, crdt_doc, accordion_state, on_locate=on_locate
        )

        def _filter_highlights(e: object) -> None:
            """Re-render reference panel filtered by search text.

            Uses the event value directly rather than search_input.value because
            NiceGUI debounces server-side value sync — reading .value here would
            return stale data.
            """
            filter_val = e.args if isinstance(e.args, str) else ""  # type: ignore[union-attr]  # NiceGUI GenericEventArguments.args is untyped
            reference_container.clear()
            with reference_container:
                _build_reference_panel(
                    tags,
                    crdt_doc,
                    filter_text=filter_val,
                    accordion_state=accordion_state,
                    on_locate=on_locate,
                )

        search_input.on("update:model-value", _filter_highlights)

        with splitter.separator:
            ui.button(
                icon="drag_indicator",
                on_click=_toggle_reference,
            ).props("flat dense round color=primary size=sm")

        with splitter.after:
            # Milkdown editor — main editing workspace (~75% default).
            # The raw HTML div is the mount point for Milkdown's ProseMirror
            # instance; everything else uses NiceGUI components.
            ui.label("Response Draft").classes("text-lg font-bold mb-2 ml-2")
            ui.html(
                f'<div id="{editor_id}" style="flex: 1; min-height: 60vh;"'
                f' data-testid="milkdown-editor-container"></div>',
                sanitize=False,
            ).classes("w-full").style("display: flex; flex-direction: column; flex: 1;")

    _setup_yjs_event_handler(
        crdt_doc, workspace_key, workspace_id, client_id, on_yjs_update_broadcast
    )

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

    def refresh_references() -> None:
        """Re-render the reference panel with current CRDT state.

        Called on tab revisit and broadcast to keep highlights in sync.
        Preserves the current search filter, accordion state, and scroll
        position across rebuilds.
        """
        # Save scroll position before clearing
        ui.run_javascript(
            "window._respondRefScroll = "
            "(document.getElementById('respond-ref-scroll') || {}).scrollTop || 0;"
        )
        reference_container.clear()
        with reference_container:
            _build_reference_panel(
                tags,
                crdt_doc,
                filter_text=search_input.value,
                accordion_state=accordion_state,
                on_locate=on_locate,
            )
        # Restore scroll position after rebuild
        ui.run_javascript(
            "setTimeout(function() {"
            "  var el = document.getElementById('respond-ref-scroll');"
            "  if (el && window._respondRefScroll)"
            "    el.scrollTop = window._respondRefScroll;"
            "}, 50);"
        )

    async def sync_markdown() -> None:
        """Sync the Milkdown editor markdown to the CRDT Text field."""
        await _sync_markdown_to_crdt(crdt_doc, workspace_key, client_id)

    return refresh_references, sync_markdown
