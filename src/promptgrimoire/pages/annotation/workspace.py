"""Workspace view, header, copy protection, and tab initialisation.

Contains the main workspace rendering logic, copy protection injection,
organise drag setup, and respond tab init. The placement dialog lives
in ``placement.py``.
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
    grant_permission,
    grant_share,
    list_entries_for_workspace,
    revoke_permission,
)
from promptgrimoire.db.users import get_user_by_email, get_user_by_id
from promptgrimoire.db.workspace_documents import list_documents
from promptgrimoire.db.workspaces import (
    PlacementContext,
    create_workspace,
    get_placement_context,
    get_workspace,
    update_workspace_sharing,
)
from promptgrimoire.pages.annotation import (
    PageState,
    _workspace_presence,
    _workspace_registry,
)
from promptgrimoire.pages.annotation.broadcast import (
    _broadcast_yjs_update,
    _setup_client_sync,
    _update_user_count,
)
from promptgrimoire.pages.annotation.content_form import _render_add_content_form
from promptgrimoire.pages.annotation.document import (
    _render_document_with_highlights,
)
from promptgrimoire.pages.annotation.highlights import (
    _push_highlights_to_client,
    _update_highlight_css,
    _warp_to_highlight,
)
from promptgrimoire.pages.annotation.organise import render_organise_tab
from promptgrimoire.pages.annotation.pdf_export import _handle_pdf_export
from promptgrimoire.pages.annotation.placement import show_placement_dialog
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
        if auth_user.get("display_name"):
            return auth_user["display_name"]
        if auth_user.get("email"):
            return auth_user["email"].split("@")[0]
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


def _get_placement_chip_style(ctx: PlacementContext) -> tuple[str, str, str]:
    """Return (label, color, icon) for a placement context chip."""
    if ctx.is_template and ctx.placement_type == "activity":
        return f"Template: {ctx.display_label}", "purple", "lock"
    if ctx.placement_type == "activity":
        return ctx.display_label, "blue", "assignment"
    if ctx.placement_type == "course":
        return ctx.display_label, "green", "folder"
    return "Unplaced", "grey", "help_outline"


def _get_current_user_id() -> UUID | None:
    """Get the local User UUID from session storage, if authenticated."""
    auth_user = app.storage.user.get("auth_user")
    if auth_user and auth_user.get("user_id"):
        return UUID(auth_user["user_id"])
    return None


def _render_sharing_controls(
    *,
    workspace_id: UUID,
    allow_sharing: bool,
    shared_with_class: bool,
    can_manage_sharing: bool,
    viewer_is_privileged: bool,
) -> None:
    """Render sharing toggle and share button in the workspace header.

    Extracted from _render_workspace_header to keep statement count manageable.

    Args:
        workspace_id: Workspace UUID.
        allow_sharing: Whether the placement context allows sharing.
        shared_with_class: Current workspace shared_with_class state.
        can_manage_sharing: Whether the user can toggle sharing.
        viewer_is_privileged: Whether the viewer is an instructor/admin.
    """
    # "Share with class" toggle -- only when activity allows sharing
    if allow_sharing and can_manage_sharing:

        async def _handle_share_toggle(value: bool) -> None:
            try:
                await update_workspace_sharing(workspace_id, shared_with_class=value)
                ui.notify(
                    "Shared with class" if value else "Unshared from class",
                    type="positive",
                )
            except Exception:
                logger.exception("Failed to update sharing for %s", workspace_id)
                ui.notify("Failed to update sharing", type="negative")

        ui.switch(
            "Share with class",
            value=shared_with_class,
            on_change=lambda e: _handle_share_toggle(e.value),
        ).props('data-testid="share-with-class-toggle"')

    # "Share with user" button -- visible to owner or privileged
    if can_manage_sharing:

        async def _open_share_dialog() -> None:
            await _open_sharing_dialog(
                workspace_id=workspace_id,
                grantor_id=_get_current_user_id(),  # type: ignore[arg-type]  # auth_user non-None (guarded at view entry), user_id always set
                sharing_allowed=allow_sharing,
                grantor_is_staff=viewer_is_privileged,
            )

        ui.button(
            "Share",
            icon="share",
            on_click=_open_share_dialog,
        ).props('flat dense data-testid="share-button"')


async def _render_workspace_header(
    state: PageState,
    workspace_id: UUID,
    protect: bool = False,
    *,
    allow_sharing: bool = False,
    shared_with_class: bool = False,
    can_manage_sharing: bool = False,
) -> None:
    """Render the header row with save status, user count, and export button.

    Extracted from _render_workspace_view to keep statement count manageable.

    Args:
        state: Page state to populate with header element references.
        workspace_id: Workspace UUID for export.
        protect: Whether copy protection is active for this workspace.
        allow_sharing: Whether the placement context allows sharing.
        shared_with_class: Current workspace shared_with_class state.
        can_manage_sharing: Whether the user can toggle sharing (owner or privileged).
    """
    logger.debug("[HEADER] START workspace=%s", workspace_id)
    with ui.row().classes("gap-4 items-center"):
        # Save status indicator (for E2E test observability)
        state.save_status = (
            ui.label("")
            .classes("text-sm text-gray-500")
            .props('data-testid="save-status"')
        )

        # User count badge
        state.user_count_badge = (
            ui.label("1 user")
            .classes("text-sm text-blue-600 bg-blue-100 px-2 py-0.5 rounded")
            .props('data-testid="user-count"')
        )
        # Update with actual count now that badge exists
        _update_user_count(state)

        # Export PDF button with loading state
        export_btn = ui.button(
            "Export PDF",
            icon="picture_as_pdf",
        ).props("color=primary")

        async def on_export_click() -> None:
            export_btn.disable()
            export_btn.props("loading")
            try:
                await _handle_pdf_export(state, workspace_id)
            finally:
                export_btn.props(remove="loading")
                export_btn.enable()

        export_btn.on_click(on_export_click)
        logger.debug("[HEADER] buttons done, calling placement_chip")

        # Placement status chip (refreshable)
        @ui.refreshable
        async def placement_chip() -> None:
            logger.debug("[HEADER] placement_chip: querying placement")
            ctx = await get_placement_context(workspace_id)
            logger.debug("[HEADER] placement_chip: got ctx, rendering chip")
            label, color, icon = _get_placement_chip_style(ctx)
            is_authenticated = _get_current_user_id() is not None

            async def open_dialog() -> None:
                await show_placement_dialog(
                    workspace_id,
                    ctx,
                    placement_chip.refresh,
                    user_id=_get_current_user_id(),
                )

            # Template workspaces have locked placement
            clickable = is_authenticated and not ctx.is_template
            props_str = 'data-testid="placement-chip" outline'
            if not clickable:
                props_str += " disable"
            chip = ui.chip(
                text=label,
                icon=icon,
                color=color,
                on_click=open_dialog if clickable else None,
            ).props(props_str)
            if ctx.is_template:
                chip.tooltip("Template placement is managed by the Activity")
            elif not is_authenticated:
                chip.tooltip("Log in to change placement")
            logger.debug("[HEADER] placement_chip: done")

        await placement_chip()
        logger.debug("[HEADER] placement_chip awaited")

        # Copy protection lock icon chip (Phase 4)
        if protect:
            ui.chip(
                "Protected",
                icon="lock",
                color="amber-7",
                text_color="white",
            ).props(
                'dense aria-label="Copy protection is enabled for this activity"'
            ).tooltip("Copy protection is enabled for this activity")

        # Sharing controls (Phase 5)
        _render_sharing_controls(
            workspace_id=workspace_id,
            allow_sharing=allow_sharing,
            shared_with_class=shared_with_class,
            can_manage_sharing=can_manage_sharing,
            viewer_is_privileged=state.viewer_is_privileged,
        )


def _is_plausible_email(email: str) -> bool:
    """Quick structural check for email format before DB lookup.

    Not a full RFC 5322 validator -- just catches obvious typos so
    the sharing dialog can show an immediate warning instead of a
    round-trip to the database.
    """
    parts = email.split("@")
    if len(parts) != 2 or not parts[0]:
        return False
    domain = parts[1]
    return "." in domain and not domain.startswith(".") and not domain.endswith(".")


async def _open_sharing_dialog(
    workspace_id: UUID,
    grantor_id: UUID,
    sharing_allowed: bool,
    grantor_is_staff: bool,
) -> None:
    """Open a dialog for sharing a workspace with a specific user by email.

    Provides email input, permission level selection, current shares list
    with revoke buttons, and clear error handling for all failure modes.

    Args:
        workspace_id: The workspace to share.
        grantor_id: The user granting the share.
        sharing_allowed: Whether sharing is enabled for this context.
        grantor_is_staff: Whether the grantor is an instructor/admin.
    """
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("Share Workspace").classes("text-lg font-bold mb-2")

        email_input = (
            ui.input(label="Recipient email", validation={"Required": bool})
            .classes("w-full")
            .props('data-testid="share-email-input"')
        )
        perm_select = (
            ui.select(
                options={"viewer": "Viewer", "editor": "Editor"},
                value="viewer",
                label="Permission",
            )
            .classes("w-full")
            .props('data-testid="share-permission-select"')
        )

        # Current shares list (refreshable)
        @ui.refreshable
        async def shares_list() -> None:
            entries = await list_entries_for_workspace(workspace_id)
            # Filter out the owner entry -- owners cannot be revoked via this UI
            share_entries = [e for e in entries if e.permission != "owner"]
            if not share_entries:
                ui.label("No shares yet.").classes("text-gray-400 text-sm")
                return
            ui.separator()
            ui.label("Current shares").classes("text-sm font-bold")
            for entry in share_entries:
                user = await get_user_by_id(entry.user_id)
                display = user.email if user else str(entry.user_id)
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(f"{display} ({entry.permission})").classes("text-sm")

                    async def _revoke(
                        uid: UUID = entry.user_id,
                    ) -> None:
                        await revoke_permission(workspace_id, uid)
                        ui.notify("Share revoked", type="positive")
                        shares_list.refresh()

                    ui.button(
                        icon="close",
                        on_click=_revoke,
                    ).props("flat dense round color=negative size=sm")

        await shares_list()

        async def _on_share() -> None:
            email = (email_input.value or "").strip()
            if not email:
                ui.notify("Please enter an email address", type="warning")
                return
            if not _is_plausible_email(email):
                ui.notify("Please enter a valid email address", type="warning")
                return

            recipient = await get_user_by_email(email)
            if recipient is None:
                ui.notify("User not found", type="negative")
                return

            try:
                await grant_share(
                    workspace_id,
                    grantor_id,
                    recipient.id,
                    str(perm_select.value),
                    sharing_allowed=sharing_allowed,
                    grantor_is_staff=grantor_is_staff,
                )
                ui.notify(f"Shared with {email}", type="positive")
                email_input.value = ""
                shares_list.refresh()
            except PermissionError as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end gap-2 mt-4"):
            ui.button(
                "Share",
                on_click=_on_share,
            ).props('color=primary data-testid="share-confirm-button"')
            ui.button("Close", on_click=dialog.close).props("flat")

    dialog.open()


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


# -- Copy protection JS injection (Phase 4) ----------------------------------

_COPY_PROTECTION_PRINT_CSS = """
@media print {
  .q-tab-panels { display: none !important; }
  .copy-protection-print-message { display: block !important; }
}
.copy-protection-print-message { display: none; }
""".strip()

_COPY_PROTECTION_PRINT_MESSAGE = (
    '<div class="copy-protection-print-message" '
    'style="display:none; padding: 2rem; text-align: center; font-size: 1.5rem;">'
    "Printing is disabled for this activity.</div>"
)


def _inject_copy_protection() -> None:
    """Inject client-side JS and CSS to block copy/cut/paste/drag/print.

    Called once during page construction when ``protect=True``. Uses event
    delegation from protected selectors so Milkdown copy (student's own
    writing) is unaffected. Paste is blocked on the Milkdown editor in
    capture phase before ProseMirror sees the event. Ctrl+P/Cmd+P is
    intercepted via keydown handler. CSS ``@media print`` hides tab panels
    and shows a "Printing is disabled" message instead.
    """
    _selectors = '#doc-container, [data-testid="respond-reference-panel"]'
    ui.run_javascript(f"setupCopyProtection({_selectors!r})")
    ui.add_css(_COPY_PROTECTION_PRINT_CSS)
    ui.html(_COPY_PROTECTION_PRINT_MESSAGE, sanitize=False)


async def _render_workspace_view(workspace_id: UUID, client: Client) -> None:  # noqa: PLR0915  # TODO(2026-02): refactor after Phase 7 -- extract tab setup into helpers
    """Render the workspace content view with documents or add content form."""
    logger.debug("[RENDER] START workspace=%s", workspace_id)

    # Check workspace exists before ACL (nonexistent → "not found",
    # not "access denied")
    workspace = await get_workspace(workspace_id)
    logger.debug("[RENDER] get_workspace done: found=%s", workspace is not None)
    if workspace is None:
        ui.label("Workspace not found").classes("text-red-500")
        ui.button("Create New Workspace", on_click=_create_workspace_and_redirect)
        return

    # --- ACL enforcement guard ---
    auth_user = app.storage.user.get("auth_user")
    permission = await check_workspace_access(workspace_id, auth_user)
    logger.debug("[RENDER] check_workspace_access done: permission=%s", permission)

    if auth_user is None:
        ui.navigate.to("/login")
        return

    if permission is None:
        ui.notify("You do not have access to this workspace", type="negative")
        ui.navigate.to("/courses")
        return

    # Compute copy protection flag (Phase 3 -- consumed by Phase 4 JS injection)
    ctx = await get_placement_context(workspace_id)
    privileged = is_privileged_user(auth_user)
    protect = ctx.copy_protection and not privileged
    # Template editors can always create tags (they're setting up the activity).
    # Privileged users (admin/instructor) can always create tags.
    # Students follow the resolved allow_tag_creation setting.
    can_create_tags = ctx.allow_tag_creation or ctx.is_template or privileged
    logger.debug(
        "[RENDER] placement done: protect=%s can_create=%s", protect, can_create_tags
    )

    # Create page state with permission capabilities
    # permission is guaranteed non-None here (guarded above) and always one of
    # the Permission.name values ("viewer", "peer", "editor", "owner").
    assert permission in {
        "viewer",
        "peer",
        "editor",
        "owner",
    }, f"Unexpected permission value: {permission!r}"
    state = PageState(
        workspace_id=workspace_id,
        user_name=_get_current_username(),
        user_id=auth_user.get("user_id"),
        effective_permission=cast("PermissionLevel", permission),
        is_anonymous=ctx.anonymous_sharing,
        viewer_is_privileged=privileged,
    )
    state.tag_info_list = await workspace_tags(workspace_id)

    # Tag management callbacks (Phase 5)
    async def _rebuild_toolbar() -> None:
        """Clear and rebuild the tag toolbar after tag mutations."""
        if state.toolbar_container is not None:
            state.toolbar_container.clear()
            with state.toolbar_container:
                from promptgrimoire.pages.annotation.css import (  # noqa: PLC0415
                    _build_tag_toolbar,
                )
                from promptgrimoire.pages.annotation.highlights import (  # noqa: PLC0415
                    _add_highlight,
                )

                async def _tag_click(key: str) -> None:
                    await _add_highlight(state, key)

                _build_tag_toolbar(
                    state.tag_info_list or [],
                    _tag_click,
                    on_add_click=(_on_add_tag if can_create_tags else None),
                    on_manage_click=_on_manage_tags,
                )

    async def _on_add_tag() -> None:
        await open_quick_create(state)
        await _rebuild_toolbar()

    async def _on_manage_tags() -> None:
        await open_tag_management(state, ctx, auth_user)
        await _rebuild_toolbar()

    # Set up client synchronization
    _setup_client_sync(workspace_id, client, state)
    logger.debug("[RENDER] client sync setup done")

    # Sharing visibility: owner or privileged (instructor/admin) can toggle
    can_manage_sharing = state.is_owner or state.viewer_is_privileged

    ui.label(f"Workspace: {workspace_id}").classes("text-gray-600 text-sm")
    logger.debug("[RENDER] calling _render_workspace_header")
    await _render_workspace_header(
        state,
        workspace_id,
        protect=protect,
        allow_sharing=ctx.allow_sharing,
        shared_with_class=workspace.shared_with_class,
        can_manage_sharing=can_manage_sharing,
    )
    logger.debug("[RENDER] header done")

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

    # Set up Tab 2 drag-and-drop and tab change handler (Phase 4)
    _setup_organise_drag(state)
    logger.debug("[RENDER] tabs and organise drag setup done")

    async def _on_tab_change(e: events.ValueChangeEventArguments) -> None:
        """Handle tab switching with deferred rendering and refresh."""
        assert state.initialised_tabs is not None
        tab_name = str(e.value)
        prev_tab = state.active_tab
        state.active_tab = tab_name

        # Sync markdown to CRDT when leaving the Respond tab (Phase 7).
        # Wrapped in try/except: sync failure must not block tab switch,
        # otherwise the Annotate refresh never runs and cards disappear.
        if prev_tab == "Respond" and state.sync_respond_markdown:
            try:
                await state.sync_respond_markdown()
            except Exception:
                logger.debug(
                    "RESPOND_MD_SYNC failed on tab leave, continuing",
                    exc_info=True,
                )

        if tab_name == "Organise" and state.organise_panel and state.crdt_doc:
            # Always re-render Organise tab to show current highlights
            state.initialised_tabs.add(tab_name)
            if state.refresh_organise:
                state.refresh_organise()
            return

        if tab_name == "Annotate":
            # Rebuild text node map and re-apply highlights. The text walker
            # does not modify the DOM (unlike char span injection) so this
            # is safe to call on every tab switch.
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

    with ui.tab_panels(tabs, value="Annotate", on_change=_on_tab_change).classes(
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
                    on_add_click=(_on_add_tag if can_create_tags else None),
                    on_manage_click=_on_manage_tags,
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

    # Inject copy protection JS after tab container is built (Phase 4)
    if protect:
        _inject_copy_protection()
