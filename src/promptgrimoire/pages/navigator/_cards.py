"""Workspace card rendering and inline title editing."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import structlog
from nicegui import ui

from promptgrimoire.db.exceptions import OwnershipError
from promptgrimoire.db.workspaces import (
    check_clone_eligibility,
    clone_workspace_from_activity,
    delete_workspace,
    get_user_workspace_for_activity,
    update_workspace_title,
)
from promptgrimoire.pages.navigator._helpers import (
    ACTION_LABELS,
    breadcrumb,
    format_updated_at,
    workspace_url,
)

if TYPE_CHECKING:
    from uuid import UUID

    from nicegui.elements.input import Input

    from promptgrimoire.db.navigator import NavigatorRow
    from promptgrimoire.pages.navigator._helpers import PageState

logger = structlog.get_logger()


def _update_row_title(
    page_state: PageState | None,
    workspace_id: UUID,
    new_title: str | None,
) -> None:
    """Replace the frozen NavigatorRow in page_state with an updated title."""
    if page_state is None:
        return
    rows = page_state["rows"]
    for i, r in enumerate(rows):
        if r.workspace_id == workspace_id:
            rows[i] = dataclasses.replace(r, title=new_title)
            return


async def _persist_title_change(
    *,
    workspace_id: UUID,
    title_input: Input,
    fallback_title: str,
    original_title: str,
    page_state: PageState | None,
) -> None:
    """Save a workspace title change to DB and sync in-memory state."""
    try:
        # NiceGUI 3.11+ types Input.value as `str | None`; normalise before
        # stripping so a cleared input does not raise AttributeError into the
        # except block below (which would silently discard the user's edit).
        new_title = (title_input.value or "").strip() or None
        await update_workspace_title(workspace_id, new_title)
        title_input.value = new_title or fallback_title
        _update_row_title(page_state, workspace_id, new_title)
    except Exception:
        logger.exception("Failed to save workspace title for %s", workspace_id)
        ui.notify("Failed to save title", type="negative")
        title_input.value = original_title


@dataclasses.dataclass
class _TitleEditIcons:
    """Pencil/confirm/cancel icon trio for one inline title editor."""

    pencil: ui.icon
    confirm: ui.icon
    cancel: ui.icon


class _TitleEditController:
    """Owns editing state and event handlers for one inline title editor.

    Replaces a set of closures that shared mutable state through a dict;
    each event handler is a plain method instead, so complexity is
    attributed per-method rather than accumulating in one function that
    nests four closures.
    """

    def __init__(
        self,
        *,
        workspace_id: UUID,
        title_input: Input,
        icons: _TitleEditIcons,
        fallback_title: str,
        page_state: PageState | None,
    ) -> None:
        self.workspace_id = workspace_id
        self.title_input = title_input
        self.icons = icons
        self.fallback_title = fallback_title
        self.page_state = page_state
        self.original_title = title_input.value
        self.editing = False
        self.saving = False

    def _set_editing_mode(self, editing: bool) -> None:
        if editing:
            self.title_input.props(remove="readonly borderless", add="outlined")
        else:
            self.title_input.props(remove="outlined", add="readonly borderless")
        self.editing = editing
        self.saving = False
        self.icons.pencil.set_visibility(not editing)
        for ico in (self.icons.confirm, self.icons.cancel):
            ico.set_visibility(editing)
        if self.page_state is not None:
            self.page_state["editing_active"] = editing

    async def activate_edit(self, _e: object) -> None:
        if self.editing:
            return
        self.original_title = self.title_input.value
        self._set_editing_mode(True)
        self.title_input.run_method("focus")
        self.title_input.run_method("select")

    async def save_title(self, _e: object) -> None:
        if not self.editing or self.saving:
            return
        self.saving = True
        await _persist_title_change(
            workspace_id=self.workspace_id,
            title_input=self.title_input,
            fallback_title=self.fallback_title,
            original_title=self.original_title,
            page_state=self.page_state,
        )
        self._set_editing_mode(False)

    async def cancel_edit(self, _e: object) -> None:
        if not self.editing:
            return
        self.title_input.value = self.original_title
        self._set_editing_mode(False)

    def handle_title_click(self, _e: object) -> None:
        if not self.editing:
            ui.navigate.to(workspace_url(self.workspace_id))


def _wire_title_edit_handlers(
    *,
    workspace_id: UUID,
    title_input: Input,
    icons: _TitleEditIcons,
    fallback_title: str,
    page_state: PageState | None,
) -> None:
    """Wire save/cancel handlers for an inline-editable title.

    The confirm/cancel icons use ``mousedown`` so they fire *before*
    the input's ``blur`` event, preventing the blur-save from racing
    with a cancel click.
    """
    controller = _TitleEditController(
        workspace_id=workspace_id,
        title_input=title_input,
        icons=icons,
        fallback_title=fallback_title,
        page_state=page_state,
    )
    icons.pencil.on("click", controller.activate_edit)
    icons.confirm.on("mousedown", controller.save_title)
    title_input.on("keydown.enter", controller.save_title)
    title_input.on("blur", controller.save_title)
    icons.cancel.on("mousedown", controller.cancel_edit)
    title_input.on("keydown.escape", controller.cancel_edit)
    title_input.on("click", controller.handle_title_click)


def render_inline_title_edit(
    row: NavigatorRow,
    page_state: PageState | None = None,
) -> None:
    """Render an inline-editable title input with pencil/check/cancel icons."""
    workspace_id = row.workspace_id
    if workspace_id is None:
        return

    display_title = row.title or row.activity_title or "Untitled"

    title_input = (
        ui.input(value=display_title)
        .classes("text-base font-medium text-primary navigator-title-input")
        .props(f'readonly borderless dense data-workspace-id="{workspace_id}"')
    )

    pencil_icon = (
        ui.icon("edit", size="xs")
        .classes(
            "cursor-pointer text-gray-400 hover:text-primary navigator-edit-title-btn"
        )
        .props(f'data-testid="edit-title-{workspace_id}"')
    )

    confirm_icon = (
        ui.icon("check_circle", size="xs")
        .classes("cursor-pointer text-green-600 hover:text-green-800")
        .props(f'data-testid="confirm-title-{workspace_id}"')
    )
    confirm_icon.set_visibility(False)

    cancel_icon = (
        ui.icon("cancel", size="xs")
        .classes("cursor-pointer text-red-500 hover:text-red-700")
        .props(f'data-testid="cancel-title-{workspace_id}"')
    )
    cancel_icon.set_visibility(False)

    _wire_title_edit_handlers(
        workspace_id=workspace_id,
        title_input=title_input,
        icons=_TitleEditIcons(
            pencil=pencil_icon, confirm=confirm_icon, cancel=cancel_icon
        ),
        fallback_title=row.activity_title or "Untitled",
        page_state=page_state,
    )


async def _delete_workspace_from_navigator(
    workspace_id: UUID,
    card: ui.card,  # noqa: ARG001 — kept for future ui.refreshable migration
    user_id: UUID,
) -> None:
    """Show confirmation dialog and delete workspace, then reload the page.

    # TODO: Replace page reload with ui.refreshable on the navigator
    # sections so deletion updates in-place without a full reload.
    """
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("Delete this workspace?").classes("text-lg font-bold")
        ui.label("This cannot be undone.").classes("text-gray-500")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props(
                'flat data-testid="cancel-delete-workspace-btn"'
            )

            async def confirm() -> None:
                try:
                    await delete_workspace(workspace_id, user_id=user_id)
                except OwnershipError:
                    logger.warning("permission_denied", operation="delete_workspace")
                    ui.notify("Permission denied", type="negative")
                    dialog.close()
                    return
                dialog.close()
                ui.notify("Workspace deleted", type="positive")
                ui.navigate.to("/")

            ui.button("Delete", on_click=confirm).props(
                'color=negative data-testid="confirm-delete-workspace-btn"'
            )
    dialog.open()


def _render_workspace_title(
    row: NavigatorRow,
    page_state: PageState | None,
) -> None:
    """Render workspace title as inline-editable (owner) or link (others)."""
    title = row.title or row.activity_title or "Untitled"
    if row.workspace_id is not None and row.permission == "owner":
        render_inline_title_edit(row, page_state=page_state)
    elif row.workspace_id is not None:
        ui.link(
            title,
            workspace_url(row.workspace_id),
        ).classes(
            "text-base font-medium text-primary "
            "no-underline hover:underline "
            "cursor-pointer"
        ).props(f'data-workspace-id="{row.workspace_id}"')
    else:
        ui.label(title).classes("text-base font-medium")


def _render_workspace_left_column(
    row: NavigatorRow,
    *,
    show_owner: bool,
    owner_label: str,
    snippets: dict[UUID, str] | None,
    page_state: PageState | None,
) -> None:
    """Render the left column: title, breadcrumb, owner, snippet."""
    with ui.column().classes("flex-grow gap-0"):
        with ui.row().classes("w-full items-center gap-2"):
            _render_workspace_title(row, page_state)

        crumb = breadcrumb(row)
        if crumb:
            ui.label(crumb).classes("text-xs text-gray-500")

        if show_owner and owner_label:
            ui.label(f"by {owner_label}").classes("text-xs text-gray-400")

        # sanitize=False is safe: ts_headline only inserts
        # <mark>/<\/mark> tags from _HEADLINE_OPTIONS; source text
        # is either HTML-stripped (documents) or plain (search_text).
        snippet_html = (
            (snippets or {}).get(row.workspace_id)
            if row.workspace_id is not None
            else None
        )
        if snippet_html is not None:
            ui.html(snippet_html, sanitize=False).classes("navigator-snippet")


def _render_workspace_right_column(
    row: NavigatorRow,
    card: ui.card,
    page_state: PageState | None,
) -> None:
    """Render the right column: date, action button, delete button."""
    with ui.column().classes("items-end gap-1"):
        date_str = format_updated_at(row)
        if date_str:
            ui.label(date_str).classes("text-xs text-gray-400")

        if row.workspace_id is not None:
            action = ACTION_LABELS.get(row.permission, "Open")
            url = workspace_url(row.workspace_id)
            ui.button(
                action,
                on_click=lambda u=url: ui.navigate.to(u),
            ).props(
                "flat dense size=sm color=primary"
                f' data-testid="open-workspace-btn-{row.workspace_id}"'
            ).classes("navigator-action-btn")

            if row.permission == "owner" and page_state is not None:
                user_id = page_state["user_id"]
                ui.button(
                    icon="delete",
                    on_click=lambda wid=row.workspace_id, c=card, uid=user_id: (
                        _delete_workspace_from_navigator(wid, c, uid)
                    ),
                ).props(
                    f"flat round dense size=sm color=negative"
                    f' data-testid="delete-workspace-card-btn-{row.workspace_id}"'
                )


def render_workspace_entry(
    row: NavigatorRow,
    *,
    show_owner: bool = False,
    owner_label: str = "",
    snippets: dict[UUID, str] | None = None,
    page_state: PageState | None = None,
) -> None:
    """Render a single workspace entry as a card row."""
    card = ui.card().classes("w-full p-3 mb-2").props("flat bordered")
    with card, ui.row().classes("w-full items-center gap-4"):
        _render_workspace_left_column(
            row,
            show_owner=show_owner,
            owner_label=owner_label,
            snippets=snippets,
            page_state=page_state,
        )
        _render_workspace_right_column(row, card, page_state)


async def _start_activity(aid: UUID, uid: UUID) -> None:
    """Clone an activity workspace or navigate to existing one."""
    existing = await get_user_workspace_for_activity(aid, uid)
    if existing is not None:
        ui.navigate.to(workspace_url(existing.id))
        return

    error = await check_clone_eligibility(aid, uid)
    if error is not None:
        ui.notify(error, type="negative")
        return

    try:
        clone, _doc_map = await clone_workspace_from_activity(aid, uid)
    except ValueError as exc:
        logger.warning("clone_workspace_failed", operation="clone_workspace")
        ui.notify(str(exc), type="negative")
        return

    ui.navigate.to(workspace_url(clone.id))


def render_unstarted_entry(
    row: NavigatorRow,
    user_id: UUID,
) -> None:
    """Render an unstarted activity entry with a Start button."""
    with (
        ui.card().classes("w-full p-3 mb-2").props("flat bordered"),
        ui.row().classes("w-full items-center gap-4"),
    ):
        with ui.column().classes("flex-grow gap-0"):
            title = row.activity_title or "Untitled Activity"
            ui.label(title).classes("text-base font-medium")

            crumb = breadcrumb(row)
            if crumb:
                ui.label(crumb).classes("text-xs text-gray-500")

        with ui.column().classes("items-end gap-1"):
            if row.activity_id is not None:
                aid = row.activity_id
                uid = user_id
                ui.button(
                    "Start",
                    on_click=lambda a=aid, u=uid: _start_activity(a, u),
                ).props(
                    "flat dense size=sm color=primary"
                    f' data-testid="start-activity-btn-{aid}"'
                ).classes("navigator-start-btn")
