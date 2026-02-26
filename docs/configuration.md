# Configuration

*Last updated: 2026-02-26*

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
| `FEATURES__` | `FeaturesConfig` | `enable_roleplay`, `enable_file_upload` |
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

## Feature Flags

`FeaturesConfig` controls deployment-level feature visibility. Both flags default to `true`.

| Flag | Effect when `false` |
|------|-------------------|
| `FEATURES__ENABLE_ROLEPLAY` | Hides `/roleplay` and `/logs` from nav; page-level guard blocks direct URL access |
| `FEATURES__ENABLE_FILE_UPLOAD` | Hides the file upload widget in the annotation content form; paste and text area remain available |

### Gating pattern

Feature flags gate pages at two levels:

1. **Navigation filtering:** `requires_roleplay=True` on `@page_route` removes the page from the nav drawer when the flag is off (handled in `registry.get_visible_pages` and `layout.page_layout`).
2. **Direct URL guard:** `require_roleplay_enabled()` at the top of the page function shows an error message if someone navigates to the URL directly.

This mirrors the existing `requires_demo` / `require_demo_enabled()` pattern used for demo pages. When adding new feature-gated pages, follow both steps.
