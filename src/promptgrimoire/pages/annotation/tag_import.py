"""Tag import section for the tag management dialog.

Renders a workspace picker that lists all accessible workspaces with
tags.  Any user (not just instructors) can import tags from a workspace
they can read.  Imports ``_refresh_tag_state`` from
``tag_management_save`` (leaf module).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal
from uuid import UUID

import structlog
from nicegui import ui

from promptgrimoire.db.exceptions import SharePermissionError, TagCreationDeniedError
from promptgrimoire.pages.annotation.tag_management_save import (
    _refresh_tag_state,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from promptgrimoire.db.models import Workspace
    from promptgrimoire.db.tags import ImportResult
    from promptgrimoire.pages.annotation import PageState

logger = structlog.get_logger()


def _pluralise(n: int, word: str) -> str:
    """Return e.g. '3 tags' or '1 group'."""
    return f"{n} {word}{'s' if n != 1 else ''}"


_NotifyType = Literal["positive", "negative", "warning", "info", "ongoing"]


def _import_notification(result: ImportResult) -> tuple[str, _NotifyType]:
    """Build notification message and type from an ImportResult.

    Returns:
        (message, notify_type) tuple for ``ui.notify()``.
    """
    if not result.created_tags and not result.created_groups:
        return "No new tags to import", "info"

    parts: list[str] = []
    if result.created_tags:
        parts.append(_pluralise(len(result.created_tags), "tag"))
    if result.created_groups:
        parts.append(_pluralise(len(result.created_groups), "group"))
    msg = f"Imported {', '.join(parts)}"

    if result.skipped_tags or result.skipped_groups:
        skipped: list[str] = []
        if result.skipped_tags:
            skipped.append(_pluralise(result.skipped_tags, "tag"))
        if result.skipped_groups:
            skipped.append(_pluralise(result.skipped_groups, "group"))
        msg += f" ({', '.join(skipped)} already existed)"

    return msg, "positive"


def _build_workspace_options(
    workspaces: list[tuple[Workspace, str | None, list[str]]],
) -> dict[str, str]:
    """Build select options with tag preview from importable workspaces."""
    options: dict[str, str] = {}
    for ws, course_name, tag_names in workspaces:
        title = ws.title or "Untitled workspace"
        prefix = f"{course_name} / " if course_name else ""
        tag_preview = ", ".join(tag_names[:5])
        if len(tag_names) > 5:
            tag_preview += f" (+{len(tag_names) - 5})"
        options[str(ws.id)] = f"{prefix}{title} ({tag_preview})"
    return options


async def _render_import_section(
    *,
    state: PageState,
    render_tag_list: Callable[[], Awaitable[None]],
) -> None:
    """Render the workspace-based tag import picker.

    Available to all users.  Lists workspaces the user can read that
    contain tags, grouped by course name.
    """
    if not state.user_id:
        return

    from promptgrimoire.db.acl import (  # noqa: PLC0415
        list_importable_workspaces,
    )
    from promptgrimoire.db.courses import (  # noqa: PLC0415
        list_user_enrollments,
    )

    uid = UUID(state.user_id)
    enrollments = await list_user_enrollments(uid)
    enrolled_course_ids = [e.course_id for e in enrollments]

    workspaces = await list_importable_workspaces(
        user_id=uid,
        exclude_workspace_id=state.workspace_id,
        is_privileged=state.viewer_is_privileged,
        enrolled_course_ids=enrolled_course_ids,
    )

    ui.separator().classes("my-2")
    with ui.column().classes("w-full").props("data-testid=tag-import-section"):
        ui.label("Import tags from another workspace").classes("text-sm font-bold mt-2")

        if not workspaces:
            ui.label("No accessible workspaces with tags").classes(
                "text-sm text-gray-400"
            )
            return

        workspace_options = _build_workspace_options(workspaces)

        with ui.row().classes("items-center gap-2 w-full"):
            ws_select = (
                ui.select(
                    options=workspace_options,
                    label="Source workspace",
                )
                .classes("flex-grow")
                .props('data-testid="import-workspace-select"')
            )

            async def _import_from_workspace() -> None:
                if not ws_select.value:
                    ui.notify("Select a workspace first", type="warning")
                    return
                from promptgrimoire.db.tags import (  # noqa: PLC0415
                    import_tags_from_workspace,
                )

                try:
                    result = await import_tags_from_workspace(
                        source_workspace_id=UUID(ws_select.value),
                        target_workspace_id=state.workspace_id,
                        user_id=UUID(state.user_id),
                        crdt_doc=state.crdt_doc,
                    )
                except (SharePermissionError, TagCreationDeniedError) as exc:
                    logger.warning(
                        "tag_import_permission_denied", operation="import_tags"
                    )
                    ui.notify(str(exc), type="negative")
                    return

                # Notify BEFORE render_tag_list() — that call clears
                # content_area which destroys dialog elements via
                # weakref.finalize, invalidating the slot context.
                msg, notify_type = _import_notification(result)
                ui.notify(msg, type=notify_type)
                await render_tag_list()
                await _refresh_tag_state(state)

            ui.button("Import", on_click=_import_from_workspace).props(
                'flat dense data-testid="import-tags-btn"'
            )
