"""Unit tests for StytchB2BClient wrapper.

These tests mock the underlying Stytch SDK to test our wrapper logic in isolation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


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
        assert "role-instructor" in result.roles

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

        # Roles are objects with role_id attribute
        mock_role = MagicMock()
        mock_role.role_id = "role-student"

        mock_session = MagicMock()
        mock_session.roles = [mock_role]

        mock_response = MagicMock()
        mock_response.member_id = "member-123"
        mock_response.organization_id = "org-456"
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
