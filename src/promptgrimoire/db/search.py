"""Full-text search infrastructure for workspace content.

Provides CRDT text extraction for FTS indexing and query helpers
for searching workspace documents and CRDT-sourced text.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import text

from promptgrimoire.crdt.annotation_doc import AnnotationDocument
from promptgrimoire.db.engine import get_session

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


_HEADLINE_OPTIONS = (
    "MaxWords=35, MinWords=15, MaxFragments=3, StartSel=<mark>, StopSel=</mark>"
)


@dataclasses.dataclass(frozen=True, slots=True)
class FTSResult:
    """A single full-text search result.

    Attributes:
        workspace_id: UUID of the workspace containing the match.
        snippet: HTML snippet with matched terms wrapped in <mark>.
        rank: ts_rank score (higher = more relevant).
        source: Origin of match -- "document" or "workspace".
    """

    workspace_id: UUID
    snippet: str
    rank: float
    source: str  # "document" or "workspace"


async def search_workspace_content(
    query: str,
    workspace_ids: Sequence[UUID] | None = None,
    limit: int = 50,
) -> list[FTSResult]:
    """Search workspace documents and CRDT-sourced text via FTS.

    Queries both the workspace_document content index and the
    workspace search_text index, returning a UNION ordered by
    ts_rank descending.

    Args:
        query: User search string. Passed to websearch_to_tsquery.
            Returns empty list if stripped query has <3 characters.
        workspace_ids: Optional filter -- only return results for
            these workspaces. None means no filter.
        limit: Maximum number of results to return.

    Returns:
        List of FTSResult ordered by relevance (highest rank first).
    """
    stripped = query.strip()
    if len(stripped) < 3:
        return []

    # Build optional workspace filter clauses (separate per table alias)
    doc_ws_filter = ""
    ws_ws_filter = ""
    params: dict[str, object] = {
        "query": stripped,
        "limit": limit,
    }
    if workspace_ids is not None:
        ws_id_strs = [str(wid) for wid in workspace_ids]
        doc_ws_filter = "AND wd.workspace_id = ANY(:ws_ids)"
        ws_ws_filter = "AND w.id = ANY(:ws_ids)"
        params["ws_ids"] = ws_id_strs

    # Document content search (HTML-stripped via regexp_replace)
    # nosec B608 -- f-string only interpolates module constants and
    # hardcoded filter clauses; all user input is bound via :query.
    doc_sql = f"""
        SELECT
            wd.workspace_id AS ws_id,
            ts_headline(
                'english',
                regexp_replace(wd.content, '<[^>]+>', ' ', 'g'),
                websearch_to_tsquery('english', :query),
                '{_HEADLINE_OPTIONS}'
            ) AS snippet,
            ts_rank(
                to_tsvector(
                    'english',
                    regexp_replace(wd.content, '<[^>]+>', ' ', 'g')
                ),
                websearch_to_tsquery('english', :query)
            ) AS rank,
            'document' AS source
        FROM workspace_document wd
        WHERE to_tsvector(
            'english',
            regexp_replace(wd.content, '<[^>]+>', ' ', 'g')
        ) @@ websearch_to_tsquery('english', :query)
        {doc_ws_filter}
    """  # nosec B608

    # Workspace search_text search (CRDT-extracted text)
    ws_sql = f"""
        SELECT
            w.id AS ws_id,
            ts_headline(
                'english',
                COALESCE(w.search_text, ''),
                websearch_to_tsquery('english', :query),
                '{_HEADLINE_OPTIONS}'
            ) AS snippet,
            ts_rank(
                to_tsvector(
                    'english',
                    COALESCE(w.search_text, '')
                ),
                websearch_to_tsquery('english', :query)
            ) AS rank,
            'workspace' AS source
        FROM workspace w
        WHERE to_tsvector(
            'english',
            COALESCE(w.search_text, '')
        ) @@ websearch_to_tsquery('english', :query)
        {ws_ws_filter}
    """  # nosec B608

    combined_sql = f"""
        SELECT ws_id, snippet, rank, source
        FROM (
            {doc_sql}
            UNION ALL
            {ws_sql}
        ) combined
        ORDER BY rank DESC
        LIMIT :limit
    """  # nosec B608

    async with get_session() as session:
        result = await session.execute(  # type: ignore[deprecated]
            text(combined_sql), params
        )
        rows = result.fetchall()

    return [
        FTSResult(
            workspace_id=UUID(str(row[0])),
            snippet=str(row[1]),
            rank=float(row[2]),
            source=str(row[3]),
        )
        for row in rows
    ]


def extract_searchable_text(
    crdt_state: bytes | None,
    tag_names: dict[str, str],
) -> str:
    """Extract searchable text from CRDT state for FTS indexing.

    Pure function: deserialises CRDT state and concatenates all
    textual content (highlight text, resolved tag names, comment
    text, response draft markdown, general notes).

    Args:
        crdt_state: Serialised pycrdt state bytes, or None.
        tag_names: Mapping of tag UUID strings to tag display
            names. Tags not found here are included as-is
            (legacy BriefTag fallback).

    Returns:
        Concatenated searchable text, or empty string if
        crdt_state is None.
    """
    if crdt_state is None:
        return ""

    doc = AnnotationDocument("extraction-tmp")
    doc.apply_update(crdt_state)

    parts: list[str] = []

    # Extract from highlights: text, resolved tags, comments
    for highlight in doc.get_all_highlights():
        if hl_text := highlight.get("text", ""):
            parts.append(hl_text)

        if tag := highlight.get("tag", ""):
            parts.append(tag_names.get(tag, tag))

        for comment in highlight.get("comments", []):
            if comment_text := comment.get("text", ""):
                parts.append(comment_text)

    # Response draft markdown (Tab 3)
    response_draft = doc.get_response_draft_markdown()
    if response_draft:
        parts.append(response_draft)

    # General notes
    general_notes = doc.get_general_notes()
    if general_notes:
        parts.append(general_notes)

    return "\n".join(parts)
