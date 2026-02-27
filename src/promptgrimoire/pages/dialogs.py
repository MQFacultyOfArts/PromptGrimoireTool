"""Reusable dialog components for NiceGUI pages."""

from __future__ import annotations

from nicegui import events, ui

from promptgrimoire.input_pipeline.html_input import CONTENT_TYPES, ContentType


async def show_content_type_dialog(
    detected_type: ContentType,
    preview: str = "",
) -> ContentType | None:
    """Show awaitable modal to confirm or override detected content type.

    Args:
        detected_type: The auto-detected content type to show as default.
        preview: Optional preview of the content (first ~200 chars).

    Returns:
        Selected content type, or None if cancelled.

    Usage:
        detected = detect_content_type(content)
        confirmed = await show_content_type_dialog(detected, preview=content[:200])
        if confirmed is None:
            return  # User cancelled
        # Use confirmed type
    """
    # Build options dict for select
    type_options = {t: t.upper() for t in CONTENT_TYPES}

    selected_type: ContentType = detected_type

    def on_type_change(e: events.ValueChangeEventArguments) -> None:
        nonlocal selected_type
        selected_type = e.value

    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("Confirm Content Type").classes("text-lg font-bold mb-2")

        if preview:
            with ui.expansion("Preview", icon="visibility").classes("w-full mb-4"):
                ui.label(preview[:500]).classes(
                    "text-xs text-gray-600 whitespace-pre-wrap font-mono"
                )

        ui.label("Detected type:").classes("text-sm text-gray-600")
        ui.select(
            options=type_options,
            value=detected_type,
            on_change=on_type_change,
            label="Content Type",
        ).props("dense outlined").classes("w-full mb-4")

        ui.label(
            "Override if detection is incorrect. "
            "HTML preserves formatting; Text treats content as plain text."
        ).classes("text-xs text-gray-500 mb-4")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat")
            ui.button(
                "Confirm",
                on_click=lambda: dialog.submit(selected_type),
            ).props('color=primary data-testid="confirm-content-type-btn"')

    dialog.open()
    result = await dialog
    return result
