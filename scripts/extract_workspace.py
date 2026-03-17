#!/usr/bin/env python3
"""Extract a workspace and its documents from PostgreSQL for debugging.

Connects via Unix socket (peer auth) by default. Outputs a single JSON file
with base64-encoded binary fields, suitable for building test fixtures.

Usage:
    uv run scripts/extract_workspace.py <workspace-uuid>
    uv run scripts/extract_workspace.py <workspace-uuid> --output /path/to/output.json

    # Override connection (e.g. local dev):
    PGUSER=brian PGDATABASE=promptgrimoire uv run scripts/extract_workspace.py <uuid>

Output format:
    {
        "workspace": { ... row as dict, crdt_state as base64 ... },
        "documents": [ { ... row as dict ... }, ... ],
        "tag_groups": [ { ... row as dict ... }, ... ],
        "tags": [ { ... row as dict ... }, ... ],
        "extracted_at": "ISO timestamp",
        "source_db": "database name"
    }
"""

import argparse
import base64
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import psycopg
import psycopg.rows


class _Encoder(json.JSONEncoder):
    """Handle UUID, datetime, bytes, and memoryview for JSON serialisation."""

    def default(self, o: object) -> object:
        if isinstance(o, UUID):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, (bytes, memoryview)):
            data = bytes(o) if isinstance(o, memoryview) else o
            return {
                "__binary__": True,
                "base64": base64.b64encode(data).decode(),
            }
        return super().default(o)


_DOC_QUERY = (
    "SELECT * FROM workspace_document WHERE workspace_id = %s ORDER BY order_index"
)
_TAG_GROUP_QUERY = (
    "SELECT * FROM tag_group WHERE workspace_id = %s ORDER BY order_index"
)
_TAG_QUERY = "SELECT * FROM tag WHERE workspace_id = %s ORDER BY order_index"


def _to_dicts(
    cur: psycopg.Cursor[tuple],
) -> list[dict]:
    """Convert cursor results to list of dicts using column descriptions."""
    cols = [desc.name for desc in (cur.description or [])]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def _to_dict(
    cur: psycopg.Cursor[tuple],
) -> dict | None:
    """Convert single cursor result to dict."""
    cols = [desc.name for desc in (cur.description or [])]
    row = cur.fetchone()
    if row is None:
        return None
    return dict(zip(cols, row, strict=True))


def extract(workspace_id: str, conninfo: str) -> dict:
    """Extract workspace and documents from the database."""
    with psycopg.connect(conninfo) as conn:
        workspace = _to_dict(
            conn.execute(
                "SELECT * FROM workspace WHERE id = %s",
                (workspace_id,),
            )
        )

        if workspace is None:
            print(
                f"No workspace found with id {workspace_id}",
                file=sys.stderr,
            )
            sys.exit(1)

        documents = _to_dicts(conn.execute(_DOC_QUERY, (workspace_id,)))
        tag_groups = _to_dicts(conn.execute(_TAG_GROUP_QUERY, (workspace_id,)))
        tags = _to_dicts(conn.execute(_TAG_QUERY, (workspace_id,)))

        return {
            "workspace": workspace,
            "documents": documents,
            "tag_groups": tag_groups,
            "tags": tags,
            "extracted_at": datetime.now(UTC).isoformat(),
            "source_db": conn.info.dbname,
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract workspace for debugging",
    )
    parser.add_argument("workspace_id", help="Workspace UUID")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output file path (default: tempdir/workspace_<uuid>.json)",
    )
    args = parser.parse_args()

    try:
        UUID(args.workspace_id)
    except ValueError:
        print(f"Invalid UUID: {args.workspace_id}", file=sys.stderr)
        sys.exit(1)

    user = os.environ.get("PGUSER", "promptgrimoire")
    dbname = os.environ.get("PGDATABASE", "promptgrimoire")
    host = os.environ.get("PGHOST", "/var/run/postgresql")
    conninfo = f"user={user} dbname={dbname} host={host}"

    tmp = Path(tempfile.gettempdir())
    output = args.output or tmp / f"workspace_{args.workspace_id}.json"

    print(f"Extracting workspace {args.workspace_id}...")
    data = extract(args.workspace_id, conninfo)

    output.write_text(json.dumps(data, cls=_Encoder, indent=2))
    print(f"  -> {output}")
    print("  workspace: 1 row")
    print(f"  documents: {len(data['documents'])} rows")
    print(f"  tag_groups: {len(data['tag_groups'])} rows")
    print(f"  tags: {len(data['tags'])} rows")

    crdt = data["workspace"].get("crdt_state")
    if crdt:
        print(f"  crdt_state: {len(crdt)} bytes")
    else:
        print("  crdt_state: NULL")

    print()
    print("scp from server:")
    print(f"  scp grimoire.drbbs.org:{output} {tmp}/")


if __name__ == "__main__":
    main()
