#!/usr/bin/env python3
"""Load an extracted workspace JSON file into a local PostgreSQL database.

Counterpart to extract_workspace.py. Inserts the workspace and its documents,
decoding base64 binary fields back to bytea. Existing rows are replaced
(delete + insert) so the script is idempotent.

The workspace is inserted standalone (activity_id and course_id set to NULL)
regardless of the original placement, so no parent records are required.

Database selection follows the same worktree-aware rules as the app: reads
DATABASE__URL from get_settings(), which auto-suffixes the database name on
feature branches. Override with PGDATABASE env var if needed.

Usage:
    uv run scripts/rehydrate_workspace.py /tmp/workspace_<uuid>.json

    # Override connection (e.g. different database):
    PGDATABASE=promptgrimoire_other uv run scripts/rehydrate_workspace.py <file>
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Engine, create_engine, text

from promptgrimoire.config import get_settings


def _resolve_engine() -> Engine:
    """Build a synchronous SQLAlchemy engine using the app's worktree-aware settings.

    Reads DATABASE__URL from get_settings() (which auto-suffixes the database
    name on feature branches), then converts the asyncpg URL to psycopg for
    synchronous access.
    """
    url = get_settings().database.url
    if not url:
        msg = (
            "DATABASE__URL not configured. Set it in the environment or "
            "use PGDATABASE/PGUSER/PGHOST env vars with a plain postgresql:// URL."
        )
        raise RuntimeError(msg)
    sync_url = url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    return create_engine(sync_url)


def _decode_binary(value: object) -> object:
    """Decode base64-encoded binary fields produced by extract_workspace.py."""
    if isinstance(value, dict):
        d = dict(value)  # dict[Any, Any] — avoids ty Never-key narrowing
        if d.get("__binary__"):
            raw = d.get("base64")
            if isinstance(raw, str):
                return base64.b64decode(raw)
    return value


def _clean_existing_rows(conn: Connection, workspace_id: str) -> None:
    """Delete existing rows for workspace (idempotent). FK order matters."""
    conn.execute(text("DELETE FROM tag WHERE workspace_id = :ws"), {"ws": workspace_id})
    conn.execute(
        text("DELETE FROM tag_group WHERE workspace_id = :ws"), {"ws": workspace_id}
    )
    conn.execute(
        text("DELETE FROM workspace_document WHERE workspace_id = :ws"),
        {"ws": workspace_id},
    )
    conn.execute(text("DELETE FROM workspace WHERE id = :ws"), {"ws": workspace_id})


def _insert_workspace_data(
    conn: Connection,
    ws: dict[str, Any],
    docs: list[dict[str, Any]],
    tag_groups: list[dict[str, Any]],
    tags: list[dict[str, Any]],
) -> None:
    """Insert workspace, documents, tag groups, and tags."""
    conn.execute(
        text("""
        INSERT INTO workspace (
            id, crdt_state, created_at, updated_at,
            activity_id, course_id,
            enable_save_as_draft, title, shared_with_class,
            next_tag_order, next_group_order,
            search_text, search_dirty
        ) VALUES (
            :id, :crdt_state, :created_at, :updated_at,
            NULL, NULL,
            :enable_save_as_draft, :title, :shared_with_class,
            :next_tag_order, :next_group_order,
            :search_text, :search_dirty
        )
        """),
        ws,
    )

    for doc in docs:
        if isinstance(doc.get("paragraph_map"), dict):
            doc["paragraph_map"] = json.dumps(doc["paragraph_map"])
        doc["source_document_id"] = None
        conn.execute(
            text("""
            INSERT INTO workspace_document (
                id, workspace_id, type, content, order_index, title,
                created_at, source_type, auto_number_paragraphs,
                paragraph_map, source_document_id
            ) VALUES (
                :id, :workspace_id, :type, :content,
                :order_index, :title, :created_at,
                :source_type, :auto_number_paragraphs,
                :paragraph_map, :source_document_id
            )
            """),
            doc,
        )

    for group in tag_groups:
        conn.execute(
            text("""
            INSERT INTO tag_group (
                id, workspace_id, name, order_index,
                created_at, color
            ) VALUES (
                :id, :workspace_id, :name, :order_index,
                :created_at, :color
            )
            """),
            group,
        )

    for tag in tags:
        conn.execute(
            text("""
            INSERT INTO tag (
                id, workspace_id, group_id, name, description,
                color, locked, order_index, created_at
            ) VALUES (
                :id, :workspace_id, :group_id, :name,
                :description, :color, :locked,
                :order_index, :created_at
            )
            """),
            tag,
        )


def _grant_owner_acl(
    conn: Connection,
    workspace_id: str,
    owner_email: str,
) -> None:
    """Grant owner ACL if user exists."""
    row = conn.execute(
        text('SELECT id FROM "user" WHERE email = :email'),
        {"email": owner_email},
    ).first()
    if row:
        conn.execute(
            text("""
            INSERT INTO acl_entry (
                id, workspace_id, user_id,
                permission, created_at
            ) VALUES (
                gen_random_uuid(),
                :ws, :uid, 'owner', now()
            )
            ON CONFLICT DO NOTHING
            """),
            {"ws": workspace_id, "uid": row[0]},
        )


def rehydrate(
    path: Path, engine_or_url: Engine | str, *, owner_email: str | None = None
) -> dict[str, Any]:
    """Load workspace JSON and insert into the database.

    Args:
        path: Path to workspace JSON file from extract_workspace.py.
        engine_or_url: SQLAlchemy Engine or database URL string.
        owner_email: Optional email of user to grant owner ACL.

    Returns:
        Summary dict with counts.
    """
    if isinstance(engine_or_url, str):
        sync_url = engine_or_url.replace(
            "postgresql+asyncpg://", "postgresql+psycopg://"
        )
        engine = create_engine(sync_url)
        owns_engine = True
    else:
        engine = engine_or_url
        owns_engine = False

    data = json.loads(path.read_text())
    ws = data["workspace"]
    docs = data["documents"]
    tag_groups = data.get("tag_groups", [])
    tags = data.get("tags", [])

    workspace_id = ws["id"]

    for key, val in ws.items():
        ws[key] = _decode_binary(val)

    try:
        with engine.begin() as conn:
            _clean_existing_rows(conn, workspace_id)
            _insert_workspace_data(conn, ws, docs, tag_groups, tags)
            if owner_email:
                _grant_owner_acl(conn, workspace_id, owner_email)
    finally:
        if owns_engine:
            engine.dispose()

    return {
        "workspace_id": workspace_id,
        "title": ws.get("title"),
        "documents": len(docs),
        "tag_groups": len(tag_groups),
        "tags": len(tags),
        "source_db": data.get("source_db"),
        "extracted_at": data.get("extracted_at"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load extracted workspace into local database",
    )
    parser.add_argument(
        "json_file",
        type=Path,
        help="Path to workspace JSON file from extract_workspace.py",
    )
    parser.add_argument(
        "--owner",
        help="Email of user to grant owner ACL (must already exist in DB)",
    )
    args = parser.parse_args()

    if not args.json_file.exists():
        print(f"File not found: {args.json_file}", file=sys.stderr)
        sys.exit(1)

    # Validate it looks like our format
    data = json.loads(args.json_file.read_text())
    if "workspace" not in data or "documents" not in data:
        print(
            "Invalid format: expected 'workspace' and 'documents' keys",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        UUID(data["workspace"]["id"])
    except KeyError, ValueError:
        print("Invalid or missing workspace id", file=sys.stderr)
        sys.exit(1)

    engine = _resolve_engine()
    try:
        result = rehydrate(args.json_file, engine, owner_email=args.owner)
    finally:
        engine.dispose()

    print(f"Loaded workspace {result['workspace_id']}")
    print(f"  title: {result['title']}")
    print(f"  documents: {result['documents']}")
    print(f"  tag_groups: {result['tag_groups']}")
    print(f"  tags: {result['tags']}")
    print(f"  from: {result['source_db']} (extracted {result['extracted_at']})")
    print()
    print(
        f"  URL: http://localhost:8080/annotation?workspace_id={result['workspace_id']}"
    )


if __name__ == "__main__":
    main()
