"""Save-on-blur handlers and tag state refresh for tag management.

Leaf module in the tag management import graph -- does NOT import from
any other ``tag_management*`` or ``tag_import`` / ``tag_quick_create``
module. Sibling annotation modules are imported lazily inside functions
to avoid circular dependencies.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from nicegui import ui

from promptgrimoire.db.exceptions import (
    DuplicateNameError,
    TagCreationDeniedError,
    TagLockedError,
)

logger = structlog.get_logger()
logging.getLogger(__name__).setLevel(logging.INFO)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from promptgrimoire.crdt.annotation_doc import AnnotationDocument
    from promptgrimoire.pages.annotation import PageState
    from promptgrimoire.pages.annotation.tag_management import TagRowInputs


async def _refresh_tag_state(
    state: PageState,
    *,
    reload_crdt: bool = False,
    skip_card_rebuild: bool = False,
) -> None:
    """Reload tags from CRDT and rebuild highlight CSS, then broadcast.

    Args:
        state: Page state to update.
        reload_crdt: If True, also reload CRDT state from DB into the
            in-memory doc and refresh annotation cards + client highlights.
            Required after tag deletion which modifies CRDT in the DB.
        skip_card_rebuild: If True, skip ``refresh_annotations()`` and
            broadcast.  Used when a modal dialog is still open and a
            DOM rebuild would detach its elements.

    Lazily imports sibling modules to avoid circular dependencies.
    """
    from promptgrimoire.pages.annotation.highlights import (  # noqa: PLC0415
        _push_highlights_to_client,
        _update_highlight_css,
    )
    from promptgrimoire.pages.annotation.tags import (  # noqa: PLC0415
        workspace_tags_from_crdt,
    )

    if state.crdt_doc is not None:
        state.tag_info_list = workspace_tags_from_crdt(state.crdt_doc)
    else:
        logger.warning(
            "_refresh_tag_state: crdt_doc is None for workspace %s, "
            "tag_info_list not updated",
            state.workspace_id,
        )
    _update_highlight_css(state)

    # Rebuild the highlight menu if it exists
    if state.highlight_menu is not None:
        from promptgrimoire.pages.annotation.document import (  # noqa: PLC0415
            _populate_highlight_menu,
        )

        on_tag_click = state._highlight_menu_tag_click
        on_add_click = state._highlight_menu_on_add_click
        if on_tag_click is not None:
            _populate_highlight_menu(state, on_tag_click, on_add_click=on_add_click)

    if reload_crdt and state.crdt_doc is not None:
        from promptgrimoire.db.workspaces import get_workspace  # noqa: PLC0415

        ws = await get_workspace(state.workspace_id)
        if ws and ws.crdt_state:
            state.crdt_doc.apply_update(ws.crdt_state)
        _push_highlights_to_client(state)

    if not skip_card_rebuild:
        # Always refresh annotation cards when tags change — card borders
        # use tag colours, so any colour/name change needs a card rebuild.
        if state.refresh_annotations:
            state.refresh_annotations()

        # Broadcast tag state change to other connected clients
        if state.broadcast_update:
            await state.broadcast_update()


def _cancel_pending_timers(
    tag_row_inputs: dict[UUID, TagRowInputs] | dict[UUID, dict[str, Any]],
    group_row_inputs: dict[UUID, dict[str, Any]],
) -> None:
    """Cancel pending debounce timers before a batch save.

    ``_setup_color_debounce`` stores a ``Timer`` under the runtime-only
    key ``"_pending_timer"`` in each model dict.  Cancelling them here
    prevents a race between a still-pending 0.3 s colour save and the
    Done-button batch save.
    """
    for rows in (tag_row_inputs, group_row_inputs):
        for row in rows.values():
            timer = row.get("_pending_timer")
            if timer is not None:
                timer.active = False
                row["_pending_timer"] = None  # type: ignore[literal-required]  # runtime-only key not in TypedDict


async def _create_tag_or_notify(
    create_tag_fn: Callable[..., Awaitable[object]],
    state: PageState,
    name: str,
    color: str,
    group_id: UUID | None,
) -> object | None:
    """Create a tag via *create_tag_fn* with dual-write; notify on failure.

    Shared error handling for both the management dialog and quick create.
    Returns the created tag, or ``None`` if creation failed.
    """
    try:
        return await create_tag_fn(
            workspace_id=state.workspace_id,
            name=name,
            color=color,
            group_id=group_id,
            crdt_doc=state.crdt_doc,
        )
    except TagCreationDeniedError:
        logger.warning("tag_creation_denied", operation="create_tag")
        ui.notify("Tag creation not allowed", type="negative")
        return None
    except DuplicateNameError:
        logger.warning("duplicate_tag_name", operation="create_tag", name=name)
        ui.notify(f"A tag named '{name}' already exists", type="warning")
        return None
    except Exception as exc:
        logger.exception("tag_creation_failed", operation="create_tag")
        ui.notify(f"Failed to create tag: {exc}", type="negative")
        return None


async def _save_all_modified_rows(
    tag_row_inputs: dict[UUID, TagRowInputs] | dict[UUID, dict[str, Any]],
    group_row_inputs: dict[UUID, dict[str, Any]],
    update_tag: Callable[..., Awaitable[object]],
    update_tag_group: Callable[..., Awaitable[object]],
    *,
    bypass_lock: bool = False,
    crdt_doc: AnnotationDocument | None = None,
) -> None:
    """Save all modified tag and group rows.

    Iterates every row in *tag_row_inputs* and *group_row_inputs* and
    calls the single-row save for any that have changes.  Called by the
    "Done" button before closing the management dialog.
    """
    for tag_id in list(tag_row_inputs):
        await _save_single_tag(
            tag_id,
            tag_row_inputs,
            update_tag,
            bypass_lock=bypass_lock,
            crdt_doc=crdt_doc,
        )
    for group_id in list(group_row_inputs):
        await _save_single_group(
            group_id,
            group_row_inputs,
            update_tag_group,
            crdt_doc=crdt_doc,
        )


async def _save_single_tag(
    tag_id: UUID,
    tag_row_inputs: dict[UUID, TagRowInputs] | dict[UUID, dict[str, Any]],
    update_tag: Callable[..., Awaitable[object]],
    *,
    bypass_lock: bool = False,
    crdt_doc: AnnotationDocument | None = None,
) -> bool:
    """Auto-save a single tag's current input values on blur.

    Returns True if save succeeded (or no changes), False on error.
    """
    inputs = tag_row_inputs.get(tag_id)
    if not inputs:
        return True
    name = inputs["name"]
    color = inputs["color"]
    desc = inputs["description"]
    group_val = inputs["group_id"]
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
            crdt_doc=crdt_doc,
        )
    except TagLockedError as exc:
        logger.warning(
            "tag_save_validation_error", operation="save_tag", tag_id=str(tag_id)
        )
        ui.notify(str(exc), type="warning")
        return False
    except DuplicateNameError:
        logger.warning("duplicate_tag_name", operation="save_tag", name=name)
        ui.notify(f"A tag named '{name}' already exists", type="warning")
        return False
    except Exception as exc:
        logger.exception("tag_save_failed", operation="save_tag", tag_id=str(tag_id))
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
    *,
    crdt_doc: AnnotationDocument | None = None,
) -> bool:
    """Auto-save a single group's current input values on blur.

    Returns True if save succeeded (or no changes), False on error.
    """
    inputs = group_row_inputs.get(group_id)
    if not inputs:
        return True
    name = inputs["name"]
    color = inputs["color"]
    if name == inputs["orig_name"] and color == inputs["orig_color"]:
        return True  # No changes
    try:
        await update_tag_group(
            group_id, name=name, color=color or None, crdt_doc=crdt_doc
        )
    except DuplicateNameError:
        logger.warning("duplicate_tag_group_name", operation="save_group", name=name)
        ui.notify(f"A tag group named '{name}' already exists", type="warning")
        return False
    except Exception as exc:
        logger.exception(
            "group_save_failed", operation="save_group", group_id=str(group_id)
        )
        ui.notify(f"Failed to save group: {exc}", type="negative")
        return False
    # Update originals so subsequent blur doesn't re-save
    inputs["orig_name"] = name
    inputs["orig_color"] = color
    return True
