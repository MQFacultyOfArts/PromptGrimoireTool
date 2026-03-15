"""Quick-create tag dialog and colour picker.

Provides the quick-create dialog opened from the annotation toolbar.
Imports ``_PRESET_PALETTE`` from ``tag_management`` (shared constant)
and ``_refresh_tag_state`` from ``tag_management_save`` (leaf module).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from nicegui import ui

from promptgrimoire.pages.annotation.tag_management import _PRESET_PALETTE
from promptgrimoire.pages.annotation.tag_management_save import (
    _create_tag_or_notify,
    _refresh_tag_state,
)
from promptgrimoire.ui_helpers import on_submit_with_value

logger = structlog.get_logger()
logging.getLogger(__name__).setLevel(logging.INFO)

if TYPE_CHECKING:
    from promptgrimoire.pages.annotation import PageState

_SWATCH_BASE = "w-8 h-8 min-w-0 p-0 rounded-full"
_SWATCH_SELECTED = f"{_SWATCH_BASE} ring-2 ring-offset-1 ring-black"


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


async def _quick_create_save(
    state: PageState,
    tag_name: str,
    selected_color: list[str],
    group_select: ui.select,
    saved_start: int | None,
    saved_end: int | None,
) -> bool:
    """Validate, create tag, optionally add highlight. Return True on success."""
    if not tag_name or not tag_name.strip():
        ui.notify("Name is required", type="warning")
        return False

    from promptgrimoire.db.tags import create_tag  # noqa: PLC0415

    group_id = UUID(group_select.value) if group_select.value else None
    new_tag = await _create_tag_or_notify(
        create_tag,
        state,
        tag_name.strip(),
        selected_color[0],
        group_id,
    )
    if new_tag is None:
        return False

    # skip_card_rebuild=True: the dialog is still open; a full rebuild
    # here races with dialog.close() and can leave the dialog visible
    # (flaky test_transition_to_compact_on_fifth_tag).  The caller
    # rebuilds after the dialog closes via `await dialog`.
    await _refresh_tag_state(state, skip_card_rebuild=True)

    tag_id = getattr(new_tag, "id", None)
    if saved_start is not None and saved_end is not None and tag_id is not None:
        from promptgrimoire.pages.annotation.highlights import (  # noqa: PLC0415
            _add_highlight,
        )

        state.selection_start = saved_start
        state.selection_end = saved_end
        await _add_highlight(state, str(tag_id))

    return True


async def open_quick_create(state: PageState) -> None:
    """Open a dialog for creating a new tag and optionally highlight.

    Must be awaited -- blocks until the dialog closes so the caller
    can rebuild the toolbar afterwards.
    """
    saved_start = state.selection_start
    saved_end = state.selection_end

    selected_color: list[str] = [_PRESET_PALETTE[0]]

    from promptgrimoire.db.tags import (  # noqa: PLC0415
        list_tag_groups_for_workspace,
    )

    groups = await list_tag_groups_for_workspace(state.workspace_id)
    group_options: dict[str, str] = {str(g.id): g.name for g in groups}

    from nicegui.context import context as _ctx  # noqa: PLC0415

    logger.debug("open_quick_create: workspace=%s", state.workspace_id)

    # Dialog must be created in the client layout context, not the
    # toolbar slot.  NiceGUI Dialog.__init__ places a hidden canary
    # element in the *current* slot; if that slot is inside the
    # toolbar, _rebuild_toolbar().clear() destroys the canary and
    # its weak-ref trigger deletes the dialog mid-interaction.
    with (
        _ctx.client.layout,
        ui.dialog() as dialog,
        ui.card().classes("w-96").props("data-testid=tag-quick-create-dialog"),
    ):
        ui.label("Quick Create Tag").classes(
            "text-lg font-bold mb-2",
        )
        name_input = (
            ui.input("Tag name")
            .props(
                'maxlength=100 data-testid="tag-quick-create-name-input"',
            )
            .classes("w-full")
        )

        _build_colour_picker(selected_color)

        # Default to ungrouped
        group_select = (
            ui.select(
                label="Group",
                options=group_options,
                value=None,
                clearable=True,
            )
            .classes("w-full")
            .props('data-testid="quick-create-group-select"')
        )

        with ui.row().classes("w-full justify-end gap-2 mt-4"):
            ui.button(
                "Cancel",
                on_click=dialog.close,
            ).props('flat data-testid="quick-create-cancel-btn"')

            async def _save(text: str) -> None:
                ok = await _quick_create_save(
                    state,
                    text,
                    selected_color,
                    group_select,
                    saved_start,
                    saved_end,
                )
                if not ok:
                    return

                dialog.close()
                ui.notify(
                    f"Tag '{text}' created",
                    type="positive",
                )

            create_btn = ui.button("Create").props(
                'color=primary data-testid="quick-create-save-btn"',
            )
            on_submit_with_value(create_btn, name_input, _save)

    dialog.open()
    await dialog
    # Deferred rebuild: now that the dialog is closed, safely rebuild
    # annotation cards and broadcast the tag change to peers.
    # Invalidate cache because tag creation changes the tag select options.
    state.invalidate_card_cache()
    if state.refresh_annotations:
        state.refresh_annotations()
    if state.broadcast_update:
        await state.broadcast_update()
