"""CRUD operations for WorkspaceDocument.

Provides async database functions for document management within workspaces.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func
from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.exceptions import ProtectedDocumentError
from promptgrimoire.db.models import ACLEntry, Workspace, WorkspaceDocument
from promptgrimoire.input_pipeline import build_paragraph_map_for_json

if TYPE_CHECKING:
    from uuid import UUID


async def add_document(
    workspace_id: UUID,
    type: str,
    content: str,
    source_type: str,
    title: str | None = None,
    auto_number_paragraphs: bool = True,
    paragraph_map: dict[str, int] | None = None,
) -> WorkspaceDocument:
    """Add a document to a workspace.

    The document gets the next order_index automatically.

    Args:
        workspace_id: The workspace UUID.
        type: Document type ("source", "draft", "ai_conversation", etc.).
        content: HTML content with character-level spans.
        source_type: Content type - "html", "rtf", "docx", "pdf", or "text".
        title: Optional document title.
        auto_number_paragraphs: True for auto-number mode (default),
            False for source-number mode (AustLII documents).
        paragraph_map: Char-offset to paragraph-number mapping.
            Defaults to ``{}`` if not provided.

    Returns:
        The created WorkspaceDocument.
    """
    async with get_session() as session:
        # Get next order_index
        result = await session.exec(
            select(func.coalesce(func.max(WorkspaceDocument.order_index), -1)).where(
                WorkspaceDocument.workspace_id == workspace_id
            )
        )
        max_index = result.one()
        next_index = max_index + 1

        doc = WorkspaceDocument(
            workspace_id=workspace_id,
            type=type,
            content=content,
            source_type=source_type,
            title=title,
            order_index=next_index,
            auto_number_paragraphs=auto_number_paragraphs,
            paragraph_map=paragraph_map if paragraph_map is not None else {},
        )
        session.add(doc)
        await session.flush()
        await session.refresh(doc)
        return doc


async def get_document(document_id: UUID) -> WorkspaceDocument | None:
    """Get a document by ID.

    Args:
        document_id: The document UUID.

    Returns:
        The WorkspaceDocument or None if not found.
    """
    async with get_session() as session:
        result = await session.exec(
            select(WorkspaceDocument).where(WorkspaceDocument.id == document_id)
        )
        return result.first()


async def list_documents(workspace_id: UUID) -> list[WorkspaceDocument]:
    """List all documents in a workspace, ordered by order_index.

    Args:
        workspace_id: The workspace UUID.

    Returns:
        List of WorkspaceDocument objects ordered by order_index.
    """
    async with get_session() as session:
        result = await session.exec(
            select(WorkspaceDocument)
            .where(WorkspaceDocument.workspace_id == workspace_id)
            .order_by("order_index")
        )
        return list(result.all())


async def workspaces_with_documents(workspace_ids: set[UUID]) -> set[UUID]:
    """Return the subset of workspace_ids that have at least one document.

    Single query using SELECT DISTINCT for clarity.
    """
    if not workspace_ids:
        return set()
    async with get_session() as session:
        result = await session.exec(
            select(WorkspaceDocument.workspace_id)
            .where(WorkspaceDocument.workspace_id.in_(workspace_ids))  # type: ignore[union-attr]  -- SQLAlchemy Column has .in_(); TODO(2026-Q2): Revisit when SQLModel updates type stubs
            .distinct()
        )
        return set(result.all())


async def update_document_paragraph_settings(
    document_id: UUID,
    auto_number_paragraphs: bool,
    paragraph_map: dict[str, int],
) -> None:
    """Update paragraph numbering settings on a WorkspaceDocument.

    Args:
        document_id: The document UUID.
        auto_number_paragraphs: True for auto-number mode, False for source-number.
        paragraph_map: New char-offset to paragraph-number mapping.
    """
    async with get_session() as session:
        result = await session.exec(
            select(WorkspaceDocument).where(WorkspaceDocument.id == document_id)
        )
        doc = result.first()
        if doc is None:
            msg = f"WorkspaceDocument {document_id} not found"
            raise ValueError(msg)
        doc.auto_number_paragraphs = auto_number_paragraphs
        doc.paragraph_map = paragraph_map
        session.add(doc)


async def update_document_content(
    document_id: UUID,
    content: str,
    workspace_id: UUID,
) -> WorkspaceDocument:
    """Replace a document's HTML content and rebuild its paragraph map.

    Sets ``search_dirty=True`` on the parent workspace so the FTS
    background worker re-indexes the updated text.

    Args:
        document_id: The document UUID.
        content: New HTML content.
        workspace_id: The parent workspace UUID (for search_dirty flag).

    Returns:
        The updated WorkspaceDocument.

    Raises:
        ValueError: If the document is not found.
    """
    async with get_session() as session:
        result = await session.exec(
            select(WorkspaceDocument).where(WorkspaceDocument.id == document_id)
        )
        doc = result.first()
        if doc is None:
            msg = f"WorkspaceDocument {document_id} not found"
            raise ValueError(msg)

        doc.content = content
        doc.paragraph_map = build_paragraph_map_for_json(
            content, auto_number=doc.auto_number_paragraphs
        )
        session.add(doc)

        workspace = await session.get(Workspace, workspace_id)
        if workspace:
            workspace.search_dirty = True
            workspace.updated_at = datetime.now(UTC)
            session.add(workspace)

        await session.flush()
        await session.refresh(doc)
        return doc


async def delete_document(document_id: UUID, *, user_id: UUID) -> bool:
    """Delete a user-uploaded document.

    Checks that ``user_id`` is a literal owner of the document's workspace
    via :class:`ACLEntry` before proceeding. This is a defence-in-depth
    check -- the UI layer should also verify ownership.

    Uses a direct ACLEntry query for ``permission == "owner"``, NOT
    ``resolve_permission()`` which would let admins pass via the full
    ACL chain. Admin bypass belongs in the UI layer only.

    Template-cloned documents (where ``source_document_id IS NOT NULL``)
    are protected and cannot be deleted -- raises
    :class:`~promptgrimoire.db.exceptions.ProtectedDocumentError`.

    Tags are NOT affected -- they belong to the workspace via
    ``TagGroup -> Workspace`` FK, not to the document.

    Args:
        document_id: The document UUID.
        user_id: The user attempting the deletion. Must be workspace owner.

    Returns:
        True if deleted, False if not found.

    Raises:
        ProtectedDocumentError: If the document is a template clone.
        PermissionError: If ``user_id`` is not the workspace owner.
    """
    async with get_session() as session:
        result = await session.exec(
            select(WorkspaceDocument).where(WorkspaceDocument.id == document_id)
        )
        doc = result.first()
        if doc is None:
            return False

        if doc.source_document_id is not None:
            raise ProtectedDocumentError(
                document_id=doc.id,
                source_document_id=doc.source_document_id,
            )

        # Check literal ownership via ACLEntry (NOT resolve_permission)
        owner_entry = await session.exec(
            select(ACLEntry).where(
                ACLEntry.workspace_id == doc.workspace_id,
                ACLEntry.user_id == user_id,
                ACLEntry.permission == "owner",
            )
        )
        if owner_entry.first() is None:
            msg = f"user {user_id} is not the owner of workspace {doc.workspace_id}"
            raise PermissionError(msg)

        await session.delete(doc)
        return True


async def count_document_clones(document_id: UUID) -> int:
    """Count workspace documents that reference this document as their source.

    Used to warn instructors before deleting a template source document
    that has student clones.

    Args:
        document_id: The template document UUID to check for clones.

    Returns:
        Number of documents whose source_document_id matches document_id.
    """
    async with get_session() as session:
        result = await session.exec(
            select(func.count()).where(
                WorkspaceDocument.source_document_id == document_id
            )
        )
        return result.one()


async def reorder_documents(workspace_id: UUID, document_ids: list[UUID]) -> None:
    """Reorder documents in a workspace.

    Args:
        workspace_id: The workspace UUID.
        document_ids: Document UUIDs in desired order.
    """
    async with get_session() as session:
        for index, doc_id in enumerate(document_ids):
            result = await session.exec(
                select(WorkspaceDocument)
                .where(WorkspaceDocument.id == doc_id)
                .where(WorkspaceDocument.workspace_id == workspace_id)
            )
            doc = result.first()
            if doc:
                doc.order_index = index
                session.add(doc)
