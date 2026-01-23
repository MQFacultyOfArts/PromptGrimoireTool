"""Unit tests for database schema verification.

These tests verify that SQLModel metadata is correctly configured
and that bootstrap functions work as expected.
"""

from __future__ import annotations


def test_all_models_registered() -> None:
    """All SQLModel table classes are registered in metadata.

    This test ensures that importing the models module registers
    all expected tables with SQLModel.metadata.
    """
    from sqlmodel import SQLModel

    import promptgrimoire.db.models  # noqa: F401 - import registers tables

    expected_tables = {
        "user",
        "class",
        "conversation",
        "highlight",
        "highlight_comment",
        "annotation_document_state",
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
    """get_expected_tables() returns all 6 table names."""
    from promptgrimoire.db import get_expected_tables

    tables = get_expected_tables()

    assert len(tables) == 6
    assert "user" in tables
    assert "class" in tables
    assert "conversation" in tables
    assert "highlight" in tables
    assert "highlight_comment" in tables
    assert "annotation_document_state" in tables


def test_is_db_configured_returns_false_when_unset(monkeypatch) -> None:
    """is_db_configured() returns False when DATABASE_URL is not set."""
    from promptgrimoire.db import is_db_configured

    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert is_db_configured() is False


def test_is_db_configured_returns_true_when_set(monkeypatch) -> None:
    """is_db_configured() returns True when DATABASE_URL is set."""
    from promptgrimoire.db import is_db_configured

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")

    assert is_db_configured() is True


def test_is_db_configured_returns_false_for_empty_string(monkeypatch) -> None:
    """is_db_configured() returns False when DATABASE_URL is empty."""
    from promptgrimoire.db import is_db_configured

    monkeypatch.setenv("DATABASE_URL", "")

    assert is_db_configured() is False


def test_run_alembic_upgrade_fails_without_database_url(monkeypatch) -> None:
    """run_alembic_upgrade() raises RuntimeError without DATABASE_URL."""
    import pytest

    from promptgrimoire.db import run_alembic_upgrade

    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL not set"):
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
