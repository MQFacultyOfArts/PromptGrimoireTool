"""Document management dialog for annotation workspaces.

Opens from the action bar header. Lists documents with delete buttons
for user-uploaded documents. Template-cloned documents are protected.
Edit mode (Phase 4): documents with zero annotations can be edited
via WYSIWYG editor in a wide dialog.

Traceability:
- Issue: #229 (CRUD management), #109 (file upload / edit mode)
- AC: crud-management-229.AC4.1, AC4.2, AC4.3, AC5.5
- AC: file-upload-109.AC3.1, AC3.2
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urlencode
from uuid import UUID

from nicegui import ui
from selectolax.lexbor import LexborHTMLParser

from promptgrimoire.db.exceptions import ProtectedDocumentError
from promptgrimoire.db.workspace_documents import (
    count_document_clones,
    delete_document,
    list_documents,
    update_document_content,
)

if TYPE_CHECKING:
    from promptgrimoire.db.models import WorkspaceDocument
    from promptgrimoire.pages.annotation import PageState

logger = logging.getLogger(__name__)


_PREVIEW_MAX_CHARS = 50


def _document_display_name(doc: WorkspaceDocument) -> str:
    """Return a display name for a document.

    Uses the title if set, otherwise extracts the first 50 characters
    of plain text from the HTML content.
    """
    if doc.title:
        return doc.title
    if doc.content:
        text = LexborHTMLParser(doc.content).text(separator=" ").strip()
        if text:
            preview = text[:_PREVIEW_MAX_CHARS]
            if len(text) > _PREVIEW_MAX_CHARS:
                preview += "..."
            return preview
    return "Untitled"


def can_edit_document(doc: WorkspaceDocument, *, annotation_count: int) -> bool:
    """Whether a document is eligible for editing.

    A document can be edited when:
    1. The document has zero annotations (highlights), AND
    2. The document is user-uploaded (source_document_id IS NULL).

    Template-cloned documents and annotated documents cannot be edited
    because editing changes char offsets, which would corrupt existing
    highlight positions.
    """
    return annotation_count == 0 and doc.source_document_id is None


def can_delete_document(doc: WorkspaceDocument, *, is_owner: bool) -> bool:
    """Whether a document is eligible for deletion in the UI.

    A document can be deleted when:
    1. The viewer is the workspace owner, AND
    2. The document is user-uploaded (source_document_id IS NULL).

    Template-cloned documents (source_document_id IS NOT NULL) never show
    a delete button (AC4.3).
    """
    return is_owner and doc.source_document_id is None


def _get_annotation_count(state: PageState, doc_id: UUID) -> int:
    """Get the number of annotations (highlights) for a document.

    Returns 0 if the CRDT doc is not loaded yet.  Returning 0 makes the
    document appear editable, which is the safer UX default: the edit button
    becomes visible and the user can click Save.  This is safe because
    CRDT annotations are stored independently of ``WorkspaceDocument.content``
    — updating the content field does not touch CRDT state.  Once the CRDT
    loads, the real count is used and the edit button is hidden if annotations
    exist.
    """
    if state.crdt_doc is None:
        return 0
    return len(state.crdt_doc.get_highlights_for_document(str(doc_id)))


def _render_document_row(
    doc: WorkspaceDocument,
    state: PageState,
    dialog: ui.dialog,
) -> None:
    """Render a single document row with badges and action buttons.

    Shows edit button for editable documents (zero annotations, no
    source template). Shows delete button for owner-uploaded documents.
    Template-cloned documents show a "Template" badge instead.
    """
    annotation_count = _get_annotation_count(state, doc.id)
    with ui.row().classes("w-full items-center gap-2 py-1"):
        ui.label(_document_display_name(doc)).classes("text-sm flex-grow")
        ui.badge(doc.source_type).classes("text-xs")
        if doc.source_document_id is not None:
            ui.badge("Template", color="blue").classes("text-xs").props(
                'data-testid="template-badge"'
            )
        elif state.is_owner:
            if can_edit_document(doc, annotation_count=annotation_count):
                ui.button(
                    icon="edit",
                    on_click=lambda d=doc: _open_edit_dialog(d, state, dialog),
                ).props(
                    "flat round dense size=sm color=primary"
                    f' data-testid="edit-document-btn-{doc.id}"'
                )
            ui.button(
                icon="delete",
                on_click=lambda d=doc: _handle_delete_document(d, state, dialog),
            ).props(
                "flat round dense size=sm color=negative"
                f' data-testid="delete-doc-btn-{doc.id}"'
            )


async def open_manage_documents_dialog(state: PageState) -> None:
    """Open a dialog listing workspace documents with edit/delete options.

    Shows each document with title, source type badge, and protection
    status. User-uploaded documents owned by the viewer show a delete
    button. Documents with zero annotations and no source template
    show an edit button (AC3.1). Annotated or template-cloned documents
    do not show an edit button (AC3.2).
    """
    documents = await list_documents(state.workspace_id)

    with ui.dialog() as dialog, ui.card().classes("w-[32rem]"):
        ui.label("Manage Documents").classes("text-lg font-bold")
        ui.separator()

        if not documents:
            ui.label("No documents in this workspace.").classes(
                "text-sm text-gray-400 italic py-2"
            )
        else:
            for doc in documents:
                _render_document_row(doc, state, dialog)

        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("Close", on_click=dialog.close).props(
                'flat data-testid="close-manage-docs-btn"'
            )

    dialog.open()


def _open_edit_dialog(
    doc: WorkspaceDocument,
    state: PageState,
    manage_dialog: ui.dialog,
) -> None:
    """Open a wide WYSIWYG editor dialog for a document.

    Closes the narrow management dialog and opens a wide editor dialog
    (80vw) with the document's HTML content pre-loaded. Save persists
    the content and triggers document refresh. Cancel returns without
    saving.
    """
    manage_dialog.close()

    with (
        ui.dialog() as edit_dialog,
        ui.card().classes("w-[80vw] max-w-none max-h-[85vh] flex flex-col"),
    ):
        ui.label(f"Edit: {_document_display_name(doc)}").classes(
            "text-lg font-bold flex-shrink-0"
        )
        ui.separator().classes("flex-shrink-0")

        # QEditor scrolls internally via content-style; fills flex space
        editor = ui.editor(value=doc.content or "").classes("w-full flex-1 min-h-0")
        editor.props(
            'data-testid="document-editor"'
            ' content-style="max-height: 60vh; overflow-y: auto"'
        )

        with ui.row().classes("w-full justify-end gap-2 mt-4 flex-shrink-0"):
            ui.button("Cancel", on_click=edit_dialog.close).props(
                'flat data-testid="edit-cancel-btn"'
            )

            async def _save() -> None:
                try:
                    await update_document_content(
                        doc.id, editor.value, state.workspace_id
                    )
                except Exception:
                    logger.exception("Failed to save document")
                    ui.notify("Failed to save document", type="negative")
                    return
                edit_dialog.close()
                ui.notify("Document saved", type="positive")
                if state.refresh_documents is not None:
                    state.refresh_documents()

            ui.button("Save", on_click=_save).props(
                'color=primary data-testid="edit-save-btn"'
            )

    edit_dialog.open()


async def _handle_delete_document(
    doc: WorkspaceDocument, state: PageState, parent_dialog: ui.dialog
) -> None:
    """Show confirmation and delete a user-uploaded document.

    Checks for student clones first. If clones exist, shows a warning
    before proceeding (AC5.5). Otherwise shows standard confirmation (AC4.1).
    """
    clone_count = await count_document_clones(doc.id)

    if clone_count > 0:
        _show_clone_warning_dialog(doc, state, clone_count, parent_dialog)
        return

    _show_delete_confirm_dialog(doc, state, parent_dialog)


def _show_clone_warning_dialog(
    doc: WorkspaceDocument,
    state: PageState,
    clone_count: int,
    parent_dialog: ui.dialog,
) -> None:
    """Show warning dialog when template document has student clones."""
    with (
        ui.dialog().props(
            'data-testid="template-delete-warning-dialog"'
        ) as warn_dialog,
        ui.card().classes("w-96"),
    ):
        ui.label(
            f"{clone_count} student{'s' if clone_count != 1 else ''} "
            f"{'have' if clone_count != 1 else 'has'} "
            "copies of this document. "
            "Deleting it will make their copies deletable."
        ).classes("text-body1").props('data-testid="clone-warning-text"')
        with ui.row().classes("justify-end w-full gap-2 mt-4"):
            ui.button("Cancel", on_click=warn_dialog.close).props(
                'flat data-testid="cancel-delete-doc-btn"'
            )

            async def _proceed() -> None:
                warn_dialog.close()
                parent_dialog.close()
                await _do_delete_document(doc, state)

            ui.button("Delete Anyway", on_click=_proceed).props(
                'color=negative data-testid="confirm-delete-doc-btn"'
            )
    warn_dialog.open()


def _show_delete_confirm_dialog(
    doc: WorkspaceDocument, state: PageState, parent_dialog: ui.dialog
) -> None:
    """Show standard confirmation dialog for user-uploaded document."""
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label(f"Delete '{_document_display_name(doc)}'?").classes(
            "text-lg font-bold"
        )
        ui.label("Annotations will be removed. Tags preserved.").classes(
            "text-gray-500"
        )
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=dialog.close).props(
                'flat data-testid="cancel-delete-doc-btn"'
            )

            async def _confirm() -> None:
                dialog.close()
                parent_dialog.close()
                await _do_delete_document(doc, state)

            ui.button("Delete", on_click=_confirm).props(
                'color=negative data-testid="confirm-delete-doc-btn"'
            )
    dialog.open()


async def _do_delete_document(doc: WorkspaceDocument, state: PageState) -> None:
    """Execute document deletion and redirect to annotation page."""
    if not state.user_id:
        ui.notify("Not logged in", type="negative")
        return
    try:
        await delete_document(doc.id, user_id=UUID(state.user_id))
    except PermissionError:
        ui.notify("Permission denied", type="negative")
        return
    except ProtectedDocumentError:
        ui.notify("This document is protected and cannot be deleted", type="negative")
        return

    ui.notify("Document deleted. You can upload a replacement.", type="positive")
    qs = urlencode({"workspace_id": str(state.workspace_id)})
    ui.navigate.to(f"/annotation?{qs}")
