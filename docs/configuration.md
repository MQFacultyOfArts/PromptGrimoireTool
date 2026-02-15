# Configuration

*Last updated: 2026-02-15*

All configuration is managed through `src/promptgrimoire/config.py` using pydantic-settings. Environment variables use double-underscore nesting: `DATABASE__URL`, `LLM__API_KEY`, `STYTCH__PROJECT_ID`, etc.

- **Access:** Call `get_settings()` for a cached, validated Settings instance
- **Branch detection:** Call `get_current_branch()` for the current git branch name (or `None` for detached HEAD). Reads `.git/HEAD` directly (no subprocess).
- **Testing:** Construct `Settings(_env_file=None, ...)` directly for isolation; call `get_settings.cache_clear()` to reset the singleton
- **`.env` files:** pydantic-settings reads `.env` natively -- no `load_dotenv()` calls anywhere
- **Secrets:** Use `SecretStr` fields; call `.get_secret_value()` at the point of use

## Sub-models

| Prefix | Model | Key fields |
|--------|-------|------------|
| `DATABASE__` | `DatabaseConfig` | `url` |
| `LLM__` | `LlmConfig` | `api_key`, `model`, `thinking_budget`, `lorebook_token_budget` |
| `APP__` | `AppConfig` | `port`, `storage_secret`, `log_dir`, `latexmk_path`, `base_url` |
| `DEV__` | `DevConfig` | `auth_mock`, `enable_demo_pages`, `database_echo`, `test_database_url`, `branch_db_suffix` |
| `STYTCH__` | `StytchConfig` | `project_id`, `secret`, `public_token`, `default_org_id`, `sso_connection_id` |

## Environment Variables

**Source of truth:** `.env.example`

All environment variables are documented in `.env.example`. Copy it to `.env` and configure for your environment.

A test (`tests/unit/test_env_vars.py`) ensures `.env.example` stays in sync with code:

- All env vars used in code must be in `.env.example`
- All vars in `.env.example` must be used in code
- Each variable must have a documentation comment

**When adding new env vars:** Add them to `.env.example` with a comment, then use in code. The test will fail if they're out of sync.
