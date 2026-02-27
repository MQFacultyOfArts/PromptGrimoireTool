"""CRUD operations for WorkspaceDocument.

Provides async database functions for document management within workspaces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func
from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import WorkspaceDocument

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
