"""Tag management dialog orchestrator.

Provides the full management dialog (``open_tag_management``) and
callback factories. Imports rendering from ``tag_management_rows``,
save logic from ``tag_management_save``, and import section from
``tag_import``. All DB imports are lazy (inside functions).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

import structlog
from nicegui import ui

from promptgrimoire.db.tags import DuplicateNameError
from promptgrimoire.pages.annotation.tag_import import (
    _render_import_section,
)
from promptgrimoire.pages.annotation.tag_management_rows import (
    _open_confirm_delete,
    _render_tag_list_content,
)
from promptgrimoire.pages.annotation.tag_management_save import (
    _create_tag_or_notify,
    _refresh_tag_state,
    _save_single_group,
    _save_single_tag,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from uuid import UUID

    from promptgrimoire.db.models import Tag
    from promptgrimoire.db.workspaces import PlacementContext
    from promptgrimoire.pages.annotation import PageState

logger = structlog.get_logger()


class GroupCallbacks(TypedDict):
    """Typed return value of ``_build_group_callbacks``."""

    delete_group: Callable[[UUID, str], None]
    add_group: Callable[[], Awaitable[None]]
    group_reorder: Callable[[Any], Awaitable[None]]
    move_group: Callable[[UUID, int], Awaitable[None]]


class TagReorderCallbacks(TypedDict):
    """Typed return value of ``_build_tag_reorder_callbacks``."""

    tag_reorder: Callable[[Any, UUID | None], Awaitable[None]]
    move_tag: Callable[[UUID, int], Awaitable[None]]


class TagCrudCallbacks(TypedDict):
    """Typed return value of ``_build_tag_crud_callbacks``."""

    delete_tag: Callable[[UUID, str], None]
    add_tag: Callable[[UUID | None], Awaitable[None]]
    lock_toggle: Callable[[UUID, bool], Awaitable[None]]


class ManagementCallbacks(GroupCallbacks, TagReorderCallbacks, TagCrudCallbacks):
    """Typed return value of ``_build_management_callbacks``.

    Merges group, reorder, and tag CRUD callbacks.
    """


class TagRowInputs(TypedDict):
    """Model dict for a single tag row, populated by ``bind_value()``.

    Values are kept in sync with NiceGUI inputs via two-way binding.
    ``_save_single_tag`` reads current values directly from this dict
    and compares against ``orig_*`` to detect changes.
    """

    name: str
    color: str
    description: str
    group_id: str | None
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


# ── Pure helpers ─────────────────────────────────────────────────────


def _unique_default_name(base: str, existing_names: set[str]) -> str:
    """Generate a unique default name not in *existing_names*."""
    if base not in existing_names:
        return base
    for i in range(2, 100):
        candidate = f"{base} {i}"
        if candidate not in existing_names:
            return candidate
    return base  # fallback, unlikely


def _unique_tag_name(existing_names: set[str]) -> str:
    """Generate a unique default tag name not in *existing_names*."""
    return _unique_default_name("New tag", existing_names)


def _highlight_count_for_tag(
    crdt_doc: object | None,
    tag_id: UUID,
) -> int:
    """Count CRDT highlights referencing *tag_id*.

    Returns 0 if *crdt_doc* is None or has no highlights.
    """
    if not crdt_doc:
        return 0
    tag_str = str(tag_id)
    return sum(
        1
        for hl in crdt_doc.get_all_highlights()  # type: ignore[union-attr]
        if hl.get("tag") == tag_str
    )


def _delete_confirmation_body(highlight_count: int) -> str:
    """Build the confirmation dialog body for tag deletion."""
    if highlight_count:
        s = "s" if highlight_count != 1 else ""
        return f"This will remove {highlight_count} highlight{s} using this tag."
    return "This tag has no highlights."


# ── Reorder helpers ──────────────────────────────────────────────────


def _reorder_list[T](items: list[T], old_index: int, new_index: int) -> list[T]:
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

    ``e`` is a Sortable event argument whose exact type is not
    exported by the NiceGUI Sortable element.
    """
    old_idx = e.args.get("oldIndex")
    new_idx = e.args.get("newIndex")
    if old_idx is None or new_idx is None or old_idx == new_idx:
        return None
    return old_idx, new_idx


# ── Done button with spinner ─────────────────────────────────────────


def _build_done_button(
    *,
    dialog: ui.dialog,
    state: PageState,
    tag_row_inputs: dict[UUID, TagRowInputs],
    group_row_inputs: dict[UUID, dict[str, Any]],
    update_tag: Callable[..., Awaitable[object]],
    update_tag_group: Callable[..., Awaitable[object]],
    is_instructor: bool,
) -> None:
    """Render a Done button that batch-saves and shows a spinner during save.

    Follows the same loading-prop pattern as the PDF export button
    (``header.py``).  The ``data-testid`` lets E2E tests gate on save
    completion by waiting for the button to lose its ``loading`` prop.
    """
    from promptgrimoire.pages.annotation.tag_management_save import (  # noqa: PLC0415
        _cancel_pending_timers,
        _save_all_modified_rows,
    )

    done_btn = ui.button("Done", icon="check").props(
        'color=primary data-testid="tag-management-done-btn"'
    )

    async def _save_all_and_close() -> None:
        done_btn.disable()
        done_btn.props("loading")
        try:
            _cancel_pending_timers(tag_row_inputs, group_row_inputs)
            await _save_all_modified_rows(
                tag_row_inputs,
                group_row_inputs,
                update_tag,
                update_tag_group,
                bypass_lock=is_instructor,
                crdt_doc=state.crdt_doc,
            )
            await _refresh_tag_state(state)
            dialog.close()
        finally:
            done_btn.props(remove="loading")
            done_btn.enable()

    done_btn.on_click(_save_all_and_close)


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

    from nicegui.context import context as _ctx  # noqa: PLC0415

    # Place canary in layout root — see tag_quick_create.py comment.
    with (
        _ctx.client.layout,
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

            tags_by_group: dict[UUID | None, list[Tag]] = {}
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
                    tag_id,
                    tag_row_inputs,
                    update_tag,
                    bypass_lock=is_instructor,
                    crdt_doc=state.crdt_doc,
                )
                if ok:
                    await _refresh_tag_state(state)

            async def _save_group_field(group_id: UUID) -> None:
                ok = await _save_single_group(
                    group_id,
                    group_row_inputs,
                    update_tag_group,
                    crdt_doc=state.crdt_doc,
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
                    on_move_group=callbacks["move_group"],
                    on_move_tag=callbacks["move_tag"],
                    tag_id_lists=tag_id_lists,
                    group_id_list=group_id_list,
                    tag_row_collector=tag_row_inputs,
                    group_row_collector=group_row_inputs,
                    on_field_save=_save_tag_field,
                    on_group_field_save=_save_group_field,
                )

                # Import section -- available to all users (AC3.6)
                await _render_import_section(
                    state=state,
                    render_tag_list=_render_tag_list,
                )

        await _render_tag_list()

        ui.separator().classes("my-2")
        with ui.row().classes("w-full justify-end"):
            _build_done_button(
                dialog=dialog,
                state=state,
                tag_row_inputs=tag_row_inputs,
                group_row_inputs=group_row_inputs,
                update_tag=update_tag,
                update_tag_group=update_tag_group,
                is_instructor=is_instructor,
            )

    dialog.open()
    await dialog


# ── Callback factory ─────────────────────────────────────────────────


def _build_group_callbacks(
    *,
    state: PageState,
    render_tag_list: Callable[[], Awaitable[None]],
    create_tag_group: Callable[..., Awaitable[object]],
    reorder_tag_groups: Callable[..., Awaitable[None]],
    group_id_list: list[UUID],
) -> GroupCallbacks:
    """Build group-related management callbacks."""

    async def _on_group_deleted(_group_name: str) -> None:
        await _refresh_tag_state(state)
        await render_tag_list()

    async def _add_group() -> None:
        existing_group_names = {
            t.group_name for t in (state.tag_info_list or []) if t.group_name
        }
        name = _unique_default_name("New group", existing_group_names)
        try:
            await create_tag_group(
                workspace_id=state.workspace_id,
                name=name,
                crdt_doc=state.crdt_doc,
            )
        except PermissionError:
            logger.warning("tag_group_creation_denied", operation="add_group")
            ui.notify("Tag creation not allowed", type="negative")
            return
        except DuplicateNameError:
            logger.warning(
                "tag_group_duplicate_name",
                operation="add_group",
                name=name,
            )
            ui.notify(
                f"A tag group named '{name}' already exists",
                type="warning",
            )
            return
        await render_tag_list()

    async def _group_reorder(e: Any) -> None:  # Sortable event
        indices = _extract_reorder_indices(e)
        if indices is None:
            return
        new_order = _reorder_list(group_id_list, *indices)
        await reorder_tag_groups(new_order, crdt_doc=state.crdt_doc)
        await render_tag_list()

    async def _move_group(group_id: UUID, direction: int) -> None:
        """Move a group up (-1) or down (+1) by one position."""
        try:
            old_idx = group_id_list.index(group_id)
        except ValueError:
            logger.warning(
                "group_not_found_for_move",
                operation="move_group",
                group_id=str(group_id),
            )
            return
        new_idx = old_idx + direction
        if new_idx < 0 or new_idx >= len(group_id_list):
            return
        new_order = _reorder_list(group_id_list, old_idx, new_idx)
        await reorder_tag_groups(new_order, crdt_doc=state.crdt_doc)
        await render_tag_list()

    def _delete_group(gid: UUID, gname: str) -> None:
        async def _do_delete() -> None:
            from promptgrimoire.db.tags import delete_tag_group  # noqa: PLC0415

            await delete_tag_group(gid, crdt_doc=state.crdt_doc)

        _open_confirm_delete(
            entity_name=f"group '{gname}'",
            body_text="Tags will become ungrouped.",
            delete_fn=_do_delete,
            on_confirmed=_on_group_deleted,
        )

    return {
        "delete_group": _delete_group,
        "add_group": _add_group,
        "group_reorder": _group_reorder,
        "move_group": _move_group,
    }


def _build_tag_reorder_callbacks(
    *,
    state: PageState,
    render_tag_list: Callable[[], Awaitable[None]],
    reorder_tags: Callable[..., Awaitable[None]],
    tag_id_lists: dict[UUID | None, list[UUID]],
) -> TagReorderCallbacks:
    """Build tag reorder callbacks (drag and button-based)."""

    async def _tag_reorder(e: Any, group_id: UUID | None) -> None:  # Sortable event
        indices = _extract_reorder_indices(e)
        if indices is None:
            return
        new_order = _reorder_list(tag_id_lists.get(group_id, []), *indices)
        await reorder_tags(new_order, crdt_doc=state.crdt_doc)
        await _refresh_tag_state(state)
        await render_tag_list()

    async def _move_tag(tag_id: UUID, direction: int) -> None:
        """Move a tag up (-1) or down (+1) within its group."""
        for _gid, id_list in tag_id_lists.items():
            if tag_id in id_list:
                try:
                    old_idx = id_list.index(tag_id)
                except ValueError:
                    logger.warning(
                        "tag_not_found_for_move",
                        operation="move_tag",
                        tag_id=str(tag_id),
                    )
                    return
                new_idx = old_idx + direction
                if new_idx < 0 or new_idx >= len(id_list):
                    return
                new_order = _reorder_list(id_list, old_idx, new_idx)
                await reorder_tags(new_order, crdt_doc=state.crdt_doc)
                await _refresh_tag_state(state)
                await render_tag_list()
                return

    return {
        "tag_reorder": _tag_reorder,
        "move_tag": _move_tag,
    }


def _build_tag_crud_callbacks(
    *,
    state: PageState,
    render_tag_list: Callable[[], Awaitable[None]],
    update_tag: Callable[..., Awaitable[object]],
    create_tag: Callable[..., Awaitable[object]],
    is_instructor: bool,
) -> TagCrudCallbacks:
    """Build tag create/delete/lock callbacks."""

    async def _on_tag_deleted(tag_name: str) -> None:
        await _refresh_tag_state(state, reload_crdt=True)
        await render_tag_list()
        ui.notify(f"Tag '{tag_name}' deleted", type="positive")

    async def _add_tag_in_group(group_id: UUID | None) -> None:
        existing_names = (
            {t.name for t in state.tag_info_list} if state.tag_info_list else set()
        )
        name = _unique_tag_name(existing_names)
        tag = await _create_tag_or_notify(
            create_tag, state, name, _PRESET_PALETTE[0], group_id
        )
        if tag is None:
            return
        await render_tag_list()
        await _refresh_tag_state(state)

    async def _lock_toggle(tag_id: UUID, locked: bool) -> None:
        try:
            await update_tag(tag_id, locked=locked, crdt_doc=state.crdt_doc)
        except Exception as exc:
            logger.exception("tag_lock_toggle_failed", operation="lock_toggle")
            ui.notify(f"Failed to update lock: {exc}", type="negative")
            return
        await render_tag_list()

    def _delete_tag(tid: UUID, tname: str) -> None:
        count = _highlight_count_for_tag(state.crdt_doc, tid)
        body = _delete_confirmation_body(count)

        async def _do_delete() -> None:
            from promptgrimoire.db.tags import delete_tag  # noqa: PLC0415

            await delete_tag(tid, bypass_lock=is_instructor, crdt_doc=state.crdt_doc)

        _open_confirm_delete(
            entity_name=f"tag '{tname}'",
            body_text=body,
            delete_fn=_do_delete,
            on_confirmed=_on_tag_deleted,
        )

    return {
        "delete_tag": _delete_tag,
        "add_tag": _add_tag_in_group,
        "lock_toggle": _lock_toggle,
    }


def _build_management_callbacks(
    *,
    state: PageState,
    render_tag_list: Callable[[], Awaitable[None]],
    update_tag: Callable[..., Awaitable[object]],
    create_tag: Callable[..., Awaitable[object]],
    create_tag_group: Callable[..., Awaitable[object]],
    reorder_tags: Callable[..., Awaitable[None]],
    reorder_tag_groups: Callable[..., Awaitable[None]],
    tag_id_lists: dict[UUID | None, list[UUID]],
    group_id_list: list[UUID],
    is_instructor: bool,
) -> ManagementCallbacks:
    """Build all management dialog callbacks as a dict.

    Delegates to sub-builders for group, reorder, and tag CRUD callbacks.
    """
    group_cbs = _build_group_callbacks(
        state=state,
        render_tag_list=render_tag_list,
        create_tag_group=create_tag_group,
        reorder_tag_groups=reorder_tag_groups,
        group_id_list=group_id_list,
    )
    tag_reorder_cbs = _build_tag_reorder_callbacks(
        state=state,
        render_tag_list=render_tag_list,
        reorder_tags=reorder_tags,
        tag_id_lists=tag_id_lists,
    )
    tag_crud_cbs = _build_tag_crud_callbacks(
        state=state,
        render_tag_list=render_tag_list,
        update_tag=update_tag,
        create_tag=create_tag,
        is_instructor=is_instructor,
    )

    return {
        "delete_tag": tag_crud_cbs["delete_tag"],
        "add_tag": tag_crud_cbs["add_tag"],
        "lock_toggle": tag_crud_cbs["lock_toggle"],
        "tag_reorder": tag_reorder_cbs["tag_reorder"],
        "move_tag": tag_reorder_cbs["move_tag"],
        "delete_group": group_cbs["delete_group"],
        "add_group": group_cbs["add_group"],
        "group_reorder": group_cbs["group_reorder"],
        "move_group": group_cbs["move_group"],
    }
