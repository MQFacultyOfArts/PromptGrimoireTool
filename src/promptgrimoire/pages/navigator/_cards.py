"""Workspace card rendering and inline title editing."""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING

from nicegui import ui

from promptgrimoire.db.workspaces import (
    check_clone_eligibility,
    clone_workspace_from_activity,
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

logger = logging.getLogger(__name__)


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
        new_title = title_input.value.strip() or None
        await update_workspace_title(workspace_id, new_title)
        title_input.value = new_title or fallback_title
        _update_row_title(page_state, workspace_id, new_title)
    except Exception:
        logger.exception("Failed to save workspace title for %s", workspace_id)
        ui.notify("Failed to save title", type="negative")
        title_input.value = original_title


def _wire_title_edit_handlers(
    *,
    row: NavigatorRow,
    title_input: Input,
    pencil_icon: ui.icon,
    confirm_icon: ui.icon,
    cancel_icon: ui.icon,
    page_state: PageState | None,
) -> None:
    """Wire save/cancel handlers for an inline-editable title.

    The confirm/cancel icons use ``mousedown`` so they fire *before*
    the input's ``blur`` event, preventing the blur-save from racing
    with a cancel click.
    """
    workspace_id = row.workspace_id
    if workspace_id is None:
        return
    original_title = title_input.value
    _state: dict[str, object] = {"editing": False, "saving": False}

    def _set_editing_mode(editing: bool) -> None:
        if editing:
            title_input.props(remove="readonly borderless", add="outlined")
        else:
            title_input.props(remove="outlined", add="readonly borderless")
        _state["editing"] = editing
        _state["saving"] = False
        pencil_icon.set_visibility(not editing)
        for ico in (confirm_icon, cancel_icon):
            ico.set_visibility(editing)
        if page_state is not None:
            page_state["editing_active"] = editing

    async def _activate_edit(_e: object) -> None:
        nonlocal original_title
        if _state["editing"]:
            return
        original_title = title_input.value
        _set_editing_mode(True)
        title_input.run_method("focus")
        title_input.run_method("select")

    pencil_icon.on("click", _activate_edit)

    async def _save_title(_e: object) -> None:
        if not _state["editing"] or _state["saving"]:
            return
        _state["saving"] = True
        await _persist_title_change(
            workspace_id=workspace_id,
            title_input=title_input,
            fallback_title=row.activity_title or "Untitled",
            original_title=original_title,
            page_state=page_state,
        )
        _set_editing_mode(False)

    confirm_icon.on("mousedown", _save_title)
    title_input.on("keydown.enter", _save_title)
    title_input.on("blur", _save_title)

    async def _cancel_edit(_e: object) -> None:
        if not _state["editing"]:
            return
        title_input.value = original_title
        _set_editing_mode(False)

    cancel_icon.on("mousedown", _cancel_edit)
    title_input.on("keydown.escape", _cancel_edit)
    title_input.on(
        "click",
        lambda _e: (
            ui.navigate.to(workspace_url(workspace_id))
            if not _state["editing"]
            else None
        ),
    )


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
        row=row,
        title_input=title_input,
        pencil_icon=pencil_icon,
        confirm_icon=confirm_icon,
        cancel_icon=cancel_icon,
        page_state=page_state,
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
    with (
        ui.card().classes("w-full p-3 mb-2").props("flat bordered"),
        ui.row().classes("w-full items-center gap-4"),
    ):
        with ui.column().classes("flex-grow gap-0"):
            with ui.row().classes("w-full items-center gap-2"):
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
                ).props("flat dense size=sm color=primary").classes(
                    "navigator-action-btn"
                )


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

                async def _start_activity(
                    aid: UUID = row.activity_id,
                    uid: UUID = user_id,
                ) -> None:
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
                        ui.notify(str(exc), type="negative")
                        return

                    ui.navigate.to(workspace_url(clone.id))

                aid = row.activity_id
                ui.button("Start", on_click=_start_activity).props(
                    "flat dense size=sm color=primary"
                    f' data-testid="start-activity-btn-{aid}"'
                ).classes("navigator-start-btn")
