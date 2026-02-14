# Pydantic-Settings Migration — Phase 3: Auth Module Migration

**Goal:** Replace `AuthConfig` dataclass and `factory.py` cache with `StytchConfig` from Settings. Eliminate all `os.environ` calls from auth and auth-related page code.

**Architecture:** `auth/config.py` is deleted entirely. `auth/factory.py` reads from `get_settings()` — stytch credentials from `settings.stytch`, mock toggle from `settings.dev.auth_mock`. `pages/auth.py` replaces `get_config()` calls with `get_settings()` and removes direct `os.environ` access. `SecretStr` is unwrapped at the factory→StytchB2BClient boundary only.

**Tech Stack:** pydantic-settings v2, pydantic v2 (SecretStr)

**Scope:** 7 phases from original design (phase 3 of 7)

**Codebase verified:** 2026-02-13

---

## Acceptance Criteria Coverage

This phase implements and tests:

### 130-pydantic-settings.AC3: AuthConfig replacement
- **130-pydantic-settings.AC3.1 Success:** `get_auth_client()` returns a Stytch client using `get_settings().stytch` credentials
- **130-pydantic-settings.AC3.2 Success:** `get_auth_client()` returns mock client when `dev.auth_mock` is `True`
- **130-pydantic-settings.AC3.3 Failure:** `get_auth_client()` raises when `stytch.project_id` is empty and `dev.auth_mock` is `False`
- **130-pydantic-settings.AC3.4 Success:** No `AuthConfig` dataclass or `from_env()` classmethod exists in codebase

### 130-pydantic-settings.AC4: SecretStr for sensitive fields
- **130-pydantic-settings.AC4.1 Success:** `str(settings)` masks `stytch.secret`, `llm.api_key`, `app.storage_secret`
- **130-pydantic-settings.AC4.2 Success:** `.get_secret_value()` returns actual secret value for consumer use

---

<!-- START_TASK_1 -->
### Task 1: Delete auth/config.py and update auth/__init__.py exports

**Verifies:** 130-pydantic-settings.AC3.4

**Files:**
- Delete: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/auth/config.py`
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/auth/__init__.py`

**Implementation:**

1. Delete `src/promptgrimoire/auth/config.py` entirely (145 lines). This removes:
   - `AuthConfig` frozen dataclass
   - `from_env()` classmethod with its 8 `os.environ.get()` calls
   - `validate()` method (SSO cross-validation now handled by `StytchConfig.sso_requires_public_token` model_validator in `config.py`)
   - `magic_link_callback_url` and `sso_callback_url` properties (unused by production code — `pages/auth.py` inlines these computations)

2. Update `src/promptgrimoire/auth/__init__.py`:
   - Remove `from promptgrimoire.auth.config import AuthConfig` (line 22)
   - Remove `AuthConfig` from `__all__` list (line 34)
   - Remove `get_config` from the import on line 23: change to `from promptgrimoire.auth.factory import clear_config_cache, get_auth_client`
   - Remove `get_config` from the docstring example (line 9)
   - Remove `get_config` from `__all__` list (line 41)

The updated `__init__.py` should be:

```python
"""Authentication module for PromptGrimoire.

Provides Stytch B2B authentication with support for:
- Magic link authentication
- SSO via SAML (AAF Rapid IdP)
- Mock client for testing

Usage:
    from promptgrimoire.auth import get_auth_client

    # Get the configured auth client
    client = get_auth_client()

    # Send a magic link
    result = await client.send_magic_link(
        email="user@example.com",
        organization_id="org-123",
        callback_url="http://localhost:8080/auth/callback",
    )
"""

from promptgrimoire.auth.factory import clear_config_cache, get_auth_client
from promptgrimoire.auth.models import (
    AuthResult,
    SendResult,
    SessionResult,
    SSOStartResult,
)
from promptgrimoire.auth.protocol import AuthClientProtocol

__all__ = [
    "AuthClientProtocol",
    "AuthResult",
    "SSOStartResult",
    "SendResult",
    "SessionResult",
    "clear_config_cache",
    "get_auth_client",
]
```

**Verification:**
Run: `uv run ruff check src/promptgrimoire/auth/`
Expected: No lint errors

**Note:** Tasks 1 and 2 must be committed together since factory.py imports from auth/config.py. Deleting config.py without updating factory.py breaks imports. Defer the import verification (`from promptgrimoire.auth import get_auth_client`) until after Task 2 is complete.
<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-3) -->
<!-- START_TASK_2 -->
### Task 2: Rewrite auth/factory.py to use get_settings()

**Verifies:** 130-pydantic-settings.AC3.1, 130-pydantic-settings.AC3.2, 130-pydantic-settings.AC3.3, 130-pydantic-settings.AC4.2

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/auth/factory.py`
- Reference: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/config.py` (created in Phase 1)
- Reference: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/auth/client.py` (StytchB2BClient.__init__ takes `str` for project_id and secret)

**Implementation:**

Rewrite `src/promptgrimoire/auth/factory.py`. The current implementation (73 lines) has its own `@lru_cache` for `_get_config()` returning `AuthConfig.from_env()`. Replace with `get_settings()` from `config.py`.

Key changes:
1. Remove `from promptgrimoire.auth.config import AuthConfig` import
2. Add `from promptgrimoire.config import get_settings` import
3. Remove `_get_config()` function entirely
4. Update `get_auth_client()`:
   - Read `settings = get_settings()`
   - Check `settings.dev.auth_mock` instead of `config.mock_enabled`
   - Pass `settings.stytch.project_id` and `settings.stytch.secret.get_secret_value()` to `StytchB2BClient`
   - Raise `ValueError` when `stytch.project_id` is empty and mock is disabled (AC3.3)
5. Remove `get_config()` public wrapper (no longer needed — consumers use `get_settings()` directly)
6. Update `clear_config_cache()` to call `get_settings.cache_clear()` instead of `_get_config.cache_clear()`

**Behavior change:** The old `AuthConfig.from_env()` raised `ValueError` at config construction if SSO fields were invalid. The new factory raises `ValueError` at `get_auth_client()` call time when `stytch.project_id` is empty and mock is disabled. This is a new check at the factory layer — previously, an empty `project_id` would silently pass through to `StytchB2BClient`, which would fail later at API call time. The new ValueError is strictly better: earlier failure with a clear message.

The rewritten `factory.py`:

```python
"""Auth client factory.

Provides a factory function to get the appropriate auth client
based on configuration (real Stytch or mock for testing).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from promptgrimoire.config import get_settings

if TYPE_CHECKING:
    from promptgrimoire.auth.protocol import AuthClientProtocol


# Cached mock client instance to preserve session state across requests
_mock_client_instance: AuthClientProtocol | None = None


def get_auth_client() -> AuthClientProtocol:
    """Get the appropriate auth client based on configuration.

    If DEV__AUTH_MOCK=true, returns MockAuthClient (singleton to preserve sessions).
    Otherwise, returns StytchB2BClient with real credentials.

    Returns:
        An auth client implementing AuthClientProtocol.

    Raises:
        ValueError: If stytch.project_id is empty and mock mode is disabled.
    """
    global _mock_client_instance  # noqa: PLW0603
    settings = get_settings()

    if settings.dev.auth_mock:
        if _mock_client_instance is None:
            from promptgrimoire.auth.mock import MockAuthClient

            _mock_client_instance = MockAuthClient()
        return _mock_client_instance

    stytch = settings.stytch
    if not stytch.project_id:
        msg = (
            "STYTCH__PROJECT_ID is required when DEV__AUTH_MOCK is not enabled. "
            "Set STYTCH__PROJECT_ID and STYTCH__SECRET in your .env file."
        )
        raise ValueError(msg)

    from promptgrimoire.auth.client import StytchB2BClient

    return StytchB2BClient(
        project_id=stytch.project_id,
        secret=stytch.secret.get_secret_value(),
    )


def clear_config_cache() -> None:
    """Clear the configuration and mock client caches.

    Useful for testing when you need to reload configuration
    or reset mock client session state.
    """
    global _mock_client_instance  # noqa: PLW0603
    get_settings.cache_clear()
    _mock_client_instance = None
```

**Testing:**
- AC3.1: Existing `test_auth_client.py` tests for StytchB2BClient construction still pass (they construct the client directly with string args, unaffected by factory changes)
- AC3.2: Manual verification — construct `Settings(_env_file=None, dev=DevConfig(auth_mock=True))`, call `get_auth_client()`, verify MockAuthClient returned
- AC3.3: Will be tested in Task 3 (TestAuthConfigValidation rewrite)
- AC4.2: The `.get_secret_value()` call in the factory ensures the actual secret reaches StytchB2BClient

**Verification:**
Run: `uv run ruff check src/promptgrimoire/auth/factory.py`
Expected: No lint errors

Run: `uv run python -c "from promptgrimoire.auth import get_auth_client; print('ok')"`
Expected: Prints `ok`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update pages/auth.py — replace os.environ and get_config() with get_settings()

**Verifies:** 130-pydantic-settings.AC3.1, 130-pydantic-settings.AC3.2

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/pages/auth.py`
- Reference: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/config.py`

**Implementation:**

Update `src/promptgrimoire/pages/auth.py` to remove all `os.environ` access and `get_config()` usage:

1. **Import changes** (top of file):
   - Remove: `import os` (line 11)
   - Change line 16 from `from promptgrimoire.auth import get_auth_client, get_config` to `from promptgrimoire.auth import get_auth_client`
   - Add: `from promptgrimoire.config import get_settings`

2. **`_upsert_local_user` function** (line 93):
   - Replace `if not os.environ.get("DATABASE_URL"):` with `if not get_settings().database.url:`

3. **`login_page` function** (line 337):
   - Replace `if os.environ.get("AUTH_MOCK") == "true":` with `if get_settings().dev.auth_mock:`

4. **`_build_magic_link_section` function** (lines 178-179):
   - Replace:
     ```python
     auth_client = get_auth_client()
     config = get_config()
     ```
   - With:
     ```python
     auth_client = get_auth_client()
     settings = get_settings()
     ```
   - Replace `config.default_org_id` with `settings.stytch.default_org_id`
   - Replace `config.base_url` with `settings.app.base_url`
   - Update error log message: `"STYTCH_DEFAULT_ORG_ID not configured"` → `"STYTCH__DEFAULT_ORG_ID not configured"`

5. **`_build_sso_section` function** (lines 215-217):
   - Replace:
     ```python
     auth_client = get_auth_client()
     config = get_config()
     ```
   - With:
     ```python
     auth_client = get_auth_client()
     settings = get_settings()
     ```
   - Replace `config.sso_connection_id` with `settings.stytch.sso_connection_id`
   - Replace `config.public_token` with `settings.stytch.public_token`
   - Update error log messages to use new env var names

6. **`_build_github_oauth_section` function** (lines 258-259):
   - Replace:
     ```python
     auth_client = get_auth_client()
     config = get_config()
     ```
   - With:
     ```python
     auth_client = get_auth_client()
     settings = get_settings()
     ```
   - Replace `config.public_token` with `settings.stytch.public_token`
   - Replace `config.default_org_id` with `settings.stytch.default_org_id`
   - Replace `config.base_url` with `settings.app.base_url`
   - Update error log messages to use new env var names

**Verification:**
Run: `uv run ruff check src/promptgrimoire/pages/auth.py`
Expected: No lint errors

Run: `uv run python -c "import ast; ast.parse(open('src/promptgrimoire/pages/auth.py').read()); print('syntax ok')"`
Expected: Prints `syntax ok`

Verify no `os.environ` or `get_config` references remain:
Run: `grep -n "os.environ\|get_config" src/promptgrimoire/pages/auth.py`
Expected: No output (no matches)

**Commit (Tasks 1-3 together):** `refactor: replace AuthConfig with Settings in auth module`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_4 -->
### Task 4: Rewrite TestAuthConfigValidation to test StytchConfig directly

**Verifies:** 130-pydantic-settings.AC3.3, 130-pydantic-settings.AC3.4, 130-pydantic-settings.AC4.1, 130-pydantic-settings.AC4.2

**Files:**
- Modify: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/tests/unit/test_auth_client.py`
  - Lines 358-427: `TestAuthConfigValidation` class — complete rewrite
- Reference: `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/130-pydantic-settings/src/promptgrimoire/config.py`

**Implementation:**

Replace the `TestAuthConfigValidation` class (lines 358-427) in `test_auth_client.py`. The current tests use `monkeypatch.setenv()` with old env var names and test `AuthConfig.from_env()`. Replace with direct `StytchConfig()` construction.

The existing tests for `StytchB2BClient` (lines 11-355) remain unchanged — they test the client wrapper directly and are unaffected by the factory changes.

Replace `TestAuthConfigValidation` with:

```python
class TestStytchConfigValidation:
    """Tests for StytchConfig validation via Settings model_validator."""

    def test_sso_connection_id_without_public_token_fails(self):
        """SSO connection ID without public token raises ValidationError."""
        import pytest
        from pydantic import ValidationError

        from promptgrimoire.config import StytchConfig

        with pytest.raises(
            ValidationError,
            match="STYTCH__SSO_CONNECTION_ID requires STYTCH__PUBLIC_TOKEN",
        ):
            StytchConfig(
                sso_connection_id="sso-conn-123",
                public_token="",
            )

    def test_sso_connection_id_with_public_token_succeeds(self):
        """SSO connection ID with public token validates successfully."""
        from promptgrimoire.config import StytchConfig

        config = StytchConfig(
            sso_connection_id="sso-conn-123",
            public_token="public-token-456",
        )

        assert config.sso_connection_id == "sso-conn-123"
        assert config.public_token == "public-token-456"

    def test_public_token_without_sso_connection_id_succeeds(self):
        """Public token alone is valid (for OAuth without SSO)."""
        from promptgrimoire.config import StytchConfig

        config = StytchConfig(
            public_token="public-token-456",
        )

        assert config.public_token == "public-token-456"
        assert config.sso_connection_id is None

    def test_minimal_config_validates(self):
        """Minimal config (all defaults) validates successfully."""
        from promptgrimoire.config import StytchConfig

        config = StytchConfig()

        assert config.project_id == ""
        assert config.public_token == ""
        assert config.sso_connection_id is None


class TestGetAuthClientFactory:
    """Tests for get_auth_client() factory function with Settings."""

    def test_raises_when_project_id_empty_and_mock_disabled(self):
        """get_auth_client() raises ValueError when stytch.project_id is empty."""
        import pytest

        from promptgrimoire.config import Settings, get_settings

        get_settings.cache_clear()

        settings = Settings(
            _env_file=None,
        )
        # Patch get_settings to return our test instance
        with pytest.raises(ValueError, match="STYTCH__PROJECT_ID is required"):
            from unittest.mock import patch

            with patch("promptgrimoire.auth.factory.get_settings", return_value=settings):
                from promptgrimoire.auth.factory import get_auth_client

                get_auth_client()

    def test_returns_mock_client_when_auth_mock_enabled(self):
        """get_auth_client() returns MockAuthClient when dev.auth_mock is True."""
        from unittest.mock import patch

        from promptgrimoire.auth.factory import clear_config_cache, get_auth_client
        from promptgrimoire.auth.mock import MockAuthClient
        from promptgrimoire.config import DevConfig, Settings

        settings = Settings(
            _env_file=None,
            dev=DevConfig(auth_mock=True),
        )

        clear_config_cache()
        with patch("promptgrimoire.auth.factory.get_settings", return_value=settings):
            client = get_auth_client()

        assert isinstance(client, MockAuthClient)


class TestSecretStrMasking:
    """Tests for SecretStr masking in Settings (AC4)."""

    def test_str_masks_secrets(self):
        """str(settings) does not expose secret values."""
        from pydantic import SecretStr

        from promptgrimoire.config import (
            AppConfig,
            LlmConfig,
            Settings,
            StytchConfig,
        )

        settings = Settings(
            _env_file=None,
            stytch=StytchConfig(secret=SecretStr("real-stytch-secret")),
            llm=LlmConfig(api_key=SecretStr("real-api-key")),
            app=AppConfig(storage_secret=SecretStr("real-storage-secret")),
        )

        settings_str = str(settings)
        assert "real-stytch-secret" not in settings_str
        assert "real-api-key" not in settings_str
        assert "real-storage-secret" not in settings_str

    def test_get_secret_value_returns_actual_value(self):
        """get_secret_value() returns the actual secret string."""
        from pydantic import SecretStr

        from promptgrimoire.config import StytchConfig

        config = StytchConfig(secret=SecretStr("my-real-secret"))
        assert config.secret.get_secret_value() == "my-real-secret"
```

**Testing:**
- AC3.3: `test_raises_when_project_id_empty_and_mock_disabled` — factory raises ValueError
- AC3.4: Verify `AuthConfig` no longer importable: `pytest.importorskip` or simply — if any test tries `from promptgrimoire.auth.config import AuthConfig`, it will fail with ImportError since the file is deleted
- AC4.1: `test_str_masks_secrets` — str() output excludes real values
- AC4.2: `test_get_secret_value_returns_actual_value` — unwrapping works

**Verification:**
Run: `uv run pytest tests/unit/test_auth_client.py -v`
Expected: All tests pass. `TestAuthConfigValidation` no longer exists. New test classes pass.

Run: `uv run test-all`
Expected: All 2354+ tests pass

**Commit:** `test: rewrite auth config tests for Settings and StytchConfig`
<!-- END_TASK_4 -->
