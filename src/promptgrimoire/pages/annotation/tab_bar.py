"""Tab bar creation, change handling, and organise drag setup.

Contains the three-tab bar builder, tab change callback factory,
SortableJS drag-and-drop wiring, and deferred tab initialisation
helpers. The main workspace entry point and document rendering
live in ``workspace.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from nicegui import events, ui

from promptgrimoire.config import get_settings
from promptgrimoire.crdt.persistence import get_persistence_manager
from promptgrimoire.db.workspace_documents import list_documents
from promptgrimoire.pages.annotation import (
    PageState,
    _workspace_presence,
    _workspace_registry,
)
from promptgrimoire.pages.annotation.broadcast import _broadcast_yjs_update
from promptgrimoire.pages.annotation.highlights import (
    _push_highlights_to_client,
    _update_highlight_css,
    _warp_to_highlight,
)
from promptgrimoire.pages.annotation.organise import render_organise_tab
from promptgrimoire.pages.annotation.respond import render_respond_tab
from promptgrimoire.pages.annotation.tags import workspace_tags_from_crdt

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

logger = logging.getLogger(__name__)


def _parse_sort_end_args(
    args: dict[str, Any],
) -> tuple[str, str, str, int]:
    """Parse SortableJS sort-end event args into highlight ID and tag keys.

    Extracts and normalizes IDs from SortableJS event args:
    - ``item``: Card HTML ID (format: ``hl-{highlight_id}``)
    - ``from``: Source container ID (format: ``sort-{raw_key}`` or
      ``sort-untagged``)
    - ``to``: Target container ID (format: ``sort-{raw_key}`` or
      ``sort-untagged``)
    - ``newIndex``: Position in target container (0-indexed)

    Returns tuple: (highlight_id, source_tag_raw_key, target_tag_raw_key,
    new_index)

    The ``hl-`` and ``sort-`` prefixes are stripped. The special key
    ``sort-untagged`` is mapped to an empty string (CRDT convention).

    Args:
        args: Event args dict from SortableJS sort-end event.

    Returns:
        Tuple of (highlight_id, source_tag, target_tag, new_index).
        Empty strings or -1 indicate missing/invalid values.
    """
    item_id: str = args.get("item", "")
    from_id: str = args.get("from", "")
    to_id: str = args.get("to", "")
    new_index: int = args.get("newIndex", -1)

    # Parse IDs: "hl-{highlight_id}" and "sort-{raw_key}"
    highlight_id = item_id.removeprefix("hl-")
    source_tag = from_id.removeprefix("sort-")
    target_tag = to_id.removeprefix("sort-")

    # "sort-untagged" -> empty string (CRDT convention)
    if source_tag == "untagged":
        source_tag = ""
    if target_tag == "untagged":
        target_tag = ""

    return highlight_id, source_tag, target_tag, new_index


def _apply_sort_reorder_or_move(
    state: PageState,
    highlight_id: str,
    source_tag: str,
    target_tag: str,
    new_index: int,
) -> None:
    """Apply a sort-end reorder or cross-column move to the CRDT.

    Same-column events update tags Map highlights in place. Cross-column events
    reassign the highlight's tag. In both cases, the Sortable element's
    internal handler syncs the Python element tree with the DOM --- callers
    must NOT rebuild the organise panel mid-event.

    Args:
        state: Page state with crdt_doc.
        highlight_id: The dragged highlight ID.
        source_tag: Raw tag key of the source column.
        target_tag: Raw tag key of the target column.
        new_index: Position in the target column (0-indexed).
    """
    assert state.crdt_doc is not None
    if source_tag == target_tag:
        current_order = state.crdt_doc.get_tag_highlights(target_tag)
        if highlight_id in current_order:
            current_order.remove(highlight_id)
        current_order.insert(new_index, highlight_id)
        # Write highlights back to tags Map
        tag_data = state.crdt_doc.get_tag(target_tag)
        if tag_data is not None:
            state.crdt_doc.set_tag(
                tag_id=target_tag,
                name=tag_data["name"],
                colour=tag_data["colour"],
                order_index=tag_data["order_index"],
                group_id=tag_data.get("group_id"),
                description=tag_data.get("description"),
                highlights=current_order,
                origin_client_id=state.client_id,
            )
        ui.notify("Reordered", type="info")
    else:
        state.crdt_doc.move_highlight_to_tag(
            highlight_id,
            from_tag=source_tag,
            to_tag=target_tag,
            position=new_index,
            origin_client_id=state.client_id,
        )
        # Resolve display name from tag_info_list (raw key is a UUID)
        target_name = next(
            (ti.name for ti in (state.tag_info_list or []) if ti.raw_key == target_tag),
            "Untagged",
        )
        ui.notify(
            f"Moved to {target_name}",
            type="positive",
            position="bottom",
        )
        # SortableJS already synced the DOM; calling refresh here would
        # destroy elements mid-event (RuntimeError in NiceGUI's slot system).


_SCROLL_SAVE_JS = (
    "(function() {"
    "  var el = document.querySelector('[data-testid=\"organise-columns\"]');"
    "  return el ? {x: el.scrollLeft, y: el.scrollTop} : null;"
    "})()"
)


async def _rebuild_organise_with_scroll(
    render_fn: Callable[[], None],
) -> None:
    """Rebuild the organise tab preserving horizontal/vertical scroll.

    Captures scroll position via awaited JS, re-renders, then restores
    via requestAnimationFrame to ensure the DOM has settled.
    """
    scroll = await ui.run_javascript(_SCROLL_SAVE_JS)
    render_fn()
    if scroll:
        x, y = scroll.get("x", 0), scroll.get("y", 0)
        ui.run_javascript(
            "requestAnimationFrame(function() {"
            "  var el = document.querySelector("
            "'[data-testid=\"organise-columns\"]');"
            f"  if (el) {{ el.scrollLeft = {x}; el.scrollTop = {y}; }}"
            "});"
        )


def _setup_organise_drag(state: PageState) -> None:
    """Set up SortableJS sort-end handler and Organise tab refresh.

    Wires the on_sort_end callback to CRDT operations and stores a
    refresh_organise callable on state for broadcast-triggered re-renders.

    Must be called after state is created but before _on_tab_change is
    defined, since the tab change handler calls state.refresh_organise.
    """

    async def _on_organise_sort_end(e: events.GenericEventArguments) -> None:
        """Handle a SortableJS sort-end event from Tab 2."""
        if state.crdt_doc is None:
            return

        highlight_id, source_tag, target_tag, new_index = _parse_sort_end_args(e.args)
        if not highlight_id:
            logger.warning("Sort-end event with no item ID: %s", e.args)
            return

        _apply_sort_reorder_or_move(
            state, highlight_id, source_tag, target_tag, new_index
        )

        # Persist to database
        pm = get_persistence_manager()
        pm.mark_dirty_workspace(
            state.workspace_id,
            state.crdt_doc.doc_id,
            last_editor=state.user_name,
        )
        await pm.force_persist_workspace(state.workspace_id)

        # Broadcast to other clients for CRDT sync.
        if state.broadcast_update:
            await state.broadcast_update()

        # Cross-column card label/colour updates on next full rebuild
        # (tab switch or broadcast). The CRDT is already correct.

    async def _on_locate(start_char: int, end_char: int) -> None:
        """Warp to a highlight in Tab 1 from Tab 2 or Tab 3."""
        await _warp_to_highlight(state, start_char, end_char)

    def _render_organise_now() -> None:
        """Re-render the Organise tab with current CRDT state."""
        if not (state.organise_panel and state.crdt_doc):
            return
        if state.tag_info_list is None:
            return  # Tags not loaded yet -- skip render
        render_organise_tab(
            state.organise_panel,
            state.tag_info_list,
            state.crdt_doc,
            on_sort_end=(_on_organise_sort_end if state.can_annotate else None),
            on_locate=_on_locate,
            state=state,
        )

    state.refresh_organise = _render_organise_now
    # Sync lambda returning a coroutine (Python has no async lambda).
    state.refresh_organise_with_scroll = lambda: _rebuild_organise_with_scroll(
        _render_organise_now
    )


async def _initialise_respond_tab(state: PageState, workspace_id: UUID) -> None:
    """Initialise the Respond tab with Milkdown editor and reference panel.

    Called once on first visit to the Respond tab (deferred rendering).
    Sets up the editor, CRDT relay, and marks the client for Yjs broadcast.
    """
    if not (state.respond_panel and state.crdt_doc):
        return

    tags = state.tag_info_list or []

    def _on_broadcast(b64_update: str, origin_client_id: str) -> None:
        _broadcast_yjs_update(workspace_id, origin_client_id, b64_update)

    async def _on_respond_locate(start_char: int, end_char: int) -> None:
        await _warp_to_highlight(state, start_char, end_char)

    (
        state.refresh_respond_references,
        state.sync_respond_markdown,
    ) = await render_respond_tab(
        panel=state.respond_panel,
        tags=tags,
        crdt_doc=state.crdt_doc,
        workspace_key=str(workspace_id),
        workspace_id=workspace_id,
        client_id=state.client_id,
        on_yjs_update_broadcast=_on_broadcast,
        on_locate=_on_respond_locate,
        state=state,
    )
    state.has_milkdown_editor = True
    # Mark this client as having a Milkdown editor for Yjs relay
    ws_key = str(workspace_id)
    clients = _workspace_presence.get(ws_key, {})
    if state.client_id in clients:
        clients[state.client_id].has_milkdown_editor = True


async def _sync_respond_on_leave(state: PageState) -> None:
    """Sync Milkdown markdown to CRDT when leaving the Respond tab.

    Failure is logged but does not propagate -- blocking tab switches
    would break the Annotate tab refresh.
    """
    if state.sync_respond_markdown:
        try:
            await state.sync_respond_markdown()
        except Exception:
            logger.debug(
                "RESPOND_MD_SYNC failed on tab leave, continuing",
                exc_info=True,
            )


def _handle_annotate_tab(state: PageState) -> None:
    """Handle switching to the Annotate tab (refresh highlights)."""
    _push_highlights_to_client(state)
    if state.refresh_annotations:
        state.refresh_annotations()
    _update_highlight_css(state)


def _handle_organise_tab(state: PageState) -> None:
    """Handle switching to the Organise tab (re-render)."""
    assert state.initialised_tabs is not None
    state.initialised_tabs.add("Organise")
    if state.refresh_organise:
        state.refresh_organise()


async def _handle_respond_tab(state: PageState, workspace_id: UUID) -> None:
    """Handle switching to the Respond tab (deferred init or refresh)."""
    assert state.initialised_tabs is not None
    if "Respond" not in state.initialised_tabs:
        state.initialised_tabs.add("Respond")
        await _initialise_respond_tab(state, workspace_id)
    elif state.refresh_respond_references:
        state.refresh_respond_references()


def _make_tab_change_handler(
    state: PageState,
    workspace_id: UUID,
) -> Any:
    """Create the tab-change callback for the three-tab workspace UI.

    Returns an async handler suitable for ``ui.tab_panels(on_change=...)``.
    """

    async def _on_tab_change(e: events.ValueChangeEventArguments) -> None:
        """Handle tab switching with deferred rendering and refresh."""
        assert state.initialised_tabs is not None
        tab_name = str(e.value)
        prev_tab = state.active_tab
        state.active_tab = tab_name

        # Tag toolbar footer is only relevant on the Annotate tab
        if state.footer is not None:
            state.footer.set_visibility(tab_name == "Annotate")

        if prev_tab == "Respond":
            await _sync_respond_on_leave(state)

        if tab_name == "Organise" and state.organise_panel and state.crdt_doc:
            _handle_organise_tab(state)
            return

        if tab_name == "Annotate":
            _handle_annotate_tab(state)
            return

        if tab_name == "Respond":
            await _handle_respond_tab(state, workspace_id)
            return

        if tab_name not in state.initialised_tabs:
            state.initialised_tabs.add(tab_name)

    return _on_tab_change


async def _build_tab_panels(
    state: PageState,
    workspace_id: UUID,
    tabs: ui.tabs,
    on_tab_change: Any,
    *,
    on_add_tag: Any,
    on_manage_tags: Any,
    can_create_tags: bool,
    footer: Any | None = None,
) -> None:
    """Build the three tab panels and store panel refs on ``state``.

    Populates Annotate (with CRDT load + document render), Organise, and
    Respond panels.  Stores ``state.tab_panels``, ``state.organise_panel``,
    and ``state.respond_panel`` for later use by broadcast callbacks.
    """
    # Late import to break circular dependency: workspace.py imports from
    # tab_bar.py (this module), so tab_bar.py cannot import from workspace.py
    # at module level.
    from promptgrimoire.pages.annotation.workspace import (
        _render_content_form_outside_refreshable,
        _render_document_container,
        _render_empty_template_toolbar,
    )

    with ui.tab_panels(tabs, value="Annotate", on_change=on_tab_change).classes(
        "w-full"
    ) as panels:
        state.tab_panels = panels

        with ui.tab_panel("Annotate"):
            # Load CRDT document for this workspace
            logger.debug("[RENDER] loading CRDT doc")
            crdt_doc = await _workspace_registry.get_or_create_for_workspace(
                workspace_id
            )
            state.crdt_doc = crdt_doc
            state.tag_info_list = workspace_tags_from_crdt(crdt_doc)
            logger.debug("[RENDER] CRDT doc loaded, tag_info_list populated")

            # WARNING -- @ui.refreshable destroys the entire subtree and
            # recreates it on .refresh().  The document renderer is complex:
            # JavaScript init (selection handlers, scroll sync, highlight CSS
            # injection), CRDT state connections, and char span rendering.
            # The NiceGUI 3.7.x regression was caused by a destroy+recreate
            # cycle that wiped char spans -- @ui.refreshable does exactly this.
            #
            # If after refresh you see char spans disappearing, JS init
            # failing, CRDT connections dropping, or selection handlers
            # broken -- look here first.  Fallback: remove @ui.refreshable,
            # hold a reference to a container div, call container.clear()
            # then _render_document_with_highlights() into it.
            # Side-channel from document_container() to
            # _render_content_form_outside_refreshable(): populated once
            # after the first await document_container() call so the content
            # form can branch on has_documents[0] without a second DB query.
            has_documents: list[bool] = []

            @ui.refreshable
            async def document_container() -> None:
                """Load documents and render the first one, or show empty state.

                Wrapped in ``@ui.refreshable`` so that adding a document via
                upload or paste can re-render in-place without a full page
                reload (file-upload-109.AC4.1).
                """
                # The footer lives outside the refreshable boundary (it's a
                # page-level Quasar element), so @ui.refreshable won't clear
                # it automatically.  Clear it here to prevent duplicate tag
                # toolbars on refresh.
                if footer is not None:
                    footer.clear()

                documents = await list_documents(workspace_id)
                has_documents.clear()
                has_documents.append(bool(documents))
                logger.debug("[RENDER] documents loaded: count=%d", len(documents))

                if documents:
                    await _render_document_container(
                        state,
                        documents[0],
                        crdt_doc,
                        on_add_tag=on_add_tag if can_create_tags else None,
                        on_manage_tags=on_manage_tags,
                        footer=footer,
                    )
                elif state.can_upload:
                    _render_empty_template_toolbar(
                        state,
                        on_add_tag=on_add_tag if can_create_tags else None,
                        on_manage_tags=on_manage_tags,
                        can_create_tags=can_create_tags,
                        footer=footer,
                    )
                else:
                    # Read-only empty state for viewers/peers
                    ui.label("This workspace has no documents yet.").classes(
                        "text-gray-500 italic mt-4"
                    )

            await document_container()

            # Expose document refresh on PageState so the Manage Documents
            # dialog can re-render documents after edit-mode save.
            state.refresh_documents = document_container.refresh

            # Late-bound callback: content_form.py captures this closure,
            # and we swap in a smarter implementation after the wrapper
            # element is created (so we can hide it on first add).
            _document_added_impl: list[Callable[[], object]] = [
                document_container.refresh
            ]

            def _on_document_added() -> object:
                return _document_added_impl[0]()

            # Content form lives OUTSIDE the refreshable boundary so it
            # is not destroyed when document_container.refresh() is called.
            content_form_wrapper = _render_content_form_outside_refreshable(
                state,
                workspace_id,
                has_documents=has_documents,
                on_document_added=_on_document_added,
            )

            # When multi-document is disabled, hide the content form after
            # the first document is added.  The wrapper persists because
            # it's outside the refreshable; we hide it via the callback.
            if (
                content_form_wrapper is not None
                and not get_settings().features.enable_multi_document
            ):

                def _hide_and_refresh() -> object:
                    content_form_wrapper.set_visibility(False)
                    return document_container.refresh()

                _document_added_impl[0] = _hide_and_refresh

        with ui.tab_panel("Organise") as organise_panel:
            state.organise_panel = organise_panel
            ui.label("Organise tab content will appear here.").classes("text-gray-400")

        with ui.tab_panel("Respond") as respond_panel:
            state.respond_panel = respond_panel
            ui.label("Respond tab content will appear here.").classes("text-gray-400")

    logger.debug("[RENDER] tab panels built, workspace=%s", workspace_id)


def build_tabs() -> ui.tabs:
    """Create the three-tab bar for the annotation workspace."""
    with ui.row().classes("w-full items-center"), ui.tabs().classes("w-full") as tabs:
        ui.tab("Annotate").props('data-testid="tab-annotate"')
        ui.tab("Organise").props('data-testid="tab-organise"')
        ui.tab("Respond").props('data-testid="tab-respond"')
    return tabs
