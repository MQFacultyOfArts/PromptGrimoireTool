"""Workspace view and document rendering.

Contains the main workspace entry point, auth/ACL resolution,
document container rendering, and tag management callbacks.
Tab creation, change handling, and organise drag setup live in
``tab_bar.py``.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlencode
from uuid import UUID

import structlog
from nicegui import app, ui

from promptgrimoire.auth import is_privileged_user
from promptgrimoire.crdt.annotation_doc import (
    _ensure_crdt_tag_consistency,
)
from promptgrimoire.db.acl import (
    grant_permission,
)
from promptgrimoire.db.workspace_documents import list_document_headers
from promptgrimoire.db.workspaces import (
    AnnotationContext,
    PlacementContext,
    create_workspace,
    resolve_annotation_context,
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

    from promptgrimoire.pages.annotation import PermissionLevel

logger = structlog.get_logger()


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
    so the ACL gate in _load_workspace_content allows access.
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


def _update_page_title(title: str | None) -> None:
    """Update browser tab title AND visible header after deferred load."""
    if title:
        safe = json.dumps(title)  # JSON-escaped, double-quoted
        ui.run_javascript(
            f"document.title = {safe};"
            " var h = document.querySelector("
            "  '[data-testid=\"page-header-title\"]');"
            f" if (h) h.textContent = {safe};"
        )


def _show_error_ui(
    client: Client,
    container: ui.element,
    message: str,
    *,
    show_create: bool = False,
) -> None:
    """Render an error state inside *container* via ``with client:``."""
    with client:
        container.clear()
        with container:
            ui.label(message).classes("text-red-500 text-lg").props(
                'data-testid="workspace-status-msg"'
            )
            if show_create:
                ui.button(
                    "Create New Workspace",
                    on_click=_create_workspace_and_redirect,
                ).props('data-testid="create-workspace-btn"')
        # Signal completion so callers waiting on __loadComplete don't hang
        ui.run_javascript("window.__loadComplete = true")


async def _resolve_db_context(
    workspace_id: UUID,
    client: Client,
    content_container: ui.element,
) -> tuple[AnnotationContext, list[Any]] | None:
    """Resolve all DB state for annotation page load.

    Returns ``(context, documents)`` or ``None`` if loading should
    stop (unauthenticated, not found, no permission, or client
    disconnected).  Error UI is rendered before returning ``None``.
    """
    from promptgrimoire.pages.annotation import (  # noqa: PLC0415 — circular
        _workspace_registry,
    )

    auth_user = app.storage.user.get("auth_user")
    user_id_str = auth_user.get("user_id") if auth_user else None
    if not user_id_str:
        with client:
            ui.navigate.to("/login")
        return None

    assert auth_user is not None  # narrowing — guarded by user_id_str check
    context = await resolve_annotation_context(
        workspace_id,
        user_id=UUID(user_id_str),
        is_admin=bool(auth_user.get("is_admin")),
    )

    if client._deleted:
        return None

    if context is None:
        _show_error_ui(
            client, content_container, "Workspace not found", show_create=True
        )
        return None

    if context.permission is None:
        _show_error_ui(
            client, content_container, "You do not have access to this workspace"
        )
        return None

    documents = await list_document_headers(workspace_id)
    if client._deleted:
        return None

    # Hydrate CRDT with pre-fetched workspace (avoids redundant DB fetch)
    crdt_doc = await _workspace_registry.get_or_create_for_workspace(
        workspace_id,
        workspace=context.workspace,
    )
    await _ensure_crdt_tag_consistency(
        crdt_doc,
        workspace_id,
        tags=context.tags,
        tag_groups=context.tag_groups,
    )

    return None if client._deleted else (context, documents)


def _log_page_load_profile(
    workspace_id: UUID,
    t_total: float,
    t_db: float,
    t_ui: float,
    t_setup: float,
    t_header: float,
    t_panels: float,
    t_done: float,
) -> None:
    """Log per-phase timing breakdown for a page load."""

    def _ms(a: float, b: float) -> float:
        return round((b - a) * 1000, 1)

    logger.info(
        "page_load_profile",
        workspace_id=str(workspace_id),
        db_resolve_ms=_ms(t_total, t_db),
        ui_setup_ms=_ms(t_ui, t_setup),
        header_ms=_ms(t_setup, t_header),
        tab_panels_ms=_ms(t_header, t_panels),
        finish_ms=_ms(t_panels, t_done),
        total_ui_ms=_ms(t_ui, t_done),
        total_ms=_ms(t_total, t_done),
    )


async def _load_workspace_content(
    workspace_id: UUID,
    client: Client,
    content_container: ui.element,
    *,
    footer: Any | None = None,
) -> None:
    """Background task: resolve context, hydrate CRDT, then build UI.

    All DB work runs outside ``with client:`` so NiceGUI's event loop
    stays responsive.  UI construction happens inside ``with client:``
    which routes element creation to the correct browser tab.

    Called from ``annotation_page()`` via ``background_tasks.create()``.
    """
    try:
        _t_total = time.monotonic()

        result = await _resolve_db_context(workspace_id, client, content_container)
        if result is None:
            return
        _t_db = time.monotonic()

        context, documents = result
        auth_user = app.storage.user.get("auth_user")
        assert auth_user is not None

        ctx = context.placement
        privileged = is_privileged_user(auth_user)
        protect = ctx.copy_protection and not privileged
        can_create_tags = ctx.allow_tag_creation or ctx.is_template or privileged

        assert context.permission in {"viewer", "peer", "editor", "owner"}, (
            f"Unexpected permission value: {context.permission!r}"
        )

        state = PageState(
            workspace_id=workspace_id,
            user_name=_get_current_username(),
            user_id=auth_user.get("user_id"),
            effective_permission=cast("PermissionLevel", context.permission),
            is_anonymous=ctx.anonymous_sharing,
            viewer_is_privileged=privileged,
            privileged_user_ids=context.privileged_user_ids,
            word_minimum=ctx.word_minimum,
            word_limit=ctx.word_limit,
            word_limit_enforcement=ctx.word_limit_enforcement,
        )

        with client:
            _t_ui = time.monotonic()
            content_container.clear()

            on_add_tag, on_manage_tags = _create_tag_callbacks(
                state, can_create_tags, ctx, auth_user
            )

            _setup_client_sync(workspace_id, client, state)
            _t_setup = time.monotonic()
            can_manage_sharing = state.is_owner or state.viewer_is_privileged

            await render_workspace_header(
                state,
                workspace_id,
                protect=protect,
                allow_sharing=ctx.allow_sharing,
                shared_with_class=context.workspace.shared_with_class,
                can_manage_sharing=can_manage_sharing,
                user_id=_get_current_user_id(),
                document=documents[0] if documents else None,
                placement_context=ctx,
            )
            _t_header = time.monotonic()

            # Update page title now we have the workspace name
            # (skeleton used generic "Annotation Workspace").
            _update_page_title(context.workspace.title)

            first_doc_tab_name = str(documents[0].id) if documents else "Source"
            state.initialised_tabs = {first_doc_tab_name}
            state.active_tab = first_doc_tab_name

            tabs = build_tabs(documents, state)
            state.footer = footer

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
            _t_panels = time.monotonic()

            _replay_existing_cursors(str(workspace_id), state.client_id, state)

            if protect:
                inject_copy_protection()

            # Signal load complete: JS flag for E2E, marker element
            # for NiceGUI integration tests.
            ui.run_javascript("window.__loadComplete = true")
            ui.element("div").props(
                'data-testid="annotation-ready" style="display:none"'
            )

            _t_done = time.monotonic()
            _log_page_load_profile(
                workspace_id,
                _t_total,
                _t_db,
                _t_ui,
                _t_setup,
                _t_header,
                _t_panels,
                _t_done,
            )

    except Exception:
        logger.exception(
            "Failed to load workspace content",
            workspace_id=str(workspace_id),
        )
        if not client._deleted:
            with client:
                content_container.clear()
                with content_container:
                    ui.notify("Failed to load workspace", type="negative")
                ui.run_javascript("window.__loadComplete = true")
                ui.element("div").props(
                    'data-testid="annotation-ready" style="display:none"'
                )
