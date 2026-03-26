"""Workspace view and document rendering.

Contains the main workspace entry point, auth/ACL resolution,
document container rendering, and tag management callbacks.
Tab creation, change handling, and organise drag setup live in
``tab_bar.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlencode
from uuid import UUID

import structlog
from nicegui import app, ui

from promptgrimoire.auth import check_workspace_access, is_privileged_user
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
)
from promptgrimoire.pages.annotation.broadcast import (
    _replay_existing_cursors,
    _setup_client_sync,
)
from promptgrimoire.pages.annotation.css import _build_tag_toolbar
from promptgrimoire.pages.annotation.header import (
    inject_copy_protection,
    render_workspace_header,
)
from promptgrimoire.pages.annotation.highlights import (
    _add_highlight,
)
from promptgrimoire.pages.annotation.tab_bar import (
    _build_tab_panels,
    _make_tab_change_handler,
    _setup_organise_drag,
    build_tabs,
)
from promptgrimoire.pages.annotation.tag_management import open_tag_management
from promptgrimoire.pages.annotation.tag_quick_create import open_quick_create

if TYPE_CHECKING:
    from nicegui import Client

    from promptgrimoire.db.models import Workspace
    from promptgrimoire.pages.annotation import PermissionLevel

logger = structlog.get_logger()
logging.getLogger(__name__).setLevel(logging.INFO)


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


async def _resolve_workspace_context(
    workspace_id: UUID,
    workspace: Workspace | None = None,
) -> tuple[PageState, PlacementContext, bool, bool, bool] | None:
    """Resolve workspace, ACL, placement context, and build PageState.

    Returns (state, ctx, protect, can_create_tags, shared_with_class)
    or None if the request was handled (redirect/error) and rendering
    should stop.

    Pass a pre-fetched ``workspace`` to avoid a redundant DB round-trip.
    """
    if workspace is None:
        workspace = await get_workspace(workspace_id)
    if workspace is None:
        ui.label("Workspace not found").classes("text-red-500").props(
            'data-testid="workspace-status-msg"'
        )
        ui.button(
            "Create New Workspace", on_click=_create_workspace_and_redirect
        ).props('data-testid="create-workspace-btn"')
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
        word_minimum=ctx.word_minimum,
        word_limit=ctx.word_limit,
        word_limit_enforcement=ctx.word_limit_enforcement,
    )
    # NOTE: tag_info_list is populated later in _build_tab_panels after
    # crdt_doc is loaded (state.crdt_doc is None at this point).

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
            logger.debug(
                "_rebuild_toolbar: clearing container id=%s with %d children",
                state.toolbar_container.id,
                len(state.toolbar_container.default_slot.children),
            )
            state.toolbar_container.clear()

            async def _tag_click(key: str) -> None:
                await _add_highlight(state, key)

            _build_tag_toolbar(
                state.tag_info_list or [],
                _tag_click,
                on_add_click=(on_add_tag if can_create_tags else None),
                on_manage_click=on_manage_tags,
                footer=state.toolbar_container,
            )

    state.refresh_toolbar = _rebuild_toolbar

    async def on_add_tag() -> None:
        await open_quick_create(state)
        await _rebuild_toolbar()

    async def on_manage_tags() -> None:
        await open_tag_management(state, ctx, auth_user)
        await _rebuild_toolbar()

    return on_add_tag, on_manage_tags


async def _render_workspace_view(
    workspace_id: UUID,
    client: Client,
    workspace: Workspace | None = None,
    *,
    footer: Any | None = None,
) -> None:
    """Render the workspace content view with documents or add content form."""
    result = await _resolve_workspace_context(workspace_id, workspace)
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

    # Pre-load documents so the header can show the paragraph toggle
    documents = await list_documents(workspace_id)
    first_doc = documents[0] if documents else None

    await render_workspace_header(
        state,
        workspace_id,
        protect=protect,
        allow_sharing=ctx.allow_sharing,
        shared_with_class=shared_with_class,
        can_manage_sharing=can_manage_sharing,
        user_id=_get_current_user_id(),
        document=first_doc,
    )

    # Pre-load the Milkdown JS bundle so it's available when Tab 3 (Respond)
    # is first visited. Must be added during page construction -- dynamically
    # injected <script> tags via ui.add_body_html after page load don't execute.
    ui.add_body_html('<script src="/milkdown/milkdown-bundle.js"></script>')

    # Three-tab container (Phase 1: three-tab UI)
    # When documents exist, the first source tab replaces the old "Annotate" tab.
    first_doc_tab_name = str(documents[0].id) if documents else "Source"
    state.initialised_tabs = {first_doc_tab_name}
    state.active_tab = first_doc_tab_name

    tabs = build_tabs(documents, state)

    # Store footer on state so the tab change handler can toggle visibility
    state.footer = footer

    # Set up Tab 2 drag-and-drop and tab change handler
    _setup_organise_drag(state)
    on_tab_change = _make_tab_change_handler(
        state,
        workspace_id,
        on_add_tag=on_add_tag,
        on_manage_tags=on_manage_tags,
        can_create_tags=can_create_tags,
        footer=footer,
    )

    await _build_tab_panels(
        state,
        workspace_id,
        tabs,
        on_tab_change,
        documents,
        on_add_tag=on_add_tag,
        on_manage_tags=on_manage_tags,
        can_create_tags=can_create_tags,
        footer=footer,
    )

    # Replay existing cursors now that doc_container_id is set.
    # Must happen after _build_tab_panels (which renders the document
    # and sets state.doc_container_id to "doc-container-{uuid}").
    #
    # There is a narrow window between _setup_client_sync (which
    # registers us in _workspace_presence) and this call.  Incoming
    # broadcasts during that window go through _handle_remote_update,
    # which does not use doc_container_id for cursor rendering, so
    # the gap is benign.
    _replay_existing_cursors(str(workspace_id), state.client_id, state)

    # Inject copy protection JS after tab container is built (Phase 4)
    if protect:
        inject_copy_protection()
