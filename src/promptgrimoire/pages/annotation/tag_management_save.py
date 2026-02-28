"""Save-on-blur handlers and tag state refresh for tag management.

Leaf module in the tag management import graph -- does NOT import from
any other ``tag_management*`` or ``tag_import`` / ``tag_quick_create``
module. Sibling annotation modules are imported lazily inside functions
to avoid circular dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from nicegui import ui

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from promptgrimoire.pages.annotation import PageState
    from promptgrimoire.pages.annotation.tag_management import TagRowInputs


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
        on_add_click = getattr(state, "_highlight_menu_on_add_click", None)
        if on_tag_click is not None:
            _populate_highlight_menu(state, on_tag_click, on_add_click=on_add_click)

    if reload_crdt and state.crdt_doc is not None:
        from promptgrimoire.db.workspaces import get_workspace  # noqa: PLC0415

        ws = await get_workspace(state.workspace_id)
        if ws and ws.crdt_state:
            state.crdt_doc.apply_update(ws.crdt_state)
        _push_highlights_to_client(state)
        if state.refresh_annotations:
            state.refresh_annotations()


async def _save_single_tag(
    tag_id: UUID,
    tag_row_inputs: dict[UUID, TagRowInputs],
    update_tag: Callable[..., Awaitable[object]],
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
    update_tag_group: Callable[..., Awaitable[object]],
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
