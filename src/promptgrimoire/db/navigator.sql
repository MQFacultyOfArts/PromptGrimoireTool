-- Navigator UNION ALL query for workspace-navigator-196
--
-- Returns all workspace data for a user across four sections in a single query.
-- This file is documentation for human review; the actual query is in navigator.py.
--
-- Parameters:
--   :user_id              UUID    The authenticated user
--   :is_privileged        bool    Whether user has staff role in any enrolled course
--   :enrolled_course_ids  UUID[]  Courses the user is enrolled in
--   :cursor_priority      int     Keyset cursor: section_priority (NULL for first page)
--   :cursor_sort_key      timestamptz  Keyset cursor: sort_key (NULL for first page)
--   :cursor_row_id        UUID    Keyset cursor: row_id (NULL for first page)
--   :lim                  int     Rows per page (default 50) -- fetch limit+1

WITH nav AS (
  -- Section 1: my_work (priority=1)
  -- All workspaces where user is owner, excluding templates.
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
  -- Exclude templates: anti-join against activity.template_workspace_id
  LEFT JOIN activity tmpl_check ON tmpl_check.template_workspace_id = w.id
  -- Activity context (optional -- loose workspaces have no activity)
  LEFT JOIN activity a ON a.id = w.activity_id
  LEFT JOIN week wk ON wk.id = a.week_id
  -- Course context: either via activity->week->course or via workspace.course_id
  LEFT JOIN course c ON c.id = COALESCE(wk.course_id, w.course_id)
  WHERE tmpl_check.id IS NULL  -- not a template

  UNION ALL

  -- Section 2: unstarted (priority=2)
  -- Published activities in enrolled courses where user owns no workspace.
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
  -- Workspaces where user has explicit editor/viewer ACL (not owner).
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
  -- Get owner info
  JOIN acl_entry owner_acl ON owner_acl.workspace_id = w.id
    AND owner_acl.permission = 'owner'
  JOIN "user" owner_u ON owner_u.id = owner_acl.user_id
  -- Activity context
  LEFT JOIN activity a ON a.id = w.activity_id
  LEFT JOIN week wk ON wk.id = a.week_id
  LEFT JOIN course c ON c.id = COALESCE(wk.course_id, w.course_id)

  UNION ALL

  -- Section 4: shared_in_unit (priority=4)
  -- Peer workspaces visible to the user in their enrolled courses.
  --
  -- Student view (is_privileged=FALSE):
  --   Only shared_with_class=TRUE workspaces in activities where sharing enabled.
  --   Excludes user's own workspaces.
  --
  -- Instructor view (is_privileged=TRUE):
  --   ALL non-template student workspaces in enrolled courses.
  --
  -- Activity-placed workspaces:
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
  -- Exclude templates
  LEFT JOIN activity tmpl_check ON tmpl_check.template_workspace_id = w.id
  -- Activity context
  JOIN activity a ON a.id = w.activity_id
  JOIN week wk ON wk.id = a.week_id
  JOIN course c ON c.id = wk.course_id
  WHERE tmpl_check.id IS NULL
    AND c.id = ANY(:enrolled_course_ids)
    -- Exclude user's own workspaces
    AND owner_acl.user_id != :user_id
    -- Student: only shared + sharing enabled
    AND (
      :is_privileged = true
      OR (
        w.shared_with_class = true
        AND COALESCE(a.allow_sharing, c.default_allow_sharing) = true
      )
    )

  UNION ALL

  -- Section 4 continued: loose workspaces (course-placed, no activity)
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
      OR w.shared_with_class = true
    )

)
SELECT *
FROM nav
WHERE (
  CAST(:cursor_priority AS int) IS NULL
  OR (section_priority > CAST(:cursor_priority AS int))
  OR (section_priority = CAST(:cursor_priority AS int) AND sort_key < CAST(:cursor_sort_key AS timestamptz))
  OR (section_priority = CAST(:cursor_priority AS int) AND sort_key = CAST(:cursor_sort_key AS timestamptz)
      AND row_id > CAST(:cursor_row_id AS uuid))
)
ORDER BY section_priority ASC, sort_key DESC, row_id ASC
LIMIT :lim;
