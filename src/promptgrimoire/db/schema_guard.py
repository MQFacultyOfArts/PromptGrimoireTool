"""Database schema guard for PromptGrimoire."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from sqlalchemy import inspect
from sqlmodel import SQLModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


async def verify_db_schema(
    engine: AsyncEngine | None,
    *,
    schema: str | None = None,
) -> None:
    """Ensure all SQLModel tables exist in the database.

    Args:
        engine: Initialized async engine to inspect.
        schema: Optional schema name to inspect (default uses database default).

    Raises:
        RuntimeError: If the engine is not initialized or tables are missing.
    """
    if engine is None:
        raise RuntimeError("Database engine is not initialized")

    # Ensure all SQLModel tables are registered in metadata.
    import promptgrimoire.db.models  # noqa: F401

    expected_tables = set(SQLModel.metadata.tables.keys())
    if not expected_tables:
        raise RuntimeError("No SQLModel tables registered; cannot verify schema")

    async with engine.begin() as connection:
        existing_tables = await connection.run_sync(
            lambda sync_conn: set(inspect(sync_conn).get_table_names(schema=schema))
        )

    missing_tables = expected_tables - existing_tables
    if missing_tables:
        database_url = os.environ.get("DATABASE_URL", "<unset>")
        missing = ", ".join(sorted(missing_tables))
        raise RuntimeError(
            "Database schema is missing required tables: "
            f"{missing}. DATABASE_URL={database_url}"
        )
