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
    # Map button id -> colour to avoid reading NiceGUI private _style
    swatch_colours: dict[int, str] = {}

    def _select_swatch(color: str) -> None:
        selected_color[0] = color
        color_el.value = color
        for btn in swatch_buttons:
            is_active = swatch_colours.get(id(btn)) == color
            btn.classes(
                replace=_SWATCH_SELECTED if is_active else _SWATCH_BASE,
            )

    with ui.row().classes("gap-1 flex-wrap"):
        for i, preset in enumerate(_PRESET_PALETTE):
            btn = ui.button(
                "",
                on_click=lambda _e, c=preset: _select_swatch(c),
            )
            btn.style(f"background-color: {preset} !important")
            cls = _SWATCH_SELECTED if i == 0 else _SWATCH_BASE
            btn.classes(cls)
            swatch_buttons.append(btn)
            swatch_colours[id(btn)] = preset

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
    # Snapshot selection coordinates before dialog interaction clears them.
    # Clicking inside the dialog fires the document-level click handler
    # which detects collapsed browser selection and wipes state.
    saved_start = state.selection_start
    saved_end = state.selection_end

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
                        group_id=(
                            UUID(group_select.value) if group_select.value else None
                        ),
                    )
                except PermissionError:
                    ui.notify(
                        "Tag creation not allowed",
                        type="negative",
                    )
                    return

                await _refresh_tag_state(state)

                if saved_start is not None and saved_end is not None:
                    from promptgrimoire.pages.annotation.highlights import (  # noqa: PLC0415
                        _add_highlight,
                    )

                    # Restore snapshot — dialog interaction cleared state
                    state.selection_start = saved_start
                    state.selection_end = saved_end
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
    is_instructor: bool,
    group_options: dict[str, str],
    on_save: Any,
    on_delete: Any,
    on_lock_toggle: Any | None = None,
) -> None:
    """Render a single tag row with inline editing controls.

    Parameters
    ----------
    tag:
        A Tag model instance.
    can_edit:
        Whether inputs should be editable (False for locked tags viewed
        by non-instructors).
    is_instructor:
        Whether the current user is an instructor on a template workspace.
    group_options:
        Mapping of group UUID string -> group name for the group select.
    on_save:
        Async callback ``(tag_id, name, color, description, group_id) -> None``.
    on_delete:
        Async callback ``(tag_id, tag_name) -> None``.
    on_lock_toggle:
        Async callback ``(tag_id, locked) -> None``. Shown only for instructors.
    """
    with ui.row().classes("items-center w-full gap-1"):
        # Drag handle
        ui.icon("drag_indicator").classes("drag-handle cursor-move text-gray-400")

        # Colour swatch
        ui.element("div").classes("w-6 h-6 rounded-full shrink-0").style(
            f"background-color: {tag.color}",
        )

        # Lock icon for locked tags (non-instructor view)
        if tag.locked and not is_instructor:
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

        # Lock toggle (AC7.8) -- instructors only
        if is_instructor and on_lock_toggle is not None:
            ui.switch(value=tag.locked).tooltip(
                "Lock tag (prevents student modification)"
            ).on_value_change(
                lambda e, tid=tag.id: on_lock_toggle(tid, e.value),
            )

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
        ui.icon("drag_indicator").classes("drag-handle cursor-move text-gray-400")
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


# ── Reorder helpers ──────────────────────────────────────────────────


def _reorder_list(items: list[Any], old_index: int, new_index: int) -> list[Any]:
    """Move an item within a list from old_index to new_index.

    Returns a new list with the item repositioned.
    """
    result = list(items)
    item = result.pop(old_index)
    result.insert(new_index, item)
    return result


def _extract_reorder_indices(e: Any) -> tuple[int, int] | None:
    """Extract old and new indices from a Sortable end event.

    Returns ``(old_index, new_index)`` or ``None`` if the event is
    missing indices or the item did not move.
    """
    old_idx = e.args.get("oldIndex")
    new_idx = e.args.get("newIndex")
    if old_idx is None or new_idx is None or old_idx == new_idx:
        return None
    return old_idx, new_idx


# ── Tag list rendering (content of management dialog) ────────────────


def _render_group_tags(
    *,
    group_tags: list[Any],
    tag_ids: list[UUID],
    is_instructor: bool,
    group_options: dict[str, str],
    on_save_tag: Any,
    on_delete_tag: Any,
    on_lock_toggle: Any | None,
    on_tag_reorder: Any,
) -> None:
    """Render tags within a group, wrapped in a Sortable for drag reorder."""
    from promptgrimoire.elements.sortable.sortable import Sortable  # noqa: PLC0415

    with Sortable(
        on_end=on_tag_reorder,
        options={"handle": ".drag-handle", "animation": 150},
    ):
        for tag in group_tags:
            tag_ids.append(tag.id)
            can_edit = not tag.locked or is_instructor
            _render_tag_row(
                tag,
                can_edit=can_edit,
                is_instructor=is_instructor,
                group_options=group_options,
                on_save=on_save_tag,
                on_delete=on_delete_tag,
                on_lock_toggle=on_lock_toggle,
            )


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
    on_lock_toggle: Any | None,
    on_tag_reorder_for_group: Any,
    on_group_reorder: Any,
    tag_id_lists: dict[UUID | None, list[UUID]],
    group_id_list: list[UUID],
) -> None:
    """Render all tag groups and ungrouped tags inside the content area.

    Wraps groups in a top-level Sortable for group reordering and each
    group's tags in a nested Sortable for tag reordering.
    """
    from promptgrimoire.elements.sortable.sortable import Sortable  # noqa: PLC0415

    # Groups section -- wrapped in Sortable for group reorder
    with Sortable(
        on_end=on_group_reorder,
        options={"handle": ".drag-handle", "animation": 150},
    ):
        for group in groups:
            group_id_list.append(group.id)
            group_tags = tags_by_group.get(group.id, [])
            tag_ids: list[UUID] = []
            tag_id_lists[group.id] = tag_ids

            # Each group section is a wrapper div (Sortable child)
            with ui.column().classes("w-full"):
                _render_group_header(
                    group,
                    on_save_group=on_save_group,
                    on_delete_group=on_delete_group,
                )
                _render_group_tags(
                    group_tags=group_tags,
                    tag_ids=tag_ids,
                    is_instructor=is_instructor,
                    group_options=group_options,
                    on_save_tag=on_save_tag,
                    on_delete_tag=on_delete_tag,
                    on_lock_toggle=on_lock_toggle,
                    on_tag_reorder=lambda e, gid=group.id: on_tag_reorder_for_group(
                        e, gid
                    ),
                )
                ui.button(
                    "+ Add tag",
                    on_click=lambda _e, gid=group.id: on_add_tag(gid),
                ).props("flat dense").classes("text-xs ml-8 mt-1")

    # Ungrouped section (outside group Sortable)
    ungrouped = tags_by_group.get(None, [])
    if ungrouped or not groups:
        ungrouped_ids: list[UUID] = []
        tag_id_lists[None] = ungrouped_ids
        ui.separator().classes("my-2")
        ui.label("Ungrouped").classes("font-bold text-gray-500 mt-2")
        _render_group_tags(
            group_tags=ungrouped,
            tag_ids=ungrouped_ids,
            is_instructor=is_instructor,
            group_options=group_options,
            on_save_tag=on_save_tag,
            on_delete_tag=on_delete_tag,
            on_lock_toggle=on_lock_toggle,
            on_tag_reorder=lambda e: on_tag_reorder_for_group(e, None),
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


# ── Import section helper ────────────────────────────────────────────


async def _render_import_section(
    *,
    ctx: PlacementContext,
    state: PageState,
    render_tag_list: Any,
) -> None:
    """Render the 'import tags from activity' dropdown (AC7.7).

    Only shown for instructors on template workspaces within a course.
    """
    if ctx.course_id is None:
        return

    from promptgrimoire.db.activities import (  # noqa: PLC0415
        list_activities_for_course,
    )

    activities = await list_activities_for_course(ctx.course_id)
    activity_options = {
        str(a.id): a.title
        for a in activities
        if a.template_workspace_id != state.workspace_id
    }

    if not activity_options:
        return

    ui.separator().classes("my-2")
    ui.label("Import tags from another activity").classes("text-sm font-bold mt-2")
    with ui.row().classes("items-center gap-2"):
        activity_select = ui.select(
            options=activity_options,
            label="Source activity",
        ).classes("w-64")

        async def _import_from_activity() -> None:
            if not activity_select.value:
                ui.notify("Select an activity first", type="warning")
                return
            from promptgrimoire.db.tags import (  # noqa: PLC0415
                import_tags_from_activity,
            )

            try:
                await import_tags_from_activity(
                    source_activity_id=UUID(activity_select.value),
                    target_workspace_id=state.workspace_id,
                )
            except ValueError as exc:
                ui.notify(str(exc), type="negative")
                return
            await render_tag_list()
            await _refresh_tag_state(state)
            ui.notify("Tags imported", type="positive")

        ui.button("Import", on_click=_import_from_activity).props("flat dense")


# ── Full management dialog ───────────────────────────────────────────


async def open_tag_management(
    state: PageState,
    ctx: PlacementContext,
    auth_user: dict[str, object],
) -> None:
    """Open the full tag management dialog.

    Shows all tags grouped by TagGroup with inline editing, group
    management, drag reorder, import, lock toggle, and
    delete-with-confirmation. Lock enforcement (AC7.9) disables
    controls for students on locked tags.

    Must be awaited -- blocks until the dialog closes so the caller
    can rebuild the toolbar afterwards.
    """
    from promptgrimoire.auth import is_privileged_user  # noqa: PLC0415
    from promptgrimoire.db.tags import (  # noqa: PLC0415
        create_tag,
        create_tag_group,
        list_tag_groups_for_workspace,
        list_tags_for_workspace,
        reorder_tag_groups,
        reorder_tags,
        update_tag,
        update_tag_group,
    )

    is_instructor = ctx.is_template and is_privileged_user(auth_user)

    with ui.dialog() as dialog, ui.card().classes("w-[600px]"):
        with ui.row().classes("w-full items-center justify-between mb-2"):
            ui.label("Manage Tags").classes("text-lg font-bold")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense")

        content_area = ui.column().classes("w-full gap-0 max-h-[60vh] overflow-y-auto")

        # Mutable state for tracking element order (populated by render)
        tag_id_lists: dict[UUID | None, list[UUID]] = {}
        group_id_list: list[UUID] = []

        async def _render_tag_list() -> None:
            """Clear and rebuild the tag list inside the dialog."""
            content_area.clear()
            tag_id_lists.clear()
            group_id_list.clear()

            groups = await list_tag_groups_for_workspace(state.workspace_id)
            all_tags = await list_tags_for_workspace(state.workspace_id)
            group_options: dict[str, str] = {str(g.id): g.name for g in groups}

            tags_by_group: dict[UUID | None, list[Any]] = {}
            for tag in all_tags:
                tags_by_group.setdefault(tag.group_id, []).append(tag)

            callbacks = _build_management_callbacks(
                state=state,
                render_tag_list=_render_tag_list,
                update_tag=update_tag,
                update_tag_group=update_tag_group,
                create_tag=create_tag,
                create_tag_group=create_tag_group,
                reorder_tags=reorder_tags,
                reorder_tag_groups=reorder_tag_groups,
                tag_id_lists=tag_id_lists,
                group_id_list=group_id_list,
            )

            with content_area:
                _render_tag_list_content(
                    groups=groups,
                    tags_by_group=tags_by_group,
                    group_options=group_options,
                    is_instructor=is_instructor,
                    on_save_tag=callbacks["save_tag"],
                    on_delete_tag=callbacks["delete_tag"],
                    on_save_group=callbacks["save_group"],
                    on_delete_group=callbacks["delete_group"],
                    on_add_tag=callbacks["add_tag"],
                    on_add_group=callbacks["add_group"],
                    on_lock_toggle=callbacks["lock_toggle"] if is_instructor else None,
                    on_tag_reorder_for_group=callbacks["tag_reorder"],
                    on_group_reorder=callbacks["group_reorder"],
                    tag_id_lists=tag_id_lists,
                    group_id_list=group_id_list,
                )

                # Import section (AC7.7) -- instructors on template only
                if is_instructor:
                    await _render_import_section(
                        ctx=ctx,
                        state=state,
                        render_tag_list=_render_tag_list,
                    )

        await _render_tag_list()

    dialog.open()
    await dialog


# ── Callback factory ─────────────────────────────────────────────────


def _build_management_callbacks(
    *,
    state: PageState,
    render_tag_list: Any,
    update_tag: Any,
    update_tag_group: Any,
    create_tag: Any,
    create_tag_group: Any,
    reorder_tags: Any,
    reorder_tag_groups: Any,
    tag_id_lists: dict[UUID | None, list[UUID]],
    group_id_list: list[UUID],
) -> dict[str, Any]:
    """Build all management dialog callbacks as a dict.

    Extracted to keep open_tag_management and _render_tag_list under
    the 50-statement ruff limit.
    """

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
        await render_tag_list()
        await _refresh_tag_state(state)
        ui.notify("Tag saved", type="positive")

    async def _on_tag_deleted(tag_name: str) -> None:
        await _refresh_tag_state(state)
        await render_tag_list()
        ui.notify(f"Tag '{tag_name}' deleted", type="positive")

    async def _on_group_deleted(group_name: str) -> None:
        await render_tag_list()
        ui.notify(f"Group '{group_name}' deleted", type="positive")

    async def _save_group(group_id: UUID, new_name: str) -> None:
        await update_tag_group(group_id, name=new_name)
        await render_tag_list()
        ui.notify("Group saved", type="positive")

    async def _add_tag_in_group(group_id: UUID | None) -> None:
        try:
            await create_tag(
                workspace_id=state.workspace_id,
                name="New tag",
                color=_PRESET_PALETTE[0],
                group_id=group_id,
            )
        except PermissionError:
            ui.notify("Tag creation not allowed", type="negative")
            return
        await render_tag_list()
        await _refresh_tag_state(state)

    async def _add_group() -> None:
        try:
            await create_tag_group(
                workspace_id=state.workspace_id,
                name="New group",
            )
        except PermissionError:
            ui.notify("Tag creation not allowed", type="negative")
            return
        await render_tag_list()

    async def _lock_toggle(tag_id: UUID, locked: bool) -> None:
        await update_tag(tag_id, locked=locked)
        await render_tag_list()

    async def _tag_reorder(e: Any, group_id: UUID | None) -> None:
        indices = _extract_reorder_indices(e)
        if indices is None:
            return
        new_order = _reorder_list(tag_id_lists.get(group_id, []), *indices)
        await reorder_tags(new_order)
        await _refresh_tag_state(state)
        await render_tag_list()

    async def _group_reorder(e: Any) -> None:
        indices = _extract_reorder_indices(e)
        if indices is None:
            return
        new_order = _reorder_list(group_id_list, *indices)
        await reorder_tag_groups(new_order)
        await render_tag_list()

    return {
        "save_tag": _save_tag,
        "delete_tag": lambda tid, tname: _open_confirm_delete_tag(
            tid,
            tname,
            on_confirmed=_on_tag_deleted,
        ),
        "save_group": _save_group,
        "delete_group": lambda gid, gname: _open_confirm_delete_group(
            gid,
            gname,
            on_confirmed=_on_group_deleted,
        ),
        "add_tag": _add_tag_in_group,
        "add_group": _add_group,
        "lock_toggle": _lock_toggle,
        "tag_reorder": _tag_reorder,
        "group_reorder": _group_reorder,
    }
