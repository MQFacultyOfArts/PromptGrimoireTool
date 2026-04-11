"""Database fixture helpers for annotation E2E tests.

Direct-SQL workspace creation for tests that need a workspace but
are NOT testing workspace creation itself.
"""

from __future__ import annotations

import os
import uuid

from sqlalchemy import Engine, create_engine, text

from tests.e2e.tag_helpers import _seed_tags_for_workspace


def _get_sync_engine() -> Engine:
    """Build a synchronous SQLAlchemy engine from DATABASE__URL.

    Converts the asyncpg URL to psycopg for synchronous access.
    All E2E database helpers should use this instead of raw psycopg.
    """
    db_url = os.environ.get("DATABASE__URL", "")
    if not db_url:
        msg = "DATABASE__URL not configured"
        raise RuntimeError(msg)
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    return create_engine(sync_url)


def grant_acl(email: str, workspace_id: str, *, permission: str = "owner") -> None:
    """Grant an ACL entry on a workspace to a user (looked up by email).

    Uses SQLAlchemy with DATABASE__URL. Idempotent (ON CONFLICT DO NOTHING).
    """
    engine = _get_sync_engine()
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text('SELECT id FROM "user" WHERE email = :email'),
                {"email": email},
            ).first()
            if not row:
                msg = f"User not found in DB: {email}"
                raise RuntimeError(msg)
            conn.execute(
                text(
                    "INSERT INTO acl_entry"
                    " (id, workspace_id, user_id, permission, created_at)"
                    " VALUES (gen_random_uuid(),"
                    " CAST(:ws AS uuid), :uid, :perm, now())"
                    " ON CONFLICT DO NOTHING"
                ),
                {"ws": workspace_id, "uid": row[0], "perm": permission},
            )
    finally:
        engine.dispose()


def _create_workspace_via_db(
    user_email: str,
    html_content: str,
    *,
    source_type: str = "text",
    seed_tags: bool = True,
) -> str:
    """Create a workspace with content via direct DB operations.

    Creates workspace, document, and ACL entry in a single transaction,
    then optionally seeds Legal Case Brief tags.

    This bypasses the UI and input pipeline, so the caller must provide
    pre-processed HTML content (e.g. ``<p>My text here</p>``).

    Use this for tests that need a workspace but are NOT testing workspace
    creation itself.  Tests that test the creation flow (e.g. instructor
    workflow) should continue using ``setup_workspace_with_content()``.

    Args:
        user_email: Email of the authenticated user (must exist in DB).
        html_content: Pre-processed HTML content for the document.
        source_type: Content type (``"text"``, ``"html"``, etc.).
        seed_tags: If True (default), seed Legal Case Brief tags.

    Returns:
        workspace_id as string.

    Raises:
        RuntimeError: If DATABASE__URL is not configured or user not found.
    """
    engine = _get_sync_engine()

    workspace_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())

    try:
        with engine.begin() as conn:
            # Look up user
            row = conn.execute(
                text('SELECT id FROM "user" WHERE email = :email'),
                {"email": user_email},
            ).first()
            if not row:
                msg = f"User not found in DB: {user_email}"
                raise RuntimeError(msg)
            user_id = row[0]

            # Create workspace
            conn.execute(
                text(
                    "INSERT INTO workspace"
                    " (id, enable_save_as_draft, created_at, updated_at)"
                    " VALUES (CAST(:id AS uuid), false, now(), now())"
                ),
                {"id": workspace_id},
            )

            # Create workspace document
            conn.execute(
                text(
                    "INSERT INTO workspace_document"
                    " (id, workspace_id, type, content,"
                    "  source_type, order_index, created_at)"
                    " VALUES (CAST(:id AS uuid), CAST(:ws AS uuid),"
                    " :type, :content, :source_type, 0, now())"
                ),
                {
                    "id": doc_id,
                    "ws": workspace_id,
                    "type": "source",
                    "content": html_content,
                    "source_type": source_type,
                },
            )

            # Create ACL entry (owner permission)
            conn.execute(
                text(
                    "INSERT INTO acl_entry"
                    " (id, workspace_id, user_id, permission, created_at)"
                    " VALUES (gen_random_uuid(),"
                    " CAST(:ws AS uuid), :uid, 'owner', now())"
                ),
                {"ws": workspace_id, "uid": user_id},
            )
    finally:
        engine.dispose()

    if seed_tags:
        _seed_tags_for_workspace(workspace_id)

    return workspace_id


def _create_multi_doc_workspace(
    user_email: str,
    documents: list[tuple[str, str]],
    *,
    seed_tags: bool = True,
) -> str:
    """Create a workspace with multiple documents via direct DB.

    Args:
        user_email: Owner email (must exist in DB).
        documents: List of (title, html_content) pairs.
        seed_tags: If True, seed Legal Case Brief tags.

    Returns:
        workspace_id as string.
    """
    engine = _get_sync_engine()

    workspace_id = str(uuid.uuid4())

    with engine.begin() as conn:
        row = conn.execute(
            text('SELECT id FROM "user" WHERE email = :email'),
            {"email": user_email},
        ).first()
        if not row:
            msg = f"User not found in DB: {user_email}"
            raise RuntimeError(msg)
        user_id = row[0]

        conn.execute(
            text(
                "INSERT INTO workspace"
                " (id, enable_save_as_draft, created_at, updated_at)"
                " VALUES (CAST(:id AS uuid), false, now(), now())"
            ),
            {"id": workspace_id},
        )

        for i, (title, html_content) in enumerate(documents):
            doc_id = str(uuid.uuid4())
            conn.execute(
                text(
                    "INSERT INTO workspace_document"
                    " (id, workspace_id, type, title, content,"
                    "  source_type, order_index, created_at)"
                    " VALUES (CAST(:id AS uuid), CAST(:ws AS uuid),"
                    " :type, :title, :content, :source_type, :order_index, now())"
                ),
                {
                    "id": doc_id,
                    "ws": workspace_id,
                    "type": "source",
                    "title": title,
                    "content": html_content,
                    "source_type": "text",
                    "order_index": i,
                },
            )

        conn.execute(
            text(
                "INSERT INTO acl_entry"
                " (id, workspace_id, user_id, permission, created_at)"
                " VALUES (gen_random_uuid(),"
                " CAST(:ws AS uuid), :uid, 'owner', now())"
            ),
            {"ws": workspace_id, "uid": user_id},
        )

    engine.dispose()

    if seed_tags:
        _seed_tags_for_workspace(workspace_id)

    return workspace_id


def _create_workspace_no_tag_permission(user_email: str) -> str:
    """Create a workspace under an activity with tag creation disabled.

    Builds the full hierarchy (course -> week -> activity -> workspace)
    via direct DB operations. The course has
    ``default_allow_tag_creation=False`` so the activity inherits it.
    The user is granted ``editor`` permission (can annotate but not
    create tags).

    Follows the same sync-DB pattern as ``_create_workspace_via_db``
    and ``_grant_workspace_access`` in the E2E test infrastructure.

    Args:
        user_email: Email of the user (must exist in DB).

    Returns:
        workspace_id as string.
    """
    engine = _get_sync_engine()

    course_id = str(uuid.uuid4())
    week_id = str(uuid.uuid4())
    activity_id = str(uuid.uuid4())
    template_ws_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())

    with engine.begin() as conn:
        # Look up user
        row = conn.execute(
            text('SELECT id FROM "user" WHERE email = :email'),
            {"email": user_email},
        ).first()
        if not row:
            msg = f"User not found in DB: {user_email}"
            raise RuntimeError(msg)
        user_id = row[0]

        # Create course with tag creation disabled
        conn.execute(
            text(
                "INSERT INTO course"
                " (id, code, name, semester, is_archived,"
                "  default_copy_protection, default_allow_sharing,"
                "  default_anonymous_sharing, default_allow_tag_creation,"
                "  created_at)"
                " VALUES (CAST(:id AS uuid), :code, :name, :semester,"
                "  false, false, false, false, false, now())"
            ),
            {
                "id": course_id,
                "code": f"NOTAG-{uuid.uuid4().hex[:6]}",
                "name": "No Tag Creation Test",
                "semester": "2026-T1",
            },
        )

        # Create week
        conn.execute(
            text(
                "INSERT INTO week"
                " (id, course_id, week_number, title,"
                "  is_published, created_at)"
                " VALUES (CAST(:id AS uuid), CAST(:cid AS uuid),"
                "  1, :title, true, now())"
            ),
            {"id": week_id, "cid": course_id, "title": "Week 1"},
        )

        # Create template workspace (required by activity FK)
        conn.execute(
            text(
                "INSERT INTO workspace"
                " (id, enable_save_as_draft, created_at, updated_at)"
                " VALUES (CAST(:id AS uuid), false, now(), now())"
            ),
            {"id": template_ws_id},
        )

        # Create activity (allow_tag_creation=NULL inherits course default=False)
        conn.execute(
            text(
                "INSERT INTO activity"
                " (id, week_id, template_workspace_id, title,"
                "  created_at, updated_at)"
                " VALUES (CAST(:id AS uuid), CAST(:wid AS uuid),"
                "  CAST(:twid AS uuid), :title, now(), now())"
            ),
            {
                "id": activity_id,
                "wid": week_id,
                "twid": template_ws_id,
                "title": "No Tags Activity",
            },
        )

        # Create user's workspace placed under the activity
        conn.execute(
            text(
                "INSERT INTO workspace"
                " (id, activity_id, enable_save_as_draft,"
                "  created_at, updated_at)"
                " VALUES (CAST(:id AS uuid), CAST(:aid AS uuid),"
                "  false, now(), now())"
            ),
            {"id": workspace_id, "aid": activity_id},
        )

        # Create workspace document
        conn.execute(
            text(
                "INSERT INTO workspace_document"
                " (id, workspace_id, type, content,"
                "  source_type, order_index, created_at)"
                " VALUES (CAST(:id AS uuid), CAST(:ws AS uuid),"
                "  'source', :content, 'text', 0, now())"
            ),
            {
                "id": doc_id,
                "ws": workspace_id,
                "content": (
                    "<p>No-permission test content for tag creation gating.</p>"
                ),
            },
        )

        # Grant editor permission (can annotate but not create tags)
        conn.execute(
            text(
                "INSERT INTO acl_entry"
                " (id, workspace_id, user_id, permission, created_at)"
                " VALUES (gen_random_uuid(),"
                "  CAST(:ws AS uuid), :uid, 'editor', now())"
            ),
            {"ws": workspace_id, "uid": user_id},
        )

        # Enrol the user in the course (required for placement resolution)
        conn.execute(
            text(
                "INSERT INTO course_enrollment"
                " (id, course_id, user_id, role, created_at)"
                " VALUES (gen_random_uuid(),"
                "  CAST(:cid AS uuid), :uid, 'student', now())"
                " ON CONFLICT DO NOTHING"
            ),
            {"cid": course_id, "uid": user_id},
        )

    engine.dispose()
    return workspace_id


def _create_workspace_with_word_limits(
    user_email: str,
    html_content: str,
    *,
    word_minimum: int | None = None,
    word_limit: int | None = None,
    word_limit_enforcement: bool | None = None,
    default_word_limit_enforcement: bool = False,
) -> str:
    """Create a workspace under an activity with word count limits configured.

    Builds the full hierarchy (course -> week -> activity -> workspace)
    via direct DB operations. Sets word count fields on both the course
    and activity.

    Args:
        user_email: Email of the user (must exist in DB).
        html_content: Pre-processed HTML content for the document.
        word_minimum: Activity-level word minimum (None = no minimum).
        word_limit: Activity-level word limit (None = no limit).
        word_limit_enforcement: Activity-level enforcement override
            (None = inherit from course, True = hard, False = soft).
        default_word_limit_enforcement: Course-level default enforcement
            (True = hard, False = soft).

    Returns:
        workspace_id as string.
    """
    engine = _get_sync_engine()

    course_id = str(uuid.uuid4())
    week_id = str(uuid.uuid4())
    activity_id = str(uuid.uuid4())
    template_ws_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())

    with engine.begin() as conn:
        # Look up user
        row = conn.execute(
            text('SELECT id FROM "user" WHERE email = :email'),
            {"email": user_email},
        ).first()
        if not row:
            msg = f"User not found in DB: {user_email}"
            raise RuntimeError(msg)
        user_id = row[0]

        # Create course with word limit enforcement setting
        conn.execute(
            text(
                "INSERT INTO course"
                " (id, code, name, semester, is_archived,"
                "  default_copy_protection, default_allow_sharing,"
                "  default_anonymous_sharing, default_allow_tag_creation,"
                "  default_word_limit_enforcement, created_at)"
                " VALUES (CAST(:id AS uuid), :code, :name, :semester,"
                "  false, false, false, false, false, :dwle, now())"
            ),
            {
                "id": course_id,
                "code": f"WDCNT-{uuid.uuid4().hex[:6]}",
                "name": "Word Count Test",
                "semester": "2026-T1",
                "dwle": default_word_limit_enforcement,
            },
        )

        # Create week
        conn.execute(
            text(
                "INSERT INTO week"
                " (id, course_id, week_number, title,"
                "  is_published, created_at)"
                " VALUES (CAST(:id AS uuid), CAST(:cid AS uuid),"
                "  1, :title, true, now())"
            ),
            {"id": week_id, "cid": course_id, "title": "Week 1"},
        )

        # Create template workspace (required by activity FK)
        conn.execute(
            text(
                "INSERT INTO workspace"
                " (id, enable_save_as_draft, created_at, updated_at)"
                " VALUES (CAST(:id AS uuid), false, now(), now())"
            ),
            {"id": template_ws_id},
        )

        # Create activity with word count fields
        conn.execute(
            text(
                "INSERT INTO activity"
                " (id, week_id, template_workspace_id, title,"
                "  word_minimum, word_limit, word_limit_enforcement,"
                "  created_at, updated_at)"
                " VALUES (CAST(:id AS uuid), CAST(:wid AS uuid),"
                "  CAST(:twid AS uuid), :title,"
                "  :word_minimum, :word_limit, :word_limit_enforcement,"
                "  now(), now())"
            ),
            {
                "id": activity_id,
                "wid": week_id,
                "twid": template_ws_id,
                "title": "Word Count Activity",
                "word_minimum": word_minimum,
                "word_limit": word_limit,
                "word_limit_enforcement": word_limit_enforcement,
            },
        )

        # Create user's workspace placed under the activity
        conn.execute(
            text(
                "INSERT INTO workspace"
                " (id, activity_id, enable_save_as_draft,"
                "  created_at, updated_at)"
                " VALUES (CAST(:id AS uuid), CAST(:aid AS uuid),"
                "  false, now(), now())"
            ),
            {"id": workspace_id, "aid": activity_id},
        )

        # Create workspace document
        conn.execute(
            text(
                "INSERT INTO workspace_document"
                " (id, workspace_id, type, content,"
                "  source_type, order_index, created_at)"
                " VALUES (CAST(:id AS uuid), CAST(:ws AS uuid),"
                "  'source', :content, 'text', 0, now())"
            ),
            {
                "id": doc_id,
                "ws": workspace_id,
                "content": html_content,
            },
        )

        # Grant owner permission
        conn.execute(
            text(
                "INSERT INTO acl_entry"
                " (id, workspace_id, user_id, permission, created_at)"
                " VALUES (gen_random_uuid(),"
                "  CAST(:ws AS uuid), :uid, 'owner', now())"
            ),
            {"ws": workspace_id, "uid": user_id},
        )

        # Enrol the user in the course (required for placement resolution)
        conn.execute(
            text(
                "INSERT INTO course_enrollment"
                " (id, course_id, user_id, role, created_at)"
                " VALUES (gen_random_uuid(),"
                "  CAST(:cid AS uuid), :uid, 'student', now())"
                " ON CONFLICT DO NOTHING"
            ),
            {"cid": course_id, "uid": user_id},
        )

    engine.dispose()
    return workspace_id


def _create_workspace_for_filename_export(
    user_email: str,
    *,
    owner_display_name: str = "Ada Lovelace",
    course_code: str = "LAWS5000",
    activity_title: str = "Final Essay",
    workspace_title: str = "Week 3 Response",
) -> str:
    """Create a workspace with deterministic metadata for filename assertions.

    Builds the full hierarchy (course -> week -> activity -> workspace)
    via direct DB operations and sets the owner's ``display_name`` to a
    known value. This enables E2E tests to assert the exact browser-suggested
    filename without embedding the production filename builder.

    Args:
        user_email: Email of the authenticated user (must exist in DB).
        owner_display_name: Display name to set on the owner user record.
        course_code: Course code for the placement hierarchy.
        activity_title: Activity title for the placement hierarchy.
        workspace_title: Title to set on the workspace.

    Returns:
        workspace_id as string.

    Raises:
        RuntimeError: If DATABASE__URL is not configured or user not found.
    """
    engine = _get_sync_engine()

    course_id = str(uuid.uuid4())
    week_id = str(uuid.uuid4())
    activity_id = str(uuid.uuid4())
    template_ws_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())

    with engine.begin() as conn:
        # Look up user
        row = conn.execute(
            text('SELECT id FROM "user" WHERE email = :email'),
            {"email": user_email},
        ).first()
        if not row:
            msg = f"User not found in DB: {user_email}"
            raise RuntimeError(msg)
        user_id = row[0]

        # Set deterministic display name on the owner
        conn.execute(
            text('UPDATE "user" SET display_name = :name WHERE id = :uid'),
            {"name": owner_display_name, "uid": user_id},
        )

        # Create course
        conn.execute(
            text(
                "INSERT INTO course"
                " (id, code, name, semester, is_archived,"
                "  default_copy_protection, default_allow_sharing,"
                "  default_anonymous_sharing, default_allow_tag_creation,"
                "  default_word_limit_enforcement, created_at)"
                " VALUES (CAST(:id AS uuid), :code, :name, :semester,"
                "  false, false, false, false, false, false, now())"
            ),
            {
                "id": course_id,
                "code": course_code,
                "name": "Filename Test Course",
                "semester": "2026-T1",
            },
        )

        # Create week
        conn.execute(
            text(
                "INSERT INTO week"
                " (id, course_id, week_number, title,"
                "  is_published, created_at)"
                " VALUES (CAST(:id AS uuid), CAST(:cid AS uuid),"
                "  1, :title, true, now())"
            ),
            {"id": week_id, "cid": course_id, "title": "Week 1"},
        )

        # Create template workspace (required by activity FK)
        conn.execute(
            text(
                "INSERT INTO workspace"
                " (id, enable_save_as_draft, created_at, updated_at)"
                " VALUES (CAST(:id AS uuid), false, now(), now())"
            ),
            {"id": template_ws_id},
        )

        # Create activity
        conn.execute(
            text(
                "INSERT INTO activity"
                " (id, week_id, template_workspace_id, title,"
                "  created_at, updated_at)"
                " VALUES (CAST(:id AS uuid), CAST(:wid AS uuid),"
                "  CAST(:twid AS uuid), :title,"
                "  now(), now())"
            ),
            {
                "id": activity_id,
                "wid": week_id,
                "twid": template_ws_id,
                "title": activity_title,
            },
        )

        # Create user workspace placed under the activity, with title
        conn.execute(
            text(
                "INSERT INTO workspace"
                " (id, activity_id, title, enable_save_as_draft,"
                "  created_at, updated_at)"
                " VALUES (CAST(:id AS uuid), CAST(:aid AS uuid),"
                "  :title, false, now(), now())"
            ),
            {"id": workspace_id, "aid": activity_id, "title": workspace_title},
        )

        # Create workspace document with minimal content
        conn.execute(
            text(
                "INSERT INTO workspace_document"
                " (id, workspace_id, type, content,"
                "  source_type, order_index, created_at)"
                " VALUES (CAST(:id AS uuid), CAST(:ws AS uuid),"
                "  'source', :content, 'text', 0, now())"
            ),
            {
                "id": doc_id,
                "ws": workspace_id,
                "content": "<p>Filename export test content.</p>",
            },
        )

        # Grant owner permission
        conn.execute(
            text(
                "INSERT INTO acl_entry"
                " (id, workspace_id, user_id, permission, created_at)"
                " VALUES (gen_random_uuid(),"
                "  CAST(:ws AS uuid), :uid, 'owner', now())"
            ),
            {"ws": workspace_id, "uid": user_id},
        )

        # Enrol the user in the course (required for placement resolution)
        conn.execute(
            text(
                "INSERT INTO course_enrollment"
                " (id, course_id, user_id, role, created_at)"
                " VALUES (gen_random_uuid(),"
                "  CAST(:cid AS uuid), :uid, 'student', now())"
                " ON CONFLICT DO NOTHING"
            ),
            {"cid": course_id, "uid": user_id},
        )

    engine.dispose()
    return workspace_id


def get_user_id_by_email(email: str) -> str:
    """Return a user's UUID (as string) from their email.

    Uses a direct sync DB query so sync Playwright tests can resolve
    deterministic anonymised labels for assertions.

    Args:
        email: User email address.

    Returns:
        User UUID as a string.

    Raises:
        RuntimeError: If DATABASE__URL is missing or user is not found.
    """
    engine = _get_sync_engine()

    with engine.begin() as conn:
        row = conn.execute(
            text('SELECT id FROM "user" WHERE email = :email'),
            {"email": email.lower()},
        ).first()
    engine.dispose()

    if not row:
        msg = f"User not found in DB: {email}"
        raise RuntimeError(msg)
    return str(row[0])
