"""Quick-create tag dialog and colour picker.

Provides the quick-create dialog opened from the annotation toolbar.
Imports ``_PRESET_PALETTE`` from ``tag_management`` (shared constant)
and ``_refresh_tag_state`` from ``tag_management_save`` (leaf module).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from nicegui import ui

from promptgrimoire.pages.annotation.tag_management import _PRESET_PALETTE
from promptgrimoire.pages.annotation.tag_management_save import (
    _refresh_tag_state,
)

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
        name_input = (
            ui.input("Tag name")
            .props('maxlength=100 data-testid="tag-quick-create-name-input"')
            .classes("w-full")
        )

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

                    # Restore snapshot -- dialog interaction cleared state
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
