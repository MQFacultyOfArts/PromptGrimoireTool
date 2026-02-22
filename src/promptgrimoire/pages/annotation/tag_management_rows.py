"""Tag and group row rendering, deletion confirmation, and list layout.

Renders individual tag rows, group headers, and the full tag list
content for the management dialog. Imports save helpers from
``tag_management_save`` (the leaf module).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nicegui import events, ui

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from uuid import UUID

    from promptgrimoire.db.models import Tag, TagGroup
    from promptgrimoire.pages.annotation.tag_management import TagRowInputs


# ── Tag row rendering helper ─────────────────────────────────────────


def _render_tag_row(
    tag: Tag,
    *,
    can_edit: bool,
    is_instructor: bool,
    group_options: dict[str, str],
    on_delete: Callable[[UUID, str], None],
    on_lock_toggle: Callable[[UUID, bool], Awaitable[None]] | None = None,
    on_move_tag: Callable[[UUID, int], Awaitable[None]] | None = None,
    tag_index: int = 0,
    total_tags: int = 1,
    row_collector: dict[UUID, TagRowInputs] | None = None,
    on_field_save: Callable[[UUID], Awaitable[None]] | None = None,
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
        Sync callback ``(tag_id, tag_name) -> None``.
    on_lock_toggle:
        Async callback ``(tag_id, locked) -> None``. Shown only for instructors.
    on_move_tag:
        Async callback ``(tag_id, direction) -> None``.
        ``direction`` is ``-1`` (up) or ``1`` (down).
    tag_index:
        Zero-based position of this tag within its group.
    total_tags:
        Total number of tags in this group (for disabling buttons).
    row_collector:
        Mutable dict to store input refs and original values for batch save.
    """
    with ui.row().classes("items-center w-full gap-1"):
        # Drag handle
        ui.icon("drag_indicator").classes("drag-handle cursor-move text-gray-400")
        # Move up/down buttons for keyboard-accessible reordering
        if on_move_tag is not None:
            up_btn = (
                ui.button(
                    icon="arrow_upward",
                    on_click=lambda _e, t=tag: on_move_tag(t.id, -1),
                )
                .props(f"flat round dense size=xs data-testid=tag-move-up-{tag.id}")
                .tooltip("Move tag up")
            )
            if tag_index == 0:
                up_btn.props("disable")
            down_btn = (
                ui.button(
                    icon="arrow_downward",
                    on_click=lambda _e, t=tag: on_move_tag(t.id, 1),
                )
                .props(f"flat round dense size=xs data-testid=tag-move-down-{tag.id}")
                .tooltip("Move tag down")
            )
            if tag_index >= total_tags - 1:
                down_btn.props("disable")

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

            async def _blur_save(
                _e: events.GenericEventArguments, tid: UUID = tag.id
            ) -> None:
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
                _e: events.ClickEventArguments,
                tid: UUID = tag.id,
                cur: bool = tag.locked,
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
    group: TagGroup,
    *,
    on_delete_group: Callable[[UUID, str], None],
    on_move_group: Callable[[UUID, int], Awaitable[None]] | None = None,
    group_index: int = 0,
    total_groups: int = 1,
    row_collector: dict[UUID, dict[str, Any]] | None = None,
    on_group_field_save: Callable[[UUID], Awaitable[None]] | None = None,
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
        # Move up/down buttons for keyboard-accessible reordering
        if on_move_group is not None:
            up_btn = (
                ui.button(
                    icon="arrow_upward",
                    on_click=lambda _e, g=group: on_move_group(g.id, -1),
                )
                .props(f"flat round dense size=xs data-testid=group-move-up-{group.id}")
                .tooltip("Move group up")
            )
            if group_index == 0:
                up_btn.props("disable")
            down_btn = (
                ui.button(
                    icon="arrow_downward",
                    on_click=lambda _e, g=group: on_move_group(g.id, 1),
                )
                .props(
                    f"flat round dense size=xs data-testid=group-move-down-{group.id}"
                )
                .tooltip("Move group down")
            )
            if group_index >= total_groups - 1:
                down_btn.props("disable")
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

            async def _blur_save(
                _e: events.GenericEventArguments, gid: UUID = group.id
            ) -> None:
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


# ── Parameterised confirmation dialog ────────────────────────────────


def _open_confirm_delete(
    entity_name: str,
    body_text: str,
    delete_fn: Callable[[], Awaitable[None]],
    on_confirmed: Callable[[str], Awaitable[None]],
) -> None:
    """Show a confirmation dialog before deleting a tag or group.

    Collapses the former ``_open_confirm_delete_tag`` and
    ``_open_confirm_delete_group`` into a single parameterised function.

    Parameters
    ----------
    entity_name:
        Display name shown in the dialog title (e.g. "tag 'Evidence'"
        or "group 'Legal'").
    body_text:
        Explanatory text shown below the title (highlight count or
        "Tags will become ungrouped.").
    delete_fn:
        Zero-arg async callable that performs the actual deletion.
        The caller constructs this closure with the appropriate ID,
        ``bypass_lock``, and error handling.
    on_confirmed:
        Async callback ``(entity_name) -> None`` called after successful
        deletion.
    """
    with ui.dialog() as dlg, ui.card():
        ui.label(f"Delete {entity_name}?").classes("font-bold")
        ui.label(body_text).classes("text-sm text-gray-600")
        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=dlg.close).props("flat")

            async def _do_delete() -> None:
                try:
                    await delete_fn()
                except (ValueError, Exception) as exc:
                    ui.notify(str(exc), type="warning")
                    dlg.close()
                    return
                dlg.close()
                await on_confirmed(entity_name)

            ui.button("Delete", on_click=_do_delete).props("color=negative")
    dlg.open()


# ── Tag list rendering (content of management dialog) ────────────────


def _render_group_tags(
    *,
    group_tags: list[Tag],
    tag_ids: list[UUID],
    is_instructor: bool,
    group_options: dict[str, str],
    on_delete_tag: Callable[[UUID, str], None],
    on_lock_toggle: Callable[[UUID, bool], Awaitable[None]] | None,
    on_tag_reorder: Any,  # Sortable on_end handler -- exact type unclear
    on_move_tag: Callable[[UUID, int], Awaitable[None]] | None = None,
    tag_row_collector: dict[UUID, TagRowInputs] | None = None,
    on_field_save: Callable[[UUID], Awaitable[None]] | None = None,
) -> None:
    """Render tags within a group, wrapped in a Sortable for drag reorder."""
    from promptgrimoire.elements.sortable.sortable import Sortable  # noqa: PLC0415

    total_tags = len(group_tags)
    with Sortable(
        on_end=on_tag_reorder,
        options={"handle": ".drag-handle", "animation": 150},
    ):
        for idx, tag in enumerate(group_tags):
            tag_ids.append(tag.id)
            can_edit = not tag.locked or is_instructor
            _render_tag_row(
                tag,
                can_edit=can_edit,
                is_instructor=is_instructor,
                group_options=group_options,
                on_delete=on_delete_tag,
                on_lock_toggle=on_lock_toggle,
                on_move_tag=on_move_tag,
                tag_index=idx,
                total_tags=total_tags,
                row_collector=tag_row_collector,
                on_field_save=on_field_save,
            )


def _render_tag_list_content(
    *,
    groups: list[TagGroup],
    tags_by_group: dict[UUID | None, list[Tag]],
    group_options: dict[str, str],
    is_instructor: bool,
    on_delete_tag: Callable[[UUID, str], None],
    on_delete_group: Callable[[UUID, str], None],
    on_add_tag: Callable[[UUID | None], Awaitable[None]],
    on_add_group: Callable[[], Awaitable[None]],
    on_lock_toggle: Callable[[UUID, bool], Awaitable[None]] | None,
    on_tag_reorder_for_group: Any,  # Sortable on_end handler -- exact type unclear
    on_group_reorder: Any,  # Sortable on_end handler -- exact type unclear
    on_move_group: Callable[[UUID, int], Awaitable[None]] | None = None,
    on_move_tag: Callable[[UUID, int], Awaitable[None]] | None = None,
    tag_id_lists: dict[UUID | None, list[UUID]],
    group_id_list: list[UUID],
    tag_row_collector: dict[UUID, TagRowInputs],
    group_row_collector: dict[UUID, dict[str, Any]],
    on_field_save: Callable[[UUID], Awaitable[None]] | None = None,
    on_group_field_save: Callable[[UUID], Awaitable[None]] | None = None,
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
        total_groups = len(groups)
        for idx, group in enumerate(groups):
            group_id_list.append(group.id)
            group_tags = tags_by_group.get(group.id, [])
            tag_ids: list[UUID] = []
            tag_id_lists[group.id] = tag_ids

            # Each group section is a wrapper div (Sortable child)
            with ui.column().classes("w-full"):
                _render_group_header(
                    group,
                    on_delete_group=on_delete_group,
                    on_move_group=on_move_group,
                    group_index=idx,
                    total_groups=total_groups,
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
                    on_move_tag=on_move_tag,
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
            on_move_tag=on_move_tag,
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
