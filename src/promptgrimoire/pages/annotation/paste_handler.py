"""Paste submission handling for the annotation page.

Processes pasted or typed content from the QEditor, runs it through
the HTML input pipeline, and persists the result as a workspace document.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import structlog
from nicegui import ui

from promptgrimoire.db.workspace_documents import add_document
from promptgrimoire.input_pipeline.html_input import (
    detect_content_type,
    process_input,
)
from promptgrimoire.input_pipeline.paragraph_map import (
    build_paragraph_map_for_json,
    detect_source_numbering,
)
from promptgrimoire.pages.annotation.upload_handler import detect_paragraph_numbering
from promptgrimoire.pages.dialogs import show_content_type_dialog

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from nicegui.elements.editor import Editor

    from promptgrimoire.input_pipeline.html_input import ContentType

logger = structlog.get_logger()
logging.getLogger(__name__).setLevel(logging.INFO)


async def handle_add_document_submission(
    workspace_id: UUID,
    content_input: Editor,
    paste_var: str,
    platform_var: str,
    on_document_added: Callable[[], object],
) -> None:
    """Process the editor contents and persist a new source document."""
    stored = await ui.run_javascript(f"window.{paste_var}")
    platform_hint = await ui.run_javascript(f"window.{platform_var}")
    content, from_paste = (stored, True) if stored else (content_input.value, False)

    if not content or not content.strip():
        ui.notify("Please enter or paste some content", type="warning")
        return

    # Skip dialog if HTML was captured from paste - we know it's HTML.
    # For direct paste, auto-detect paragraph numbering mode.
    if from_paste:
        confirmed_type: ContentType = "html"
        auto_number_override: bool | None = None  # use auto-detect
    else:
        dialog_result = await show_content_type_dialog(
            detect_content_type(content),
            content[:500],
            source_numbering_detected=detect_source_numbering(content),
        )
        if dialog_result is None:
            return  # User cancelled
        confirmed_type, auto_number_from_dialog = dialog_result
        auto_number_override = auto_number_from_dialog

    try:
        processed_html = await process_input(
            content=content,
            source_type=confirmed_type,
            platform_hint=platform_hint,
        )
        if auto_number_override is not None:
            # User chose a value in the dialog — honour it
            auto_number = auto_number_override
            para_map = build_paragraph_map_for_json(
                processed_html, auto_number=auto_number
            )
        else:
            # Paste path — auto-detect
            auto_number, para_map = detect_paragraph_numbering(processed_html)
        await add_document(
            workspace_id=workspace_id,
            type="source",
            content=processed_html,
            source_type=confirmed_type,
            title=None,
            auto_number_paragraphs=auto_number,
            paragraph_map=para_map,
        )
        content_input.value = ""
        ui.notify("Document added successfully", type="positive")
        on_document_added()
    except Exception as exc:
        logger.exception("Failed to add document")
        ui.notify(f"Failed to add document: {exc}", type="negative")
