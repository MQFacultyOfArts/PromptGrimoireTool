"""Auth client factory.

Provides a factory function to get the appropriate auth client
based on configuration (real Stytch or mock for testing).
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from promptgrimoire.auth.config import AuthConfig

if TYPE_CHECKING:
    from promptgrimoire.auth.protocol import AuthClientProtocol


@lru_cache(maxsize=1)
def _get_config() -> AuthConfig:
    """Get the auth configuration (cached)."""
    return AuthConfig.from_env()


# Cached mock client instance to preserve session state across requests
_mock_client_instance: AuthClientProtocol | None = None


def get_auth_client() -> AuthClientProtocol:
    """Get the appropriate auth client based on configuration.

    If AUTH_MOCK=true, returns MockAuthClient (singleton to preserve sessions).
    Otherwise, returns StytchB2BClient with real credentials.

    Returns:
        An auth client implementing AuthClientProtocol.
    """
    global _mock_client_instance  # noqa: PLW0603
    config = _get_config()

    if config.mock_enabled:
        if _mock_client_instance is None:
            from promptgrimoire.auth.mock import MockAuthClient

            _mock_client_instance = MockAuthClient()
        return _mock_client_instance

    from promptgrimoire.auth.client import StytchB2BClient

    return StytchB2BClient(
        project_id=config.project_id,
        secret=config.secret,
    )


def get_config() -> AuthConfig:
    """Get the auth configuration.

    Returns:
        The AuthConfig instance.
    """
    return _get_config()


def clear_config_cache() -> None:
    """Clear the configuration and mock client caches.

    Useful for testing when you need to reload configuration
    or reset mock client session state.
    """
    global _mock_client_instance  # noqa: PLW0603
    _get_config.cache_clear()
    _mock_client_instance = None
