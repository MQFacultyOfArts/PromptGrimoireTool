"""Unit tests for StytchB2BClient wrapper.

These tests mock the underlying Stytch SDK to test our wrapper logic in isolation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestExtractRoles:
    """Tests for the _extract_roles helper function."""

    def test_returns_empty_list_for_none(self):
        """Returns empty list when roles is None."""
        from promptgrimoire.auth.client import _extract_roles

        assert _extract_roles(None) == []

    def test_returns_empty_list_for_empty_list(self):
        """Returns empty list when roles is empty."""
        from promptgrimoire.auth.client import _extract_roles

        assert _extract_roles([]) == []

    def test_extracts_string_roles(self):
        """Handles string roles directly."""
        from promptgrimoire.auth.client import _extract_roles

        result = _extract_roles(["admin", "user", "moderator"])
        assert result == ["admin", "user", "moderator"]

    def test_extracts_object_roles_with_role_id(self):
        """Handles role objects with role_id attribute."""
        from promptgrimoire.auth.client import _extract_roles

        role1 = MagicMock()
        role1.role_id = "stytch_admin"
        role2 = MagicMock()
        role2.role_id = "instructor"

        result = _extract_roles([role1, role2])
        assert result == ["stytch_admin", "instructor"]

    def test_handles_single_role(self):
        """Handles list with single role."""
        from promptgrimoire.auth.client import _extract_roles

        assert _extract_roles(["only_role"]) == ["only_role"]


class TestSendMagicLink:
    """Tests for the send_magic_link method."""

    async def test_send_magic_link_success(self, mock_stytch_client):
        """Successfully sends magic link and returns member info."""
        from promptgrimoire.auth.client import StytchB2BClient

        # Arrange
        mock_response = MagicMock()
        mock_response.member_id = "member-test-123"
        mock_response.member_created = False
        mock_stytch_client.magic_links.email.login_or_signup_async = AsyncMock(
            return_value=mock_response
        )

        client = StytchB2BClient(project_id="proj-123", secret="secret-123")

        # Act
        result = await client.send_magic_link(
            email="test@example.com",
            organization_id="org-123",
            callback_url="http://localhost:8080/auth/callback",
        )

        # Assert
        assert result.success is True
        assert result.member_id == "member-test-123"
        assert result.member_created is False
        assert result.error is None

        # Verify Stytch was called correctly
        mock_stytch_client.magic_links.email.login_or_signup_async.assert_called_once_with(
            organization_id="org-123",
            email_address="test@example.com",
            login_redirect_url="http://localhost:8080/auth/callback",
            signup_redirect_url="http://localhost:8080/auth/callback",
        )

    async def test_send_magic_link_new_member(self, mock_stytch_client):
        """Returns member_created=True for new signups."""
        from promptgrimoire.auth.client import StytchB2BClient

        mock_response = MagicMock()
        mock_response.member_id = "member-new-456"
        mock_response.member_created = True
        mock_stytch_client.magic_links.email.login_or_signup_async = AsyncMock(
            return_value=mock_response
        )

        client = StytchB2BClient(project_id="proj-123", secret="secret-123")
        result = await client.send_magic_link(
            email="newuser@example.com",
            organization_id="org-123",
            callback_url="http://localhost/callback",
        )

        assert result.success is True
        assert result.member_created is True

    async def test_send_magic_link_invalid_email(self, mock_stytch_client):
        """Handles invalid email error from Stytch."""
        from stytch.core.response_base import StytchError

        from promptgrimoire.auth.client import StytchB2BClient

        # Create a mock StytchError
        mock_error_details = MagicMock()
        mock_error_details.error_type = "invalid_email"
        mock_error = StytchError(mock_error_details)

        mock_stytch_client.magic_links.email.login_or_signup_async = AsyncMock(
            side_effect=mock_error
        )

        client = StytchB2BClient(project_id="proj-123", secret="secret-123")
        result = await client.send_magic_link(
            email="not-an-email",
            organization_id="org-123",
            callback_url="http://localhost/callback",
        )

        assert result.success is False
        assert result.error == "invalid_email"
        assert result.member_id is None


class TestAuthenticateMagicLink:
    """Tests for the authenticate_magic_link method."""

    async def test_authenticate_magic_link_success(self, mock_stytch_client):
        """Successfully authenticates token and returns session."""
        from promptgrimoire.auth.client import StytchB2BClient

        # Build mock response
        mock_member = MagicMock()
        mock_member.email_address = "user@example.com"
        mock_member.name = "Test User"

        # Roles are objects with role_id attribute
        mock_role = MagicMock()
        mock_role.role_id = "role-student"

        mock_session = MagicMock()
        mock_session.roles = [mock_role]

        mock_response = MagicMock()
        mock_response.member_authenticated = True
        mock_response.member_id = "member-123"
        mock_response.organization_id = "org-456"
        mock_response.session_token = "session-token-xyz"
        mock_response.session_jwt = "jwt-token-abc"
        mock_response.member = mock_member
        mock_response.member_session = mock_session

        mock_stytch_client.magic_links.authenticate_async = AsyncMock(
            return_value=mock_response
        )

        client = StytchB2BClient(project_id="proj-123", secret="secret-123")
        result = await client.authenticate_magic_link(token="valid-token")

        assert result.success is True
        assert result.session_token == "session-token-xyz"
        assert result.session_jwt == "jwt-token-abc"
        assert result.member_id == "member-123"
        assert result.organization_id == "org-456"
        assert result.email == "user@example.com"
        assert result.name == "Test User"
        assert "role-student" in result.roles

    async def test_authenticate_magic_link_invalid_token(self, mock_stytch_client):
        """Handles invalid/expired token error."""
        from stytch.core.response_base import StytchError

        from promptgrimoire.auth.client import StytchB2BClient

        mock_error_details = MagicMock()
        mock_error_details.error_type = "invalid_token"
        mock_error = StytchError(mock_error_details)

        mock_stytch_client.magic_links.authenticate_async = AsyncMock(
            side_effect=mock_error
        )

        client = StytchB2BClient(project_id="proj-123", secret="secret-123")
        result = await client.authenticate_magic_link(token="expired-token")

        assert result.success is False
        assert result.error == "invalid_token"
        assert result.session_token is None

    async def test_authenticate_magic_link_mfa_required(self, mock_stytch_client):
        """Handles MFA required response (member_authenticated=False)."""
        from promptgrimoire.auth.client import StytchB2BClient

        mock_response = MagicMock()
        mock_response.member_authenticated = False
        mock_response.intermediate_session_token = "ist-token"

        mock_stytch_client.magic_links.authenticate_async = AsyncMock(
            return_value=mock_response
        )

        client = StytchB2BClient(project_id="proj-123", secret="secret-123")
        result = await client.authenticate_magic_link(token="valid-but-needs-mfa")

        assert result.success is False
        assert result.error == "mfa_required"


class TestAuthenticateSSO:
    """Tests for the authenticate_sso method."""

    async def test_authenticate_sso_success(self, mock_stytch_client):
        """Successfully authenticates SSO token."""
        from promptgrimoire.auth.client import StytchB2BClient

        mock_member = MagicMock()
        mock_member.email_address = "aaf-user@uni.edu"
        mock_member.name = "SSO User"

        # Roles are objects with role_id attribute
        mock_role = MagicMock()
        mock_role.role_id = "role-instructor"

        mock_session = MagicMock()
        mock_session.roles = [mock_role]

        mock_response = MagicMock()
        mock_response.member_id = "member-sso-123"
        mock_response.organization_id = "org-uni"
        mock_response.session_token = "sso-session-token"
        mock_response.session_jwt = "sso-jwt"
        mock_response.member = mock_member
        mock_response.member_session = mock_session

        mock_stytch_client.sso.authenticate_async = AsyncMock(
            return_value=mock_response
        )

        client = StytchB2BClient(project_id="proj-123", secret="secret-123")
        result = await client.authenticate_sso(token="sso-callback-token")

        assert result.success is True
        assert result.session_token == "sso-session-token"
        assert result.email == "aaf-user@uni.edu"
        assert result.name == "SSO User"
        assert "role-instructor" in result.roles

    async def test_authenticate_sso_passes_trusted_metadata(self, mock_stytch_client):
        """AC4.6: trusted_metadata from Stytch response flows through."""
        from promptgrimoire.auth.client import StytchB2BClient

        mock_member = MagicMock()
        mock_member.email_address = "aaf-user@uni.edu"
        mock_member.name = "SSO User"
        mock_member.trusted_metadata = {
            "eduperson_affiliation": "staff",
            "schac_home_organization": "mq.edu.au",
        }

        mock_role = MagicMock()
        mock_role.role_id = "stytch_member"

        mock_session = MagicMock()
        mock_session.roles = [mock_role]

        mock_response = MagicMock()
        mock_response.member_id = "member-sso-456"
        mock_response.organization_id = "org-uni"
        mock_response.session_token = "sso-session-token"
        mock_response.session_jwt = "sso-jwt"
        mock_response.member = mock_member
        mock_response.member_session = mock_session

        mock_stytch_client.sso.authenticate_async = AsyncMock(
            return_value=mock_response
        )

        client = StytchB2BClient(project_id="proj-123", secret="secret-123")
        result = await client.authenticate_sso(token="sso-token")

        assert result.success is True
        assert result.trusted_metadata == {
            "eduperson_affiliation": "staff",
            "schac_home_organization": "mq.edu.au",
        }

    async def test_authenticate_sso_missing_trusted_metadata(self, mock_stytch_client):
        """trusted_metadata gracefully handles missing attribute."""
        from promptgrimoire.auth.client import StytchB2BClient

        mock_member = MagicMock(spec=["email_address", "name"])
        mock_member.email_address = "user@uni.edu"
        mock_member.name = "User"

        mock_session = MagicMock()
        mock_session.roles = []

        mock_response = MagicMock()
        mock_response.member_id = "member-789"
        mock_response.organization_id = "org-uni"
        mock_response.session_token = "session"
        mock_response.session_jwt = "jwt"
        mock_response.member = mock_member
        mock_response.member_session = mock_session

        mock_stytch_client.sso.authenticate_async = AsyncMock(
            return_value=mock_response
        )

        client = StytchB2BClient(project_id="proj-123", secret="secret-123")
        result = await client.authenticate_sso(token="sso-token")

        assert result.success is True
        assert result.trusted_metadata is None

    async def test_authenticate_sso_invalid_token(self, mock_stytch_client):
        """Handles invalid SSO token."""
        from stytch.core.response_base import StytchError

        from promptgrimoire.auth.client import StytchB2BClient

        mock_error_details = MagicMock()
        mock_error_details.error_type = "invalid_token"
        mock_error = StytchError(mock_error_details)

        mock_stytch_client.sso.authenticate_async = AsyncMock(side_effect=mock_error)

        client = StytchB2BClient(project_id="proj-123", secret="secret-123")
        result = await client.authenticate_sso(token="bad-sso-token")

        assert result.success is False
        assert result.error == "invalid_token"


class TestValidateSession:
    """Tests for the validate_session method."""

    async def test_validate_session_success(self, mock_stytch_client):
        """Successfully validates an active session."""
        from promptgrimoire.auth.client import StytchB2BClient

        mock_member = MagicMock()
        mock_member.email_address = "user@example.com"
        mock_member.name = "Test User"

        # Roles are objects with role_id attribute
        mock_role = MagicMock()
        mock_role.role_id = "role-student"

        mock_session = MagicMock()
        mock_session.roles = [mock_role]
        mock_session.member_id = "member-123"
        mock_session.organization_id = "org-456"

        mock_response = MagicMock()
        mock_response.member = mock_member
        mock_response.member_session = mock_session

        mock_stytch_client.sessions.authenticate_async = AsyncMock(
            return_value=mock_response
        )

        client = StytchB2BClient(project_id="proj-123", secret="secret-123")
        result = await client.validate_session(session_token="valid-session")

        assert result.valid is True
        assert result.member_id == "member-123"
        assert result.email == "user@example.com"
        assert result.name == "Test User"

    async def test_validate_session_expired(self, mock_stytch_client):
        """Handles expired/invalid session."""
        from stytch.core.response_base import StytchError

        from promptgrimoire.auth.client import StytchB2BClient

        mock_error_details = MagicMock()
        mock_error_details.error_type = "session_not_found"
        mock_error = StytchError(mock_error_details)

        mock_stytch_client.sessions.authenticate_async = AsyncMock(
            side_effect=mock_error
        )

        client = StytchB2BClient(project_id="proj-123", secret="secret-123")
        result = await client.validate_session(session_token="expired-session")

        assert result.valid is False
        assert result.error == "session_not_found"


class TestGetSSOStartUrl:
    """Tests for the get_sso_start_url method."""

    def test_generates_correct_url(self):
        """Generates the correct Stytch SSO start URL."""
        from promptgrimoire.auth.client import StytchB2BClient

        with patch("promptgrimoire.auth.client.B2BClient"):
            client = StytchB2BClient(project_id="proj-123", secret="secret-123")
            result = client.get_sso_start_url(
                connection_id="saml-connection-abc",
                public_token="public-token-xyz",
            )

        assert result.success is True
        assert result.redirect_url is not None
        assert "saml-connection-abc" in result.redirect_url
        assert "public-token-xyz" in result.redirect_url
        assert "stytch.com" in result.redirect_url


class TestStytchConfigValidation:
    """Tests for StytchConfig validation via Settings model_validator."""

    def test_sso_connection_id_without_public_token_fails(self):
        """SSO connection ID without public token raises ValidationError."""
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
        """AC3.3: get_auth_client() raises ValueError for empty project_id."""
        from unittest.mock import patch

        from promptgrimoire.config import DevConfig, Settings, StytchConfig

        settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
            stytch=StytchConfig(project_id=""),
            dev=DevConfig(auth_mock=False),
        )
        with (
            patch(
                "promptgrimoire.auth.factory.get_settings",
                return_value=settings,
            ),
            pytest.raises(ValueError, match="STYTCH__PROJECT_ID is required"),
        ):
            from promptgrimoire.auth.factory import get_auth_client

            get_auth_client()

    def test_returns_mock_client_when_auth_mock_enabled(self):
        """AC3.2: get_auth_client() returns MockAuthClient when mock enabled."""
        from unittest.mock import patch

        from promptgrimoire.auth.factory import (
            clear_config_cache,
            get_auth_client,
        )
        from promptgrimoire.auth.mock import MockAuthClient
        from promptgrimoire.config import DevConfig, Settings

        settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
            dev=DevConfig(auth_mock=True),
        )

        clear_config_cache()
        with patch(
            "promptgrimoire.auth.factory.get_settings",
            return_value=settings,
        ):
            client = get_auth_client()

        assert isinstance(client, MockAuthClient)


class TestSecretStrMasking:
    """Tests for SecretStr masking in Settings (AC4)."""

    def test_str_masks_secrets(self):
        """AC4.1: str(settings) does not expose secret values."""
        from pydantic import SecretStr

        from promptgrimoire.config import (
            AppConfig,
            LlmConfig,
            Settings,
            StytchConfig,
        )

        settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
            stytch=StytchConfig(secret=SecretStr("real-stytch-secret")),
            llm=LlmConfig(api_key=SecretStr("real-api-key")),
            app=AppConfig(storage_secret=SecretStr("real-storage-secret")),
        )

        settings_str = str(settings)
        assert "real-stytch-secret" not in settings_str
        assert "real-api-key" not in settings_str
        assert "real-storage-secret" not in settings_str

    def test_get_secret_value_returns_actual_value(self):
        """AC4.2: get_secret_value() returns the actual secret string."""
        from pydantic import SecretStr

        from promptgrimoire.config import StytchConfig

        config = StytchConfig(secret=SecretStr("my-real-secret"))
        assert config.secret.get_secret_value() == "my-real-secret"
