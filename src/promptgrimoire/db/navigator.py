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

_NAVIGATOR_SQL = text("""\
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
""")


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
    params: dict[str, object] = {
        "user_id": user_id,
        "is_privileged": is_privileged,
        "enrolled_course_ids": list(enrolled_course_ids),
        "cursor_priority": cursor.section_priority if cursor else None,
        "cursor_sort_key": cursor.sort_key if cursor else None,
        "cursor_row_id": cursor.row_id if cursor else None,
        "lim": limit + 1,  # fetch one extra to detect next page
    }

    async with get_session() as session:
        # session.exec() does not support raw text() SQL; must use
        # the underlying SQLAlchemy execute().
        result = await session.execute(_NAVIGATOR_SQL, params)
        raw_rows = result.fetchall()

    # Detect next page
    has_more = len(raw_rows) > limit
    if has_more:
        raw_rows = raw_rows[:limit]

    # Map rows to NavigatorRow.  Each row is a SQLAlchemy Row with
    # positional access matching the SELECT column order.
    rows = [
        NavigatorRow(
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
            sort_key=row[16],
            row_id=row[17],
        )
        for row in raw_rows
    ]

    next_cursor: NavigatorCursor | None = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = NavigatorCursor(
            section_priority=last.section_priority,
            sort_key=last.sort_key,
            row_id=last.row_id,
        )

    return rows, next_cursor
