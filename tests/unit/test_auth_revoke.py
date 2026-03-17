"""Tests for revoke_member_sessions auth method."""

from __future__ import annotations

import pytest

from promptgrimoire.auth.mock import MockAuthClient, _email_to_member_id


@pytest.fixture
def mock_client() -> MockAuthClient:
    return MockAuthClient()


class TestMockRevokeMemberSessions:
    """Tests for MockAuthClient.revoke_member_sessions."""

    async def test_revoke_clears_sessions_for_member(
        self, mock_client: MockAuthClient
    ) -> None:
        """AC4.1: revoke_member_sessions clears all sessions for the member."""
        # Authenticate to create a session
        result = await mock_client.authenticate_magic_link("mock-token-ban@test.com")
        assert result.success
        assert result.session_token is not None
        session_token: str = result.session_token

        # Verify session is active
        session = await mock_client.validate_session(session_token)
        assert session.valid

        # Revoke all sessions for this member
        member_id = _email_to_member_id("ban@test.com")
        revoke_result = await mock_client.revoke_member_sessions(member_id=member_id)
        assert revoke_result.valid

        # Session should now be invalid
        session = await mock_client.validate_session(session_token)
        assert not session.valid

    async def test_revoke_only_affects_target_member(
        self, mock_client: MockAuthClient
    ) -> None:
        """Revoking one member's sessions does not affect another member."""
        # Authenticate two users
        r1 = await mock_client.authenticate_magic_link("mock-token-user1@test.com")
        r2 = await mock_client.authenticate_magic_link("mock-token-user2@test.com")
        assert r1.success and r2.success
        assert r1.session_token is not None
        assert r2.session_token is not None
        token1: str = r1.session_token
        token2: str = r2.session_token

        # Revoke user1's sessions
        member_id_1 = _email_to_member_id("user1@test.com")
        await mock_client.revoke_member_sessions(member_id=member_id_1)

        # user1 session invalid, user2 session still valid
        s1 = await mock_client.validate_session(token1)
        s2 = await mock_client.validate_session(token2)
        assert not s1.valid
        assert s2.valid

    async def test_revoke_no_sessions_succeeds(
        self, mock_client: MockAuthClient
    ) -> None:
        """Revoking sessions for a member with no sessions returns success."""
        result = await mock_client.revoke_member_sessions(
            member_id="mock-member-nonexistent"
        )
        assert result.valid

    async def test_revoke_returns_session_result(
        self, mock_client: MockAuthClient
    ) -> None:
        """Return type is SessionResult with valid=True."""
        from promptgrimoire.auth.models import SessionResult

        result = await mock_client.revoke_member_sessions(member_id="any-id")
        assert isinstance(result, SessionResult)
        assert result.valid is True
