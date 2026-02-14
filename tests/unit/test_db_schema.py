"""Unit tests for database schema verification.

These tests verify that SQLModel metadata is correctly configured
and that bootstrap functions work as expected.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from promptgrimoire.config import DatabaseConfig, Settings


def test_all_models_registered() -> None:
    """All SQLModel table classes are registered in metadata.

    This test ensures that importing the models module registers
    all expected tables with SQLModel.metadata.
    """
    from sqlmodel import SQLModel

    import promptgrimoire.db.models  # noqa: F401 - import registers tables

    expected_tables = {
        "activity",
        "user",
        "course",
        "course_enrollment",
        "week",
        "workspace",
        "workspace_document",
    }
    actual_tables = set(SQLModel.metadata.tables.keys())

    assert expected_tables == actual_tables, (
        f"Table mismatch.\n"
        f"Expected: {sorted(expected_tables)}\n"
        f"Actual: {sorted(actual_tables)}\n"
        f"Missing: {sorted(expected_tables - actual_tables)}\n"
        f"Extra: {sorted(actual_tables - expected_tables)}"
    )


def test_get_expected_tables_returns_all_tables() -> None:
    """get_expected_tables() returns all 7 table names."""
    from promptgrimoire.db import get_expected_tables

    tables = get_expected_tables()

    assert len(tables) == 7
    assert "activity" in tables
    assert "user" in tables
    assert "course" in tables
    assert "course_enrollment" in tables
    assert "week" in tables
    assert "workspace" in tables
    assert "workspace_document" in tables


def test_is_db_configured_returns_false_when_unset() -> None:
    """is_db_configured() returns False when database.url is not set."""
    from promptgrimoire.db import is_db_configured

    settings_no_db = Settings(
        _env_file=None,  # type: ignore[call-arg]
        database=DatabaseConfig(url=None),
    )
    with patch(
        "promptgrimoire.db.bootstrap.get_settings",
        return_value=settings_no_db,
    ):
        assert is_db_configured() is False


def test_is_db_configured_returns_true_when_set() -> None:
    """is_db_configured() returns True when database.url is set."""
    from promptgrimoire.db import is_db_configured

    settings_with_db = Settings(
        _env_file=None,  # type: ignore[call-arg]
        database=DatabaseConfig(
            url="postgresql+asyncpg://test:test@localhost/test",
        ),
    )
    with patch(
        "promptgrimoire.db.bootstrap.get_settings",
        return_value=settings_with_db,
    ):
        assert is_db_configured() is True


def test_is_db_configured_returns_false_for_empty_string() -> None:
    """is_db_configured() returns False when database.url is empty."""
    from promptgrimoire.db import is_db_configured

    settings_empty_db = Settings(
        _env_file=None,  # type: ignore[call-arg]
        database=DatabaseConfig(url=""),
    )
    with patch(
        "promptgrimoire.db.bootstrap.get_settings",
        return_value=settings_empty_db,
    ):
        assert is_db_configured() is False


def test_run_alembic_upgrade_fails_without_database_url() -> None:
    """run_alembic_upgrade() raises RuntimeError without database.url."""
    from promptgrimoire.db import run_alembic_upgrade

    settings_no_db = Settings(
        _env_file=None,  # type: ignore[call-arg]
        database=DatabaseConfig(url=None),
    )
    with (
        patch(
            "promptgrimoire.db.bootstrap.get_settings",
            return_value=settings_no_db,
        ),
        pytest.raises(
            RuntimeError,
            match="DATABASE__URL not configured",
        ),
    ):
        run_alembic_upgrade()


def test_mask_password_in_error_messages() -> None:
    """Password is masked in database URLs for safe logging."""
    from promptgrimoire.db.bootstrap import _mask_password

    # Standard PostgreSQL URL
    url = "postgresql+asyncpg://user:secret123@localhost:5432/mydb"
    masked = _mask_password(url)
    assert masked == "postgresql+asyncpg://user:***@localhost:5432/mydb"
    assert "secret123" not in masked

    # URL without password
    url_no_pass = "postgresql+asyncpg://user@localhost:5432/mydb"
    assert _mask_password(url_no_pass) == url_no_pass

    # URL with special characters in password
    url_special = "postgresql+asyncpg://user:p@ss:word@localhost/db"
    masked_special = _mask_password(url_special)
    assert "p@ss:word" not in masked_special


# --- ensure_database_exists() return value tests ---


def test_ensure_database_exists_returns_false_for_none_url() -> None:
    """ensure_database_exists(None) returns False without connecting."""
    from promptgrimoire.db.bootstrap import ensure_database_exists

    assert ensure_database_exists(None) is False


def test_ensure_database_exists_returns_false_for_empty_url() -> None:
    """ensure_database_exists('') returns False without connecting."""
    from promptgrimoire.db.bootstrap import ensure_database_exists

    assert ensure_database_exists("") is False


def test_ensure_database_exists_returns_false_for_url_without_db_name() -> None:
    """ensure_database_exists returns False when URL has no database name."""
    from promptgrimoire.db.bootstrap import ensure_database_exists

    assert ensure_database_exists("postgresql://host/") is False


def test_ensure_database_exists_returns_true_when_created() -> None:
    """ensure_database_exists returns True when it creates a new database."""
    from unittest.mock import MagicMock

    from promptgrimoire.db.bootstrap import ensure_database_exists

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None  # DB does not exist

    mock_conn = MagicMock()
    mock_conn.execute.return_value = mock_cursor
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    with patch("promptgrimoire.db.bootstrap.psycopg.connect", return_value=mock_conn):
        result = ensure_database_exists("postgresql://user:pass@localhost/testdb")

    assert result is True
    # Called twice: SELECT pg_database + CREATE DATABASE
    assert mock_conn.execute.call_count == 2


def test_ensure_database_exists_returns_false_when_exists() -> None:
    """ensure_database_exists returns False when the database already exists."""
    from unittest.mock import MagicMock

    from promptgrimoire.db.bootstrap import ensure_database_exists

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (1,)  # DB already exists

    mock_conn = MagicMock()
    mock_conn.execute.return_value = mock_cursor
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    with patch("promptgrimoire.db.bootstrap.psycopg.connect", return_value=mock_conn):
        result = ensure_database_exists("postgresql://user:pass@localhost/testdb")

    assert result is False
    # Called once: SELECT pg_database only
    assert mock_conn.execute.call_count == 1
