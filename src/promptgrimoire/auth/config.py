"""Authentication configuration.

Load Stytch credentials and app settings from environment variables.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthConfig:
    """Configuration for Stytch authentication.

    Attributes:
        project_id: Stytch project ID.
        secret: Stytch secret key.
        public_token: Stytch public token (for frontend SSO).
        base_url: Base URL for the application.
        storage_secret: Secret for NiceGUI session storage.
        mock_enabled: Whether to use MockAuthClient instead of real Stytch.
        default_org_id: Default organization ID for magic links.
        sso_connection_id: SSO connection ID for AAF integration.
    """

    project_id: str
    secret: str
    public_token: str
    base_url: str
    storage_secret: str
    mock_enabled: bool = False
    default_org_id: str | None = None
    sso_connection_id: str | None = None

    @classmethod
    def from_env(cls) -> AuthConfig:
        """Load configuration from environment variables.

        Required environment variables (always required, even in mock mode):
            - STYTCH_PROJECT_ID: Must point to Stytch test realm for AUTH_MOCK=true
            - STYTCH_SECRET: Must be valid for the project
            - STORAGE_SECRET: NiceGUI session encryption secret

        Optional environment variables:
            - STYTCH_PUBLIC_TOKEN (default: empty string)
            - BASE_URL (default: http://localhost:8080)
            - AUTH_MOCK (default: false) - uses Stytch test realm with real credentials

        Returns:
            AuthConfig instance populated from environment.

        Raises:
            ValueError: If required environment variables are missing.
        """
        mock_enabled = os.environ.get("AUTH_MOCK", "false").lower() == "true"

        # HIGH-6: Mock mode requires Stytch TEST realm credentials, not hardcoded
        # defaults. This ensures we're always using real (test) Stytch infra.
        if mock_enabled:
            logger.warning(
                "AUTH_MOCK=true: Using Stytch test realm. "
                "Ensure STYTCH_PROJECT_ID and STYTCH_SECRET point to test environment."
            )

        # Real mode - require credentials
        project_id = os.environ.get("STYTCH_PROJECT_ID")
        secret = os.environ.get("STYTCH_SECRET")
        storage_secret = os.environ.get("STORAGE_SECRET")

        missing = []
        if not project_id:
            missing.append("STYTCH_PROJECT_ID")
        if not secret:
            missing.append("STYTCH_SECRET")
        if not storage_secret:
            missing.append("STORAGE_SECRET")

        if missing:
            msg = f"Missing required environment variables: {', '.join(missing)}"
            raise ValueError(msg)

        # Type narrowing: after validation, these are guaranteed to be non-None
        assert project_id is not None
        assert secret is not None
        assert storage_secret is not None

        config = cls(
            project_id=project_id,
            secret=secret,
            public_token=os.environ.get("STYTCH_PUBLIC_TOKEN", ""),
            base_url=os.environ.get("BASE_URL", "http://localhost:8080"),
            storage_secret=storage_secret,
            mock_enabled=mock_enabled,  # HIGH-6: Requires real credentials
            default_org_id=os.environ.get("STYTCH_DEFAULT_ORG_ID"),
            sso_connection_id=os.environ.get("STYTCH_SSO_CONNECTION_ID"),
        )

        # Validate config to fail fast on misconfiguration
        config.validate()

        return config

    def validate(self) -> None:
        """Validate configuration and fail fast on misconfigurations.

        Raises:
            ValueError: If configuration is incomplete or inconsistent.
        """
        errors: list[str] = []

        # SSO requires both connection_id AND public_token
        if self.sso_connection_id and not self.public_token:
            errors.append(
                "STYTCH_SSO_CONNECTION_ID is set but STYTCH_PUBLIC_TOKEN is empty. "
                "SSO requires both to be configured."
            )

        # If public_token is set, we expect some SSO/OAuth use
        # But SSO specifically requires connection_id
        # (OAuth only needs public_token + default_org_id, so that's fine)

        # Magic links require default_org_id
        # But this is optional - app can work without magic links

        if errors:
            error_msg = "Auth configuration errors:\n" + "\n".join(
                f"  - {e}" for e in errors
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

    @property
    def magic_link_callback_url(self) -> str:
        """Get the magic link callback URL."""
        return f"{self.base_url}/auth/callback"

    @property
    def sso_callback_url(self) -> str:
        """Get the SSO callback URL."""
        return f"{self.base_url}/auth/sso/callback"
