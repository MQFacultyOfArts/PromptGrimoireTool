"""Repository for AnnotationDocumentState CRUD operations.

Provides async functions to load and save CRDT state for annotation documents.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import select

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import AnnotationDocumentState


async def get_state_by_case_id(case_id: str) -> AnnotationDocumentState | None:
    """Load persisted CRDT state for a case.

    Args:
        case_id: Unique identifier for the document (e.g., "demo-case-183").

    Returns:
        The AnnotationDocumentState or None if not found.
    """
    async with get_session() as session:
        result = await session.exec(
            select(AnnotationDocumentState).where(
                AnnotationDocumentState.case_id == case_id
            )
        )
        return result.first()


async def save_state(
    case_id: str,
    crdt_state: bytes,
    highlight_count: int,
    last_editor: str | None = None,
) -> AnnotationDocumentState:
    """Save or update CRDT state for a case (upsert).

    If state for this case_id exists, updates it. Otherwise creates new.

    Args:
        case_id: Unique identifier for the document.
        crdt_state: Serialized pycrdt state bytes.
        highlight_count: Number of highlights in the document.
        last_editor: Display name of last user to edit.

    Returns:
        The saved or updated AnnotationDocumentState.
    """
    async with get_session() as session:
        result = await session.exec(
            select(AnnotationDocumentState).where(
                AnnotationDocumentState.case_id == case_id
            )
        )
        state = result.first()

        if state:
            state.crdt_state = crdt_state
            state.highlight_count = highlight_count
            state.last_editor = last_editor
            state.updated_at = datetime.now(UTC)
        else:
            state = AnnotationDocumentState(
                case_id=case_id,
                crdt_state=crdt_state,
                highlight_count=highlight_count,
                last_editor=last_editor,
            )
            session.add(state)

        await session.flush()
        await session.refresh(state)
        return state
