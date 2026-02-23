"""Placement dialog — course/activity assignment for workspaces."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
from uuid import UUID

from nicegui import events, ui

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

from promptgrimoire.db.activities import list_activities_for_week
from promptgrimoire.db.courses import list_courses, list_user_enrollments
from promptgrimoire.db.weeks import list_weeks
from promptgrimoire.db.workspaces import (
    PlacementContext,
    make_workspace_loose,
    place_workspace_in_activity,
    place_workspace_in_course,
)


async def _load_enrolled_course_options(
    user_id: UUID,
) -> dict[str, str]:
    """Load course select options for courses the user is enrolled in."""
    enrollments = await list_user_enrollments(user_id)
    course_ids = {e.course_id for e in enrollments}
    # TODO(Seam-D): Replace with single JOIN query if course count grows
    courses_list = await list_courses()
    return {
        str(c.id): f"{c.code} - {c.name}" for c in courses_list if c.id in course_ids
    }


def _build_activity_cascade(
    course_options: dict[str, str],
    selected: dict[str, UUID | None],
) -> None:
    """Build the Course -> Week -> Activity cascading selects.

    Renders UI elements in the current NiceGUI context.
    Stores selected IDs into ``selected`` dict under keys
    "course", "week", "activity".
    """

    course_select = (
        ui.select(options=course_options, label="Course", with_input=True)
        .classes("w-full")
        .props('data-testid="placement-course"')
    )
    week_select = (
        ui.select(options={}, label="Week")
        .classes("w-full")
        .props('data-testid="placement-week"')
    )
    week_select.disable()
    activity_select = (
        ui.select(options={}, label="Activity")
        .classes("w-full")
        .props('data-testid="placement-activity"')
    )
    activity_select.disable()

    async def on_course_change(e: events.ValueChangeEventArguments) -> None:
        week_select.options = {}
        week_select.value = None
        week_select.disable()
        activity_select.options = {}
        activity_select.value = None
        activity_select.disable()
        selected["course"] = selected["week"] = selected["activity"] = None
        if e.value:
            try:
                cid = UUID(e.value)
                selected["course"] = cid
                weeks = await list_weeks(cid)
                week_select.options = {
                    str(w.id): f"Week {w.week_number}: {w.title}" for w in weeks
                }
                week_select.update()
                if weeks:
                    week_select.enable()
            except Exception as exc:
                ui.notify(str(exc), type="negative")

    course_select.on_value_change(on_course_change)

    async def on_week_change(e: events.ValueChangeEventArguments) -> None:
        activity_select.options = {}
        activity_select.value = None
        activity_select.disable()
        selected["week"] = selected["activity"] = None
        if e.value:
            try:
                wid = UUID(e.value)
                selected["week"] = wid
                activities = await list_activities_for_week(wid)
                activity_select.options = {str(a.id): a.title for a in activities}
                activity_select.update()
                if activities:
                    activity_select.enable()
            except Exception as exc:
                ui.notify(str(exc), type="negative")

    week_select.on_value_change(on_week_change)

    def on_activity_change(e: events.ValueChangeEventArguments) -> None:
        selected["activity"] = UUID(e.value) if e.value else None

    activity_select.on_value_change(on_activity_change)


def _build_course_only_select(
    course_options: dict[str, str],
    selected: dict[str, UUID | None],
) -> None:
    """Build a single Course select for course-level placement.

    Stores the selected course ID into ``selected["course_only"]``.
    """

    course_only_select = (
        ui.select(options=course_options, label="Course", with_input=True)
        .classes("w-full")
        .props('data-testid="placement-course-only"')
    )

    def on_change(e: events.ValueChangeEventArguments) -> None:
        selected["course_only"] = UUID(e.value) if e.value else None

    course_only_select.on_value_change(on_change)


async def _apply_placement(
    mode_value: str,
    workspace_id: UUID,
    selected: dict[str, UUID | None],
) -> bool:
    """Apply the placement based on the selected mode.

    Returns True on success, False if validation failed.
    """
    if mode_value == "loose":
        await make_workspace_loose(workspace_id)
        ui.notify("Workspace unplaced", type="positive")
        return True
    if mode_value == "activity":
        aid = selected.get("activity")
        if aid is None:
            ui.notify(
                "Please select a course, week, and activity",
                type="warning",
            )
            return False
        await place_workspace_in_activity(workspace_id, aid)
        ui.notify("Workspace placed in activity", type="positive")
        return True
    if mode_value == "course":
        cid = selected.get("course_only")
        if cid is None:
            ui.notify("Please select a course", type="warning")
            return False
        await place_workspace_in_course(workspace_id, cid)
        ui.notify("Workspace associated with course", type="positive")
        return True
    return False


async def show_placement_dialog(
    workspace_id: UUID,
    current_ctx: PlacementContext,
    on_changed: Callable[[], Awaitable[None]],
    user_id: UUID | None,
) -> None:
    """Open the placement dialog for changing workspace placement.

    Args:
        workspace_id: The workspace to place.
        current_ctx: Current placement context (for pre-selecting state).
        on_changed: Async callable to invoke after placement changes.
        user_id: The authenticated user's UUID, or None if not logged in.
    """
    if user_id is None:
        ui.notify("Please log in to change placement", type="warning")
        return

    initial_mode = current_ctx.placement_type
    if initial_mode not in {"activity", "course"}:
        initial_mode = "loose"

    course_options = await _load_enrolled_course_options(user_id)
    selected: dict[str, UUID | None] = {}

    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("Change Workspace Placement").classes("text-lg font-bold mb-2")
        mode = ui.radio(
            options={
                "loose": "Unplaced",
                "activity": "Place in Activity",
                "course": "Associate with Course",
            },
            value=initial_mode,
        ).props('data-testid="placement-mode"')

        activity_container = ui.column().classes("w-full gap-2")
        course_container = ui.column().classes("w-full gap-2")

        with activity_container:
            _build_activity_cascade(course_options, selected)
        with course_container:
            _build_course_only_select(course_options, selected)

        def update_visibility() -> None:
            activity_container.set_visibility(mode.value == "activity")
            course_container.set_visibility(mode.value == "course")

        mode.on_value_change(lambda _: update_visibility())
        update_visibility()

        with ui.row().classes("w-full justify-end gap-2 mt-4"):

            async def on_confirm() -> None:
                try:
                    ok = await _apply_placement(
                        cast("str", mode.value), workspace_id, selected
                    )
                except ValueError as exc:
                    ui.notify(str(exc), type="negative")
                    return
                if ok:
                    dialog.close()
                    await on_changed()

            ui.button("Confirm", on_click=on_confirm).props("color=primary")
            ui.button("Cancel", on_click=dialog.close).props("flat")

    dialog.open()
