-- PromptGrimoire usage snapshot query
-- Recovered 2026-06-01 from session 4687f652 (originally written 2026-05-01, lost to /tmp).
--
-- Run on prod (you must run it; this machine has no prod access):
--   ssh grimoire.drbbs.org
--   sudo -u promptgrimoire psql -d promptgrimoire -t -A -f - < scripts/grimoire_usage_snapshot.sql | jq . > snapshot.json
-- Or from an interactive psql session:  \i scripts/grimoire_usage_snapshot.sql
--
-- Provenance note (from the 6 April snapshot): the `totals` block dedupes users,
-- the per-unit fields do not. Summing per-unit has_logged_in double-counts anyone
-- cross-enrolled across units (the LAWS cohort overlaps heavily). Cite `totals` for
-- defensible distinct-human numbers, not the per-unit sum.

\pset pager off
\pset format unaligned
\pset tuples_only on

SELECT json_build_object(
  'units', (
    SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json) FROM (
      SELECT
        um.code || ' — ' || um.name || ' (' || um.semester || ')' AS unit,
        um.code,
        um.is_archived,

        -- Enrolment
        COUNT(DISTINCT ce.user_id) FILTER (WHERE ce.role = 'student')                              AS enrolled_students,
        COUNT(DISTINCT ce.user_id) FILTER (WHERE ce.role IN ('instructor','coordinator','tutor')) AS enrolled_staff,
        COUNT(DISTINCT ce.user_id) FILTER (WHERE u.stytch_member_id IS NULL)                       AS never_logged_in,
        COUNT(DISTINCT ce.user_id) FILTER (WHERE u.last_login IS NOT NULL)                         AS has_logged_in,

        -- Content volume
        COUNT(DISTINCT w.id)                                                AS workspaces,
        COUNT(DISTINCT wd.id)                                               AS documents,
        COUNT(DISTINCT w.id) FILTER (WHERE w.shared_with_class = TRUE)      AS shared_workspaces,
        COUNT(DISTINCT a.id)                                                AS activities,
        COUNT(DISTINCT wk.id)                                               AS weeks,
        COUNT(DISTINCT wk.id) FILTER (WHERE wk.is_published = TRUE)         AS published_weeks,

        -- Momentum proxies (week.published_at does not exist; using created_at of published weeks)
        MIN(wk.created_at)   FILTER (WHERE wk.is_published = TRUE)          AS first_published_week_created_at,
        MIN(wk.visible_from) FILTER (WHERE wk.is_published = TRUE)          AS earliest_scheduled_publish_at,
        MIN(w.created_at)                                                   AS first_workspace_at,
        MAX(w.created_at)                                                   AS last_workspace_at,
        MIN(wd.created_at)                                                  AS first_document_at,
        MAX(wd.created_at)                                                  AS last_document_at,

        -- Engagement = enrolled students with >=1 owner ACL on a workspace under this unit
        (
          SELECT COUNT(DISTINCT acl_x.user_id)
          FROM acl_entry acl_x
          JOIN workspace w_x ON w_x.id = acl_x.workspace_id
          JOIN activity  a_x ON a_x.id = w_x.activity_id
          JOIN week     wk_x ON wk_x.id = a_x.week_id
          JOIN course_enrollment ce_x
            ON ce_x.user_id = acl_x.user_id
           AND ce_x.course_id = wk_x.course_id
           AND ce_x.role = 'student'
          WHERE wk_x.course_id = um.id
            AND acl_x.permission = 'owner'
        ) AS engaged_students,

        -- Activities that have any non-template student workspace clone
        (
          SELECT COUNT(DISTINCT a_y.id)
          FROM activity a_y
          JOIN week   wk_y ON wk_y.id = a_y.week_id
          JOIN workspace w_y ON w_y.activity_id = a_y.id
          WHERE wk_y.course_id = um.id
            AND (a_y.template_workspace_id IS NULL OR w_y.id <> a_y.template_workspace_id)
        ) AS activities_with_clones

      FROM course um
      LEFT JOIN course_enrollment ce ON ce.course_id = um.id
      LEFT JOIN "user" u             ON u.id = ce.user_id
      LEFT JOIN week wk              ON wk.course_id = um.id
      LEFT JOIN activity a           ON a.week_id = wk.id
      LEFT JOIN workspace w          ON w.activity_id = a.id
      LEFT JOIN workspace_document wd ON wd.workspace_id = w.id
      GROUP BY um.id, um.code, um.name, um.semester, um.is_archived
      ORDER BY um.is_archived, um.semester DESC, um.code
    ) t
  ),

  'totals', (
    SELECT row_to_json(s) FROM (
      SELECT
        COUNT(DISTINCT u.id)                                          AS total_users,
        COUNT(DISTINCT u.id) FILTER (WHERE u.last_login IS NOT NULL)  AS total_logged_in,
        (SELECT COUNT(*) FROM workspace)                              AS total_workspaces,
        (SELECT COUNT(*) FROM workspace_document)                     AS total_documents,

        (SELECT COUNT(DISTINCT user_id) FROM course_enrollment)
                                                                      AS unique_enrolled_users,
        (SELECT COUNT(DISTINCT user_id) FROM course_enrollment WHERE role = 'student')
                                                                      AS unique_enrolled_students,
        (SELECT COUNT(DISTINCT user_id) FROM course_enrollment
          WHERE role IN ('instructor','coordinator','tutor'))         AS unique_enrolled_staff,

        (
          SELECT COUNT(DISTINCT acl_z.user_id)
          FROM acl_entry acl_z
          JOIN course_enrollment ce_z
            ON ce_z.user_id = acl_z.user_id AND ce_z.role = 'student'
          WHERE acl_z.permission = 'owner' AND acl_z.workspace_id IS NOT NULL
        )                                                              AS unique_students_with_owned_workspace,

        (
          SELECT COUNT(*) FROM (
            SELECT user_id
            FROM course_enrollment
            WHERE role = 'student'
            GROUP BY user_id
            HAVING COUNT(DISTINCT course_id) > 1
          ) m
        )                                                              AS students_enrolled_in_multiple_units
      FROM "user" u
    ) s
  ),

  'momentum_workspaces_by_day', (
    SELECT json_agg(row_to_json(m) ORDER BY m.day) FROM (
      SELECT date_trunc('day', w.created_at)::date AS day,
             COUNT(*) AS workspaces_created
      FROM workspace w
      WHERE w.created_at >= '2026-01-01'
      GROUP BY date_trunc('day', w.created_at)
    ) m
  ),
  'momentum_documents_by_day', (
    SELECT json_agg(row_to_json(m) ORDER BY m.day) FROM (
      SELECT date_trunc('day', wd.created_at)::date AS day,
             COUNT(*) AS documents_created
      FROM workspace_document wd
      WHERE wd.created_at >= '2026-01-01'
      GROUP BY date_trunc('day', wd.created_at)
    ) m
  )
);
