"""Authentication configuration.

Load Stytch credentials and app settings from environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


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

        Required environment variables:
            - STYTCH_PROJECT_ID
            - STYTCH_SECRET
            - STORAGE_SECRET

        Optional environment variables:
            - STYTCH_PUBLIC_TOKEN (default: empty string)
            - BASE_URL (default: http://localhost:8080)
            - AUTH_MOCK (default: false)

        Returns:
            AuthConfig instance populated from environment.

        Raises:
            ValueError: If required environment variables are missing.
        """
        mock_enabled = os.environ.get("AUTH_MOCK", "false").lower() == "true"

        # If mock is enabled, we don't need real credentials
        if mock_enabled:
            return cls(
                project_id=os.environ.get("STYTCH_PROJECT_ID", "mock-project"),
                secret=os.environ.get("STYTCH_SECRET", "mock-secret"),
                public_token=os.environ.get("STYTCH_PUBLIC_TOKEN", "mock-public-token"),
                base_url=os.environ.get("BASE_URL", "http://localhost:8080"),
                storage_secret=os.environ.get("STORAGE_SECRET", "dev-storage-secret"),
                mock_enabled=True,
                default_org_id=os.environ.get("STYTCH_DEFAULT_ORG_ID"),
                sso_connection_id=os.environ.get("STYTCH_SSO_CONNECTION_ID"),
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

        return cls(
            project_id=project_id,
            secret=secret,
            public_token=os.environ.get("STYTCH_PUBLIC_TOKEN", ""),
            base_url=os.environ.get("BASE_URL", "http://localhost:8080"),
            storage_secret=storage_secret,
            mock_enabled=False,
            default_org_id=os.environ.get("STYTCH_DEFAULT_ORG_ID"),
            sso_connection_id=os.environ.get("STYTCH_SSO_CONNECTION_ID"),
        )

    @property
    def magic_link_callback_url(self) -> str:
        """Get the magic link callback URL."""
        return f"{self.base_url}/auth/callback"

    @property
    def sso_callback_url(self) -> str:
        """Get the SSO callback URL."""
        return f"{self.base_url}/auth/sso/callback"
