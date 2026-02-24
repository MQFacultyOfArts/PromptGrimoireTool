"""Sharing controls and per-user sharing dialog for workspaces."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from nicegui import ui

if TYPE_CHECKING:
    from uuid import UUID

from promptgrimoire.db.acl import (
    grant_share,
    list_entries_for_workspace,
    revoke_permission,
)
from promptgrimoire.db.users import get_user_by_email, get_user_by_id
from promptgrimoire.db.workspaces import update_workspace_sharing

logger = logging.getLogger(__name__)


def render_sharing_controls(
    *,
    workspace_id: UUID,
    allow_sharing: bool,
    shared_with_class: bool,
    can_manage_sharing: bool,
    viewer_is_privileged: bool,
    grantor_id: UUID | None,
) -> None:
    """Render sharing toggle and share button in the workspace header.

    Args:
        workspace_id: Workspace UUID.
        allow_sharing: Whether the placement context allows sharing.
        shared_with_class: Current workspace shared_with_class state.
        can_manage_sharing: Whether the user can toggle sharing.
        viewer_is_privileged: Whether the viewer is an instructor/admin.
        grantor_id: The local User UUID for the current session, or None.
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
            if grantor_id is None:
                return  # Unreachable: can_manage_sharing requires auth
            await open_sharing_dialog(
                workspace_id=workspace_id,
                grantor_id=grantor_id,
                sharing_allowed=allow_sharing,
                grantor_is_staff=viewer_is_privileged,
            )

        ui.button(
            "Share",
            icon="share",
            on_click=_open_share_dialog,
        ).props('flat dense data-testid="share-button"')


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


async def open_sharing_dialog(
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
            ui.input(
                label="Recipient email",
                validation={"Required": bool},
            )
            .without_auto_validation()
            .classes("w-full")
            .props('data-testid="share-email-input"')
        )
        email_input.on("blur", email_input.validate)
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
