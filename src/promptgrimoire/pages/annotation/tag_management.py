"""Tag management dialogs for creating and organising annotation tags.

Provides quick-create and full management dialogs for the annotation
page toolbar. All DB and sibling-module imports are lazy (inside
functions) to avoid circular dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from nicegui import ui

if TYPE_CHECKING:
    from promptgrimoire.db.workspaces import PlacementContext
    from promptgrimoire.pages.annotation import PageState

_PRESET_PALETTE: list[str] = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
]

_SWATCH_BASE = "w-8 h-8 min-w-0 p-0 rounded-full"
_SWATCH_SELECTED = f"{_SWATCH_BASE} ring-2 ring-offset-1 ring-black"


async def _refresh_tag_state(state: PageState) -> None:
    """Reload tags from DB and rebuild highlight CSS.

    Lazily imports sibling modules to avoid circular dependencies.
    """
    from promptgrimoire.pages.annotation.highlights import (  # noqa: PLC0415
        _update_highlight_css,
    )
    from promptgrimoire.pages.annotation.tags import (  # noqa: PLC0415
        workspace_tags,
    )

    state.tag_info_list = await workspace_tags(state.workspace_id)
    _update_highlight_css(state)


def _build_colour_picker(
    selected_color: list[str],
) -> tuple[list[ui.button], ui.color_input]:
    """Build preset swatch row and custom colour input.

    Returns the list of swatch buttons (for visual update) and
    the ``ui.color_input`` element.
    """
    ui.label("Colour").classes("text-sm text-gray-600 mt-2")

    swatch_buttons: list[ui.button] = []

    def _select_swatch(color: str) -> None:
        selected_color[0] = color
        color_el.value = color
        for btn in swatch_buttons:
            bg = btn._style.get("background-color", "")
            is_active = bg == color
            btn.classes(
                replace=_SWATCH_SELECTED if is_active else _SWATCH_BASE,
            )

    with ui.row().classes("gap-1 flex-wrap"):
        for i, preset in enumerate(_PRESET_PALETTE):
            btn = ui.button(
                "",
                on_click=lambda _e, c=preset: _select_swatch(c),
            )
            btn.style(f"background-color: {preset}")
            cls = _SWATCH_SELECTED if i == 0 else _SWATCH_BASE
            btn.classes(cls)
            swatch_buttons.append(btn)

    def _on_custom_color(e: object) -> None:
        val = getattr(e, "value", None)
        if val:
            selected_color[0] = val
            for btn in swatch_buttons:
                btn.classes(replace=_SWATCH_BASE)

    color_el = ui.color_input(
        label="Custom",
        value=selected_color[0],
        preview=True,
        on_change=_on_custom_color,
    )

    return swatch_buttons, color_el


async def open_quick_create(state: PageState) -> None:
    """Open a dialog for creating a new tag and optionally highlight.

    The dialog provides a name field, preset colour swatches with a
    custom colour picker, and an optional group dropdown. On save,
    the tag is created via ``db.tags.create_tag()`` and optionally
    applied as a highlight if text is currently selected.

    Must be awaited -- blocks until the dialog closes so the caller
    can rebuild the toolbar afterwards.
    """
    selected_color: list[str] = [_PRESET_PALETTE[0]]

    from promptgrimoire.db.tags import (  # noqa: PLC0415
        list_tag_groups_for_workspace,
    )

    groups = await list_tag_groups_for_workspace(state.workspace_id)
    group_options: dict[str, str] = {str(g.id): g.name for g in groups}

    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("Quick Create Tag").classes(
            "text-lg font-bold mb-2",
        )
        name_input = ui.input("Tag name").classes("w-full")

        _build_colour_picker(selected_color)

        group_select = ui.select(
            label="Group (optional)",
            options=group_options,
            value=None,
            clearable=True,
        ).classes("w-full")

        with ui.row().classes("w-full justify-end gap-2 mt-4"):
            ui.button("Cancel", on_click=dialog.close).props("flat")

            async def _save() -> None:
                tag_name = name_input.value
                if not tag_name or not tag_name.strip():
                    ui.notify("Name is required", type="warning")
                    return

                from promptgrimoire.db.tags import (  # noqa: PLC0415
                    create_tag,
                )

                try:
                    new_tag = await create_tag(
                        workspace_id=state.workspace_id,
                        name=tag_name.strip(),
                        color=selected_color[0],
                        group_id=group_select.value,
                    )
                except PermissionError:
                    ui.notify(
                        "Tag creation not allowed",
                        type="negative",
                    )
                    return

                await _refresh_tag_state(state)

                if (
                    state.selection_start is not None
                    and state.selection_end is not None
                ):
                    from promptgrimoire.pages.annotation.highlights import (  # noqa: PLC0415
                        _add_highlight,
                    )

                    await _add_highlight(state, str(new_tag.id))

                dialog.close()
                ui.notify(
                    f"Tag '{tag_name.strip()}' created",
                    type="positive",
                )

            ui.button("Create", on_click=_save).props(
                "color=primary",
            )

    dialog.open()
    await dialog


# ── Tag row rendering helper ─────────────────────────────────────────


def _render_tag_row(
    tag: Any,
    *,
    can_edit: bool,
    group_options: dict[str, str],
    on_save: Any,
    on_delete: Any,
) -> None:
    """Render a single tag row with inline editing controls.

    Parameters
    ----------
    tag:
        A Tag model instance.
    can_edit:
        Whether inputs should be editable (False for locked tags viewed
        by non-instructors).
    group_options:
        Mapping of group UUID string -> group name for the group select.
    on_save:
        Async callback ``(tag_id, name, color, description, group_id) -> None``.
    on_delete:
        Async callback ``(tag_id, tag_name) -> None``.
    """
    with ui.row().classes("items-center w-full gap-1"):
        # Colour swatch
        ui.element("div").classes("w-6 h-6 rounded-full shrink-0").style(
            f"background-color: {tag.color}",
        )

        # Lock icon for locked tags
        if tag.locked:
            ui.icon("lock").classes("text-gray-400").tooltip("Locked")

        # Editable fields
        name_input = ui.input(value=tag.name).classes("w-32")
        color_input = ui.color_input(value=tag.color, preview=True).classes("w-24")
        desc_input = ui.input(value=tag.description or "", label="Description").classes(
            "flex-1"
        )
        group_sel = ui.select(
            options=group_options,
            value=str(tag.group_id) if tag.group_id else None,
            clearable=True,
            label="Group",
        ).classes("w-32")

        if not can_edit:
            for inp in (name_input, color_input, desc_input):
                inp.props("readonly")
            group_sel.props("disable")

        # Action buttons
        save_btn = (
            ui.button(
                icon="save",
                on_click=lambda _e, t=tag: on_save(
                    t.id,
                    name_input.value,
                    color_input.value,
                    desc_input.value,
                    group_sel.value,
                ),
            )
            .props("flat round dense")
            .tooltip("Save changes")
        )
        del_btn = (
            ui.button(
                icon="delete",
                on_click=lambda _e, t=tag: on_delete(t.id, t.name),
            )
            .props("flat round dense color=negative")
            .tooltip("Delete tag")
        )

        if not can_edit:
            save_btn.props("disable")
            del_btn.props("disable")


# ── Group header rendering helper ────────────────────────────────────


def _render_group_header(
    group: Any,
    *,
    on_save_group: Any,
    on_delete_group: Any,
) -> None:
    """Render a group header with name input and action buttons."""
    with ui.row().classes("items-center w-full gap-2 mt-4 mb-1"):
        ui.icon("folder").classes("text-blue-600")
        group_name_input = ui.input(value=group.name).classes("font-bold text-blue-800")
        ui.button(
            icon="save",
            on_click=lambda _e, g=group: on_save_group(g.id, group_name_input.value),
        ).props("flat round dense").tooltip("Save group name")
        ui.button(
            icon="delete",
            on_click=lambda _e, g=group: on_delete_group(g.id, g.name),
        ).props("flat round dense color=negative").tooltip("Delete group")


# ── Confirmation dialog helpers ──────────────────────────────────────


def _open_confirm_delete_tag(
    tag_id: UUID,
    tag_name: str,
    *,
    on_confirmed: Any,
) -> None:
    """Show a confirmation dialog before deleting a tag."""
    with ui.dialog() as dlg, ui.card():
        ui.label(f"Delete tag '{tag_name}'?").classes("font-bold")
        ui.label("This will remove all highlights using this tag.").classes(
            "text-sm text-gray-600"
        )
        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=dlg.close).props("flat")

            async def _do_delete() -> None:
                from promptgrimoire.db.tags import delete_tag  # noqa: PLC0415

                try:
                    await delete_tag(tag_id)
                except ValueError as exc:
                    ui.notify(str(exc), type="warning")
                    dlg.close()
                    return
                dlg.close()
                await on_confirmed(tag_name)

            ui.button("Delete", on_click=_do_delete).props("color=negative")
    dlg.open()


def _open_confirm_delete_group(
    group_id: UUID,
    group_name: str,
    *,
    on_confirmed: Any,
) -> None:
    """Show a confirmation dialog before deleting a tag group."""
    with ui.dialog() as dlg, ui.card():
        ui.label(f"Delete group '{group_name}'?").classes("font-bold")
        ui.label("Tags will become ungrouped.").classes("text-sm text-gray-600")
        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=dlg.close).props("flat")

            async def _do_delete() -> None:
                from promptgrimoire.db.tags import delete_tag_group  # noqa: PLC0415

                await delete_tag_group(group_id)
                dlg.close()
                await on_confirmed(group_name)

            ui.button("Delete", on_click=_do_delete).props("color=negative")
    dlg.open()


# ── Tag list rendering (content of management dialog) ────────────────


def _render_tag_list_content(
    *,
    groups: list[Any],
    tags_by_group: dict[UUID | None, list[Any]],
    group_options: dict[str, str],
    is_instructor: bool,
    on_save_tag: Any,
    on_delete_tag: Any,
    on_save_group: Any,
    on_delete_group: Any,
    on_add_tag: Any,
    on_add_group: Any,
) -> None:
    """Render all tag groups and ungrouped tags inside the content area."""
    for group in groups:
        group_tags = tags_by_group.get(group.id, [])
        _render_group_header(
            group,
            on_save_group=on_save_group,
            on_delete_group=on_delete_group,
        )
        for tag in group_tags:
            can_edit = not tag.locked or is_instructor
            _render_tag_row(
                tag,
                can_edit=can_edit,
                group_options=group_options,
                on_save=on_save_tag,
                on_delete=on_delete_tag,
            )
        ui.button(
            "+ Add tag",
            on_click=lambda _e, gid=group.id: on_add_tag(gid),
        ).props("flat dense").classes("text-xs ml-8 mt-1")

    # Ungrouped section
    ungrouped = tags_by_group.get(None, [])
    if ungrouped or not groups:
        ui.separator().classes("my-2")
        ui.label("Ungrouped").classes("font-bold text-gray-500 mt-2")
        for tag in ungrouped:
            can_edit = not tag.locked or is_instructor
            _render_tag_row(
                tag,
                can_edit=can_edit,
                group_options=group_options,
                on_save=on_save_tag,
                on_delete=on_delete_tag,
            )
        ui.button(
            "+ Add tag",
            on_click=lambda _e: on_add_tag(None),
        ).props("flat dense").classes("text-xs ml-8 mt-1")

    # Add group button
    ui.separator().classes("my-2")
    ui.button("+ Add group", on_click=on_add_group).props("flat dense").classes(
        "text-xs"
    )


# ── Full management dialog ───────────────────────────────────────────


async def open_tag_management(
    state: PageState,
    ctx: PlacementContext,
    auth_user: dict[str, object],
) -> None:
    """Open the full tag management dialog.

    Shows all tags grouped by TagGroup with inline editing, group
    management, and delete-with-confirmation. Lock enforcement
    (AC7.9) disables controls for students on locked tags.

    Must be awaited -- blocks until the dialog closes so the caller
    can rebuild the toolbar afterwards.
    """
    from promptgrimoire.auth import is_privileged_user  # noqa: PLC0415
    from promptgrimoire.db.tags import (  # noqa: PLC0415
        create_tag,
        create_tag_group,
        list_tag_groups_for_workspace,
        list_tags_for_workspace,
        update_tag,
        update_tag_group,
    )

    is_instructor = ctx.is_template and is_privileged_user(auth_user)

    with ui.dialog() as dialog, ui.card().classes("w-[600px]"):
        with ui.row().classes("w-full items-center justify-between mb-2"):
            ui.label("Manage Tags").classes("text-lg font-bold")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense")

        content_area = ui.column().classes("w-full gap-0 max-h-[60vh] overflow-y-auto")

        async def _render_tag_list() -> None:
            """Clear and rebuild the tag list inside the dialog."""
            content_area.clear()
            groups = await list_tag_groups_for_workspace(state.workspace_id)
            all_tags = await list_tags_for_workspace(state.workspace_id)
            group_options: dict[str, str] = {str(g.id): g.name for g in groups}

            tags_by_group: dict[UUID | None, list[Any]] = {}
            for tag in all_tags:
                tags_by_group.setdefault(tag.group_id, []).append(tag)

            # ── Callbacks ──

            async def _save_tag(
                tag_id: UUID,
                name: str,
                color: str,
                description: str,
                group_id_str: str | None,
            ) -> None:
                gid = UUID(group_id_str) if group_id_str else None
                try:
                    await update_tag(
                        tag_id,
                        name=name,
                        color=color,
                        description=description or None,
                        group_id=gid,
                    )
                except ValueError as exc:
                    ui.notify(str(exc), type="warning")
                    return
                await _render_tag_list()
                await _refresh_tag_state(state)
                ui.notify("Tag saved", type="positive")

            async def _on_tag_deleted(tag_name: str) -> None:
                await _refresh_tag_state(state)
                await _render_tag_list()
                ui.notify(f"Tag '{tag_name}' deleted", type="positive")

            async def _on_group_deleted(group_name: str) -> None:
                await _render_tag_list()
                ui.notify(f"Group '{group_name}' deleted", type="positive")

            async def _save_group(group_id: UUID, new_name: str) -> None:
                await update_tag_group(group_id, name=new_name)
                await _render_tag_list()
                ui.notify("Group saved", type="positive")

            async def _add_tag_in_group(group_id: UUID | None) -> None:
                await create_tag(
                    workspace_id=state.workspace_id,
                    name="New tag",
                    color=_PRESET_PALETTE[0],
                    group_id=group_id,
                )
                await _render_tag_list()
                await _refresh_tag_state(state)

            async def _add_group() -> None:
                await create_tag_group(
                    workspace_id=state.workspace_id,
                    name="New group",
                )
                await _render_tag_list()

            with content_area:
                _render_tag_list_content(
                    groups=groups,
                    tags_by_group=tags_by_group,
                    group_options=group_options,
                    is_instructor=is_instructor,
                    on_save_tag=_save_tag,
                    on_delete_tag=lambda tid, tname: _open_confirm_delete_tag(
                        tid,
                        tname,
                        on_confirmed=_on_tag_deleted,
                    ),
                    on_save_group=_save_group,
                    on_delete_group=lambda gid, gname: _open_confirm_delete_group(
                        gid,
                        gname,
                        on_confirmed=_on_group_deleted,
                    ),
                    on_add_tag=_add_tag_in_group,
                    on_add_group=_add_group,
                )

        await _render_tag_list()

    dialog.open()
    await dialog
