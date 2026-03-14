"""File upload handling for the annotation page.

Detects content type from file extensions, generates previews,
and processes uploaded files through the HTML input pipeline.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import structlog
from nicegui import events, ui

from promptgrimoire.db.workspace_documents import add_document
from promptgrimoire.input_pipeline.html_input import (
    detect_content_type,
    process_input,
)
from promptgrimoire.input_pipeline.paragraph_map import (
    build_paragraph_map_for_json,
    detect_source_numbering,
)
from promptgrimoire.pages.dialogs import show_content_type_dialog

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from promptgrimoire.input_pipeline.html_input import ContentType

logger = structlog.get_logger()
logging.getLogger(__name__).setLevel(logging.INFO)


def _detect_type_from_extension(filename: str) -> ContentType | None:
    """Detect content type from file extension.

    Returns None if extension is not recognized.
    """
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    ext_to_type: dict[str, ContentType] = {
        "html": "html",
        "htm": "html",
        "rtf": "rtf",
        "docx": "docx",
        "pdf": "pdf",
        "txt": "text",
        "md": "text",
        "markdown": "text",
    }
    return ext_to_type.get(ext)


def _get_file_preview(
    content_bytes: bytes, detected_type: ContentType, filename: str
) -> str:
    """Get preview text for file content."""
    try:
        if detected_type in ("html", "text"):
            return content_bytes.decode("utf-8")[:500]
        return f"[Binary file: {filename}]"
    except UnicodeDecodeError:
        return f"[Binary file: {filename}]"


def detect_paragraph_numbering(
    processed_html: str,
) -> tuple[bool, dict[str, int]]:
    """Detect paragraph numbering mode and build the paragraph map.

    Returns:
        Tuple of (auto_number_paragraphs, paragraph_map) ready for
        persistence (map keys converted to strings for JSON storage).
    """
    auto_number = not detect_source_numbering(processed_html)
    para_map = build_paragraph_map_for_json(processed_html, auto_number=auto_number)
    return auto_number, para_map


def _detect_source_numbering_from_bytes(
    content_bytes: bytes,
    detected_type: ContentType,
) -> bool:
    """Try to detect source paragraph numbering from raw upload bytes.

    Only meaningful for HTML/text uploads where the bytes can be decoded
    and inspected.  Binary formats (DOCX, PDF, RTF) return ``False``.
    """
    if detected_type not in ("html", "text"):
        return False
    try:
        text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return detect_source_numbering(text)


async def _handle_file_upload(
    workspace_id: UUID,
    upload_event: events.UploadEventArguments,
    on_document_added: Callable[[], object],
) -> None:
    """Handle file upload through HTML pipeline.

    Extracted from ``_render_add_content_form`` to reduce function complexity.
    """
    # Access file via .file attribute (FileUpload dataclass)
    # ty cannot resolve this type due to TYPE_CHECKING import in nicegui
    filename: str = upload_event.file.name  # pyright: ignore[reportAttributeAccessIssue]
    content_bytes = await upload_event.file.read()  # pyright: ignore[reportAttributeAccessIssue]

    # Detect type from extension, fall back to content detection
    detected_type = _detect_type_from_extension(filename)
    if detected_type is None:
        detected_type = detect_content_type(content_bytes)

    preview = _get_file_preview(content_bytes, detected_type, filename)

    # Detect source numbering on HTML uploads (binary formats
    # like DOCX/PDF will return False — safe default).
    source_numbered = _detect_source_numbering_from_bytes(content_bytes, detected_type)

    dialog_result = await show_content_type_dialog(
        detected_type=detected_type,
        preview=preview,
        source_numbering_detected=source_numbered,
    )

    if dialog_result is None:
        ui.notify("Upload cancelled", type="info")
        return

    confirmed_type, auto_number = dialog_result

    try:
        processed_html = await process_input(
            content=content_bytes,
            source_type=confirmed_type,
            platform_hint=None,
        )
        para_map = build_paragraph_map_for_json(processed_html, auto_number=auto_number)
        await add_document(
            workspace_id=workspace_id,
            type="source",
            content=processed_html,
            source_type=confirmed_type,
            title=filename,
            auto_number_paragraphs=auto_number,
            paragraph_map=para_map,
        )
        ui.notify(f"Uploaded: {filename}", type="positive")
        on_document_added()
    except NotImplementedError as not_impl_err:
        ui.notify(f"Format not yet supported: {not_impl_err}", type="warning")
    except Exception as exc:
        logger.exception("Failed to process uploaded file")
        ui.notify(f"Failed to process file: {exc}", type="negative")
