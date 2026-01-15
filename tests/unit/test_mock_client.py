"""Unit tests for MockAuthClient.

These tests verify the mock auth client behaves correctly
with its predefined test values.
"""

from __future__ import annotations

import pytest

from promptgrimoire.auth.mock import (
    MOCK_MEMBER_ID,
    MOCK_ORG_ID,
    MOCK_VALID_EMAILS,
    MOCK_VALID_MAGIC_TOKEN,
    MOCK_VALID_SESSION,
    MOCK_VALID_SSO_TOKEN,
    MockAuthClient,
)


class TestMockSendMagicLink:
    """Tests for MockAuthClient.send_magic_link."""

    @pytest.fixture
    def client(self):
        """Create a MockAuthClient instance."""
        return MockAuthClient()

    async def test_send_magic_link_valid_email(self, client):
        """Successfully sends magic link for valid email."""
        result = await client.send_magic_link(
            email="test@example.com",
            organization_id="org-123",
            callback_url="http://localhost/callback",
        )

        assert result.success is True
        assert result.member_id == MOCK_MEMBER_ID
        assert result.error is None

    async def test_send_magic_link_new_member(self, client):
        """Returns member_created=True for student@uni.edu."""
        result = await client.send_magic_link(
            email="student@uni.edu",
            organization_id="org-123",
            callback_url="http://localhost/callback",
        )

        assert result.success is True
        assert result.member_created is True

    async def test_send_magic_link_invalid_email(self, client):
        """Returns error for invalid email."""
        result = await client.send_magic_link(
            email="invalid@nowhere.com",
            organization_id="org-123",
            callback_url="http://localhost/callback",
        )

        assert result.success is False
        assert result.error == "invalid_email"
        assert result.member_id is None

    async def test_tracks_sent_magic_links(self, client):
        """Tracks magic links sent for test assertions."""
        await client.send_magic_link(
            email="test@example.com",
            organization_id="org-abc",
            callback_url="http://example.com/callback",
        )

        sent = client.get_sent_magic_links()
        assert len(sent) == 1
        assert sent[0]["email"] == "test@example.com"
        assert sent[0]["organization_id"] == "org-abc"

    async def test_clear_sent_magic_links(self, client):
        """Can clear tracked magic links."""
        await client.send_magic_link(
            email="test@example.com",
            organization_id="org-abc",
            callback_url="http://example.com/callback",
        )
        client.clear_sent_magic_links()

        assert len(client.get_sent_magic_links()) == 0


class TestMockAuthenticateMagicLink:
    """Tests for MockAuthClient.authenticate_magic_link."""

    @pytest.fixture
    def client(self):
        """Create a MockAuthClient instance."""
        return MockAuthClient()

    async def test_authenticate_valid_token(self, client):
        """Successfully authenticates with valid token."""
        result = await client.authenticate_magic_link(token=MOCK_VALID_MAGIC_TOKEN)

        assert result.success is True
        assert result.session_token == MOCK_VALID_SESSION
        assert result.member_id == MOCK_MEMBER_ID
        assert result.organization_id == MOCK_ORG_ID
        assert result.email == "test@example.com"
        assert "stytch_member" in result.roles

    async def test_authenticate_invalid_token(self, client):
        """Returns error for invalid token."""
        result = await client.authenticate_magic_link(token="bad-token")

        assert result.success is False
        assert result.error == "invalid_token"
        assert result.session_token is None


class TestMockAuthenticateSSO:
    """Tests for MockAuthClient.authenticate_sso."""

    @pytest.fixture
    def client(self):
        """Create a MockAuthClient instance."""
        return MockAuthClient()

    async def test_authenticate_valid_sso_token(self, client):
        """Successfully authenticates with valid SSO token."""
        result = await client.authenticate_sso(token=MOCK_VALID_SSO_TOKEN)

        assert result.success is True
        assert result.session_token == MOCK_VALID_SESSION
        assert result.email == "aaf-user@uni.edu"
        assert "instructor" in result.roles

    async def test_authenticate_invalid_sso_token(self, client):
        """Returns error for invalid SSO token."""
        result = await client.authenticate_sso(token="bad-sso-token")

        assert result.success is False
        assert result.error == "invalid_token"


class TestMockValidateSession:
    """Tests for MockAuthClient.validate_session."""

    @pytest.fixture
    def client(self):
        """Create a MockAuthClient instance."""
        return MockAuthClient()

    async def test_validate_valid_session(self, client):
        """Successfully validates a valid session."""
        result = await client.validate_session(session_token=MOCK_VALID_SESSION)

        assert result.valid is True
        assert result.member_id == MOCK_MEMBER_ID
        assert result.email == "test@example.com"

    async def test_validate_invalid_session(self, client):
        """Returns error for invalid session."""
        result = await client.validate_session(session_token="expired-session")

        assert result.valid is False
        assert result.error == "session_not_found"


class TestMockGetSSOStartUrl:
    """Tests for MockAuthClient.get_sso_start_url."""

    @pytest.fixture
    def client(self):
        """Create a MockAuthClient instance."""
        return MockAuthClient()

    def test_generates_mock_url(self, client):
        """Generates a mock SSO start URL."""
        result = client.get_sso_start_url(
            connection_id="saml-abc",
            public_token="public-xyz",
        )

        assert result.success is True
        assert "mock.stytch.com" in result.redirect_url
        assert "saml-abc" in result.redirect_url
        assert "public-xyz" in result.redirect_url


class TestMockConstants:
    """Tests to verify mock constants are accessible."""

    def test_valid_emails_exported(self):
        """MOCK_VALID_EMAILS contains expected test emails."""
        assert "test@example.com" in MOCK_VALID_EMAILS
        assert "student@uni.edu" in MOCK_VALID_EMAILS
        assert "instructor@uni.edu" in MOCK_VALID_EMAILS

    def test_tokens_exported(self):
        """Mock tokens are non-empty strings."""
        assert MOCK_VALID_MAGIC_TOKEN
        assert MOCK_VALID_SSO_TOKEN
        assert MOCK_VALID_SESSION
