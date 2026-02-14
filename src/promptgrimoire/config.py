"""Centralised application configuration using pydantic-settings.

All environment variables are read through the Settings class.
Consumers call ``get_settings()`` to obtain a cached, validated instance.
Tests construct ``Settings(_env_file=None, ...)`` directly for isolation.
"""

from __future__ import annotations

import hashlib
import logging
import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path resolution for worktree-aware .env loading
# ---------------------------------------------------------------------------
# src/promptgrimoire/config.py  ->  parent x3  ->  project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# For worktrees at .worktrees/<branch>/, two levels up from project root
# reaches the main checkout's root where .env typically lives.
# In the main checkout this resolves outside the project (harmless — file
# won't exist).
_MAIN_WORKTREE_ENV = _PROJECT_ROOT.parent.parent / ".env"


# ---------------------------------------------------------------------------
# Sub-models (one per configuration domain)
# ---------------------------------------------------------------------------
class StytchConfig(BaseModel):
    """Stytch authentication provider credentials."""

    project_id: str = ""
    secret: SecretStr = SecretStr("")
    public_token: str = ""
    default_org_id: str | None = None
    sso_connection_id: str | None = None

    @model_validator(mode="after")
    def sso_requires_public_token(self) -> StytchConfig:
        if self.sso_connection_id and not self.public_token:
            msg = "STYTCH__SSO_CONNECTION_ID requires STYTCH__PUBLIC_TOKEN to be set"
            raise ValueError(msg)
        return self


class DatabaseConfig(BaseModel):
    """Database connection configuration."""

    url: str | None = None


class LlmConfig(BaseModel):
    """Claude API / LLM configuration."""

    api_key: SecretStr = SecretStr("")
    model: str = "claude-sonnet-4-20250514"
    thinking_budget: int = 1024
    lorebook_token_budget: int = 0


class AppConfig(BaseModel):
    """Application runtime configuration."""

    base_url: str = "http://localhost:8080"
    port: int = 8080
    storage_secret: SecretStr = SecretStr("dev-secret-change-me")
    log_dir: Path = Path("logs/sessions")
    latexmk_path: str = ""


class DevConfig(BaseModel):
    """Development and testing toggles."""

    auth_mock: bool = False
    enable_demo_pages: bool = False
    database_echo: bool = False
    test_database_url: str | None = None
    branch_db_suffix: bool = True


# ---------------------------------------------------------------------------
# Branch detection for per-worktree database isolation
# ---------------------------------------------------------------------------
def _current_branch() -> str | None:
    """Detect the current git branch from .git/HEAD (no subprocess).

    Handles both main checkouts (.git is a directory) and worktrees
    (.git is a file with a gitdir pointer).

    Returns:
        Branch name (e.g., "130-pydantic-settings") or None for detached HEAD
        or missing .git.
    """
    git_path = _PROJECT_ROOT / ".git"
    if git_path.is_file():
        # Worktree: .git is a file containing "gitdir: /path/to/..."
        gitdir = git_path.read_text().strip().removeprefix("gitdir: ")
        head_path = Path(gitdir) / "HEAD"
    elif git_path.is_dir():
        head_path = git_path / "HEAD"
    else:
        return None
    try:
        head = head_path.read_text().strip()
    except OSError:
        return None
    if head.startswith("ref: refs/heads/"):
        return head.removeprefix("ref: refs/heads/")
    return None  # detached HEAD


def get_current_branch() -> str | None:
    """Return the current git branch name, or None for detached HEAD."""
    return _current_branch()


def _branch_db_suffix(branch: str | None) -> str:
    """Derive a database name suffix from the branch name.

    Returns empty string for main/master/None (no suffix needed).
    Sanitises: lowercase, non-alphanumeric -> '_', dedup '__', max 40 chars.
    If the sanitised name exceeds 40 chars, truncate and append a short hash.
    """
    if branch is None or branch in ("main", "master"):
        return ""

    sanitised = re.sub(r"[^a-z0-9]", "_", branch.lower())
    sanitised = re.sub(r"_+", "_", sanitised).strip("_")

    if not sanitised:
        return ""

    if len(sanitised) > 40:
        h = hashlib.sha256(branch.encode()).hexdigest()[:8]
        sanitised = f"{sanitised[:31]}_{h}"

    return sanitised


def _suffix_db_url(url: str | None, suffix: str) -> str | None:
    """Append a branch suffix to the database name in a PostgreSQL URL.

    Idempotent: if the URL already ends with the suffix, returns unchanged.
    Preserves query parameters.

    Args:
        url: PostgreSQL connection string or None.
        suffix: Branch suffix from _branch_db_suffix(). Empty string = no-op.

    Returns:
        Suffixed URL, or the original if suffix is empty or URL is None.
    """
    if not url or not suffix:
        return url

    # Split off query params
    if "?" in url:
        base, query = url.rsplit("?", 1)
        query = "?" + query
    else:
        base = url
        query = ""

    # Extract database name (last path segment)
    if "/" not in base:
        return url

    prefix, db_name = base.rsplit("/", 1)
    full_suffix = f"_{suffix}"

    if db_name.endswith(full_suffix):
        return url  # idempotent

    return f"{prefix}/{db_name}{full_suffix}{query}"


# ---------------------------------------------------------------------------
# Root settings
# ---------------------------------------------------------------------------
class Settings(BaseSettings):
    """Application settings with automatic .env loading and type validation.

    Environment variables use double-underscore delimiter for nesting:
    ``STYTCH__PROJECT_ID``, ``DATABASE__URL``, ``LLM__API_KEY``, etc.

    Worktree support: when running from ``.worktrees/<branch>/``, the main
    checkout's ``.env`` is loaded as a fallback. A local ``.env`` in the
    worktree overrides it.

    Per-worktree database isolation: on feature branches, database URLs are
    automatically suffixed with a sanitised branch name to prevent migration
    conflicts between worktrees.
    """

    model_config = SettingsConfigDict(
        env_file=(_MAIN_WORKTREE_ENV, _PROJECT_ROOT / ".env"),
        env_nested_delimiter="__",
        # Ignore unknown env vars (e.g. old-format names in developer .env files).
        # Safe to remove once all .env files are migrated to double-underscore format.
        extra="ignore",
    )

    stytch: StytchConfig = StytchConfig()
    database: DatabaseConfig = DatabaseConfig()
    llm: LlmConfig = LlmConfig()
    app: AppConfig = AppConfig()
    dev: DevConfig = DevConfig()

    @model_validator(mode="after")
    def _apply_branch_db_suffix(self) -> Settings:
        """Suffix database URLs with branch name for worktree isolation."""
        if not self.dev.branch_db_suffix:
            return self

        branch = _current_branch()
        suffix = _branch_db_suffix(branch)
        if not suffix:
            return self

        self.database.url = _suffix_db_url(self.database.url, suffix)
        self.dev.test_database_url = _suffix_db_url(self.dev.test_database_url, suffix)
        return self


# ---------------------------------------------------------------------------
# Singleton access
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Call ``get_settings.cache_clear()`` in tests to reset.
    """
    settings = Settings()

    # Log which .env file(s) were loaded (INFO level, first call only).
    env_file = settings.model_config.get("env_file")
    if env_file is not None:
        paths = env_file if isinstance(env_file, (list, tuple)) else (env_file,)
        loaded = [str(p) for p in paths if Path(str(p)).is_file()]
        if loaded:
            logger.info("Settings loaded .env from: %s", ", ".join(loaded))
        else:
            logger.info("Settings: no .env file found, using env vars and defaults")

    return settings
