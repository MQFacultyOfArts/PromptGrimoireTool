"""Workspace view, tab initialisation, and organise drag setup.

Contains the main workspace rendering logic, organise drag setup, and
respond tab init. The placement dialog lives in ``placement.py``;
sharing controls live in ``sharing.py``; header rendering and copy
protection live in ``header.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlencode
from uuid import UUID

from nicegui import app, events, ui

from promptgrimoire.auth import check_workspace_access, is_privileged_user
from promptgrimoire.crdt.persistence import get_persistence_manager
from promptgrimoire.db.acl import (
    get_privileged_user_ids_for_workspace,
    grant_permission,
)
from promptgrimoire.db.workspace_documents import list_documents
from promptgrimoire.db.workspaces import (
    PlacementContext,
    create_workspace,
    get_placement_context,
    get_workspace,
)
from promptgrimoire.pages.annotation import (
    PageState,
    _workspace_presence,
    _workspace_registry,
)
from promptgrimoire.pages.annotation.broadcast import (
    _broadcast_yjs_update,
    _setup_client_sync,
)
from promptgrimoire.pages.annotation.content_form import _render_add_content_form
from promptgrimoire.pages.annotation.css import _build_tag_toolbar
from promptgrimoire.pages.annotation.document import (
    _render_document_with_highlights,
)
from promptgrimoire.pages.annotation.header import (
    inject_copy_protection,
    render_workspace_header,
)
from promptgrimoire.pages.annotation.highlights import (
    _add_highlight,
    _push_highlights_to_client,
    _update_highlight_css,
    _warp_to_highlight,
)
from promptgrimoire.pages.annotation.organise import render_organise_tab
from promptgrimoire.pages.annotation.respond import render_respond_tab
from promptgrimoire.pages.annotation.tag_management import open_tag_management
from promptgrimoire.pages.annotation.tag_quick_create import open_quick_create
from promptgrimoire.pages.annotation.tags import workspace_tags

if TYPE_CHECKING:
    from nicegui import Client

    from promptgrimoire.pages.annotation import PermissionLevel

logger = logging.getLogger(__name__)


def _get_current_username() -> str:
    """Get the display name for the current user."""
    auth_user = app.storage.user.get("auth_user")
    if auth_user:
        if auth_user.get("name"):
            return auth_user["name"]
        if auth_user.get("display_name"):
            return auth_user["display_name"]
        if auth_user.get("email"):
            return auth_user["email"].split("@")[0].replace(".", " ").title()
    return "Anonymous"


async def _create_workspace_and_redirect() -> None:
    """Create a new workspace and redirect to it.

    Requires authenticated user. Grants the creator "owner" permission
    so the ACL gate in _render_workspace_view allows access.
    """
    auth_user = app.storage.user.get("auth_user")
    if not auth_user:
        ui.notify("Please log in to create a workspace", type="warning")
        ui.navigate.to("/login")
        return

    user_id = auth_user.get("user_id")
    if not user_id:
        ui.notify("Session error — please log in again", type="warning")
        ui.navigate.to("/login")
        return

    try:
        workspace = await create_workspace()
        await grant_permission(workspace.id, UUID(user_id), "owner")
        logger.info("Created workspace %s for user %s", workspace.id, user_id)
        ui.navigate.to(f"/annotation?{urlencode({'workspace_id': str(workspace.id)})}")
    except Exception:
        logger.exception("Failed to create workspace")
        ui.notify("Failed to create workspace", type="negative")


def _get_current_user_id() -> UUID | None:
    """Get the local User UUID from session storage, if authenticated."""
    auth_user = app.storage.user.get("auth_user")
    if auth_user and auth_user.get("user_id"):
        return UUID(auth_user["user_id"])
    return None


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


def _setup_organise_drag(state: PageState) -> None:
    """Set up SortableJS sort-end handler and Organise tab refresh.

    Wires the on_sort_end callback to CRDT operations and stores a
    refresh_organise callable on state for broadcast-triggered re-renders.

    Must be called after state is created but before _on_tab_change is
    defined, since the tab change handler calls state.refresh_organise.
    """

    async def _on_organise_sort_end(e: events.GenericEventArguments) -> None:
        """Handle a SortableJS sort-end event from Tab 2.

        Parses source/target tag from Sortable container HTML IDs
        (``sort-{raw_key}``) and highlight_id from card HTML ID
        (``hl-{highlight_id}``). Same-column reorders within the tag;
        cross-column moves reassign the highlight's tag. Both mutate
        CRDT and broadcast.
        """
        if state.crdt_doc is None:
            return

        highlight_id, source_tag, target_tag, new_index = _parse_sort_end_args(e.args)

        if not highlight_id:
            logger.warning("Sort-end event with no item ID: %s", e.args)
            return

        if source_tag == target_tag:
            # Same-column reorder: SortableJS gives us the exact newIndex.
            current_order = state.crdt_doc.get_tag_order(target_tag)
            if highlight_id in current_order:
                current_order.remove(highlight_id)
            current_order.insert(new_index, highlight_id)
            state.crdt_doc.set_tag_order(
                target_tag, current_order, origin_client_id=state.client_id
            )
            ui.notify("Reordered", type="info", position="bottom")
        else:
            # Cross-column move: reassign tag and update orders
            state.crdt_doc.move_highlight_to_tag(
                highlight_id,
                from_tag=source_tag,
                to_tag=target_tag,
                position=new_index,
                origin_client_id=state.client_id,
            )
            ui.notify(
                f"Moved to {target_tag or 'Untagged'}",
                type="positive",
                position="bottom",
            )
            # Re-render to update card tag labels and colours
            _render_organise_now()

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

    async def _on_locate(start_char: int, end_char: int) -> None:
        """Warp to a highlight in Tab 1 from Tab 2 or Tab 3."""
        await _warp_to_highlight(state, start_char, end_char)

    def _render_organise_now() -> None:
        """Re-render the Organise tab with current CRDT state."""
        if not (state.organise_panel and state.crdt_doc):
            return
        if state.tag_info_list is None:
            return  # Tags not loaded yet — skip render
        render_organise_tab(
            state.organise_panel,
            state.tag_info_list,
            state.crdt_doc,
            on_sort_end=(_on_organise_sort_end if state.can_annotate else None),
            on_locate=_on_locate,
            state=state,
        )

    state.refresh_organise = _render_organise_now


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
    )
    state.has_milkdown_editor = True
    # Mark this client as having a Milkdown editor for Yjs relay
    ws_key = str(workspace_id)
    clients = _workspace_presence.get(ws_key, {})
    if state.client_id in clients:
        clients[state.client_id].has_milkdown_editor = True


async def _resolve_workspace_context(
    workspace_id: UUID,
) -> tuple[PageState, PlacementContext, bool, bool, bool] | None:
    """Resolve workspace, ACL, placement context, and build PageState.

    Returns (state, ctx, protect, can_create_tags, shared_with_class)
    or None if the request was handled (redirect/error) and rendering
    should stop.
    """
    workspace = await get_workspace(workspace_id)
    if workspace is None:
        ui.label("Workspace not found").classes("text-red-500")
        ui.button("Create New Workspace", on_click=_create_workspace_and_redirect)
        return None

    auth_user = app.storage.user.get("auth_user")
    permission = await check_workspace_access(workspace_id, auth_user)

    if auth_user is None:
        ui.navigate.to("/login")
        return None

    if permission is None:
        ui.label("You do not have access to this workspace").classes(
            "text-red-500 text-lg"
        )
        return None

    ctx = await get_placement_context(workspace_id)
    privileged = is_privileged_user(auth_user)
    protect = ctx.copy_protection and not privileged
    can_create_tags = ctx.allow_tag_creation or ctx.is_template or privileged

    assert permission in {"viewer", "peer", "editor", "owner"}, (
        f"Unexpected permission value: {permission!r}"
    )
    priv_ids = await get_privileged_user_ids_for_workspace(workspace_id)
    state = PageState(
        workspace_id=workspace_id,
        user_name=_get_current_username(),
        user_id=auth_user.get("user_id"),
        effective_permission=cast("PermissionLevel", permission),
        is_anonymous=ctx.anonymous_sharing,
        viewer_is_privileged=privileged,
        privileged_user_ids=priv_ids,
    )
    state.tag_info_list = await workspace_tags(workspace_id)

    return state, ctx, protect, can_create_tags, workspace.shared_with_class


def _create_tag_callbacks(
    state: PageState,
    can_create_tags: bool,
    ctx: PlacementContext,
    auth_user: dict[str, Any],
) -> tuple[Any, Any]:
    """Create tag management closures for the workspace toolbar.

    Returns (on_add_tag, on_manage_tags) callables.  The closures
    capture ``state`` and the tag creation permission flag.
    """

    async def _rebuild_toolbar() -> None:
        """Clear and rebuild the tag toolbar after tag mutations."""
        if state.toolbar_container is not None:
            state.toolbar_container.clear()
            with state.toolbar_container:

                async def _tag_click(key: str) -> None:
                    await _add_highlight(state, key)

                _build_tag_toolbar(
                    state.tag_info_list or [],
                    _tag_click,
                    on_add_click=(on_add_tag if can_create_tags else None),
                    on_manage_click=on_manage_tags,
                )

    async def on_add_tag() -> None:
        await open_quick_create(state)
        await _rebuild_toolbar()

    async def on_manage_tags() -> None:
        await open_tag_management(state, ctx, auth_user)
        await _rebuild_toolbar()

    return on_add_tag, on_manage_tags


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

        # Sync markdown to CRDT when leaving the Respond tab.
        # Failure must not block tab switch — Annotate refresh would break.
        if prev_tab == "Respond" and state.sync_respond_markdown:
            try:
                await state.sync_respond_markdown()
            except Exception:
                logger.debug(
                    "RESPOND_MD_SYNC failed on tab leave, continuing",
                    exc_info=True,
                )

        # Always re-render Organise tab to show current highlights
        if tab_name == "Organise" and state.organise_panel and state.crdt_doc:
            state.initialised_tabs.add(tab_name)
            if state.refresh_organise:
                state.refresh_organise()
            return

        # Rebuild text node map and re-apply highlights. The text walker
        # does not modify the DOM so this is safe on every tab switch.
        if tab_name == "Annotate":
            _push_highlights_to_client(state)
            if state.refresh_annotations:
                state.refresh_annotations()
            _update_highlight_css(state)
            return

        if tab_name == "Respond":
            if tab_name not in state.initialised_tabs:
                state.initialised_tabs.add(tab_name)
                await _initialise_respond_tab(state, workspace_id)
            elif state.refresh_respond_references:
                state.refresh_respond_references()
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
) -> None:
    """Build the three tab panels and store panel refs on ``state``.

    Populates Annotate (with CRDT load + document render), Organise, and
    Respond panels.  Stores ``state.tab_panels``, ``state.organise_panel``,
    and ``state.respond_panel`` for later use by broadcast callbacks.
    """
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
            logger.debug("[RENDER] CRDT doc loaded")

            # Load existing documents
            documents = await list_documents(workspace_id)
            logger.debug("[RENDER] documents loaded: count=%d", len(documents))

            if documents:
                # Render first document with highlight support
                doc = documents[0]
                logger.debug("[RENDER] rendering document with highlights")
                await _render_document_with_highlights(
                    state,
                    doc,
                    crdt_doc,
                    on_add_click=(on_add_tag if can_create_tags else None),
                    on_manage_click=on_manage_tags,
                )
                logger.debug("[RENDER] document rendered")

                # "Add Document" button for editors/owners with
                # existing documents
                if state.can_upload:
                    with ui.expansion(
                        "Add Document",
                        icon="note_add",
                    ).classes("w-full mt-4"):
                        _render_add_content_form(workspace_id)
            elif state.can_upload:
                # Show add content form for editors/owners
                logger.debug("[RENDER] no documents, showing add content form")
                _render_add_content_form(workspace_id)
            else:
                # Read-only empty state for viewers/peers
                ui.label("This workspace has no documents yet.").classes(
                    "text-gray-500 italic mt-4"
                )

        with ui.tab_panel("Organise") as organise_panel:
            state.organise_panel = organise_panel
            ui.label("Organise tab content will appear here.").classes("text-gray-400")

        with ui.tab_panel("Respond") as respond_panel:
            state.respond_panel = respond_panel
            ui.label("Respond tab content will appear here.").classes("text-gray-400")

    logger.debug("[RENDER] tab panels built, workspace=%s", workspace_id)


async def _render_workspace_view(workspace_id: UUID, client: Client) -> None:
    """Render the workspace content view with documents or add content form."""
    result = await _resolve_workspace_context(workspace_id)
    if result is None:
        return
    state, ctx, protect, can_create_tags, shared_with_class = result
    # auth_user is guaranteed non-None: _resolve_workspace_context
    # redirects to /login when unauthenticated.
    auth_user = app.storage.user.get("auth_user")
    assert auth_user is not None

    on_add_tag, on_manage_tags = _create_tag_callbacks(
        state, can_create_tags, ctx, auth_user
    )

    _setup_client_sync(workspace_id, client, state)
    can_manage_sharing = state.is_owner or state.viewer_is_privileged

    ui.label(f"Workspace: {workspace_id}").classes("text-gray-600 text-sm")
    await render_workspace_header(
        state,
        workspace_id,
        protect=protect,
        allow_sharing=ctx.allow_sharing,
        shared_with_class=shared_with_class,
        can_manage_sharing=can_manage_sharing,
        user_id=_get_current_user_id(),
    )

    # Pre-load the Milkdown JS bundle so it's available when Tab 3 (Respond)
    # is first visited. Must be added during page construction -- dynamically
    # injected <script> tags via ui.add_body_html after page load don't execute.
    ui.add_body_html('<script src="/milkdown/milkdown-bundle.js"></script>')

    # Three-tab container (Phase 1: three-tab UI)
    state.initialised_tabs = {"Annotate"}

    with ui.tabs().classes("w-full") as tabs:
        ui.tab("Annotate")
        ui.tab("Organise")
        ui.tab("Respond")

    # Set up Tab 2 drag-and-drop and tab change handler
    _setup_organise_drag(state)
    on_tab_change = _make_tab_change_handler(state, workspace_id)

    await _build_tab_panels(
        state,
        workspace_id,
        tabs,
        on_tab_change,
        on_add_tag=on_add_tag,
        on_manage_tags=on_manage_tags,
        can_create_tags=can_create_tags,
    )

    # Inject copy protection JS after tab container is built (Phase 4)
    if protect:
        inject_copy_protection()
