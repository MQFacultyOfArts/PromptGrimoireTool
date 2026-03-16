"""Banned user suspension page.

Displayed when a banned user attempts to access any protected page.
Uses @ui.page directly (not page_route) to avoid redirect loops.
"""

from nicegui import ui


@ui.page("/banned")
async def banned_page() -> None:
    """Display account suspension message with no navigation."""
    with ui.column().classes("absolute-center items-center"):
        ui.icon("block", size="xl").classes("text-red-500")
        ui.label("Your account has been suspended.").classes("text-2xl font-bold mt-4")
        ui.label("Contact your instructor.").classes("text-lg text-grey-7 mt-2")
