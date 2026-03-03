"""Document management dialog for annotation workspaces.

Opens from the action bar header. Lists documents with delete buttons
for user-uploaded documents. Template-cloned documents are protected.

Traceability:
- Issue: #229 (CRUD management)
- AC: crud-management-229.AC4.1, AC4.2, AC4.3, AC5.5
"""

from __future__ import annotations

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
)

if TYPE_CHECKING:
    from promptgrimoire.db.models import WorkspaceDocument
    from promptgrimoire.pages.annotation import PageState


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


def can_delete_document(doc: WorkspaceDocument, *, is_owner: bool) -> bool:
    """Whether a document is eligible for deletion in the UI.

    A document can be deleted when:
    1. The viewer is the workspace owner, AND
    2. The document is user-uploaded (source_document_id IS NULL).

    Template-cloned documents (source_document_id IS NOT NULL) never show
    a delete button (AC4.3).
    """
    return is_owner and doc.source_document_id is None


async def open_manage_documents_dialog(state: PageState) -> None:
    """Open a dialog listing workspace documents with delete options.

    Shows each document with title, source type badge, and protection
    status. User-uploaded documents owned by the viewer show a delete
    button. Template-cloned documents show a "Template" badge.
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
                with ui.row().classes("w-full items-center gap-2 py-1"):
                    ui.label(_document_display_name(doc)).classes("text-sm flex-grow")
                    ui.badge(doc.source_type).classes("text-xs")
                    if doc.source_document_id is not None:
                        ui.badge("Template", color="blue").classes("text-xs").props(
                            'data-testid="template-badge"'
                        )
                    elif state.is_owner:
                        ui.button(
                            icon="delete",
                            on_click=lambda d=doc: _handle_delete_document(
                                d, state, dialog
                            ),
                        ).props(
                            "flat round dense size=sm color=negative"
                            f' data-testid="delete-doc-btn-{doc.id}"'
                        )

        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("Close", on_click=dialog.close).props(
                'flat data-testid="close-manage-docs-btn"'
            )

    dialog.open()


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
