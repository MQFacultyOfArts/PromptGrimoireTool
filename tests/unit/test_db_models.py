"""Unit tests for SQLModel database models."""

from __future__ import annotations

from datetime import UTC
from uuid import UUID

from tests.unit.conftest import SAMPLE_OWNER_ID, SAMPLE_USER_ID


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


class TestClassModel:
    """Tests for Class SQLModel."""

    def test_class_has_default_uuid(self, make_class) -> None:
        """Class gets auto-generated UUID if not provided."""
        cls = make_class()
        assert cls.id is not None
        assert isinstance(cls.id, UUID)

    def test_class_has_default_created_at(self, make_class) -> None:
        """Class gets auto-generated created_at timestamp."""
        cls = make_class()
        assert cls.created_at is not None

    def test_class_created_at_is_timezone_aware(self, make_class) -> None:
        """Class.created_at should be timezone-aware UTC."""
        cls = make_class()
        assert cls.created_at.tzinfo == UTC

    def test_class_stores_name(self, make_class) -> None:
        """Class preserves name value."""
        cls = make_class()
        assert cls.name == "Test Class"

    def test_class_stores_owner_id(self, make_class) -> None:
        """Class preserves owner_id value."""
        cls = make_class()
        assert cls.owner_id == SAMPLE_USER_ID

    def test_class_table_name(self) -> None:
        """Class has explicit table name to avoid keyword issues."""
        from promptgrimoire.db.models import Class

        assert Class.__tablename__ == "class"


class TestConversationModel:
    """Tests for Conversation SQLModel."""

    def test_conversation_has_default_uuid(self, make_conversation) -> None:
        """Conversation gets auto-generated UUID if not provided."""
        conv = make_conversation()
        assert conv.id is not None
        assert isinstance(conv.id, UUID)

    def test_conversation_has_default_created_at(self, make_conversation) -> None:
        """Conversation gets auto-generated created_at timestamp."""
        conv = make_conversation()
        assert conv.created_at is not None

    def test_conversation_created_at_is_timezone_aware(self, make_conversation) -> None:
        """Conversation.created_at should be timezone-aware UTC."""
        conv = make_conversation()
        assert conv.created_at.tzinfo == UTC

    def test_conversation_stores_raw_text(self, make_conversation) -> None:
        """Conversation preserves raw_text content."""
        text = "Human: What is 2+2?\n\nAssistant: 2+2 equals 4."
        conv = make_conversation(raw_text=text)
        assert conv.raw_text == text

    def test_conversation_crdt_state_optional(self, make_conversation) -> None:
        """crdt_state defaults to None."""
        conv = make_conversation()
        assert conv.crdt_state is None

    def test_conversation_accepts_crdt_state_bytes(self, make_conversation) -> None:
        """Conversation can store CRDT state as bytes."""
        crdt_bytes = b"\x00\x01\x02\x03"
        conv = make_conversation(crdt_state=crdt_bytes)
        assert conv.crdt_state == crdt_bytes

    def test_conversation_stores_class_id(self, make_conversation) -> None:
        """Conversation preserves class_id value."""
        conv = make_conversation()
        assert conv.class_id == SAMPLE_USER_ID

    def test_conversation_stores_owner_id(self, make_conversation) -> None:
        """Conversation preserves owner_id value."""
        conv = make_conversation()
        assert conv.owner_id == SAMPLE_OWNER_ID
