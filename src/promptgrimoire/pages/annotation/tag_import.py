"""Tag import section for the tag management dialog.

Renders the 'import tags from another activity' dropdown. Imports
``_refresh_tag_state`` from ``tag_management_save`` (leaf module).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from nicegui import ui

from promptgrimoire.pages.annotation.tag_management_save import (
    _refresh_tag_state,
)

if TYPE_CHECKING:
    from promptgrimoire.db.workspaces import PlacementContext
    from promptgrimoire.pages.annotation import PageState


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
