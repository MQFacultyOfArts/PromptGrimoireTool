"""Database bootstrap and schema management for PromptGrimoire.

Provides unified database initialization for both app and test contexts.
This module is the single source of truth for database setup.

Key principles:
- Alembic is the ONLY way to create/modify schema
- All models must be imported before schema operations
- Fail fast if schema is invalid
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import inspect
from sqlmodel import SQLModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


def is_db_configured() -> bool:
    """Check if DATABASE_URL environment variable is set.

    Returns:
        True if DATABASE_URL is set and non-empty.
    """
    return bool(os.environ.get("DATABASE_URL"))


def run_alembic_upgrade() -> None:
    """Run Alembic migrations to upgrade schema to head.

    This is the ONLY approved way to create or modify database schema.
    Never use SQLModel.metadata.create_all() outside of Alembic migrations.

    Raises:
        RuntimeError: If DATABASE_URL is not set or migrations fail.
    """
    if not is_db_configured():
        raise RuntimeError("DATABASE_URL not set - cannot run migrations")

    # Find project root (where alembic.ini lives)
    project_root = Path(__file__).parent.parent.parent.parent

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        encoding="utf-8",
        check=False,
        cwd=project_root,
        env=dict(os.environ),
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Alembic migrations failed:\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )


def get_expected_tables() -> set[str]:
    """Get the set of table names expected from SQLModel metadata.

    This imports all models to ensure they're registered with SQLModel.metadata.

    Returns:
        Set of table names that should exist in the database.
    """
    # Import models to register them with SQLModel.metadata
    import promptgrimoire.db.models  # noqa: F401, PLC0415

    return set(SQLModel.metadata.tables.keys())


async def verify_schema(engine: AsyncEngine | None) -> None:
    """Verify all expected SQLModel tables exist in the database.

    This is called at app startup to fail fast if schema is invalid.

    Args:
        engine: Initialized async engine to inspect.

    Raises:
        RuntimeError: If engine is None or tables are missing.
    """
    if engine is None:
        raise RuntimeError("Database engine is not initialized")

    expected_tables = get_expected_tables()
    if not expected_tables:
        raise RuntimeError("No SQLModel tables registered; cannot verify schema")

    async with engine.begin() as connection:
        existing_tables = await connection.run_sync(
            lambda sync_conn: set(inspect(sync_conn).get_table_names())
        )

    missing_tables = expected_tables - existing_tables
    if missing_tables:
        database_url = os.environ.get("DATABASE_URL", "<unset>")
        # Mask password in URL for logging
        masked_url = _mask_password(database_url)
        missing = ", ".join(sorted(missing_tables))
        raise RuntimeError(
            f"Database schema is missing required tables: {missing}. "
            f"DATABASE_URL={masked_url}. "
            f"Run 'alembic upgrade head' to create tables."
        )


def _mask_password(url: str) -> str:
    """Mask password in database URL for safe logging."""
    if "@" not in url or "://" not in url:
        return url

    # postgresql+asyncpg://user:password@host:port/db
    try:
        protocol, rest = url.split("://", 1)
        if "@" in rest:
            creds, host_part = rest.rsplit("@", 1)
            if ":" in creds:
                user, _ = creds.split(":", 1)
                return f"{protocol}://{user}:***@{host_part}"
        return url
    except ValueError:
        return url
