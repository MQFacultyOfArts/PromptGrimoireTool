"""Integration tests for database clone/drop round-trip.

Verifies that clone_database() and drop_database() work against a real
PostgreSQL instance.  Uses the branch test database (DEV__TEST_DATABASE_URL)
as the template source.

Requires a running PostgreSQL instance with DEV__TEST_DATABASE_URL set.
"""

from __future__ import annotations

import contextlib
import uuid

import psycopg
import pytest

from promptgrimoire.config import get_settings

# Skip all tests if no test database URL is configured
pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


def _sync_url(url: str) -> str:
    """Convert an async database URL to a sync psycopg URL."""
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _list_tables(url: str) -> set[str]:
    """Return the set of user table names in the given database."""
    sync_url = _sync_url(url)
    with psycopg.connect(sync_url, autocommit=True) as conn:
        rows = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
    return {row[0] for row in rows}


def _database_exists(url: str, db_name: str) -> bool:
    """Check whether a database exists via the postgres maintenance DB."""
    base = url.split("?", maxsplit=1)[0]
    maintenance_url = base.rsplit("/", 1)[0] + "/postgres"
    maintenance_url = maintenance_url.replace("postgresql+asyncpg://", "postgresql://")
    if "?" in url:
        maintenance_url += "?" + url.split("?", 1)[1]

    with psycopg.connect(maintenance_url, autocommit=True) as conn:
        row = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
        ).fetchone()
    return row is not None


def test_clone_and_drop_round_trip() -> None:
    """Clone a database from template, verify schema, then drop it."""
    from promptgrimoire.db.bootstrap import clone_database, drop_database

    source_url = get_settings().dev.test_database_url
    assert source_url, "DEV__TEST_DATABASE_URL must be set"

    target_name = f"pg_test_clone_{uuid.uuid4().hex[:8]}"
    clone_url: str | None = None

    try:
        # Clone the source database
        clone_url = clone_database(source_url, target_name)

        # Verify the cloned database exists
        assert _database_exists(source_url, target_name), (
            f"Cloned database {target_name!r} does not exist after clone_database()"
        )

        # Verify the clone has the same tables as the source
        source_tables = _list_tables(source_url)
        clone_tables = _list_tables(clone_url)

        assert source_tables, "Source database has no tables -- is schema migrated?"
        assert clone_tables == source_tables, (
            f"Table mismatch.\n"
            f"Source: {sorted(source_tables)}\n"
            f"Clone:  {sorted(clone_tables)}\n"
            f"Missing from clone: {sorted(source_tables - clone_tables)}\n"
            f"Extra in clone:     {sorted(clone_tables - source_tables)}"
        )

        # Drop the cloned database
        drop_database(clone_url)

        # Verify the database no longer exists
        assert not _database_exists(source_url, target_name), (
            f"Database {target_name!r} still exists after drop_database()"
        )

    finally:
        # Cleanup: ensure the cloned database is dropped even if assertions fail
        if clone_url is not None:
            with contextlib.suppress(Exception):
                drop_database(clone_url)


def test_drop_is_idempotent() -> None:
    """Dropping a database twice does not raise an error."""
    from promptgrimoire.db.bootstrap import clone_database, drop_database

    source_url = get_settings().dev.test_database_url
    assert source_url, "DEV__TEST_DATABASE_URL must be set"

    target_name = f"pg_test_clone_{uuid.uuid4().hex[:8]}"
    clone_url: str | None = None

    try:
        clone_url = clone_database(source_url, target_name)

        # First drop
        drop_database(clone_url)
        assert not _database_exists(source_url, target_name)

        # Second drop -- should not raise
        drop_database(clone_url)

    finally:
        if clone_url is not None:
            with contextlib.suppress(Exception):
                drop_database(clone_url)
