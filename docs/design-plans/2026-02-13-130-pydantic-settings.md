# Migrate to pydantic-settings Design

## Summary

PromptGrimoire currently uses 18 scattered `os.environ.get()` calls across 15 files to read configuration, with explicit `load_dotenv()` calls at multiple entry points and an existing frozen dataclass (`AuthConfig`) for Stytch credentials. This design migrates all environment variable access to a single Pydantic-based configuration system using `pydantic-settings` with automatic `.env` file loading, type validation, and nested sub-models organized by domain (authentication, database, LLM, application runtime, development toggles).

The migration introduces double-underscore naming convention (`STYTCH__PROJECT_ID`, `DATABASE__URL`) to group related variables, uses `SecretStr` for sensitive credentials to prevent accidental logging, and implements worktree-aware `.env` resolution so feature branches in `.worktrees/<branch>/` can inherit the main project's configuration with optional local overrides. A singleton `get_settings()` function provides cached access to a validated configuration instance, enabling fail-fast startup validation while maintaining test isolation through cache clearing and direct `Settings()` construction with `_env_file=None`.

## Definition of Done

Replace all 18 scattered `os.environ.get()` calls across 15 files with a single `Settings(BaseSettings)` class using nested `BaseModel` sub-models per domain (Stytch, Database, LLM, App). Environment variables renamed to double-underscore convention (`STYTCH__PROJECT_ID`, `DATABASE__URL`, etc.). All env vars validated at startup with correct types. `load_dotenv()` eliminated from all call sites. `AuthConfig` frozen dataclass replaced with Pydantic `BaseModel` sub-model. Tests use direct `Settings()` construction instead of `os.environ` manipulation. `SecretStr` used for sensitive fields (STYTCH_SECRET, ANTHROPIC_API_KEY, STORAGE_SECRET). `.env.example` updated with new names and documentation.

**Out of scope:** Secrets file integration (Docker/K8s), env var encryption, config hot-reloading.

## Acceptance Criteria

### 130-pydantic-settings.AC1: Type validation at startup
- **130-pydantic-settings.AC1.1 Success:** `Settings()` accepts valid `.env` with correct types and populates all fields
- **130-pydantic-settings.AC1.2 Success:** Bool fields accept `true`/`false`/`1`/`0`/`yes`/`no` case-insensitively
- **130-pydantic-settings.AC1.3 Success:** Int fields (`port`, `thinking_budget`, `lorebook_token_budget`) coerce from string
- **130-pydantic-settings.AC1.4 Failure:** Non-integer string for int field raises `ValidationError`
- **130-pydantic-settings.AC1.5 Failure:** Missing `.env` file and no env vars produces Settings with all defaults (app still boots)

### 130-pydantic-settings.AC2: Startup validation for cross-field rules
- **130-pydantic-settings.AC2.1 Success:** `StytchConfig` with `sso_connection_id` and `public_token` both set passes validation
- **130-pydantic-settings.AC2.2 Failure:** `StytchConfig` with `sso_connection_id` set but `public_token` empty raises `ValidationError`
- **130-pydantic-settings.AC2.3 Success:** `StytchConfig` with neither `sso_connection_id` nor `public_token` passes (both optional)

### 130-pydantic-settings.AC3: AuthConfig replacement
- **130-pydantic-settings.AC3.1 Success:** `get_auth_client()` returns a Stytch client using `get_settings().stytch` credentials
- **130-pydantic-settings.AC3.2 Success:** `get_auth_client()` returns mock client when `dev.auth_mock` is `True`
- **130-pydantic-settings.AC3.3 Failure:** `get_auth_client()` raises when `stytch.project_id` is empty and `dev.auth_mock` is `False`
- **130-pydantic-settings.AC3.4 Success:** No `AuthConfig` dataclass or `from_env()` classmethod exists in codebase

### 130-pydantic-settings.AC4: SecretStr for sensitive fields
- **130-pydantic-settings.AC4.1 Success:** `str(settings)` masks `stytch.secret`, `llm.api_key`, `app.storage_secret`
- **130-pydantic-settings.AC4.2 Success:** `.get_secret_value()` returns actual secret value for consumer use

### 130-pydantic-settings.AC5: .env.example sync
- **130-pydantic-settings.AC5.1 Success:** Every field in Settings model schema has a corresponding entry in `.env.example`
- **130-pydantic-settings.AC5.2 Success:** Every variable in `.env.example` corresponds to a Settings field
- **130-pydantic-settings.AC5.3 Success:** All env var names use double-underscore convention

### 130-pydantic-settings.AC6: load_dotenv elimination
- **130-pydantic-settings.AC6.1 Success:** Zero `load_dotenv()` calls in application code, test code, or Alembic
- **130-pydantic-settings.AC6.2 Success:** Zero `os.environ.get()` or `os.environ[]` calls in application code
- **130-pydantic-settings.AC6.3 Success:** pydantic-settings reads `.env` natively without explicit `load_dotenv()`

### 130-pydantic-settings.AC7: Worktree .env fallback
- **130-pydantic-settings.AC7.1 Success:** Settings loads `.env` from current project root in main worktree
- **130-pydantic-settings.AC7.2 Success:** Settings loads main worktree `.env` as fallback when running in `.worktrees/<branch>/`
- **130-pydantic-settings.AC7.3 Success:** Local `.env` in worktree overrides main worktree `.env` values
- **130-pydantic-settings.AC7.4 Success:** `get_settings()` logs which `.env` file(s) were loaded at `INFO` level on first call

### 130-pydantic-settings.AC8: Test isolation
- **130-pydantic-settings.AC8.1 Success:** Tests construct `Settings(_env_file=None, ...)` without reading `.env` or env vars
- **130-pydantic-settings.AC8.2 Success:** `get_settings.cache_clear()` resets singleton for test isolation
- **130-pydantic-settings.AC8.3 Success:** Unit tests for pure functions pass config values as parameters (no Settings dependency)

## Glossary

- **pydantic-settings**: Third-party library that extends Pydantic to read configuration from environment variables and `.env` files with automatic type validation and conversion.
- **BaseSettings**: Pydantic class that enables reading configuration from environment variables, `.env` files, and other sources with automatic validation against type-annotated fields.
- **BaseModel**: Core Pydantic class for data validation using Python type hints. Used here for nested configuration sub-models that don't read from env vars directly.
- **SecretStr**: Pydantic type for sensitive string values that prevents accidental exposure in logs, error messages, or `str()` representation. Access actual value via `.get_secret_value()`.
- **env_nested_delimiter**: pydantic-settings configuration that maps nested model fields to environment variables using a delimiter (e.g., `"__"` maps `StytchConfig.project_id` to `STYTCH__PROJECT_ID`).
- **@lru_cache**: Python standard library decorator that caches function results. Used with `maxsize=1` to create a singleton pattern — first call constructs and caches `Settings`, subsequent calls return the cached instance.
- **@model_validator**: Pydantic decorator for cross-field validation rules that run after individual field validation. Used here to enforce "SSO connection ID requires public token" constraint.
- **Git worktree**: Git feature allowing multiple working directories from a single repository. PromptGrimoire uses `.worktrees/<branch>/` for parallel feature development.
- **load_dotenv()**: Function from `python-dotenv` library that manually loads a `.env` file into `os.environ`. Replaced by pydantic-settings' native `.env` reading.
- **Singleton pattern**: Design pattern ensuring a class has only one instance, accessed through a global access point. Here: `get_settings()` returns the same cached `Settings` instance across all calls.
- **Stytch**: Third-party authentication service used by PromptGrimoire for magic link login, passkeys, and RBAC. Configuration includes project ID, secret, and SSO settings.
- **Functional core / imperative shell**: Architecture pattern where pure functions (core) receive values as parameters and shell code (page handlers, CLI) calls singletons like `get_settings()` and passes values down.
- **Alembic**: Database migration tool for SQLAlchemy. Currently reads `DATABASE_URL` after calling `load_dotenv()` — will be migrated to use `get_settings()`.
- **ValidationError**: Pydantic exception raised when configuration values fail type validation or custom validators (e.g., non-integer string for int field).

## Architecture

Single `Settings(BaseSettings)` root class in `src/promptgrimoire/config.py` with five nested `BaseModel` sub-models, one per domain:

| Sub-model | Fields | Purpose |
|-----------|--------|---------|
| `StytchConfig` | `project_id`, `secret: SecretStr`, `public_token`, `default_org_id`, `sso_connection_id` | Auth provider credentials |
| `DatabaseConfig` | `url: str \| None` | Connection string (optional — app runs without DB) |
| `LlmConfig` | `api_key: SecretStr`, `model`, `thinking_budget`, `lorebook_token_budget` | Claude API settings |
| `AppConfig` | `base_url`, `port`, `storage_secret: SecretStr`, `log_dir: Path`, `latexmk_path` | Runtime configuration |
| `DevConfig` | `auth_mock`, `enable_demo_pages`, `database_echo`, `test_database_url` | Dev/debug toggles and test overrides |

`SettingsConfigDict` uses `env_nested_delimiter="__"`. Environment variables become `STYTCH__PROJECT_ID`, `DATABASE__URL`, `LLM__API_KEY`, `APP__PORT`, `DEV__AUTH_MOCK`, etc.

### Singleton Access

`get_settings()` with `@lru_cache(maxsize=1)` provides a single cached `Settings` instance. All consumers import and call `get_settings()` — never construct `Settings()` directly outside tests. Tests call `get_settings.cache_clear()` to reset. On first call, `get_settings()` logs which `.env` file(s) were loaded at `INFO` level for transparency (especially useful in worktrees where the fallback path may be in effect).

### Worktree .env Resolution

`config.py` computes `.env` paths from `__file__` rather than relying on CWD:

- `_PROJECT_ROOT` = `Path(__file__).resolve().parent.parent.parent` (src/promptgrimoire/config.py -> project root)
- `_MAIN_WORKTREE_ENV` = `_PROJECT_ROOT.parent.parent / ".env"` (two levels up — for worktrees at `.worktrees/<branch>/`, this resolves to the main project root)

`SettingsConfigDict` gets `env_file=(_MAIN_WORKTREE_ENV, _PROJECT_ROOT / ".env")`. Later files override earlier ones:

- **Main worktree:** `_MAIN_WORKTREE_ENV` points outside the project (doesn't exist, harmless). Local `.env` is read.
- **Worktree at `.worktrees/branch/`:** `_MAIN_WORKTREE_ENV` resolves to main project's `.env`. Local `.env` (if present) overrides it.

Precedence (highest to lowest): OS env vars > local `.env` > main worktree `.env` > field defaults.

### Consumer Pattern

Follows functional core / imperative shell. Pure functions receive config values as parameters. Only shell code (page handlers, CLI entry points, app startup) calls `get_settings()`:

```python
# Shell (page handler) — reads settings, passes values
settings = get_settings()
client = ClaudeClient(model=settings.llm.model, thinking_budget=settings.llm.thinking_budget)

# Core (pure function) — receives values, no Settings dependency
def build_system_prompt(lorebook_budget: int, ...) -> str: ...
```

This means unit tests call pure functions with explicit arguments — no `Settings` construction needed. Integration tests that test wiring construct `Settings(_env_file=None, ...)` directly.

### Startup Validation

All sub-model fields have defaults (empty string or `None`) so the app boots even when optional services (Stytch, Anthropic) aren't configured. Validation is deferred to consumers: `get_auth_client()` raises if `stytch.project_id` is empty and `dev.auth_mock` is `False`. This preserves current behaviour where annotation-only usage needs no external credentials.

`StytchConfig` retains the SSO cross-validation (`sso_connection_id` requires `public_token`) as a `@model_validator(mode="after")`.

### Settings Contract

```python
from pathlib import Path
from pydantic import BaseModel, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class StytchConfig(BaseModel):
    project_id: str = ""
    secret: SecretStr = SecretStr("")
    public_token: str = ""
    default_org_id: str | None = None
    sso_connection_id: str | None = None

    @model_validator(mode="after")
    def sso_requires_public_token(self) -> "StytchConfig": ...

class DatabaseConfig(BaseModel):
    url: str | None = None

class LlmConfig(BaseModel):
    api_key: SecretStr = SecretStr("")
    model: str = "claude-sonnet-4-20250514"
    thinking_budget: int = 1024
    lorebook_token_budget: int = 0

class AppConfig(BaseModel):
    base_url: str = "http://localhost:8080"
    port: int = 8080
    storage_secret: SecretStr = SecretStr("dev-secret-change-me")
    log_dir: Path = Path("logs/sessions")
    latexmk_path: str = ""

class DevConfig(BaseModel):
    auth_mock: bool = False
    enable_demo_pages: bool = False
    database_echo: bool = False
    test_database_url: str | None = None

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_MAIN_WORKTREE_ENV, _PROJECT_ROOT / ".env"),
        env_nested_delimiter="__",
    )
    stytch: StytchConfig = StytchConfig()
    database: DatabaseConfig = DatabaseConfig()
    llm: LlmConfig = LlmConfig()
    app: AppConfig = AppConfig()
    dev: DevConfig = DevConfig()
```

### Env Var Rename Map

| Old Name | New Name | Sub-model | Type |
|----------|----------|-----------|------|
| `STYTCH_PROJECT_ID` | `STYTCH__PROJECT_ID` | StytchConfig | `str = ""` |
| `STYTCH_SECRET` | `STYTCH__SECRET` | StytchConfig | `SecretStr` |
| `STYTCH_PUBLIC_TOKEN` | `STYTCH__PUBLIC_TOKEN` | StytchConfig | `str = ""` |
| `STYTCH_DEFAULT_ORG_ID` | `STYTCH__DEFAULT_ORG_ID` | StytchConfig | `str \| None` |
| `STYTCH_SSO_CONNECTION_ID` | `STYTCH__SSO_CONNECTION_ID` | StytchConfig | `str \| None` |
| `DATABASE_URL` | `DATABASE__URL` | DatabaseConfig | `str \| None` |
| `ANTHROPIC_API_KEY` | `LLM__API_KEY` | LlmConfig | `SecretStr` |
| `CLAUDE_MODEL` | `LLM__MODEL` | LlmConfig | `str` |
| `CLAUDE_THINKING_BUDGET` | `LLM__THINKING_BUDGET` | LlmConfig | `int` |
| `LOREBOOK_TOKEN_BUDGET` | `LLM__LOREBOOK_TOKEN_BUDGET` | LlmConfig | `int` |
| `BASE_URL` | `APP__BASE_URL` | AppConfig | `str` |
| `PROMPTGRIMOIRE_PORT` | `APP__PORT` | AppConfig | `int` |
| `STORAGE_SECRET` | `APP__STORAGE_SECRET` | AppConfig | `SecretStr` |
| `ROLEPLAY_LOG_DIR` | `APP__LOG_DIR` | AppConfig | `Path` |
| `LATEXMK_PATH` | `APP__LATEXMK_PATH` | AppConfig | `str` |
| `AUTH_MOCK` | `DEV__AUTH_MOCK` | DevConfig | `bool` |
| `ENABLE_DEMO_PAGES` | `DEV__ENABLE_DEMO_PAGES` | DevConfig | `bool` |
| `DATABASE_ECHO` | `DEV__DATABASE_ECHO` | DevConfig | `bool` |
| `TEST_DATABASE_URL` | `DEV__TEST_DATABASE_URL` | DevConfig | `str \| None` |

## Existing Patterns

Investigation found an existing structured config pattern in `src/promptgrimoire/auth/config.py`: a frozen `@dataclass` with `from_env()` classmethod, explicit validation in `validate()`, and `@lru_cache(maxsize=1)` singleton in `auth/factory.py`. This design follows the same singleton-with-validation approach but replaces the manual implementation with pydantic-settings machinery.

The module-level constant pattern (`CLAUDE_MODEL = os.environ.get(...)` at import time) is widespread but considered an anti-pattern for testability. This design shifts all config reads to call time via `get_settings()`.

The `load_dotenv()` pattern appears in three entry points (`__init__.py`, `cli.py`, `conftest.py`) plus `alembic/env.py`. pydantic-settings replaces this entirely with native `.env` reading.

The project root detection pattern in `db/bootstrap.py` (`Path(__file__).parent.parent.parent.parent`) is reused for the worktree `.env` fallback path computation.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Settings Infrastructure

**Goal:** Create `config.py` with all Settings classes and add pydantic-settings dependency.

**Components:**
- `pyproject.toml` — add `pydantic-settings` dependency
- `src/promptgrimoire/config.py` — new file with all `BaseModel` sub-models, `Settings(BaseSettings)`, `get_settings()` singleton, worktree `.env` path resolution
- `.env.example` — update all env var names to double-underscore convention with documentation comments

**Dependencies:** None (first phase)

**Done when:** `uv sync` succeeds. `Settings()` can be constructed in a Python REPL. `.env.example` documents all new env var names.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Test Infrastructure Migration

**Goal:** Update test fixtures to use Settings and verify the new config validates correctly.

**Components:**
- `tests/conftest.py` — remove `load_dotenv()`, update `db_schema_guard` to read `DEV__TEST_DATABASE_URL` and construct Settings, clear `get_settings` cache
- `tests/unit/test_env_vars.py` — rewrite to introspect Settings model schema against `.env.example` instead of grepping source files
- New unit tests for Settings itself — validation, defaults, worktree path resolution, SSO cross-validation

**Dependencies:** Phase 1

**Covers:** 130-pydantic-settings.AC1 (type validation), 130-pydantic-settings.AC2 (startup validation), 130-pydantic-settings.AC5 (.env.example sync)

**Done when:** `uv run test-all` passes. Settings construction with missing/invalid types raises `ValidationError`. SSO cross-validation rejects `sso_connection_id` without `public_token`.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Auth Module Migration

**Goal:** Replace `AuthConfig` dataclass and `factory.py` cache with `StytchConfig` from Settings.

**Components:**
- `src/promptgrimoire/auth/config.py` — remove `AuthConfig` dataclass and `from_env()` classmethod
- `src/promptgrimoire/auth/factory.py` — update `get_auth_client()` to read from `get_settings().stytch`, remove `_get_config()` lru_cache
- `src/promptgrimoire/auth/__init__.py` — update public API exports
- `src/promptgrimoire/pages/auth.py` — replace `os.environ.get("AUTH_MOCK")` and `os.environ.get("STYTCH_*")` with Settings access

**Dependencies:** Phase 2

**Covers:** 130-pydantic-settings.AC3 (AuthConfig replacement), 130-pydantic-settings.AC4 (SecretStr for secrets)

**Done when:** `uv run test-all` passes. Auth mock mode works via `DEV__AUTH_MOCK=true`. No `os.environ` calls remain in auth module.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Database and Export Module Migration

**Goal:** Migrate database engine, bootstrap, schema guard, and LaTeX export to use Settings.

**Components:**
- `src/promptgrimoire/db/engine.py` — replace `os.environ.get("DATABASE_URL")` and `os.environ.get("DATABASE_ECHO")` with `get_settings().database.url` and `get_settings().dev.database_echo`
- `src/promptgrimoire/db/bootstrap.py` — replace `os.environ.get("DATABASE_URL")` with Settings access
- `src/promptgrimoire/db/schema_guard.py` — replace `os.environ.get("DATABASE_URL")` with Settings access
- `src/promptgrimoire/export/pdf.py` — replace `os.environ.get("LATEXMK_PATH")` with `get_settings().app.latexmk_path`

**Dependencies:** Phase 2

**Covers:** 130-pydantic-settings.AC1 (type validation for database_echo bool, port int)

**Done when:** `uv run test-all` passes. Database initialisation respects `DATABASE__URL`. LaTeX export respects `APP__LATEXMK_PATH`. No `os.environ` calls remain in db/ or export/ modules.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: LLM, Roleplay, and Logviewer Migration

**Goal:** Replace module-level env var constants in LLM client, prompt assembly, roleplay, and logviewer with Settings access at call sites.

**Components:**
- `src/promptgrimoire/llm/client.py` — replace `os.environ.get("ANTHROPIC_API_KEY")` with parameter injection from caller
- `src/promptgrimoire/llm/prompt.py` — remove module-level `LOREBOOK_TOKEN_BUDGET` constant; callers pass the value
- `src/promptgrimoire/pages/roleplay.py` — replace module-level `CLAUDE_MODEL`, `THINKING_BUDGET`, `LOG_DIR` with `get_settings()` calls in page handler
- `src/promptgrimoire/pages/logviewer.py` — replace module-level `LOG_DIR` with `get_settings().app.log_dir`

**Dependencies:** Phase 2

**Covers:** 130-pydantic-settings.AC1 (type validation for thinking_budget int), 130-pydantic-settings.AC4 (SecretStr for api_key)

**Done when:** `uv run test-all` passes. No module-level `os.environ` constants remain. Roleplay page reads model/budget from Settings. Logviewer reads log_dir from Settings.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: App Startup, CLI, and Remaining Pages

**Goal:** Migrate the application entry point, CLI commands, and remaining page modules.

**Components:**
- `src/promptgrimoire/__init__.py` — remove `load_dotenv()`, replace `os.environ.get("DATABASE_URL")` and `STORAGE_SECRET` with Settings access
- `src/promptgrimoire/cli.py` — remove `load_dotenv()`, replace all `os.environ.get()` calls with Settings access, update test runner to use `DEV__TEST_DATABASE_URL`
- `src/promptgrimoire/pages/courses.py` — replace `os.environ.get("DATABASE_URL")` with Settings access
- `src/promptgrimoire/pages/layout.py` — replace `demos_enabled()` with `get_settings().dev.enable_demo_pages`
- `alembic/env.py` — remove `load_dotenv()`, read database URL from Settings

**Dependencies:** Phases 3, 4, 5

**Covers:** 130-pydantic-settings.AC6 (load_dotenv elimination)

**Done when:** `uv run test-all` passes. Zero `os.environ.get()` calls remain in application code. Zero `load_dotenv()` calls remain anywhere. `uv run python -m promptgrimoire` starts successfully with `.env` using new var names.
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Cleanup and Dependency Removal

**Goal:** Remove python-dotenv dependency (if no longer needed), clean up any remaining references, verify complete migration.

**Components:**
- `pyproject.toml` — remove `python-dotenv` from dependencies if no remaining imports
- Codebase-wide sweep for any remaining `os.environ`, `os.getenv`, or `load_dotenv` references
- Update `.env` file in working directory to use new names (developer action, documented in migration notes)

**Dependencies:** Phase 6

**Done when:** `uv run test-all` passes. `ruff check` clean. `ty check` clean. No `os.environ.get()`, `os.getenv()`, or `load_dotenv()` calls in application or test code. `python-dotenv` removed from dependencies (unless pydantic-settings requires it as a transitive dependency for `.env` reading).
<!-- END_PHASE_7 -->

## Additional Considerations

**python-dotenv as transitive dependency:** pydantic-settings uses python-dotenv internally for `.env` file reading. Even after removing all direct `load_dotenv()` calls, python-dotenv may remain as an indirect dependency. This is fine — the goal is removing direct usage, not the package itself. If pydantic-settings doesn't require it, remove it.

**Alembic .env loading:** `alembic/env.py` currently calls `load_dotenv()` before reading `DATABASE_URL`. After migration, it must import and call `get_settings()` instead. This affects Alembic migrations run via `alembic upgrade head` directly (not through the app's CLI wrapper). Verify Alembic still works standalone after migration.
