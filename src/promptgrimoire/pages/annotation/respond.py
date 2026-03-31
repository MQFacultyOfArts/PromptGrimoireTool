"""Tab 3 (Respond) rendering for the annotation page.

Embeds a Milkdown WYSIWYG editor bound to the ``response_draft`` XmlFragment
in the shared CRDT Doc, plus a read-only reference panel showing highlights
grouped by tag.

The Milkdown editor uses the same JS bundle as the spike page
(``static/milkdown/dist/milkdown-bundle.js``) but binds to a named
XmlFragment (``response_draft``) instead of the default Doc-level binding.
Yjs updates are Doc-level, so they flow through the existing annotation
broadcast mechanism without fragment-level routing.

This module imports TagInfo -- the tag-agnostic abstraction ensures Tab 3
rendering is decoupled from any specific tag definition.

Traceability:
- Design: docs/implementation-plans/2026-02-07-three-tab-ui-98/phase_05.md Tasks 2-3
- AC: three-tab-ui.AC4.1, AC4.2, AC4.3, AC4.4, AC4.5
"""

from __future__ import annotations

import base64
import html as _html
import json
import time
from typing import TYPE_CHECKING, Any

import structlog
from nicegui import ui

from promptgrimoire.crdt.persistence import get_persistence_manager
from promptgrimoire.pages.annotation.card_shared import anonymise_display_author
from promptgrimoire.pages.annotation.word_count_badge import format_word_count_badge
from promptgrimoire.word_count import word_count

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from promptgrimoire.crdt.annotation_doc import AnnotationDocument
    from promptgrimoire.pages.annotation import PageState
    from promptgrimoire.pages.annotation.tags import TagInfo

logger = structlog.get_logger()
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


def _render_reference_card_html(
    *,
    tag_display: str,
    color: str,
    display_author: str,
    text: str,
    para_ref: str,
    comments: list[tuple[str, str]],
) -> str:
    """Render the body of a reference card as an HTML string.

    Returns an HTML fragment for use with ``ui.html(sanitize=False)``.
    All interpolated string values are escaped via ``html.escape()``
    (defence-in-depth — values originate from authenticated UI but
    we never trust interpolated content in raw HTML).

    The locate button is NOT included here — it requires a server-side
    callback for tab switching and is added as a separate NiceGUI element
    by the caller.

    Args:
        tag_display: Human-readable tag name.
        color: Hex colour for tag label.
        display_author: Pre-anonymised author display name.
        text: Highlighted text content.
        para_ref: Paragraph reference (empty string if absent).
        comments: List of (display_author, text) tuples, pre-anonymised.
    """
    esc = _html.escape
    parts: list[str] = [
        # Tag label
        f'<div style="display:flex;align-items:center;gap:4px;">'
        f'<span style="font-weight:bold;color:{esc(color)};max-width:100px;'
        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
        f"{esc(tag_display)}</span>"
        f"</div>",
        # Author
        f'<div style="font-size:0.85em;color:#666;">by {esc(display_author)}</div>',
    ]

    # Text preview with CSS overflow
    if text:
        parts.append(
            f'<div style="font-size:0.85em;white-space:pre-wrap;'
            f'max-height:4.5em;overflow:hidden;">'
            f"{esc(text)}</div>"
        )

    # Para ref (conditional)
    if para_ref:
        parts.append(
            f'<div class="text-xs font-mono text-gray-400">{esc(para_ref)}</div>'
        )

    # Comments
    for c_author, c_text in comments:
        if not c_text:
            continue
        parts.append(
            f'<div style="border-left:2px solid #e0e0e0;padding-left:8px;'
            f'margin-top:4px;">'
            f'<span style="font-size:0.75em;color:#666;font-weight:500;">'
            f"{esc(c_author)}:</span> "
            f'<span style="font-size:0.75em;color:#555;">'
            f"{esc(c_text)}</span></div>"
        )

    return "".join(parts)


def _build_reference_card_html(
    highlight: dict[str, Any],
    tag_colour: str,
    display_tag_name: str,
    state: PageState,
    on_locate: Callable[..., Any] | None = None,
) -> None:
    """Render a reference card as single ``ui.html()`` plus NiceGUI locate button.

    Replaces ``_build_reference_card()`` — collapses 8-10 NiceGUI elements
    per card into 2-3 (wrapper div + html + optional locate button).

    Args:
        highlight: Highlight data dict from CRDT.
        tag_colour: Hex colour for the left border.
        display_tag_name: Human-readable tag name.
        state: Page state for anonymisation context.
        on_locate: Optional async callback(start_char, end_char, document_id)
            to warp to the highlight in Tab 1.
    """
    raw_author = highlight.get("author", "Unknown")
    hl_user_id = highlight.get("user_id")
    start_char: int = int(highlight.get("start_char", 0))
    end_char: int = int(highlight.get("end_char", 0))
    full_text = highlight.get("text", "")
    comments_raw: list[dict[str, Any]] = highlight.get("comments", [])
    para_ref = highlight.get("para_ref", "")

    display_author = anonymise_display_author(raw_author, hl_user_id, state)

    # Pre-anonymise comment authors for the pure renderer
    comments: list[tuple[str, str]] = []
    for comment in comments_raw:
        c_text = comment.get("text", "")
        if not c_text:
            continue
        raw_c_author = comment.get("author", "")
        c_uid = comment.get("user_id")
        display_c_author = anonymise_display_author(raw_c_author, c_uid, state)
        comments.append((display_c_author, c_text))

    html_str = _render_reference_card_html(
        tag_display=display_tag_name,
        color=tag_colour,
        display_author=display_author,
        text=full_text,
        para_ref=para_ref,
        comments=comments,
    )

    with (
        ui.element("div")
        .style(
            f"border-left: 4px solid {tag_colour}; padding: 8px;"
            " margin-bottom: 4px; position: relative;"
        )
        .props('data-testid="respond-reference-card"')
    ):
        ui.html(html_str, sanitize=False)
        if on_locate is not None:
            hl_doc_id = highlight.get("document_id")

            async def _do_locate(
                sc: int = start_char,
                ec: int = end_char,
                did: str | None = hl_doc_id,
            ) -> None:
                await on_locate(sc, ec, did)

            ui.button(icon="my_location", on_click=_do_locate).props(
                'flat dense size=xs data-testid="respond-locate-btn"'
            ).tooltip("Locate in document").style(
                "position: absolute; top: 4px; right: 4px;"
            )


def _matches_filter(
    highlight: dict[str, Any],
    filter_text: str,
    state: PageState,
) -> bool:
    """Check if a highlight matches the search filter (case-insensitive).

    Author names are resolved through ``anonymise_display_author`` so that
    the filter searches against the *displayed* name (pseudonym when
    anonymous sharing is active), not the raw CRDT value.
    """
    needle = filter_text.lower()
    text = highlight.get("text", "").lower()
    # Anonymise highlight author for filtering
    raw_author = highlight.get("author", "")
    hl_user_id = highlight.get("user_id")
    display_author = anonymise_display_author(raw_author, hl_user_id, state).lower()
    if needle in text or needle in display_author:
        return True
    for comment in highlight.get("comments", []):
        if needle in comment.get("text", "").lower():
            return True
        # Anonymise comment author for filtering
        raw_c_author = comment.get("author", "")
        c_uid = comment.get("user_id")
        display_c_author = anonymise_display_author(raw_c_author, c_uid, state).lower()
        if needle in display_c_author:
            return True
    return False


def _filter_highlights(
    highlights: list[dict[str, Any]],
    active_filter: str,
    state: PageState,
    tag_name: str = "",
) -> list[dict[str, Any]]:
    """Filter highlights by text content or author, optionally matching tag name."""
    if not active_filter:
        return highlights
    return [
        hl
        for hl in highlights
        if _matches_filter(hl, active_filter, state)
        or (tag_name and active_filter.lower() in tag_name.lower())
    ]


def _tracked_expansion(
    tag_name: str,
    accordion_state: dict[str, bool] | None,
) -> ui.expansion:
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


def _build_reference_panel(
    tags: list[TagInfo],
    crdt_doc: AnnotationDocument,
    state: PageState,
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
        state: Page state for anonymisation context.
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

    active_filter = filter_text.strip() if filter_text else ""

    _t0 = time.monotonic()
    card_count = 0

    for tag_info in tags:
        filtered = _filter_highlights(
            tagged_highlights[tag_info.name], active_filter, state, tag_info.name
        )
        if not filtered:
            continue
        with _tracked_expansion(tag_info.name, accordion_state):
            for hl in filtered:
                _build_reference_card_html(
                    hl, tag_info.colour, tag_info.name, state, on_locate
                )
                card_count += 1

    untagged_filtered = _filter_highlights(untagged_highlights, active_filter, state)
    if untagged_filtered:
        with _tracked_expansion("Untagged", accordion_state):
            for hl in untagged_filtered:
                _build_reference_card_html(hl, "#999999", "Untagged", state, on_locate)
                card_count += 1

    logger.info(
        "respond_card_build",
        elapsed_ms=round((time.monotonic() - _t0) * 1000, 1),
        card_count=card_count,
    )


def _build_reference_column(
    splitter: ui.splitter,
    tags: list[TagInfo],
    crdt_doc: AnnotationDocument,
    accordion_state: dict[str, bool],
    state: PageState,
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
                tags,
                crdt_doc,
                state,
                accordion_state=accordion_state,
                on_locate=on_locate,
            )

    return reference_container, search_input


def _update_markdown_mirror(
    crdt_doc: AnnotationDocument,
    md: str | None,
    workspace_key: str,
    client_id: str,
) -> None:
    """Write markdown from event payload to CRDT response_draft_markdown.

    Missing field (old client without markdown in payload) preserves
    the existing mirror — blanking it would cause data loss for PDF
    export and pre-restart flush that read from this field.
    """
    if md is None:
        logger.debug(
            "RESPOND_YJS_NO_MARKDOWN ws=%s client=%s (old client?)",
            workspace_key,
            client_id[:8],
        )
        return
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
    state: PageState,
) -> None:
    """Register the NiceGUI event handler for Yjs updates from the Milkdown editor.

    Receives base64-encoded Yjs updates from the browser, applies them to the
    server-side CRDT Doc, broadcasts to other clients, syncs the markdown
    mirror to the CRDT Text field, and updates the word count badge.

    Args:
        crdt_doc: The CRDT annotation document.
        workspace_key: Workspace identifier for broadcast lookup.
        workspace_id: Workspace UUID for persistence.
        client_id: This client's unique ID (for echo prevention).
        on_yjs_update_broadcast: Callable(b64_update, origin_client_id) to
            broadcast Yjs updates to other clients.
        state: PageState containing word count limits and badge reference.
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
        # Write markdown from event payload to CRDT mirror (no JS round-trip).
        md: str | None = e.args.get("markdown")  # type: ignore[union-attr]  # NiceGUI GenericEventArguments.args is untyped
        _update_markdown_mirror(crdt_doc, md, workspace_key, client_id)
        # Update word count badge if limits configured
        if state.word_count_badge is not None:
            markdown = str(crdt_doc.response_draft_markdown)
            count = word_count(markdown)
            badge_state = format_word_count_badge(
                count, state.word_minimum, state.word_limit
            )
            state.word_count_badge.set_text(badge_state.text)
            state.word_count_badge.classes(replace=badge_state.css_classes)
        # Persist CRDT state to database (debounced by persistence manager)
        pm = get_persistence_manager()
        pm.mark_dirty_workspace(
            workspace_id,
            crdt_doc.doc_id,
            last_editor=client_id,
        )

    ui.on("respond_yjs_update", on_yjs_update)


def _on_markdown_flush(
    e: object,
    *,
    crdt_doc: AnnotationDocument,
    workspace_id: UUID,
    client_id: str,
) -> None:
    """Handle ``respond_markdown_flush`` event from pre-restart drain.

    Writes the browser's current markdown into the CRDT
    ``response_draft_markdown`` Text field and marks the workspace dirty
    for persistence.  Does NOT relay to peers or update word-count badges
    — this is shutdown capture only.

    Args:
        e: NiceGUI GenericEventArguments with ``args["markdown"]``.
        crdt_doc: The CRDT annotation document.
        workspace_id: Workspace UUID (str or UUID).
        client_id: Client identifier for logging.
    """
    md: str | None = e.args.get("markdown")  # type: ignore[union-attr]  # NiceGUI GenericEventArguments.args is untyped
    if md is None:
        logger.debug("RESPOND_FLUSH_NO_MARKDOWN client=%s", client_id[:8])
        return
    text_field = crdt_doc.response_draft_markdown
    current = str(text_field)
    if current != md:
        with crdt_doc.doc.transaction():
            current_len = len(text_field)
            if current_len > 0:
                del text_field[:current_len]
            if md:
                text_field += md
        pm = get_persistence_manager()
        pm.mark_dirty_workspace(
            workspace_id,
            crdt_doc.doc_id,
            last_editor=client_id,
        )
    logger.debug(
        "RESPOND_FLUSH_CAPTURE client=%s len=%d",
        client_id[:8],
        len(md),
    )


def _build_editor_init_js(
    editor_id: str,
    fragment_name: str,
    crdt_doc: AnnotationDocument,
    workspace_key: str,
    client_id: str,
) -> str:
    """Build the bundled editor init JS block (fire-and-forget).

    Computes full-state CRDT sync and seed markdown Python-side, then
    creates a self-executing async IIFE that initialises the Milkdown
    editor, applies the sync, seeds markdown if needed, and emits
    ``editor_ready`` on success or failure.
    """
    full_state = crdt_doc.get_full_state()
    b64_state = ""
    if len(full_state) > 2:
        b64_state = base64.b64encode(full_state).decode("ascii")
        logger.debug(
            "RESPOND_FULL_STATE_SYNC ws=%s to_client=%s bytes=%d",
            workspace_key,
            client_id[:8],
            len(full_state),
        )

    initial_md = crdt_doc.get_response_draft_markdown()
    seed_md = ""
    if initial_md and not str(crdt_doc.response_draft):
        logger.debug(
            "RESPOND_SEED ws=%s md_len=%d",
            workspace_key,
            len(initial_md),
        )
        seed_md = initial_md

    b64_js = f"window._applyRemoteUpdate('{b64_state}');" if b64_state else ""
    seed_js = f"window._setMilkdownMarkdown({json.dumps(seed_md)});" if seed_md else ""
    return f"""
        (async function() {{
            try {{
                const root = document.getElementById('{editor_id}');
                if (!root || !window._createMilkdownEditor) {{
                    console.error(
                        '[respond-tab] bundle not loaded'
                        + ' or #{editor_id} missing'
                    );
                    emitEvent('editor_ready', {{
                        status: 'error',
                        error: 'bundle not loaded or root missing'
                    }});
                    return;
                }}
                await window._createMilkdownEditor(
                    root, '', function(b64Update) {{
                        emitEvent('respond_yjs_update',
                                  {{update: b64Update,
                                   markdown: window._getMilkdownMarkdown()}});
                    }}, '{fragment_name}'
                );
                {b64_js}
                {seed_js}
                emitEvent('editor_ready', {{status: 'ok'}});
            }} catch (e) {{
                console.error('[respond-tab] init failed', e);
                emitEvent('editor_ready', {{
                    status: 'error', error: e.message
                }});
            }}
        }})();
        // Defined outside the IIFE — available immediately, safe when editor failed
        window._flushRespondMarkdownNow = function() {{
            var md = window._getMilkdownMarkdown();
            emitEvent('respond_markdown_flush', {{markdown: md}});
        }};
        """


def _handle_editor_ready(
    e: object,
    state: PageState,
    workspace_key: str,
    client_id: str,
) -> None:
    """Handle the ``editor_ready`` event emitted by the bundled init JS.

    Sets ``has_milkdown_editor`` on both ``PageState`` and the
    ``_RemotePresence`` entry so Yjs relay includes this client.
    On failure, logs the error and leaves the flag unset.
    """
    from promptgrimoire.pages.annotation import (  # noqa: PLC0415
        _workspace_presence,
    )

    args = e.args  # type: ignore[union-attr]  # NiceGUI GenericEventArguments
    if args.get("status") == "ok":
        state.has_milkdown_editor = True
        clients = _workspace_presence.get(workspace_key, {})
        if client_id in clients:
            clients[client_id].has_milkdown_editor = True
        # Catch-up: any Yjs updates that arrived between the initial
        # full-state snapshot (computed at JS send time) and now were
        # skipped by _broadcast_yjs_update because has_milkdown_editor
        # was False. Send a fresh full-state to converge.
        if state.crdt_doc is not None:
            full_state = state.crdt_doc.get_full_state()
            if len(full_state) > 2:
                b64_state = base64.b64encode(full_state).decode("ascii")
                presence = clients.get(client_id)
                if presence and presence.nicegui_client:
                    presence.nicegui_client.run_javascript(
                        f"window._applyRemoteUpdate('{b64_state}')"
                    )
        logger.debug(
            "EDITOR_READY ws=%s client=%s",
            workspace_key,
            client_id[:8],
        )
    else:
        logger.error(
            "editor_init_failed",
            workspace_key=workspace_key,
            client_id=client_id[:8],
            error=args.get("error", "unknown"),
        )


async def render_respond_tab(
    panel: ui.element,
    tags: list[TagInfo],
    crdt_doc: AnnotationDocument,
    workspace_key: str,
    workspace_id: UUID,
    client_id: str,
    on_yjs_update_broadcast: Any,
    on_locate: Callable[..., Any] | None = None,
    *,
    state: PageState,
) -> Callable[[], None]:
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
        state: PageState containing word count limits and badge reference,
            passed through to the Yjs event handler for live badge updates.

    Returns:
        refresh_references: Callable that refreshes the reference panel.
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
            splitter, tags, crdt_doc, accordion_state, state=state, on_locate=on_locate
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
                    state,
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
        crdt_doc,
        workspace_key,
        workspace_id,
        client_id,
        on_yjs_update_broadcast,
        state=state,
    )

    # Wait for WebSocket, then initialize the editor
    await ui.context.client.connected()

    # Fire-and-forget: bundle editor init + CRDT sync + markdown seed
    # into a single JS block. emitEvent('editor_ready') signals Python.
    ui.run_javascript(
        _build_editor_init_js(
            editor_id,
            _FRAGMENT_NAME,
            crdt_doc,
            workspace_key,
            client_id,
        )
    )

    # Readiness gating: has_milkdown_editor is set only after the
    # browser emits editor_ready, not when render_respond_tab returns.
    ui.on(
        "editor_ready",
        lambda e: _handle_editor_ready(
            e,
            state,
            workspace_key,
            client_id,
        ),
    )

    # Pre-restart drain: browser fires respond_markdown_flush with current
    # editor content so the server can persist it before shutdown.
    ui.on(
        "respond_markdown_flush",
        lambda e: _on_markdown_flush(
            e,
            crdt_doc=crdt_doc,
            workspace_id=workspace_id,
            client_id=client_id,
        ),
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
                state,
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

    return refresh_references
