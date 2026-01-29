"""Unit tests for SQLModel database models."""

from __future__ import annotations

from datetime import UTC
from uuid import UUID


class TestUserModel:
    """Tests for User SQLModel."""

    def test_user_has_default_uuid(self, make_user) -> None:
        """User gets auto-generated UUID if not provided."""
        user = make_user()
        assert user.id is not None
        assert isinstance(user.id, UUID)

    def test_user_has_default_created_at(self, make_user) -> None:
        """User gets auto-generated created_at timestamp."""
        user = make_user()
        assert user.created_at is not None

    def test_user_created_at_is_timezone_aware(self, make_user) -> None:
        """User.created_at should be timezone-aware UTC."""
        user = make_user()
        assert user.created_at.tzinfo == UTC

    def test_user_stytch_member_id_optional(self, make_user) -> None:
        """stytch_member_id defaults to None."""
        user = make_user()
        assert user.stytch_member_id is None

    def test_user_stores_email(self, make_user) -> None:
        """User preserves email value."""
        user = make_user()
        assert user.email == "test@example.com"

    def test_user_stores_display_name(self, make_user) -> None:
        """User preserves display_name value."""
        user = make_user()
        assert user.display_name == "Test User"
