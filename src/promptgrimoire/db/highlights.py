"""CRUD operations for Highlight and HighlightComment.

Provides async database functions for the Case Brief Tool.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import select

if TYPE_CHECKING:
    from uuid import UUID

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import Highlight, HighlightComment


async def get_highlights_for_case(case_id: str) -> list[Highlight]:
    """Get all highlights for a case, ordered by creation time.

    Args:
        case_id: The case document identifier.

    Returns:
        List of Highlight objects for the case.
    """
    async with get_session() as session:
        result = await session.exec(
            select(Highlight).where(Highlight.case_id == case_id).order_by("created_at")
        )
        return list(result.all())


async def get_highlight_by_id(highlight_id: UUID) -> Highlight | None:
    """Get a single highlight by ID.

    Args:
        highlight_id: The highlight UUID.

    Returns:
        The Highlight or None if not found.
    """
    async with get_session() as session:
        return await session.get(Highlight, highlight_id)


async def create_highlight(
    case_id: str,
    tag: str,
    start_offset: int,
    end_offset: int,
    text: str,
    created_by: str,
    para_num: int | None = None,
    section_header: str | None = None,
) -> Highlight:
    """Create a new highlight.

    Args:
        case_id: The case document identifier.
        tag: The brief tag type.
        start_offset: Character position where highlight starts.
        end_offset: Character position where highlight ends.
        text: The highlighted text content.
        created_by: Display name of the user.
        para_num: Paragraph number where highlight starts (from <ol><li>).
        section_header: Nearest preceding section header (e.g., JUDGMENT).

    Returns:
        The created Highlight with generated ID.
    """
    async with get_session() as session:
        highlight = Highlight(
            case_id=case_id,
            tag=tag,
            start_offset=start_offset,
            end_offset=end_offset,
            text=text,
            created_by=created_by,
            para_num=para_num,
            section_header=section_header,
        )
        session.add(highlight)
        await session.flush()
        await session.refresh(highlight)
        return highlight


async def delete_highlight(highlight_id: UUID) -> bool:
    """Delete a highlight and its comments (cascade).

    Args:
        highlight_id: The highlight UUID.

    Returns:
        True if deleted, False if not found.
    """
    async with get_session() as session:
        highlight = await session.get(Highlight, highlight_id)
        if not highlight:
            return False
        await session.delete(highlight)
        return True


async def get_comments_for_highlight(highlight_id: UUID) -> list[HighlightComment]:
    """Get all comments for a highlight, ordered by creation time.

    Args:
        highlight_id: The parent highlight UUID.

    Returns:
        List of HighlightComment objects.
    """
    async with get_session() as session:
        result = await session.exec(
            select(HighlightComment)
            .where(HighlightComment.highlight_id == highlight_id)
            .order_by("created_at")
        )
        return list(result.all())


async def create_comment(
    highlight_id: UUID,
    author: str,
    text: str,
) -> HighlightComment:
    """Add a comment to a highlight thread.

    Args:
        highlight_id: The parent highlight UUID.
        author: Display name of the comment author.
        text: The comment content.

    Returns:
        The created HighlightComment with generated ID.
    """
    async with get_session() as session:
        comment = HighlightComment(
            highlight_id=highlight_id,
            author=author,
            text=text,
        )
        session.add(comment)
        await session.flush()
        await session.refresh(comment)
        return comment
