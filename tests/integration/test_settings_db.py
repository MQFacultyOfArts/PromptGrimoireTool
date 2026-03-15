"""Integration tests for database bootstrap (ensure_database_exists).

These are real PostgreSQL integration tests that create and drop temporary
databases. They require DEV__TEST_DATABASE_URL to be configured.

Moved from tests/unit/test_settings.py — these are integration tests, not unit
tests, because they connect to a real PostgreSQL server.
"""

from __future__ import annotations

import uuid

import psycopg
import psycopg.sql
import pytest

from promptgrimoire.config import get_settings
from promptgrimoire.db.bootstrap import ensure_database_exists

pytestmark = pytest.mark.skipif(
    not get_settings().dev.test_database_url,
    reason="DEV__TEST_DATABASE_URL not configured",
)


def _get_test_db_url() -> str:
    """Get a PostgreSQL URL for integration tests."""
    url = get_settings().dev.test_database_url
    assert url is not None
    return url


class TestEnsureDatabaseExistsIntegration:
    """AC10.1, AC10.2: Real PostgreSQL integration tests."""

    def test_creates_missing_database(self) -> None:
        """AC10.1: Creates a database that doesn't exist."""
        base_url = _get_test_db_url()
        db_name = f"test_ensure_{uuid.uuid4().hex[:12]}"
        base = base_url.split("?")[0]
        prefix = base.rsplit("/", 1)[0]
        query = "?" + base_url.split("?", 1)[1] if "?" in base_url else ""
        test_url = f"{prefix}/{db_name}{query}"

        try:
            ensure_database_exists(test_url)

            maint_url = (
                prefix.replace("postgresql+asyncpg://", "postgresql://")
                + "/postgres"
                + query
            )
            with psycopg.connect(maint_url, autocommit=True) as conn:
                row = conn.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (db_name,),
                ).fetchone()
                assert row is not None, f"Database {db_name} was not created"
        finally:
            maint_url = (
                prefix.replace("postgresql+asyncpg://", "postgresql://")
                + "/postgres"
                + query
            )
            with psycopg.connect(maint_url, autocommit=True) as conn:
                conn.execute(
                    psycopg.sql.SQL("DROP DATABASE IF EXISTS {}").format(
                        psycopg.sql.Identifier(db_name)
                    )
                )

    def test_idempotent_no_error_on_existing(self) -> None:
        """AC10.2: Calling twice on same DB doesn't error."""
        base_url = _get_test_db_url()
        db_name = f"test_idem_{uuid.uuid4().hex[:12]}"
        base = base_url.split("?")[0]
        prefix = base.rsplit("/", 1)[0]
        query = "?" + base_url.split("?", 1)[1] if "?" in base_url else ""
        test_url = f"{prefix}/{db_name}{query}"

        try:
            ensure_database_exists(test_url)
            ensure_database_exists(test_url)  # second call — no error
        finally:
            maint_url = (
                prefix.replace("postgresql+asyncpg://", "postgresql://")
                + "/postgres"
                + query
            )
            with psycopg.connect(maint_url, autocommit=True) as conn:
                conn.execute(
                    psycopg.sql.SQL("DROP DATABASE IF EXISTS {}").format(
                        psycopg.sql.Identifier(db_name)
                    )
                )
