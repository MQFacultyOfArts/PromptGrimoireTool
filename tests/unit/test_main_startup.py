"""Tests for auto-create/migrate/seed behaviour in main().

Verifies:
- 165-auto-create-branch-db.AC3.1: App startup auto-creates missing branch DB,
  runs migrations, seeds if new.
- 165-auto-create-branch-db.AC3.2: App startup prints branch and database name
  for feature branches.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from promptgrimoire.config import AppConfig, DatabaseConfig, DevConfig, Settings


def _make_settings(
    *,
    database_url: str | None = None,
) -> Settings:
    """Build a minimal Settings instance for testing main()."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        database=DatabaseConfig(url=database_url),
        app=AppConfig(),
        dev=DevConfig(branch_db_suffix=False),
    )


@pytest.fixture
def _mock_main_deps():
    """Mock all heavy dependencies so main() returns immediately.

    Patches:
    - _setup_logging: prevents log file creation
    - nicegui.ui.run: prevents blocking event loop
    - App.add_static_files: prevents filesystem access (instance method)
    - promptgrimoire.pages: prevents route registration side effects
    - promptgrimoire.get_git_commit: returns deterministic value
    """
    with (
        patch("promptgrimoire._setup_logging"),
        patch("nicegui.ui.run"),
        patch("nicegui.app.app.App.add_static_files"),
        patch("promptgrimoire.pages", create=True),
        patch("promptgrimoire.get_git_commit", return_value="abc1234"),
    ):
        yield


class TestBootstrapCalledWithDbUrl:
    """ensure_database_exists and run_alembic_upgrade called when DB configured."""

    @pytest.mark.usefixtures("_mock_main_deps")
    def test_bootstrap_functions_called(self) -> None:
        settings = _make_settings(
            database_url="postgresql+asyncpg://u:p@localhost/testdb",
        )
        with (
            patch("promptgrimoire.config.get_settings", return_value=settings),
            patch(
                "promptgrimoire.db.bootstrap.ensure_database_exists",
                return_value=False,
            ) as mock_ensure,
            patch(
                "promptgrimoire.db.bootstrap.run_alembic_upgrade",
            ) as mock_upgrade,
            patch(
                "promptgrimoire.config.get_current_branch",
                return_value="main",
            ),
        ):
            from promptgrimoire import main

            main()

            mock_ensure.assert_called_once_with(
                "postgresql+asyncpg://u:p@localhost/testdb",
            )
            mock_upgrade.assert_called_once()


class TestSeedOnCreation:
    """seed-data invoked when ensure_database_exists returns True."""

    @pytest.mark.usefixtures("_mock_main_deps")
    def test_seed_data_subprocess_called(self) -> None:
        settings = _make_settings(
            database_url="postgresql+asyncpg://u:p@localhost/testdb",
        )
        with (
            patch("promptgrimoire.config.get_settings", return_value=settings),
            patch(
                "promptgrimoire.db.bootstrap.ensure_database_exists",
                return_value=True,
            ),
            patch("promptgrimoire.db.bootstrap.run_alembic_upgrade"),
            patch(
                "promptgrimoire.config.get_current_branch",
                return_value="main",
            ),
            patch("subprocess.run") as mock_subprocess,
        ):
            from promptgrimoire import main

            main()

            # Find the seed-data call among any subprocess.run calls
            seed_calls = [
                c
                for c in mock_subprocess.call_args_list
                if c.args and c.args[0] == ["uv", "run", "seed-data"]
            ]
            assert len(seed_calls) == 1, (
                f"Expected one seed-data call, got {mock_subprocess.call_args_list}"
            )


class TestNoSeedOnExistingDb:
    """seed-data NOT invoked when ensure_database_exists returns False."""

    @pytest.mark.usefixtures("_mock_main_deps")
    def test_seed_data_not_called(self) -> None:
        settings = _make_settings(
            database_url="postgresql+asyncpg://u:p@localhost/testdb",
        )
        with (
            patch("promptgrimoire.config.get_settings", return_value=settings),
            patch(
                "promptgrimoire.db.bootstrap.ensure_database_exists",
                return_value=False,
            ),
            patch("promptgrimoire.db.bootstrap.run_alembic_upgrade"),
            patch(
                "promptgrimoire.config.get_current_branch",
                return_value="main",
            ),
            patch("subprocess.run") as mock_subprocess,
        ):
            from promptgrimoire import main

            main()

            # No seed-data calls should exist
            seed_calls = [
                c
                for c in mock_subprocess.call_args_list
                if c.args and c.args[0] == ["uv", "run", "seed-data"]
            ]
            assert len(seed_calls) == 0, (
                f"Expected no seed-data calls, got {mock_subprocess.call_args_list}"
            )


class TestBranchInfoPrintedForFeatureBranch:
    """Branch info printed for feature branch (AC3.2)."""

    @pytest.mark.usefixtures("_mock_main_deps")
    def test_branch_and_db_in_stdout(self, capsys) -> None:
        settings = _make_settings(
            database_url="postgresql+asyncpg://u:p@localhost/pg_branch_165",
        )
        with (
            patch("promptgrimoire.config.get_settings", return_value=settings),
            patch(
                "promptgrimoire.db.bootstrap.ensure_database_exists",
                return_value=False,
            ),
            patch("promptgrimoire.db.bootstrap.run_alembic_upgrade"),
            patch(
                "promptgrimoire.config.get_current_branch",
                return_value="165-auto-create-branch-db",
            ),
        ):
            from promptgrimoire import main

            main()

        captured = capsys.readouterr()
        assert "Branch: 165-auto-create-branch-db" in captured.out
        assert "pg_branch_165" in captured.out


class TestBranchInfoNotPrintedForMain:
    """Branch info NOT printed for main branch (AC3.2)."""

    @pytest.mark.usefixtures("_mock_main_deps")
    def test_no_branch_line_on_main(self, capsys) -> None:
        settings = _make_settings(
            database_url="postgresql+asyncpg://u:p@localhost/testdb",
        )
        with (
            patch("promptgrimoire.config.get_settings", return_value=settings),
            patch(
                "promptgrimoire.db.bootstrap.ensure_database_exists",
                return_value=False,
            ),
            patch("promptgrimoire.db.bootstrap.run_alembic_upgrade"),
            patch(
                "promptgrimoire.config.get_current_branch",
                return_value="main",
            ),
        ):
            from promptgrimoire import main

            main()

        captured = capsys.readouterr()
        assert "Branch:" not in captured.out


class TestNoBootstrapWithoutDbUrl:
    """No bootstrap calls when DB not configured."""

    @pytest.mark.usefixtures("_mock_main_deps")
    def test_neither_ensure_nor_upgrade_called(self) -> None:
        settings = _make_settings(database_url=None)
        with (
            patch("promptgrimoire.config.get_settings", return_value=settings),
            patch(
                "promptgrimoire.db.bootstrap.ensure_database_exists",
            ) as mock_ensure,
            patch(
                "promptgrimoire.db.bootstrap.run_alembic_upgrade",
            ) as mock_upgrade,
        ):
            from promptgrimoire import main

            main()

            mock_ensure.assert_not_called()
            mock_upgrade.assert_not_called()
