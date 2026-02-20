"""Tag management dialogs for creating and organising annotation tags.

Provides quick-create and full management dialogs for the annotation
page toolbar. All DB and sibling-module imports are lazy (inside
functions) to avoid circular dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict
from uuid import UUID

from nicegui import ui

if TYPE_CHECKING:
    from promptgrimoire.db.workspaces import PlacementContext
    from promptgrimoire.pages.annotation import PageState


class TagRowInputs(TypedDict):
    """Input element references and original values for a single tag row.

    Used by ``_save_single_tag`` and ``_render_tag_row`` to track live
    NiceGUI input widgets alongside the last-saved values so save-on-blur
    can detect changes and skip unnecessary DB writes.
    """

    name: ui.input
    color: ui.color_input
    desc: ui.input
    group: ui.select
    orig_name: str
    orig_color: str
    orig_desc: str
    orig_group: str | None


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


async def _refresh_tag_state(
    state: PageState,
    *,
    reload_crdt: bool = False,
) -> None:
    """Reload tags from DB and rebuild highlight CSS.

    Args:
        state: Page state to update.
        reload_crdt: If True, also reload CRDT state from DB into the
            in-memory doc and refresh annotation cards + client highlights.
            Required after tag deletion which modifies CRDT in the DB.

    Lazily imports sibling modules to avoid circular dependencies.
    """
    from promptgrimoire.pages.annotation.highlights import (  # noqa: PLC0415
        _push_highlights_to_client,
        _update_highlight_css,
    )
    from promptgrimoire.pages.annotation.tags import (  # noqa: PLC0415
        workspace_tags,
    )

    state.tag_info_list = await workspace_tags(state.workspace_id)
    _update_highlight_css(state)

    # Rebuild the highlight menu if it exists
    if state.highlight_menu is not None:
        from promptgrimoire.pages.annotation.document import (  # noqa: PLC0415
            _populate_highlight_menu,
        )

        on_tag_click = getattr(state, "_highlight_menu_tag_click", None)
        if on_tag_click is not None:
            _populate_highlight_menu(state, on_tag_click)

    if reload_crdt and state.crdt_doc is not None:
        from promptgrimoire.db.workspaces import get_workspace  # noqa: PLC0415

        ws = await get_workspace(state.workspace_id)
        if ws and ws.crdt_state:
            state.crdt_doc.apply_update(ws.crdt_state)
        _push_highlights_to_client(state)
        if state.refresh_annotations:
            state.refresh_annotations()


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

    with (
        ui.dialog() as dialog,
        ui.card().classes("w-96").props("data-testid=tag-quick-create-dialog"),
    ):
        ui.label("Quick Create Tag").classes(
            "text-lg font-bold mb-2",
        )
        name_input = ui.input("Tag name").props("maxlength=100").classes("w-full")

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
                except Exception as exc:
                    from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

                    if isinstance(
                        exc, IntegrityError
                    ) and "uq_tag_workspace_name" in str(exc):
                        ui.notify(
                            f"A tag named '{tag_name.strip()}' already exists",
                            type="warning",
                        )
                    else:
                        ui.notify(f"Failed to create tag: {exc}", type="negative")
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
    on_delete: Any,
    on_lock_toggle: Any | None = None,
    row_collector: dict[UUID, TagRowInputs] | None = None,
    on_field_save: Any | None = None,
) -> None:
    """Render a single tag row with inline editing controls.

    Inputs are collected into ``row_collector`` for save-on-blur. When any
    field loses focus, changed values are saved immediately.

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
    on_delete:
        Async callback ``(tag_id, tag_name) -> None``.
    on_lock_toggle:
        Async callback ``(tag_id, locked) -> None``. Shown only for instructors.
    row_collector:
        Mutable dict to store input refs and original values for batch save.
    """
    with ui.row().classes("items-center w-full gap-1"):
        # Drag handle
        ui.icon("drag_indicator").classes("drag-handle cursor-move text-gray-400")

        # Colour swatch
        ui.element("div").classes("w-6 h-6 rounded-full shrink-0").style(
            f"background-color: {tag.color}",
        )

        # Editable fields
        name_input = (
            ui.input(value=tag.name)
            .props(f"maxlength=100 data-testid=tag-name-input-{tag.id}")
            .classes("w-40")
        )
        color_input = (
            ui.color_input(value=tag.color, preview=True)
            .props(f"data-testid=tag-color-input-{tag.id}")
            .classes("w-28")
        )
        desc_input = ui.input(
            value=tag.description or "",
            placeholder="Description",
        ).classes("flex-1")
        group_sel = ui.select(
            options=group_options,
            value=str(tag.group_id) if tag.group_id else None,
            clearable=True,
            label="Group",
        ).classes("w-40")

        # Auto-save on blur for each editable field
        if can_edit and on_field_save is not None:

            async def _blur_save(_e: Any, tid: UUID = tag.id) -> None:
                await on_field_save(tid)

            for inp in (name_input, desc_input):
                inp.on("blur", _blur_save)
            color_input.on("change", _blur_save)
            group_sel.on("update:model-value", _blur_save)

        if not can_edit:
            for inp in (name_input, color_input, desc_input):
                inp.props("readonly")
            group_sel.props("disable")

        # Lock toggle + delete button (side by side)
        if is_instructor and on_lock_toggle is not None:
            lock_icon = "lock" if tag.locked else "lock_open"
            lock_tip = "Unlock tag" if tag.locked else "Lock tag"

            async def _toggle_lock(
                _e: Any, tid: UUID = tag.id, cur: bool = tag.locked
            ) -> None:
                await on_lock_toggle(tid, not cur)

            ui.button(icon=lock_icon, on_click=_toggle_lock).props(
                f"flat round dense data-testid=tag-lock-icon-{tag.id}"
            ).tooltip(lock_tip)
        elif tag.locked:
            ui.icon("lock").classes("text-gray-400").props(
                f"data-testid=tag-lock-icon-{tag.id}"
            ).tooltip("Locked")

        del_btn = (
            ui.button(
                icon="delete",
                on_click=lambda _e, t=tag: on_delete(t.id, t.name),
            )
            .props(
                f"flat round dense color=negative data-testid=tag-delete-btn-{tag.id}"
            )
            .tooltip("Delete tag")
        )

        if not can_edit:
            del_btn.props("disable")

        # Collect input refs for batch save
        if row_collector is not None and can_edit:
            row_collector[tag.id] = {
                "name": name_input,
                "color": color_input,
                "desc": desc_input,
                "group": group_sel,
                "orig_name": tag.name,
                "orig_color": tag.color,
                "orig_desc": tag.description or "",
                "orig_group": str(tag.group_id) if tag.group_id else None,
            }


# ── Group header rendering helper ────────────────────────────────────


def _render_group_header(
    group: Any,
    *,
    on_delete_group: Any,
    row_collector: dict[UUID, dict[str, Any]] | None = None,
    on_group_field_save: Any | None = None,
) -> None:
    """Render a group header with name input, colour, and delete button.

    Input refs are stored in ``row_collector`` for save-on-blur.
    """
    with (
        ui.row()
        .classes("items-center w-full gap-2 mt-4 mb-1")
        .props(f"data-testid=tag-group-header-{group.id}")
    ):
        ui.icon("drag_indicator").classes("drag-handle cursor-move text-gray-400")
        ui.icon("folder").classes("text-blue-600")
        group_name_input = (
            ui.input(value=group.name)
            .props("maxlength=100")
            .classes("font-bold text-blue-800")
        )
        group_color_input = ui.color_input(
            value=group.color or "",
            label="Bg",
            preview=True,
        ).classes("w-20")
        ui.button(
            icon="delete",
            on_click=lambda _e, g=group: on_delete_group(g.id, g.name),
        ).props(
            f"flat round dense color=negative data-testid=group-delete-btn-{group.id}"
        ).tooltip("Delete group")

        # Auto-save on blur for group fields
        if on_group_field_save is not None:

            async def _blur_save(_e: Any, gid: UUID = group.id) -> None:
                await on_group_field_save(gid)

            group_name_input.on("blur", _blur_save)
            group_color_input.on("change", _blur_save)

    # Collect input refs for save-on-blur
    if row_collector is not None:
        row_collector[group.id] = {
            "name": group_name_input,
            "color": group_color_input,
            "orig_name": group.name,
            "orig_color": group.color or "",
        }


# ── Confirmation dialog helpers ──────────────────────────────────────


def _open_confirm_delete_tag(
    tag_id: UUID,
    tag_name: str,
    *,
    on_confirmed: Any,
    bypass_lock: bool = False,
    highlight_count: int = 0,
) -> None:
    """Show a confirmation dialog before deleting a tag."""
    with ui.dialog() as dlg, ui.card():
        ui.label(f"Delete tag '{tag_name}'?").classes("font-bold")
        if highlight_count:
            msg = (
                f"This will remove {highlight_count} "
                f"highlight{'s' if highlight_count != 1 else ''} using this tag."
            )
        else:
            msg = "This tag has no highlights."
        ui.label(msg).classes("text-sm text-gray-600")
        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=dlg.close).props("flat")

            async def _do_delete() -> None:
                from promptgrimoire.db.tags import delete_tag  # noqa: PLC0415

                try:
                    await delete_tag(tag_id, bypass_lock=bypass_lock)
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

                try:
                    await delete_tag_group(group_id)
                except Exception as exc:
                    ui.notify(f"Failed to delete group: {exc}", type="negative")
                    dlg.close()
                    return
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
    on_delete_tag: Any,
    on_lock_toggle: Any | None,
    on_tag_reorder: Any,
    tag_row_collector: dict[UUID, TagRowInputs] | None = None,
    on_field_save: Any | None = None,
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
                on_delete=on_delete_tag,
                on_lock_toggle=on_lock_toggle,
                row_collector=tag_row_collector,
                on_field_save=on_field_save,
            )


def _render_tag_list_content(
    *,
    groups: list[Any],
    tags_by_group: dict[UUID | None, list[Any]],
    group_options: dict[str, str],
    is_instructor: bool,
    on_delete_tag: Any,
    on_delete_group: Any,
    on_add_tag: Any,
    on_add_group: Any,
    on_lock_toggle: Any | None,
    on_tag_reorder_for_group: Any,
    on_group_reorder: Any,
    tag_id_lists: dict[UUID | None, list[UUID]],
    group_id_list: list[UUID],
    tag_row_collector: dict[UUID, TagRowInputs],
    group_row_collector: dict[UUID, dict[str, Any]],
    on_field_save: Any | None = None,
    on_group_field_save: Any | None = None,
) -> None:
    """Render all tag groups and ungrouped tags inside the content area.

    Wraps groups in a top-level Sortable for group reordering and each
    group's tags in a nested Sortable for tag reordering. Input refs are
    stored in the collector dicts for save-on-blur.
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
                    on_delete_group=on_delete_group,
                    row_collector=group_row_collector,
                    on_group_field_save=on_group_field_save,
                )
                _render_group_tags(
                    group_tags=group_tags,
                    tag_ids=tag_ids,
                    is_instructor=is_instructor,
                    group_options=group_options,
                    on_delete_tag=on_delete_tag,
                    on_lock_toggle=on_lock_toggle,
                    on_tag_reorder=lambda e, gid=group.id: on_tag_reorder_for_group(
                        e, gid
                    ),
                    tag_row_collector=tag_row_collector,
                    on_field_save=on_field_save,
                )
                ui.button(
                    "+ Add tag",
                    on_click=lambda _e, gid=group.id: on_add_tag(gid),
                ).props(f"flat dense data-testid=group-add-tag-btn-{group.id}").classes(
                    "text-xs ml-8 mt-1"
                )

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
            on_delete_tag=on_delete_tag,
            on_lock_toggle=on_lock_toggle,
            on_tag_reorder=lambda e: on_tag_reorder_for_group(e, None),
            tag_row_collector=tag_row_collector,
            on_field_save=on_field_save,
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
    with ui.column().classes("w-full").props("data-testid=tag-import-section"):
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


async def _save_single_tag(
    tag_id: UUID,
    tag_row_inputs: dict[UUID, TagRowInputs],
    update_tag: Any,
    *,
    bypass_lock: bool = False,
) -> bool:
    """Auto-save a single tag's current input values on blur.

    Returns True if save succeeded (or no changes), False on error.
    """
    inputs = tag_row_inputs.get(tag_id)
    if not inputs:
        return True
    name = inputs["name"].value
    color = inputs["color"].value
    desc = inputs["desc"].value
    group_val = inputs["group"].value
    if (
        name == inputs["orig_name"]
        and color == inputs["orig_color"]
        and desc == inputs["orig_desc"]
        and group_val == inputs["orig_group"]
    ):
        return True  # No changes
    gid = UUID(group_val) if group_val else None
    try:
        await update_tag(
            tag_id,
            name=name,
            color=color,
            description=desc or None,
            group_id=gid,
            bypass_lock=bypass_lock,
        )
    except ValueError as exc:
        ui.notify(str(exc), type="warning")
        return False
    except Exception as exc:
        from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

        if isinstance(exc, IntegrityError) and "uq_tag_workspace_name" in str(exc):
            ui.notify(f"A tag named '{name}' already exists", type="warning")
        else:
            ui.notify(f"Failed to save: {exc}", type="negative")
        return False
    # Update originals so subsequent blur doesn't re-save
    inputs["orig_name"] = name
    inputs["orig_color"] = color
    inputs["orig_desc"] = desc
    inputs["orig_group"] = group_val
    return True


async def _save_single_group(
    group_id: UUID,
    group_row_inputs: dict[UUID, dict[str, Any]],
    update_tag_group: Any,
) -> bool:
    """Auto-save a single group's current input values on blur.

    Returns True if save succeeded (or no changes), False on error.
    """
    inputs = group_row_inputs.get(group_id)
    if not inputs:
        return True
    name = inputs["name"].value
    color = inputs["color"].value
    if name == inputs["orig_name"] and color == inputs["orig_color"]:
        return True  # No changes
    try:
        await update_tag_group(group_id, name=name, color=color or None)
    except Exception as exc:
        ui.notify(f"Failed to save group: {exc}", type="negative")
        return False
    # Update originals so subsequent blur doesn't re-save
    inputs["orig_name"] = name
    inputs["orig_color"] = color
    return True


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

    # Instructor = template workspace owner OR org-level admin.
    # Students never access templates (ACL gate in workspace.py), so
    # is_template reliably identifies instructor context.  Org admins
    # get instructor powers everywhere.
    is_instructor = ctx.is_template or is_privileged_user(auth_user)

    with (
        ui.dialog() as dialog,
        ui.card()
        .style("width: 800px !important; max-width: 90vw !important;")
        .props("data-testid=tag-management-dialog"),
    ):
        ui.label("Manage Tags").classes("text-lg font-bold mb-2")

        content_area = ui.column().classes("w-full gap-0 max-h-[60vh] overflow-y-auto")

        # Mutable state for tracking element order (populated by render)
        tag_id_lists: dict[UUID | None, list[UUID]] = {}
        group_id_list: list[UUID] = []
        # Row input collectors for save-on-blur (populated by render helpers)
        tag_row_inputs: dict[UUID, TagRowInputs] = {}
        group_row_inputs: dict[UUID, dict[str, Any]] = {}

        async def _render_tag_list() -> None:
            """Clear and rebuild the tag list inside the dialog."""
            content_area.clear()
            tag_id_lists.clear()
            group_id_list.clear()
            tag_row_inputs.clear()
            group_row_inputs.clear()

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
                create_tag=create_tag,
                create_tag_group=create_tag_group,
                reorder_tags=reorder_tags,
                reorder_tag_groups=reorder_tag_groups,
                tag_id_lists=tag_id_lists,
                group_id_list=group_id_list,
                is_instructor=is_instructor,
            )

            async def _save_tag_field(tag_id: UUID) -> None:
                ok = await _save_single_tag(
                    tag_id, tag_row_inputs, update_tag, bypass_lock=is_instructor
                )
                if ok:
                    await _refresh_tag_state(state)

            async def _save_group_field(group_id: UUID) -> None:
                ok = await _save_single_group(
                    group_id, group_row_inputs, update_tag_group
                )
                if ok:
                    await _refresh_tag_state(state)

            with content_area:
                _render_tag_list_content(
                    groups=groups,
                    tags_by_group=tags_by_group,
                    group_options=group_options,
                    is_instructor=is_instructor,
                    on_delete_tag=callbacks["delete_tag"],
                    on_delete_group=callbacks["delete_group"],
                    on_add_tag=callbacks["add_tag"],
                    on_add_group=callbacks["add_group"],
                    on_lock_toggle=callbacks["lock_toggle"] if is_instructor else None,
                    on_tag_reorder_for_group=callbacks["tag_reorder"],
                    on_group_reorder=callbacks["group_reorder"],
                    tag_id_lists=tag_id_lists,
                    group_id_list=group_id_list,
                    tag_row_collector=tag_row_inputs,
                    group_row_collector=group_row_inputs,
                    on_field_save=_save_tag_field,
                    on_group_field_save=_save_group_field,
                )

                # Import section (AC7.7) -- instructors on template only
                if is_instructor:
                    await _render_import_section(
                        ctx=ctx,
                        state=state,
                        render_tag_list=_render_tag_list,
                    )

        await _render_tag_list()

        # "Done" button — refreshes toolbar state and closes
        async def _save_all_and_close() -> None:
            await _refresh_tag_state(state)
            dialog.close()

        ui.separator().classes("my-2")
        with ui.row().classes("w-full justify-end"):
            ui.button("Done", on_click=_save_all_and_close).props(
                "color=primary data-testid=tag-management-done-btn"
            )

    dialog.open()
    await dialog


# ── Callback factory ─────────────────────────────────────────────────


def _build_group_callbacks(
    *,
    state: PageState,
    render_tag_list: Any,
    create_tag_group: Any,
    reorder_tag_groups: Any,
    group_id_list: list[UUID],
) -> dict[str, Any]:
    """Build group-related management callbacks."""

    async def _on_group_deleted(_group_name: str) -> None:
        await _refresh_tag_state(state)
        await render_tag_list()

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

    async def _group_reorder(e: Any) -> None:
        indices = _extract_reorder_indices(e)
        if indices is None:
            return
        new_order = _reorder_list(group_id_list, *indices)
        await reorder_tag_groups(new_order)
        await render_tag_list()

    return {
        "delete_group": lambda gid, gname: _open_confirm_delete_group(
            gid,
            gname,
            on_confirmed=_on_group_deleted,
        ),
        "add_group": _add_group,
        "group_reorder": _group_reorder,
    }


def _build_management_callbacks(
    *,
    state: PageState,
    render_tag_list: Any,
    update_tag: Any,
    create_tag: Any,
    create_tag_group: Any,
    reorder_tags: Any,
    reorder_tag_groups: Any,
    tag_id_lists: dict[UUID | None, list[UUID]],
    group_id_list: list[UUID],
    is_instructor: bool,
) -> dict[str, Any]:
    """Build all management dialog callbacks as a dict."""
    group_cbs = _build_group_callbacks(
        state=state,
        render_tag_list=render_tag_list,
        create_tag_group=create_tag_group,
        reorder_tag_groups=reorder_tag_groups,
        group_id_list=group_id_list,
    )

    async def _on_tag_deleted(tag_name: str) -> None:
        await _refresh_tag_state(state, reload_crdt=True)
        await render_tag_list()
        ui.notify(f"Tag '{tag_name}' deleted", type="positive")

    async def _add_tag_in_group(group_id: UUID | None) -> None:
        # Find a unique default name from DB state
        existing_names = (
            {t.name for t in state.tag_info_list} if state.tag_info_list else set()
        )
        name = "New tag"
        if name in existing_names:
            for i in range(2, 100):
                candidate = f"New tag {i}"
                if candidate not in existing_names:
                    name = candidate
                    break

        try:
            await create_tag(
                workspace_id=state.workspace_id,
                name=name,
                color=_PRESET_PALETTE[0],
                group_id=group_id,
            )
        except PermissionError:
            ui.notify("Tag creation not allowed", type="negative")
            return
        except Exception as exc:
            from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

            if isinstance(exc, IntegrityError) and "uq_tag_workspace_name" in str(exc):
                ui.notify(
                    f"A tag named '{name}' already exists",
                    type="warning",
                )
            else:
                ui.notify(f"Failed to create tag: {exc}", type="negative")
            return
        await render_tag_list()
        await _refresh_tag_state(state)

    async def _lock_toggle(tag_id: UUID, locked: bool) -> None:
        try:
            await update_tag(tag_id, locked=locked)
        except Exception as exc:
            ui.notify(f"Failed to update lock: {exc}", type="negative")
            return
        await render_tag_list()

    async def _tag_reorder(e: Any, group_id: UUID | None) -> None:
        indices = _extract_reorder_indices(e)
        if indices is None:
            return
        new_order = _reorder_list(tag_id_lists.get(group_id, []), *indices)
        await reorder_tags(new_order)
        await _refresh_tag_state(state)
        await render_tag_list()

    def _count_highlights_for_tag(tag_id: UUID) -> int:
        """Count CRDT highlights referencing a tag."""
        if not state.crdt_doc:
            return 0
        tag_str = str(tag_id)
        return sum(
            1 for hl in state.crdt_doc.get_all_highlights() if hl.get("tag") == tag_str
        )

    return {
        "delete_tag": lambda tid, tname: _open_confirm_delete_tag(
            tid,
            tname,
            on_confirmed=_on_tag_deleted,
            bypass_lock=is_instructor,
            highlight_count=_count_highlights_for_tag(tid),
        ),
        "add_tag": _add_tag_in_group,
        "lock_toggle": _lock_toggle,
        "tag_reorder": _tag_reorder,
        **group_cbs,
    }
