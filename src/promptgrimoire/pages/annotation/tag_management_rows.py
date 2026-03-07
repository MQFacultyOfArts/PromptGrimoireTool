"""Tag and group row rendering, deletion confirmation, and list layout.

Renders individual tag rows, group headers, and the full tag list
content for the management dialog. Imports save helpers from
``tag_management_save`` (the leaf module).

Tag and group rows use ``bind_value()`` to two-way sync NiceGUI inputs
with plain model dicts. The "Done" button saves all modified rows on
close; colour changes trigger a debounced immediate save for live
feedback.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from nicegui import ui

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from uuid import UUID

    from nicegui.timer import Timer

    from promptgrimoire.db.models import Tag, TagGroup
    from promptgrimoire.pages.annotation.tag_management import (
        TagRowInputs,
    )


# ── Element creation helpers ────────────────────────────────────────


def _create_move_buttons(
    entity_id: Any,
    *,
    on_move: Callable[[Any, int], Awaitable[None]],
    index: int,
    total: int,
    prefix: str,
) -> None:
    """Render up/down move buttons for a tag or group row."""
    up_btn = (
        ui.button(
            icon="arrow_upward",
            on_click=lambda _e, eid=entity_id: on_move(eid, -1),
        )
        .props(f"flat round dense size=xs data-testid={prefix}-move-up-{entity_id}")
        .tooltip(f"Move {prefix} up")
    )
    if index == 0:
        up_btn.props("disable")
    down_btn = (
        ui.button(
            icon="arrow_downward",
            on_click=lambda _e, eid=entity_id: on_move(eid, 1),
        )
        .props(f"flat round dense size=xs data-testid={prefix}-move-down-{entity_id}")
        .tooltip(f"Move {prefix} down")
    )
    if index >= total - 1:
        down_btn.props("disable")


def _create_color_input(
    model: dict[str, Any],
    key: str,
    *,
    testid: str,
) -> ui.color_input:
    """Create a colour picker bound to ``model[key]``."""
    _props = f'data-testid={testid} dense input-class="hidden"'
    return (
        ui.color_input(value=model[key], preview=True)
        .bind_value(model, key)
        .props(_props)
        .classes("shrink-0")
        .style("width: 3rem")
    )


def _setup_color_debounce(
    color_input: ui.color_input,
    save_coro: Callable[[], Any],
    row_model: dict[str, Any],
) -> None:
    """Attach a debounced save to a colour input's change event.

    Cancels previous pending timer on each change, then schedules a
    0.3 s one-shot timer to trigger the save coroutine.

    The pending ``Timer`` is stored in ``row_model["_pending_timer"]``
    so that ``_save_all_modified_rows`` can cancel it before executing a
    batch save (Done button), eliminating the race condition where both
    the debounce timer and the batch save call ``update_tag`` concurrently.

    Parameters
    ----------
    color_input:
        The colour input element whose change event triggers the debounce.
    save_coro:
        Zero-arg async callable that performs the save.
    row_model:
        The model dict for this row.  The pending timer is stored under
        the key ``"_pending_timer"`` and reset to ``None`` after firing.
    """

    def _on_color_change() -> None:
        existing: Timer | None = row_model.get("_pending_timer")
        if existing is not None:
            existing.active = False

        _task_store: list[asyncio.Task[None]] = []

        def _fire() -> None:
            row_model["_pending_timer"] = None
            _task_store.append(asyncio.create_task(save_coro()))

        row_model["_pending_timer"] = ui.timer(0.3, _fire, once=True)

    color_input.on_value_change(_on_color_change)


# ── Tag row field helpers ────────────────────────────────────────────


def _create_tag_fields(
    model: dict[str, Any],
    tag_id: Any,
    *,
    group_options: dict[str, str],
    can_edit: bool,
    on_field_save: (Callable[[Any], Awaitable[None]] | None),
) -> None:
    """Create and bind the name, colour, description, and group inputs."""
    color_input = _create_color_input(
        model,
        "color",
        testid=f"tag-color-input-{tag_id}",
    )

    name_input = (
        ui.input(label="Name", value=model["name"])
        .bind_value(model, "name")
        .props(f"maxlength=100 data-testid=tag-name-input-{tag_id}")
        .classes("w-40")
    )
    desc_input = (
        ui.input(label="Description", value=model["description"])
        .bind_value(model, "description")
        .classes("flex-1 min-w-0")
    )
    group_sel = (
        ui.select(
            options=group_options,
            value=model["group_id"],
            clearable=True,
            label="Group",
        )
        .bind_value(model, "group_id")
        .classes("w-32")
    )

    if can_edit and on_field_save is not None:
        _setup_color_debounce(
            color_input,
            lambda tid=tag_id: on_field_save(tid),
            model,
        )

    if not can_edit:
        for inp in (name_input, color_input, desc_input):
            inp.props("readonly")
        group_sel.props("disable")


# ── Tag row rendering helper ─────────────────────────────────────────


def _render_tag_row(
    tag: Tag,
    *,
    can_edit: bool,
    is_instructor: bool,
    group_options: dict[str, str],
    on_delete: Callable[[UUID, str], None],
    on_lock_toggle: (Callable[[UUID, bool], Awaitable[None]] | None) = None,
    on_move_tag: (Callable[[UUID, int], Awaitable[None]] | None) = None,
    tag_index: int = 0,
    total_tags: int = 1,
    row_collector: dict[UUID, TagRowInputs] | None = None,
    on_field_save: (Callable[[UUID], Awaitable[None]] | None) = None,
) -> None:
    """Render a single tag row with inline editing controls.

    Values are stored in a model dict and kept in sync with inputs
    via ``bind_value()``. The model dict is stored in
    ``row_collector`` for the "Done" button to save all changes.

    Parameters
    ----------
    tag:
        A Tag model instance.
    can_edit:
        Whether inputs should be editable.
    is_instructor:
        Whether the current user is an instructor.
    group_options:
        Mapping of group UUID string -> group name.
    on_delete:
        Sync callback ``(tag_id, tag_name) -> None``.
    on_lock_toggle:
        Async callback ``(tag_id, locked) -> None``.
    on_move_tag:
        Async callback ``(tag_id, direction) -> None``.
    tag_index:
        Zero-based position within its group.
    total_tags:
        Total tags in this group.
    row_collector:
        Mutable dict to store model dicts for batch save.
    on_field_save:
        Async callback for immediate save (colour debounce).
    """
    # Model dict — bind_value keeps this in sync with inputs
    model: TagRowInputs = {
        "name": tag.name,
        "color": tag.color,
        "description": tag.description or "",
        "group_id": (str(tag.group_id) if tag.group_id else None),
        "orig_name": tag.name,
        "orig_color": tag.color,
        "orig_desc": tag.description or "",
        "orig_group": (str(tag.group_id) if tag.group_id else None),
    }

    with ui.row().classes("items-center w-full gap-1"):
        # Drag handle
        ui.icon("drag_indicator").classes("drag-handle cursor-move text-gray-400")
        # Move up/down buttons
        if on_move_tag is not None:
            _create_move_buttons(
                tag.id,
                on_move=on_move_tag,
                index=tag_index,
                total=total_tags,
                prefix="tag",
            )

        # Editable fields (colour, name, description, group)
        _create_tag_fields(
            model,  # type: ignore[arg-type]  # TagRowInputs is a dict at runtime
            tag.id,
            group_options=group_options,
            can_edit=can_edit,
            on_field_save=on_field_save,
        )

        # Lock toggle + delete button
        _render_lock_toggle(
            tag,
            is_instructor=is_instructor,
            on_lock_toggle=on_lock_toggle,
        )

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

        # Store model dict for batch save on dialog close
        if row_collector is not None and can_edit:
            row_collector[tag.id] = model


def _render_lock_toggle(
    tag: Tag,
    *,
    is_instructor: bool,
    on_lock_toggle: (Callable[[UUID, bool], Awaitable[None]] | None),
) -> None:
    """Render the lock/unlock button or icon for a tag row."""
    if is_instructor and on_lock_toggle is not None:
        lock_icon = "lock" if tag.locked else "lock_open"
        lock_tip = "Unlock tag" if tag.locked else "Lock tag"

        async def _toggle_lock(
            _e: Any,
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


# ── Group header rendering helper ────────────────────────────────────


def _render_group_header(
    group: TagGroup,
    *,
    on_delete_group: Callable[[UUID, str], None],
    on_move_group: (Callable[[UUID, int], Awaitable[None]] | None) = None,
    group_index: int = 0,
    total_groups: int = 1,
    row_collector: dict[UUID, dict[str, Any]] | None = None,
    on_group_field_save: (Callable[[UUID], Awaitable[None]] | None) = None,
) -> None:
    """Render a group header with name input, colour, and delete.

    Values are stored in a model dict kept in sync via
    ``bind_value()``.
    """
    model: dict[str, Any] = {
        "name": group.name,
        "color": group.color or "",
        "orig_name": group.name,
        "orig_color": group.color or "",
    }

    with (
        ui.row()
        .classes("items-center w-full gap-2 mt-4 mb-1")
        .props(f"data-testid=tag-group-header-{group.id}")
    ):
        ui.icon("drag_indicator").classes("drag-handle cursor-move text-gray-400")
        # Move up/down buttons
        if on_move_group is not None:
            _create_move_buttons(
                group.id,
                on_move=on_move_group,
                index=group_index,
                total=total_groups,
                prefix="group",
            )
        ui.icon("folder").classes("text-blue-600")
        (
            ui.input(value=model["name"])
            .bind_value(model, "name")
            .props(f"maxlength=100 data-testid=group-name-input-{group.id}")
            .classes("font-bold text-blue-800")
        )
        group_color_input = _create_color_input(
            model,
            "color",
            testid=f"group-color-input-{group.id}",
        )
        ui.button(
            icon="delete",
            on_click=lambda _e, g=group: on_delete_group(g.id, g.name),
        ).props(
            f"flat round dense color=negative data-testid=group-delete-btn-{group.id}"
        ).tooltip("Delete group")

        # Debounced colour save for immediate visual feedback
        if on_group_field_save is not None:
            _setup_color_debounce(
                group_color_input,
                lambda gid=group.id: on_group_field_save(gid),
                model,
            )

    # Store model dict for batch save on dialog close
    if row_collector is not None:
        row_collector[group.id] = model


# ── Parameterised confirmation dialog ────────────────────────────────


def _open_confirm_delete(
    entity_name: str,
    body_text: str,
    delete_fn: Callable[[], Awaitable[None]],
    on_confirmed: Callable[[str], Awaitable[None]],
) -> None:
    """Show a confirmation dialog before deleting a tag or group.

    Collapses the former ``_open_confirm_delete_tag`` and
    ``_open_confirm_delete_group`` into a single parameterised
    function.

    Parameters
    ----------
    entity_name:
        Display name shown in the dialog title.
    body_text:
        Explanatory text shown below the title.
    delete_fn:
        Zero-arg async callable that performs the deletion.
    on_confirmed:
        Async callback called after successful deletion.
    """
    with ui.dialog() as dlg, ui.card():
        ui.label(f"Delete {entity_name}?").classes("font-bold")
        ui.label(body_text).classes("text-sm text-gray-600")
        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=dlg.close).props("flat")

            async def _do_delete() -> None:
                try:
                    await delete_fn()
                except Exception as exc:
                    ui.notify(str(exc), type="negative")
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
    on_lock_toggle: (Callable[[UUID, bool], Awaitable[None]] | None),
    on_tag_reorder: Any,
    on_move_tag: (Callable[[UUID, int], Awaitable[None]] | None) = None,
    tag_row_collector: (dict[UUID, TagRowInputs] | None) = None,
    on_field_save: (Callable[[UUID], Awaitable[None]] | None) = None,
) -> None:
    """Render tags within a group in a Sortable."""
    from promptgrimoire.elements.sortable.sortable import (  # noqa: PLC0415
        Sortable,
    )

    total_tags = len(group_tags)
    with Sortable(
        on_end=on_tag_reorder,
        options={
            "handle": ".drag-handle",
            "animation": 150,
        },
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
    on_lock_toggle: (Callable[[UUID, bool], Awaitable[None]] | None),
    on_tag_reorder_for_group: Any,
    on_group_reorder: Any,
    on_move_group: (Callable[[UUID, int], Awaitable[None]] | None) = None,
    on_move_tag: (Callable[[UUID, int], Awaitable[None]] | None) = None,
    tag_id_lists: dict[UUID | None, list[UUID]],
    group_id_list: list[UUID],
    tag_row_collector: dict[UUID, TagRowInputs],
    group_row_collector: dict[UUID, dict[str, Any]],
    on_field_save: (Callable[[UUID], Awaitable[None]] | None) = None,
    on_group_field_save: (Callable[[UUID], Awaitable[None]] | None) = None,
) -> None:
    """Render all tag groups and ungrouped tags.

    Wraps groups in a top-level Sortable for group reordering and
    each group's tags in a nested Sortable for tag reordering.
    Model dicts are stored in the collector dicts for batch save.
    """
    from promptgrimoire.elements.sortable.sortable import (  # noqa: PLC0415
        Sortable,
    )

    # Groups section -- wrapped in Sortable for group reorder
    with Sortable(
        on_end=on_group_reorder,
        options={
            "handle": ".drag-handle",
            "animation": 150,
        },
    ):
        total_groups = len(groups)
        for idx, group in enumerate(groups):
            group_id_list.append(group.id)
            group_tags = tags_by_group.get(group.id, [])
            tag_ids: list[UUID] = []
            tag_id_lists[group.id] = tag_ids

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
        ).props('flat dense data-testid="add-ungrouped-tag-btn"').classes(
            "text-xs ml-8 mt-1"
        )

    # Add group button
    ui.separator().classes("my-2")
    ui.button("+ Add group", on_click=on_add_group).props(
        'flat dense data-testid="add-tag-group-btn"'
    ).classes("text-xs")
