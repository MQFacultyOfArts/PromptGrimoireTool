"""Tests for promptgrimoire.config -- Settings, sub-models, branch DB isolation.

Every test constructs Settings(_env_file=None, ...) to avoid reading real .env files.
The _env_file parameter is a pydantic-settings internal not visible to ty.
"""

from __future__ import annotations

import inspect
import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import SecretStr, ValidationError

from promptgrimoire.config import (
    _MAIN_WORKTREE_ENV,
    _PROJECT_ROOT,
    AppConfig,
    DatabaseConfig,
    DevConfig,
    LlmConfig,
    Settings,
    StytchConfig,
    _branch_db_suffix,
    _suffix_db_url,
    get_settings,
)


# ---------------------------------------------------------------------------
# AC1: Type validation at startup
# ---------------------------------------------------------------------------
class TestTypeValidation:
    """AC1: Pydantic type validation on Settings construction."""

    def test_valid_typed_values_populate_all_fields(self) -> None:
        """AC1.1: Construct Settings with valid typed values, verify all fields."""
        s = Settings(
            _env_file=None,  # type: ignore[call-arg]
            stytch=StytchConfig(
                project_id="proj-123",
                secret=SecretStr("sec-456"),
                public_token="pub-789",
            ),
            database=DatabaseConfig(url="postgresql://u:p@h/db"),
            llm=LlmConfig(
                api_key=SecretStr("sk-test"),
                model="claude-sonnet-4-20250514",
                thinking_budget=2048,
                lorebook_token_budget=100,
            ),
            app=AppConfig(
                base_url="http://localhost:9090",
                port=9090,
                storage_secret=SecretStr("my-secret"),
                log_dir=Path("/tmp/logs"),
                latexmk_path="/usr/bin/latexmk",
            ),
            dev=DevConfig(
                auth_mock=True,
                enable_demo_pages=True,
                database_echo=True,
                test_database_url="postgresql://u:p@h/testdb",
                branch_db_suffix=False,
            ),
        )
        assert s.stytch.project_id == "proj-123"
        assert s.stytch.secret.get_secret_value() == "sec-456"
        assert s.stytch.public_token == "pub-789"
        assert s.database.url == "postgresql://u:p@h/db"
        assert s.llm.api_key.get_secret_value() == "sk-test"
        assert s.llm.model == "claude-sonnet-4-20250514"
        assert s.llm.thinking_budget == 2048
        assert s.llm.lorebook_token_budget == 100
        assert s.app.port == 9090
        assert s.app.base_url == "http://localhost:9090"
        assert s.app.storage_secret.get_secret_value() == "my-secret"
        assert s.app.log_dir == Path("/tmp/logs")
        assert s.app.latexmk_path == "/usr/bin/latexmk"
        assert s.dev.auth_mock is True
        assert s.dev.enable_demo_pages is True
        assert s.dev.database_echo is True
        assert s.dev.test_database_url == "postgresql://u:p@h/testdb"
        assert s.dev.branch_db_suffix is False

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("true", True),
            ("false", False),
            ("1", True),
            ("0", False),
            ("yes", True),
            ("no", False),
            ("True", True),
            ("FALSE", False),
        ],
    )
    def test_bool_coercion_case_insensitive(self, raw: str, expected: bool) -> None:
        """AC1.2: DevConfig coerces string values to bool."""
        cfg = DevConfig(auth_mock=raw)  # type: ignore[arg-type]
        assert cfg.auth_mock is expected

    def test_int_coercion_from_string(self) -> None:
        """AC1.3: Int fields coerce string values."""
        app = AppConfig(port="9090")  # type: ignore[arg-type]
        assert app.port == 9090
        assert isinstance(app.port, int)

        llm1 = LlmConfig(thinking_budget="2048")  # type: ignore[arg-type]
        assert llm1.thinking_budget == 2048
        assert isinstance(llm1.thinking_budget, int)

        llm2 = LlmConfig(lorebook_token_budget="500")  # type: ignore[arg-type]
        assert llm2.lorebook_token_budget == 500
        assert isinstance(llm2.lorebook_token_budget, int)

    def test_invalid_int_raises_validation_error(self) -> None:
        """AC1.4: Invalid int string raises ValidationError."""
        with pytest.raises(ValidationError):
            AppConfig(port="not-a-number")  # type: ignore[arg-type]

    def test_missing_env_file_uses_defaults(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC1.5: Settings with no env file and no env vars uses defaults."""
        # Clear any env vars that pydantic-settings would read
        # (_env_file=None suppresses .env, but os.environ is still read)
        for key in list(os.environ):
            if "__" in key and key.split("__")[0] in (
                "STYTCH",
                "DATABASE",
                "LLM",
                "APP",
                "DEV",
            ):
                monkeypatch.delenv(key, raising=False)
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.app.port == 8080
        assert s.app.base_url == "http://localhost:8080"
        assert s.dev.auth_mock is False
        assert s.llm.thinking_budget == 1024
        assert s.llm.lorebook_token_budget == 0
        assert s.database.url is None
        assert s.stytch.project_id == ""


# ---------------------------------------------------------------------------
# AC2: Startup validation for cross-field rules
# ---------------------------------------------------------------------------
class TestCrossFieldValidation:
    """AC2: Cross-field validation rules on sub-models."""

    def test_sso_with_public_token_passes(self) -> None:
        """AC2.1: SSO with public_token set is valid."""
        cfg = StytchConfig(sso_connection_id="test-id", public_token="test-token")
        assert cfg.sso_connection_id == "test-id"
        assert cfg.public_token == "test-token"

    def test_sso_without_public_token_raises(self) -> None:
        """AC2.2: SSO without public_token raises ValidationError."""
        with pytest.raises(ValidationError, match="STYTCH__PUBLIC_TOKEN"):
            StytchConfig(sso_connection_id="test-id", public_token="")

    def test_neither_sso_nor_public_token_passes(self) -> None:
        """AC2.3: No SSO and no public_token is valid (defaults)."""
        cfg = StytchConfig()
        assert cfg.sso_connection_id is None
        assert cfg.public_token == ""


# ---------------------------------------------------------------------------
# AC7: Worktree .env fallback paths
# ---------------------------------------------------------------------------
class TestWorktreeEnvPaths:
    """AC7: Worktree-aware .env path resolution."""

    def test_project_root_env_in_config(self) -> None:
        """AC7.1: _PROJECT_ROOT / '.env' is in env_file tuple."""
        env_file = Settings.model_config["env_file"]
        assert isinstance(env_file, tuple)
        assert _PROJECT_ROOT / ".env" in env_file

    def test_main_worktree_env_in_config(self) -> None:
        """AC7.2: _MAIN_WORKTREE_ENV is in env_file tuple."""
        env_file = Settings.model_config["env_file"]
        assert isinstance(env_file, tuple)
        assert _MAIN_WORKTREE_ENV in env_file

    def test_local_env_overrides_main_worktree(self) -> None:
        """AC7.3: Local .env AFTER main worktree (later = higher priority)."""
        env_file = Settings.model_config["env_file"]
        assert isinstance(env_file, tuple)
        main_idx = env_file.index(_MAIN_WORKTREE_ENV)
        local_idx = env_file.index(_PROJECT_ROOT / ".env")
        assert local_idx > main_idx, (
            f"Local .env (index {local_idx}) must come after "
            f"main worktree (index {main_idx})"
        )

    def test_get_settings_logs_env_files(
        self,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AC7.4: get_settings() emits INFO log about .env loading."""
        import promptgrimoire.config as config_module

        # Patch Settings in the config module so get_settings() constructs
        # without reading the real .env (which may have old-format vars).
        original_init = config_module.Settings.__init__

        def _patched_init(self: object, *args: object, **kwargs: object) -> None:
            kwargs.setdefault("_env_file", None)
            original_init(self, *args, **kwargs)  # type: ignore[invalid-argument-type]

        monkeypatch.setattr(config_module.Settings, "__init__", _patched_init)
        get_settings.cache_clear()
        try:
            with caplog.at_level(logging.INFO, logger="promptgrimoire.config"):
                get_settings()
            messages = [r.message for r in caplog.records]
            assert any("Settings" in m and ".env" in m for m in messages), (
                f"Expected INFO log about .env, got: {messages}"
            )
        finally:
            get_settings.cache_clear()


# ---------------------------------------------------------------------------
# AC8: Test isolation patterns
# ---------------------------------------------------------------------------
class TestTestIsolation:
    """AC8: Patterns for isolating tests from real configuration."""

    def test_settings_construction_without_env(self) -> None:
        """AC8.1: Direct Settings construction with explicit values."""
        s = Settings(
            _env_file=None,  # type: ignore[unknown-argument]
            app=AppConfig(port=1234),
        )
        assert s.app.port == 1234

    def test_cache_clear_resets_singleton(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC8.2: get_settings() caching and cache_clear() behavior."""
        import promptgrimoire.config as config_module

        original_init = config_module.Settings.__init__

        def _patched_init(self: object, *args: object, **kwargs: object) -> None:
            kwargs.setdefault("_env_file", None)
            original_init(self, *args, **kwargs)  # type: ignore[invalid-argument-type]

        monkeypatch.setattr(config_module.Settings, "__init__", _patched_init)
        get_settings.cache_clear()
        try:
            a = get_settings()
            b = get_settings()
            assert a is b, "Cached calls should return same instance"

            get_settings.cache_clear()
            c = get_settings()
            assert a is not c, "After cache_clear, should return new instance"
        finally:
            get_settings.cache_clear()

    def test_pure_function_no_settings_dependency(self) -> None:
        """AC8.3: Documentation test -- pure functions take explicit args.

        Demonstrates the functional core pattern: business logic functions
        accept explicit parameters rather than importing get_settings().
        """

        def compute_greeting(name: str, prefix: str = "Hello") -> str:
            """Example pure function -- no Settings dependency."""
            return f"{prefix}, {name}!"

        result = compute_greeting("World")
        assert result == "Hello, World!"
        result2 = compute_greeting("Test", prefix="Hi")
        assert result2 == "Hi, Test!"


# ---------------------------------------------------------------------------
# AC9: Per-worktree database isolation
# ---------------------------------------------------------------------------
class TestBranchDbIsolation:
    """AC9: Branch detection, suffix derivation, URL suffixing, validator."""

    # -- Branch detection (AC9.4, AC9.5) --

    def test_branch_detection_worktree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC9.4: Detect branch from worktree .git file + gitdir/HEAD."""
        import promptgrimoire.config as config_module

        gitdir = tmp_path / "gitdir"
        gitdir.mkdir()
        head_file = gitdir / "HEAD"
        head_file.write_text("ref: refs/heads/feature-branch\n")

        dot_git = tmp_path / ".git"
        dot_git.write_text(f"gitdir: {gitdir}\n")

        monkeypatch.setattr(config_module, "_PROJECT_ROOT", tmp_path)
        from promptgrimoire.config import _current_branch

        result = _current_branch()
        assert result == "feature-branch"

    def test_branch_detection_main_worktree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC9.4 (main worktree): Detect branch from .git directory."""
        import promptgrimoire.config as config_module

        dot_git = tmp_path / ".git"
        dot_git.mkdir()
        head_file = dot_git / "HEAD"
        head_file.write_text("ref: refs/heads/main\n")

        monkeypatch.setattr(config_module, "_PROJECT_ROOT", tmp_path)
        from promptgrimoire.config import _current_branch

        result = _current_branch()
        assert result == "main"

    def test_detached_head_no_suffix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC9.5: Detached HEAD (raw SHA) returns None."""
        import promptgrimoire.config as config_module

        dot_git = tmp_path / ".git"
        dot_git.mkdir()
        head_file = dot_git / "HEAD"
        head_file.write_text("abc123def456789012345678901234567890abcd\n")

        monkeypatch.setattr(config_module, "_PROJECT_ROOT", tmp_path)
        from promptgrimoire.config import _current_branch

        result = _current_branch()
        assert result is None

    # -- Suffix derivation (AC9.1, AC9.2, AC9.6, AC9.7) --

    def test_main_branch_no_suffix(self) -> None:
        """AC9.1: main/master/None produce empty suffix."""
        assert _branch_db_suffix("main") == ""
        assert _branch_db_suffix("master") == ""
        assert _branch_db_suffix(None) == ""

    def test_feature_branch_suffixed(self) -> None:
        """AC9.2: Feature branch produces sanitised suffix."""
        result = _branch_db_suffix("130-pydantic-settings")
        assert result == "130_pydantic_settings"

    def test_special_chars_sanitised(self) -> None:
        """AC9.6: Special characters are replaced with underscores."""
        result = _branch_db_suffix("feature/my.branch-name")
        assert result == "feature_my_branch_name"

    def test_long_branch_truncated_with_hash(self) -> None:
        """AC9.7: Long names truncated with hash, max 40 chars."""
        long_branch = "a" * 60
        result = _branch_db_suffix(long_branch)
        assert len(result) <= 40
        assert "_" in result
        # Deterministic
        assert result == _branch_db_suffix(long_branch)

    # -- URL suffixing (AC9.8, AC9.9) --

    def test_suffix_db_url_basic(self) -> None:
        """Basic URL suffixing."""
        result = _suffix_db_url("postgresql://u:p@h/mydb", "feature")
        assert result == "postgresql://u:p@h/mydb_feature"

    def test_idempotent_suffix(self) -> None:
        """AC9.8: Already-suffixed URL returns unchanged."""
        url = "postgresql://u:p@h/mydb_feature"
        result = _suffix_db_url(url, "feature")
        assert result == url

    def test_query_params_preserved(self) -> None:
        """AC9.9: Query parameters are preserved after suffixing."""
        result = _suffix_db_url("postgresql://u:p@h/mydb?host=/tmp", "feature")
        assert result == "postgresql://u:p@h/mydb_feature?host=/tmp"

    def test_suffix_db_url_none_url(self) -> None:
        """None URL returns None."""
        assert _suffix_db_url(None, "feature") is None

    def test_suffix_db_url_empty_suffix(self) -> None:
        """Empty suffix returns URL unchanged."""
        url = "postgresql://u:p@h/mydb"
        assert _suffix_db_url(url, "") == url

    # -- Settings validator (AC9.3, AC9.10) --

    @patch(
        "promptgrimoire.config._current_branch",
        return_value="130-pydantic-settings",
    )
    def test_both_urls_suffixed(self, _mock_branch: object) -> None:
        """AC9.3: Both database.url and dev.test_database_url suffixed."""
        s = Settings(
            _env_file=None,  # type: ignore[call-arg]
            database=DatabaseConfig(url="postgresql://u:p@h/mydb"),
            dev=DevConfig(test_database_url="postgresql://u:p@h/testdb"),
        )
        expected_db = "postgresql://u:p@h/mydb_130_pydantic_settings"
        expected_test = "postgresql://u:p@h/testdb_130_pydantic_settings"
        assert s.database.url == expected_db
        assert s.dev.test_database_url == expected_test

    @patch("promptgrimoire.config._current_branch", return_value="main")
    def test_main_branch_urls_unchanged(self, _mock_branch: object) -> None:
        """AC9.1 via validator: main branch leaves URLs unchanged."""
        s = Settings(
            _env_file=None,  # type: ignore[call-arg]
            database=DatabaseConfig(url="postgresql://u:p@h/mydb"),
            dev=DevConfig(test_database_url="postgresql://u:p@h/testdb"),
        )
        assert s.database.url == "postgresql://u:p@h/mydb"
        assert s.dev.test_database_url == "postgresql://u:p@h/testdb"

    @patch(
        "promptgrimoire.config._current_branch",
        return_value="feature",
    )
    def test_opt_out_branch_db_suffix(self, _mock_branch: object) -> None:
        """AC9.10: branch_db_suffix=False leaves URL unchanged."""
        s = Settings(
            _env_file=None,  # type: ignore[call-arg]
            database=DatabaseConfig(url="postgresql://u:p@h/mydb"),
            dev=DevConfig(branch_db_suffix=False),
        )
        assert s.database.url == "postgresql://u:p@h/mydb"


class TestEnsureDatabaseExists:
    """AC10: Database auto-creation for branch-specific databases."""

    def test_noop_on_none_url(self) -> None:
        """AC10.3: None URL is a no-op."""
        from promptgrimoire.db.bootstrap import ensure_database_exists

        ensure_database_exists(None)

    def test_noop_on_empty_url(self) -> None:
        """AC10.3: Empty string URL is a no-op."""
        from promptgrimoire.db.bootstrap import ensure_database_exists

        ensure_database_exists("")

    def test_uses_psycopg(self) -> None:
        """AC10.3: Verify the function uses psycopg (import check)."""
        import promptgrimoire.db.bootstrap as bootstrap_module

        source = inspect.getsource(bootstrap_module.ensure_database_exists)
        assert "psycopg" in source

    def test_invalid_db_name_raises_value_error(self) -> None:
        """Invalid database name characters raise ValueError."""
        from promptgrimoire.db.bootstrap import ensure_database_exists

        with pytest.raises(ValueError, match="Invalid database name"):
            ensure_database_exists("postgresql://u:p@h/my-invalid-db!")


# ---------------------------------------------------------------------------
# AC10.1, AC10.2: Integration tests for ensure_database_exists
# ---------------------------------------------------------------------------
def _get_test_db_url() -> str | None:
    """Get a PostgreSQL URL for integration tests."""
    url = os.environ.get("DEV__TEST_DATABASE_URL") or os.environ.get(
        "TEST_DATABASE_URL"
    )
    return url


_skip_no_pg = pytest.mark.skipif(
    not _get_test_db_url(),
    reason="No test PostgreSQL configured",
)


@_skip_no_pg
class TestEnsureDatabaseExistsIntegration:
    """AC10.1, AC10.2: Real PostgreSQL integration tests."""

    def test_creates_missing_database(self) -> None:
        """AC10.1: Creates a database that doesn't exist."""
        import uuid

        import psycopg
        import psycopg.sql

        from promptgrimoire.db.bootstrap import ensure_database_exists

        base_url = _get_test_db_url()
        assert base_url is not None
        db_name = f"test_ensure_{uuid.uuid4().hex[:12]}"
        # Build URL with unique db name
        base = base_url.split("?")[0]
        prefix = base.rsplit("/", 1)[0]
        query = "?" + base_url.split("?", 1)[1] if "?" in base_url else ""
        test_url = f"{prefix}/{db_name}{query}"

        try:
            ensure_database_exists(test_url)

            # Verify: connect to postgres and check pg_database
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
            # Cleanup: drop the test database
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
        import uuid

        import psycopg
        import psycopg.sql

        from promptgrimoire.db.bootstrap import ensure_database_exists

        base_url = _get_test_db_url()
        assert base_url is not None
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
