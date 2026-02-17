# Pydantic-Settings Migration — Phase 1: Settings Infrastructure

**Goal:** Create `src/promptgrimoire/config.py` with all Settings classes (including per-worktree database isolation), add `ensure_database_exists()` to `db/bootstrap.py`, add `pydantic-settings` dependency, and update `.env.example` with double-underscore convention.

**Architecture:** Single `Settings(BaseSettings)` root class with five nested `BaseModel` sub-models (`StytchConfig`, `DatabaseConfig`, `LlmConfig`, `AppConfig`, `DevConfig`). Environment variables use `__` delimiter (e.g., `STYTCH__PROJECT_ID`). Worktree-aware `.env` fallback via `__file__` path computation. `@lru_cache` singleton via `get_settings()`. Per-worktree database isolation via branch detection from `.git/HEAD`, URL suffixing, and a `model_validator(mode="after")` on Settings. Database auto-creation via `ensure_database_exists()` using sync psycopg.

**Tech Stack:** pydantic-settings v2, pydantic v2 (SecretStr, model_validator), psycopg (sync, for DB creation)

**Scope:** 7 phases from original design (phase 1 of 7)

**Codebase verified:** 2026-02-14

---

## Acceptance Criteria Coverage

This phase is infrastructure — it creates the Settings module, database helper, and updates `.env.example`. No acceptance criteria are directly tested here (tests are in Phase 2). This phase's "done when" is operational: `uv sync` succeeds, `Settings()` is constructable, `ensure_database_exists()` is importable, `.env.example` documents new names.

**Verifies: None** (infrastructure phase — verified operationally)

---

<!-- START_TASK_1 -->
### Task 1: Add pydantic-settings dependency

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/pyproject.toml` (line 19-32, dependencies array)

**Step 1: Add dependency**

Add `pydantic-settings>=2.7` to the `dependencies` array in `pyproject.toml`. Place it after the existing `pydantic>=2.10` entry.

Current dependencies section (lines 19-32):
```toml
dependencies = [
    "nicegui==3.6.1",
    ...
    "pydantic>=2.10",
    ...
    "python-dotenv>=1.0",
    ...
]
```

Add `"pydantic-settings>=2.7",` after `"pydantic>=2.10",`.

**Step 2: Verify operationally**

Run: `uv sync`
Expected: Dependencies install without errors. pydantic-settings and its transitive deps resolve.

Run: `uv run python -c "from pydantic_settings import BaseSettings; print('ok')"`
Expected: Prints `ok`

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add pydantic-settings for typed configuration"
```
<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-4) -->
<!-- START_TASK_2 -->
### Task 2: Create config.py with Settings classes and get_settings() singleton

**Files:**
- Create: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/config.py`

**Step 1: Create the config module**

Create `src/promptgrimoire/config.py` with the following contents:

```python
"""Centralised application configuration using pydantic-settings.

All environment variables are read through the Settings class.
Consumers call ``get_settings()`` to obtain a cached, validated instance.
Tests construct ``Settings(_env_file=None, ...)`` directly for isolation.
"""

from __future__ import annotations

import logging
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


def _branch_db_suffix(branch: str | None) -> str:
    """Derive a database name suffix from the branch name.

    Returns empty string for main/master/None (no suffix needed).
    Sanitises: lowercase, non-alphanumeric -> '_', dedup '__', max 40 chars.
    If the sanitised name exceeds 40 chars, truncate and append a short hash.
    """
    import hashlib
    import re

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
        self.dev.test_database_url = _suffix_db_url(
            self.dev.test_database_url, suffix
        )
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
        if isinstance(env_file, (list, tuple)):
            loaded = [str(p) for p in env_file if Path(p).is_file()]
        else:
            loaded = [str(env_file)] if Path(env_file).is_file() else []
        if loaded:
            logger.info("Settings loaded .env from: %s", ", ".join(loaded))
        else:
            logger.info("Settings: no .env file found, using env vars and defaults")

    return settings
```

**Step 2: Verify operationally**

Run: `uv run python -c "from promptgrimoire.config import Settings, get_settings; s = Settings(_env_file=None); print(s.app.port); print(type(s.stytch.secret))"`
Expected: Prints `8080` and `<class 'pydantic.types.SecretStr'>`

Run: `uv run ruff check src/promptgrimoire/config.py`
Expected: No lint errors

Run: `uvx ty check`
Expected: No type errors in config.py

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update .env.example with double-underscore convention

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/.env.example`

**Step 1: Rewrite .env.example**

Replace the entire contents of `.env.example` with the new double-underscore naming convention. Every field in the Settings model must have a corresponding entry. Group by sub-model with section headers.

The rename map (old -> new):

| Old Name | New Name |
|----------|----------|
| `STYTCH_PROJECT_ID` | `STYTCH__PROJECT_ID` |
| `STYTCH_SECRET` | `STYTCH__SECRET` |
| `STYTCH_PUBLIC_TOKEN` | `STYTCH__PUBLIC_TOKEN` |
| `STYTCH_DEFAULT_ORG_ID` | `STYTCH__DEFAULT_ORG_ID` |
| `STYTCH_SSO_CONNECTION_ID` | `STYTCH__SSO_CONNECTION_ID` |
| `DATABASE_URL` | `DATABASE__URL` |
| `ANTHROPIC_API_KEY` | `LLM__API_KEY` |
| `CLAUDE_MODEL` | `LLM__MODEL` |
| `CLAUDE_THINKING_BUDGET` | `LLM__THINKING_BUDGET` |
| `LOREBOOK_TOKEN_BUDGET` | `LLM__LOREBOOK_TOKEN_BUDGET` |
| `BASE_URL` | `APP__BASE_URL` |
| `PROMPTGRIMOIRE_PORT` | `APP__PORT` |
| `STORAGE_SECRET` | `APP__STORAGE_SECRET` |
| `ROLEPLAY_LOG_DIR` | `APP__LOG_DIR` |
| `LATEXMK_PATH` | `APP__LATEXMK_PATH` |
| `AUTH_MOCK` | `DEV__AUTH_MOCK` |
| `ENABLE_DEMO_PAGES` | `DEV__ENABLE_DEMO_PAGES` |
| `DATABASE_ECHO` | `DEV__DATABASE_ECHO` |
| `TEST_DATABASE_URL` | `DEV__TEST_DATABASE_URL` |

The new `.env.example` must include:
- A documentation comment above each variable explaining its purpose
- The default value (matching the Settings field default) or example value
- Section headers grouping by sub-model
- **NEW:** `DEV__BRANCH_DB_SUFFIX=true` in the Dev/Testing section with a comment explaining per-worktree database isolation

Preserve the documentation quality and structure of the existing `.env.example` but use new variable names throughout.

**Step 2: Verify operationally**

Visually confirm:
- Every Settings sub-model field has a corresponding `.env.example` entry
- All variable names use double-underscore convention
- Each variable has a documentation comment

**Step 3: Commit**

```bash
git add src/promptgrimoire/config.py .env.example
git commit -m "feat: add Settings infrastructure with pydantic-settings"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add ensure_database_exists() to db/bootstrap.py

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/db/bootstrap.py`

**Step 1: Add the ensure_database_exists function**

Add the following function to `src/promptgrimoire/db/bootstrap.py` **after the existing imports and before `is_db_configured()`**. This is a pure addition — no existing functions are modified.

```python
import re

import psycopg


def ensure_database_exists(url: str | None) -> None:
    """Create the target database if it doesn't exist.

    Connects to the ``postgres`` maintenance database using sync psycopg
    with AUTOCOMMIT isolation (CREATE DATABASE cannot run inside a
    transaction).

    Args:
        url: PostgreSQL connection string. If None or empty, no-op.

    Raises:
        ValueError: If the database name contains invalid characters.
    """
    if not url:
        return

    # Extract database name from URL (last path segment, before query params)
    base = url.split("?")[0]
    if "/" not in base:
        return
    db_name = base.rsplit("/", 1)[1]
    if not db_name:
        return

    # Belt-and-suspenders: validate db_name characters
    if not re.match(r"^[a-zA-Z0-9_]+$", db_name):
        msg = f"Invalid database name: {db_name!r}"
        raise ValueError(msg)

    # Build maintenance URL: replace db name with "postgres" and use
    # sync psycopg driver
    maintenance_url = base.rsplit("/", 1)[0] + "/postgres"
    # Normalise driver to sync psycopg
    maintenance_url = (
        maintenance_url
        .replace("postgresql+asyncpg://", "postgresql+psycopg://")
        .replace("postgresql://", "postgresql+psycopg://")
    )
    # Restore query params if present
    if "?" in url:
        maintenance_url += "?" + url.split("?", 1)[1]

    conn = psycopg.connect(maintenance_url, autocommit=True)
    try:
        row = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
        ).fetchone()
        if row is None:
            # Use quoted identifier — db_name is already validated
            conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        conn.close()
```

**Step 2: Verify operationally**

Run: `uv run python -c "from promptgrimoire.db.bootstrap import ensure_database_exists; print('import ok')"`
Expected: Prints `import ok`

Run: `uv run ruff check src/promptgrimoire/db/bootstrap.py`
Expected: No lint errors

**Step 3: Commit**

```bash
git add src/promptgrimoire/db/bootstrap.py
git commit -m "feat: add ensure_database_exists() for branch DB auto-creation"
```
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_A -->
