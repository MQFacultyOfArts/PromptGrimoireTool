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
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import psycopg

from promptgrimoire.config import get_settings


def _resolve_conninfo() -> str:
    """Build psycopg conninfo using the same worktree-aware settings as the app.

    Reads DATABASE__URL from get_settings() (which auto-suffixes the database
    name on feature branches), then converts the asyncpg URL to psycopg
    connection parameters. Falls back to PGDATABASE/PGUSER/PGHOST env vars
    if get_settings() fails.
    """
    url = get_settings().database.url
    if url:
        parsed = urlparse(url)
        user = parsed.username or os.environ.get("PGUSER", "brian")
        dbname = parsed.path.lstrip("/") or "promptgrimoire"
        host = parsed.hostname or os.environ.get("PGHOST", "/var/run/postgresql")
        # query params may contain host for unix socket
        if "host=" in (parsed.query or ""):
            for param in parsed.query.split("&"):
                if param.startswith("host="):
                    host = param.split("=", 1)[1]
        return f"user={user} dbname={dbname} host={host}"

    # Fallback: raw libpq env vars
    user = os.environ.get("PGUSER", "brian")
    dbname = os.environ.get("PGDATABASE", "promptgrimoire")
    host = os.environ.get("PGHOST", "/var/run/postgresql")
    return f"user={user} dbname={dbname} host={host}"


def _decode_binary(value: object) -> object:
    """Decode base64-encoded binary fields produced by extract_workspace.py."""
    if isinstance(value, dict):
        d = dict(value)  # dict[Any, Any] — avoids ty Never-key narrowing
        if d.get("__binary__"):
            raw = d.get("base64")
            if isinstance(raw, str):
                return base64.b64decode(raw)
    return value


def _clean_existing_rows(cur: Any, workspace_id: str) -> None:
    """Delete existing rows for workspace (idempotent). FK order matters."""
    cur.execute("DELETE FROM tag WHERE workspace_id = %s", (workspace_id,))
    cur.execute("DELETE FROM tag_group WHERE workspace_id = %s", (workspace_id,))
    cur.execute(
        "DELETE FROM workspace_document WHERE workspace_id = %s", (workspace_id,)
    )
    cur.execute("DELETE FROM workspace WHERE id = %s", (workspace_id,))


def _insert_workspace_data(
    cur: Any,
    ws: dict,
    docs: list[dict],
    tag_groups: list[dict],
    tags: list[dict],
) -> None:
    """Insert workspace, documents, tag groups, and tags."""
    cur.execute(
        """
        INSERT INTO workspace (
            id, crdt_state, created_at, updated_at,
            activity_id, course_id,
            enable_save_as_draft, title, shared_with_class,
            next_tag_order, next_group_order,
            search_text, search_dirty
        ) VALUES (
            %(id)s, %(crdt_state)s, %(created_at)s, %(updated_at)s,
            NULL, NULL,
            %(enable_save_as_draft)s, %(title)s, %(shared_with_class)s,
            %(next_tag_order)s, %(next_group_order)s,
            %(search_text)s, %(search_dirty)s
        )
        """,
        ws,
    )

    for doc in docs:
        if isinstance(doc.get("paragraph_map"), dict):
            doc["paragraph_map"] = json.dumps(doc["paragraph_map"])
        doc["source_document_id"] = None
        cur.execute(
            """
            INSERT INTO workspace_document (
                id, workspace_id, type, content, order_index, title,
                created_at, source_type, auto_number_paragraphs,
                paragraph_map, source_document_id
            ) VALUES (
                %(id)s, %(workspace_id)s, %(type)s, %(content)s,
                %(order_index)s, %(title)s, %(created_at)s,
                %(source_type)s, %(auto_number_paragraphs)s,
                %(paragraph_map)s, %(source_document_id)s
            )
            """,
            doc,
        )

    for group in tag_groups:
        cur.execute(
            """
            INSERT INTO tag_group (
                id, workspace_id, name, order_index,
                created_at, color
            ) VALUES (
                %(id)s, %(workspace_id)s, %(name)s, %(order_index)s,
                %(created_at)s, %(color)s
            )
            """,
            group,
        )

    for tag in tags:
        cur.execute(
            """
            INSERT INTO tag (
                id, workspace_id, group_id, name, description,
                color, locked, order_index, created_at
            ) VALUES (
                %(id)s, %(workspace_id)s, %(group_id)s, %(name)s,
                %(description)s, %(color)s, %(locked)s,
                %(order_index)s, %(created_at)s
            )
            """,
            tag,
        )


def _grant_owner_acl(
    cur: Any,
    workspace_id: str,
    owner_email: str,
) -> None:
    """Grant owner ACL if user exists."""
    cur.execute(
        'SELECT id FROM "user" WHERE email = %s',
        (owner_email,),
    )
    owner_row = cur.fetchone()
    if owner_row:
        cur.execute(
            """
            INSERT INTO acl_entry (
                id, workspace_id, user_id,
                permission, created_at
            ) VALUES (
                gen_random_uuid(),
                %s, %s, 'owner', now()
            )
            ON CONFLICT DO NOTHING
            """,
            (workspace_id, owner_row[0]),
        )


def rehydrate(path: Path, conninfo: str, *, owner_email: str | None = None) -> dict:
    """Load workspace JSON and insert into the database.

    Returns summary dict with counts.
    """
    data = json.loads(path.read_text())
    ws = data["workspace"]
    docs = data["documents"]
    tag_groups = data.get("tag_groups", [])
    tags = data.get("tags", [])

    workspace_id = ws["id"]

    for key, val in ws.items():
        ws[key] = _decode_binary(val)

    with psycopg.connect(conninfo) as conn:
        with conn.cursor() as cur:
            _clean_existing_rows(cur, workspace_id)
            _insert_workspace_data(cur, ws, docs, tag_groups, tags)
            if owner_email:
                _grant_owner_acl(cur, workspace_id, owner_email)

        conn.commit()

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

    conninfo = _resolve_conninfo()

    result = rehydrate(args.json_file, conninfo, owner_email=args.owner)

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
