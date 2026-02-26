"""Workspace navigator data loader.

Executes the UNION ALL query that powers the workspace navigator,
returning all workspace data for a user across four sections:
  1. my_work -- owned workspaces
  2. unstarted -- published activities with no workspace yet
  3. shared_with_me -- workspaces shared via explicit ACL
  4. shared_in_unit -- peer workspaces in enrolled courses

The query is documented in navigator.sql (same directory).
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, NamedTuple

from sqlalchemy import text

from promptgrimoire.db.engine import get_session

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime
    from typing import Any
    from uuid import UUID


@dataclasses.dataclass(frozen=True, slots=True)
class NavigatorRow:
    """One row from the navigator query."""

    section: str
    section_priority: int
    workspace_id: UUID | None
    activity_id: UUID | None
    activity_title: str | None
    week_title: str | None
    week_number: int | None
    course_id: UUID | None
    course_code: str | None
    course_name: str | None
    title: str | None
    updated_at: datetime | None
    owner_user_id: UUID | None
    owner_display_name: str | None
    permission: str | None
    shared_with_class: bool
    anonymous_sharing: bool
    owner_is_privileged: bool
    sort_key: datetime
    row_id: UUID


class NavigatorCursor(NamedTuple):
    """Keyset cursor for navigator pagination."""

    section_priority: int
    sort_key: datetime
    row_id: UUID


# ---------------------------------------------------------------------------
# SQL query text
# ---------------------------------------------------------------------------

# Shared CTE: all workspaces visible to :user_id across four sections.
# Binds: :user_id, :enrolled_course_ids, :is_privileged
_NAV_CTE = """\
WITH nav AS (
  -- Section 1: my_work (priority=1)
  SELECT
    'my_work'::text           AS section,
    1                         AS section_priority,
    w.id                      AS workspace_id,
    a.id                      AS activity_id,
    a.title                   AS activity_title,
    wk.title                  AS week_title,
    wk.week_number            AS week_number,
    c.id                      AS course_id,
    c.code                    AS course_code,
    c.name                    AS course_name,
    w.title                   AS title,
    w.updated_at              AS updated_at,
    acl.user_id               AS owner_user_id,
    u.display_name            AS owner_display_name,
    'owner'::text             AS permission,
    w.shared_with_class       AS shared_with_class,
    COALESCE(a.anonymous_sharing,
      c.default_anonymous_sharing, false
    )                         AS anonymous_sharing,
    false                     AS owner_is_privileged,  -- viewer privilege separate
    w.updated_at              AS sort_key,
    w.id                      AS row_id
  FROM workspace w
  JOIN acl_entry acl ON acl.workspace_id = w.id
    AND acl.user_id = :user_id
    AND acl.permission = 'owner'
  JOIN "user" u ON u.id = acl.user_id
  LEFT JOIN activity tmpl_check ON tmpl_check.template_workspace_id = w.id
  LEFT JOIN activity a ON a.id = w.activity_id
  LEFT JOIN week wk ON wk.id = a.week_id
  LEFT JOIN course c ON c.id = COALESCE(wk.course_id, w.course_id)
  WHERE tmpl_check.id IS NULL

  UNION ALL

  -- Section 2: unstarted (priority=2)
  SELECT
    'unstarted'::text         AS section,
    2                         AS section_priority,
    NULL::uuid                AS workspace_id,
    a.id                      AS activity_id,
    a.title                   AS activity_title,
    wk.title                  AS week_title,
    wk.week_number            AS week_number,
    c.id                      AS course_id,
    c.code                    AS course_code,
    c.name                    AS course_name,
    NULL::text                AS title,
    NULL::timestamptz         AS updated_at,
    NULL::uuid                AS owner_user_id,
    NULL::text                AS owner_display_name,
    NULL::text                AS permission,
    false                     AS shared_with_class,
    false                     AS anonymous_sharing,
    false                     AS owner_is_privileged,  -- no owner yet
    a.created_at              AS sort_key,
    a.id                      AS row_id
  FROM activity a
  JOIN week wk ON wk.id = a.week_id
  JOIN course c ON c.id = wk.course_id
  WHERE wk.is_published = true
    AND (wk.visible_from IS NULL OR wk.visible_from <= NOW())
    AND c.id = ANY(:enrolled_course_ids)
    AND NOT EXISTS (
      SELECT 1
      FROM workspace w2
      JOIN acl_entry acl2 ON acl2.workspace_id = w2.id
        AND acl2.user_id = :user_id
        AND acl2.permission = 'owner'
      WHERE w2.activity_id = a.id
    )

  UNION ALL

  -- Section 3: shared_with_me (priority=3)
  SELECT
    'shared_with_me'::text    AS section,
    3                         AS section_priority,
    w.id                      AS workspace_id,
    a.id                      AS activity_id,
    a.title                   AS activity_title,
    wk.title                  AS week_title,
    wk.week_number            AS week_number,
    c.id                      AS course_id,
    c.code                    AS course_code,
    c.name                    AS course_name,
    w.title                   AS title,
    w.updated_at              AS updated_at,
    owner_acl.user_id         AS owner_user_id,
    owner_u.display_name      AS owner_display_name,
    acl.permission            AS permission,
    w.shared_with_class       AS shared_with_class,
    COALESCE(a.anonymous_sharing,
      c.default_anonymous_sharing, false
    )                         AS anonymous_sharing,
    (owner_u.is_admin OR EXISTS (
      SELECT 1 FROM course_enrollment ce
      JOIN course_role cr ON cr.name = ce.role
      WHERE ce.user_id = owner_acl.user_id
        AND cr.is_staff = true
    ))                        AS owner_is_privileged,
    w.updated_at              AS sort_key,
    w.id                      AS row_id
  FROM workspace w
  JOIN acl_entry acl ON acl.workspace_id = w.id
    AND acl.user_id = :user_id
    AND acl.permission IN ('editor', 'viewer')
  JOIN acl_entry owner_acl ON owner_acl.workspace_id = w.id
    AND owner_acl.permission = 'owner'
  JOIN "user" owner_u ON owner_u.id = owner_acl.user_id
  LEFT JOIN activity a ON a.id = w.activity_id
  LEFT JOIN week wk ON wk.id = a.week_id
  LEFT JOIN course c ON c.id = COALESCE(wk.course_id, w.course_id)

  UNION ALL

  -- Section 4a: shared_in_unit — activity-placed workspaces (priority=4)
  SELECT
    'shared_in_unit'::text    AS section,
    4                         AS section_priority,
    w.id                      AS workspace_id,
    a.id                      AS activity_id,
    a.title                   AS activity_title,
    wk.title                  AS week_title,
    wk.week_number            AS week_number,
    c.id                      AS course_id,
    c.code                    AS course_code,
    c.name                    AS course_name,
    w.title                   AS title,
    w.updated_at              AS updated_at,
    owner_acl.user_id         AS owner_user_id,
    owner_u.display_name      AS owner_display_name,
    'peer'::text              AS permission,
    w.shared_with_class       AS shared_with_class,
    COALESCE(a.anonymous_sharing,
      c.default_anonymous_sharing, false
    )                         AS anonymous_sharing,
    (owner_u.is_admin OR EXISTS (
      SELECT 1 FROM course_enrollment ce
      JOIN course_role cr ON cr.name = ce.role
      WHERE ce.user_id = owner_acl.user_id
        AND ce.course_id = c.id
        AND cr.is_staff = true
    ))                        AS owner_is_privileged,
    w.updated_at              AS sort_key,
    w.id                      AS row_id
  FROM workspace w
  JOIN acl_entry owner_acl ON owner_acl.workspace_id = w.id
    AND owner_acl.permission = 'owner'
  JOIN "user" owner_u ON owner_u.id = owner_acl.user_id
  LEFT JOIN activity tmpl_check ON tmpl_check.template_workspace_id = w.id
  JOIN activity a ON a.id = w.activity_id
  JOIN week wk ON wk.id = a.week_id
  JOIN course c ON c.id = wk.course_id
  WHERE tmpl_check.id IS NULL
    AND c.id = ANY(:enrolled_course_ids)
    AND owner_acl.user_id != :user_id
    AND (
      :is_privileged = true
      OR (
        w.shared_with_class = true
        AND COALESCE(a.allow_sharing, c.default_allow_sharing) = true
      )
    )

  UNION ALL

  -- Section 4b: shared_in_unit — loose workspaces (priority=4)
  SELECT
    'shared_in_unit'::text    AS section,
    4                         AS section_priority,
    w.id                      AS workspace_id,
    NULL::uuid                AS activity_id,
    NULL::text                AS activity_title,
    NULL::text                AS week_title,
    NULL::int                 AS week_number,
    c.id                      AS course_id,
    c.code                    AS course_code,
    c.name                    AS course_name,
    w.title                   AS title,
    w.updated_at              AS updated_at,
    owner_acl.user_id         AS owner_user_id,
    owner_u.display_name      AS owner_display_name,
    'peer'::text              AS permission,
    w.shared_with_class       AS shared_with_class,
    COALESCE(c.default_anonymous_sharing, false
    )                         AS anonymous_sharing,
    (owner_u.is_admin OR EXISTS (
      SELECT 1 FROM course_enrollment ce
      JOIN course_role cr ON cr.name = ce.role
      WHERE ce.user_id = owner_acl.user_id
        AND ce.course_id = c.id
        AND cr.is_staff = true
    ))                        AS owner_is_privileged,
    w.updated_at              AS sort_key,
    w.id                      AS row_id
  FROM workspace w
  JOIN acl_entry owner_acl ON owner_acl.workspace_id = w.id
    AND owner_acl.permission = 'owner'
  JOIN "user" owner_u ON owner_u.id = owner_acl.user_id
  JOIN course c ON c.id = w.course_id
  WHERE w.activity_id IS NULL
    AND c.id = ANY(:enrolled_course_ids)
    AND owner_acl.user_id != :user_id
    AND (
      :is_privileged = true
      OR (
        w.shared_with_class = true
        AND c.default_allow_sharing = true
      )
    )

)
"""

# Paginated query for infinite scroll.
# Additional binds: :cursor_priority, :cursor_sort_key, :cursor_row_id, :lim
_NAVIGATOR_SQL = text(
    _NAV_CTE
    + """\
SELECT *
FROM nav
WHERE (
  CAST(:cursor_priority AS int) IS NULL
  OR section_priority > CAST(:cursor_priority AS int)
  OR (section_priority = CAST(:cursor_priority AS int)
      AND sort_key < CAST(:cursor_sort_key AS timestamptz))
  OR (section_priority = CAST(:cursor_priority AS int)
      AND sort_key = CAST(:cursor_sort_key AS timestamptz)
      AND row_id > CAST(:cursor_row_id AS uuid))
)
ORDER BY section_priority ASC, sort_key DESC, row_id ASC
LIMIT :lim
"""
)

# Combined search: nav CTE (permissions) + FTS in one query.
# Additional binds: :query, :lim
_HEADLINE_OPTIONS = (
    "MaxWords=35, MinWords=15, MaxFragments=3, StartSel=<mark>, StopSel=</mark>"
)
# nosec B608 -- f-string only interpolates module constants (_NAV_CTE,
# _HEADLINE_OPTIONS); all user input is bound via :query.
_SEARCH_SQL = text(
    _NAV_CTE
    + f"""\
, visible_ws AS (
  SELECT DISTINCT workspace_id FROM nav WHERE workspace_id IS NOT NULL
),
fts AS (
  SELECT wd.workspace_id AS ws_id,
    ts_headline('english',
      regexp_replace(wd.content, '<[^>]+>', ' ', 'g'),
      websearch_to_tsquery('english', :query),
      '{_HEADLINE_OPTIONS}'
    ) AS snippet,
    ts_rank(
      to_tsvector('english', regexp_replace(wd.content, '<[^>]+>', ' ', 'g')),
      websearch_to_tsquery('english', :query)
    ) AS rank
  FROM workspace_document wd
  WHERE wd.workspace_id IN (SELECT workspace_id FROM visible_ws)
    AND to_tsvector('english', regexp_replace(wd.content, '<[^>]+>', ' ', 'g'))
      @@ websearch_to_tsquery('english', :query)
  UNION ALL
  SELECT w.id AS ws_id,
    ts_headline('english',
      COALESCE(w.title, '') || ' '
        || COALESCE(a.title, '') || ' '
        || COALESCE(w.search_text, ''),
      websearch_to_tsquery('english', :query),
      '{_HEADLINE_OPTIONS}'
    ) AS snippet,
    ts_rank(
      to_tsvector('english',
        COALESCE(w.title, '') || ' '
          || COALESCE(a.title, '') || ' '
          || COALESCE(w.search_text, '')),
      websearch_to_tsquery('english', :query)
    ) AS rank
  FROM workspace w
  LEFT JOIN activity a ON a.id = w.activity_id
  WHERE w.id IN (SELECT workspace_id FROM visible_ws)
    AND to_tsvector('english',
      COALESCE(w.title, '') || ' '
        || COALESCE(a.title, '') || ' '
        || COALESCE(w.search_text, ''))
      @@ websearch_to_tsquery('english', :query)
),
best_fts AS (
  SELECT DISTINCT ON (ws_id) ws_id, snippet, rank
  FROM fts
  ORDER BY ws_id, rank DESC
)
SELECT nav.*, best_fts.snippet, best_fts.rank
FROM nav
JOIN best_fts ON best_fts.ws_id = nav.workspace_id
ORDER BY best_fts.rank DESC
LIMIT :lim
"""  # nosec B608
)


def _row_from_tuple(row: Any) -> NavigatorRow:
    """Map a single positional SQLAlchemy Row to a NavigatorRow."""
    return NavigatorRow(
        section=row[0],
        section_priority=row[1],
        workspace_id=row[2],
        activity_id=row[3],
        activity_title=row[4],
        week_title=row[5],
        week_number=row[6],
        course_id=row[7],
        course_code=row[8],
        course_name=row[9],
        title=row[10],
        updated_at=row[11],
        owner_user_id=row[12],
        owner_display_name=row[13],
        permission=row[14],
        shared_with_class=row[15],
        anonymous_sharing=row[16],
        owner_is_privileged=row[17],
        sort_key=row[18],
        row_id=row[19],
    )


def _rows_from_raw(raw_rows: Sequence[Any]) -> list[NavigatorRow]:
    """Map positional SQLAlchemy Row tuples to NavigatorRow dataclasses."""
    return [_row_from_tuple(row) for row in raw_rows]


def _base_params(
    user_id: UUID,
    is_privileged: bool,
    enrolled_course_ids: Sequence[UUID],
) -> dict[str, object]:
    """Common bind parameters shared by all navigator queries."""
    return {
        "user_id": user_id,
        "is_privileged": is_privileged,
        "enrolled_course_ids": list(enrolled_course_ids),
    }


async def load_navigator_page(
    user_id: UUID,
    is_privileged: bool,
    enrolled_course_ids: Sequence[UUID],
    cursor: NavigatorCursor | None = None,
    limit: int = 50,
) -> tuple[list[NavigatorRow], NavigatorCursor | None]:
    """Load one page of workspace navigator data.

    Executes the UNION ALL query across all four sections and returns
    rows with an optional next-page cursor.

    Parameters
    ----------
    user_id : UUID
        The authenticated user.
    is_privileged : bool
        Whether user has staff role in any enrolled course.
    enrolled_course_ids : Sequence[UUID]
        Courses the user is enrolled in.
    cursor : NavigatorCursor | None
        Keyset cursor from a previous page, or None for the first page.
    limit : int
        Maximum rows per page (default 50).

    Returns
    -------
    tuple[list[NavigatorRow], NavigatorCursor | None]
        (rows, next_cursor). next_cursor is None if there are no more pages.
    """
    params = _base_params(user_id, is_privileged, enrolled_course_ids)
    params.update(
        {
            "cursor_priority": cursor.section_priority if cursor else None,
            "cursor_sort_key": cursor.sort_key if cursor else None,
            "cursor_row_id": cursor.row_id if cursor else None,
            "lim": limit + 1,  # fetch one extra to detect next page
        }
    )

    async with get_session() as session:
        result = await session.execute(_NAVIGATOR_SQL, params)
        raw_rows = result.fetchall()

    # Detect next page
    has_more = len(raw_rows) > limit
    if has_more:
        raw_rows = raw_rows[:limit]

    rows = _rows_from_raw(raw_rows)

    next_cursor: NavigatorCursor | None = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = NavigatorCursor(
            section_priority=last.section_priority,
            sort_key=last.sort_key,
            row_id=last.row_id,
        )

    return rows, next_cursor


@dataclasses.dataclass(frozen=True, slots=True)
class SearchHit:
    """A NavigatorRow with FTS snippet and rank."""

    row: NavigatorRow
    snippet: str
    rank: float


async def search_navigator(
    query: str,
    *,
    user_id: UUID,
    is_privileged: bool,
    enrolled_course_ids: Sequence[UUID],
    limit: int = 50,
) -> list[SearchHit]:
    """Search visible workspaces via FTS in a single query.

    The nav CTE restricts to workspaces the user can see (via ACL
    WHERE clauses). FTS runs only against those workspaces.
    Returns NavigatorRows with snippet and rank, ordered by relevance.
    """
    stripped = query.strip()
    if len(stripped) < 3:
        return []

    params = _base_params(user_id, is_privileged, enrolled_course_ids)
    params["query"] = stripped
    params["lim"] = limit

    async with get_session() as session:
        result = await session.execute(_SEARCH_SQL, params)
        raw_rows = result.fetchall()

    # NavigatorRow fields followed by snippet + rank from the FTS join
    nav_field_count = len(dataclasses.fields(NavigatorRow))
    return [
        SearchHit(
            row=_row_from_tuple(r),
            snippet=str(r[nav_field_count]),
            rank=float(r[nav_field_count + 1]),
        )
        for r in raw_rows
    ]
