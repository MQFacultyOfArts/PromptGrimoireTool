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
from urllib.parse import quote_plus
from uuid import UUID

from sqlalchemy import Engine, create_engine, text


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


def _build_engine() -> Engine:
    """Build a synchronous SQLAlchemy engine from PGUSER/PGDATABASE/PGHOST env vars.

    This script is designed to run on the production server with peer auth,
    so it uses libpq-style env vars rather than DATABASE__URL.
    """
    user = os.environ.get("PGUSER", "promptgrimoire")
    dbname = os.environ.get("PGDATABASE", "promptgrimoire")
    host = os.environ.get("PGHOST", "/var/run/postgresql")
    url = f"postgresql+psycopg://{quote_plus(user)}@/{quote_plus(dbname)}?host={quote_plus(host)}"
    return create_engine(url)


def extract(workspace_id: str, engine: Engine) -> dict:
    """Extract workspace and documents from the database."""
    with engine.connect() as conn:
        row = (
            conn.execute(
                text("SELECT * FROM workspace WHERE id = :ws"),
                {"ws": workspace_id},
            )
            .mappings()
            .first()
        )

        if row is None:
            print(
                f"No workspace found with id {workspace_id}",
                file=sys.stderr,
            )
            sys.exit(1)

        workspace = dict(row)

        documents = [
            dict(r)
            for r in conn.execute(
                text(
                    "SELECT * FROM workspace_document"
                    " WHERE workspace_id = :ws ORDER BY order_index"
                ),
                {"ws": workspace_id},
            ).mappings()
        ]
        tag_groups = [
            dict(r)
            for r in conn.execute(
                text(
                    "SELECT * FROM tag_group"
                    " WHERE workspace_id = :ws ORDER BY order_index"
                ),
                {"ws": workspace_id},
            ).mappings()
        ]
        tags = [
            dict(r)
            for r in conn.execute(
                text("SELECT * FROM tag WHERE workspace_id = :ws ORDER BY order_index"),
                {"ws": workspace_id},
            ).mappings()
        ]

        # Get database name from engine URL
        dbname = engine.url.database or "unknown"

        return {
            "workspace": workspace,
            "documents": documents,
            "tag_groups": tag_groups,
            "tags": tags,
            "extracted_at": datetime.now(UTC).isoformat(),
            "source_db": dbname,
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

    engine = _build_engine()

    tmp = Path(tempfile.gettempdir())
    output = args.output or tmp / f"workspace_{args.workspace_id}.json"

    print(f"Extracting workspace {args.workspace_id}...")
    try:
        data = extract(args.workspace_id, engine)
    finally:
        engine.dispose()

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
