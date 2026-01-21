"""Unit tests for SQLModel database models."""

from __future__ import annotations

from datetime import UTC
from uuid import UUID

from promptgrimoire.db.models import Class, Conversation, User


class TestUserModel:
    """Tests for User SQLModel."""

    def test_user_has_default_uuid(self) -> None:
        """User gets auto-generated UUID if not provided."""
        user = User(email="test@example.com", display_name="Test User")
        assert user.id is not None
        assert isinstance(user.id, UUID)

    def test_user_has_default_created_at(self) -> None:
        """User gets auto-generated created_at timestamp."""
        user = User(email="test@example.com", display_name="Test User")
        assert user.created_at is not None

    def test_user_created_at_is_timezone_aware(self) -> None:
        """User.created_at should be timezone-aware UTC."""
        user = User(email="test@example.com", display_name="Test User")
        assert user.created_at.tzinfo == UTC

    def test_user_stytch_member_id_optional(self) -> None:
        """stytch_member_id defaults to None."""
        user = User(email="test@example.com", display_name="Test User")
        assert user.stytch_member_id is None

    def test_user_stores_email(self) -> None:
        """User preserves email value."""
        user = User(email="test@example.com", display_name="Test User")
        assert user.email == "test@example.com"

    def test_user_stores_display_name(self) -> None:
        """User preserves display_name value."""
        user = User(email="test@example.com", display_name="Test User")
        assert user.display_name == "Test User"


class TestClassModel:
    """Tests for Class SQLModel."""

    def test_class_has_default_uuid(self) -> None:
        """Class gets auto-generated UUID if not provided."""
        cls = Class(
            name="Test Class",
            owner_id=UUID("12345678-1234-5678-1234-567812345678"),
            invite_code="ABC123",
        )
        assert cls.id is not None
        assert isinstance(cls.id, UUID)

    def test_class_has_default_created_at(self) -> None:
        """Class gets auto-generated created_at timestamp."""
        cls = Class(
            name="Test Class",
            owner_id=UUID("12345678-1234-5678-1234-567812345678"),
            invite_code="ABC123",
        )
        assert cls.created_at is not None

    def test_class_created_at_is_timezone_aware(self) -> None:
        """Class.created_at should be timezone-aware UTC."""
        cls = Class(
            name="Test Class",
            owner_id=UUID("12345678-1234-5678-1234-567812345678"),
            invite_code="ABC123",
        )
        assert cls.created_at.tzinfo == UTC

    def test_class_stores_name(self) -> None:
        """Class preserves name value."""
        cls = Class(
            name="Test Class",
            owner_id=UUID("12345678-1234-5678-1234-567812345678"),
            invite_code="ABC123",
        )
        assert cls.name == "Test Class"

    def test_class_stores_owner_id(self) -> None:
        """Class preserves owner_id value."""
        owner_id = UUID("12345678-1234-5678-1234-567812345678")
        cls = Class(name="Test Class", owner_id=owner_id, invite_code="ABC123")
        assert cls.owner_id == owner_id

    def test_class_table_name(self) -> None:
        """Class has explicit table name to avoid keyword issues."""
        assert Class.__tablename__ == "class"


class TestConversationModel:
    """Tests for Conversation SQLModel."""

    def test_conversation_has_default_uuid(self) -> None:
        """Conversation gets auto-generated UUID if not provided."""
        conv = Conversation(
            class_id=UUID("12345678-1234-5678-1234-567812345678"),
            owner_id=UUID("87654321-4321-8765-4321-876543218765"),
            raw_text="Human: Hello\n\nAssistant: Hi!",
        )
        assert conv.id is not None
        assert isinstance(conv.id, UUID)

    def test_conversation_has_default_created_at(self) -> None:
        """Conversation gets auto-generated created_at timestamp."""
        conv = Conversation(
            class_id=UUID("12345678-1234-5678-1234-567812345678"),
            owner_id=UUID("87654321-4321-8765-4321-876543218765"),
            raw_text="Human: Hello\n\nAssistant: Hi!",
        )
        assert conv.created_at is not None

    def test_conversation_created_at_is_timezone_aware(self) -> None:
        """Conversation.created_at should be timezone-aware UTC."""
        conv = Conversation(
            class_id=UUID("12345678-1234-5678-1234-567812345678"),
            owner_id=UUID("87654321-4321-8765-4321-876543218765"),
            raw_text="Test",
        )
        assert conv.created_at.tzinfo == UTC

    def test_conversation_stores_raw_text(self) -> None:
        """Conversation preserves raw_text content."""
        text = "Human: What is 2+2?\n\nAssistant: 2+2 equals 4."
        conv = Conversation(
            class_id=UUID("12345678-1234-5678-1234-567812345678"),
            owner_id=UUID("87654321-4321-8765-4321-876543218765"),
            raw_text=text,
        )
        assert conv.raw_text == text

    def test_conversation_crdt_state_optional(self) -> None:
        """crdt_state defaults to None."""
        conv = Conversation(
            class_id=UUID("12345678-1234-5678-1234-567812345678"),
            owner_id=UUID("87654321-4321-8765-4321-876543218765"),
            raw_text="Test",
        )
        assert conv.crdt_state is None

    def test_conversation_accepts_crdt_state_bytes(self) -> None:
        """Conversation can store CRDT state as bytes."""
        crdt_bytes = b"\x00\x01\x02\x03"
        conv = Conversation(
            class_id=UUID("12345678-1234-5678-1234-567812345678"),
            owner_id=UUID("87654321-4321-8765-4321-876543218765"),
            raw_text="Test",
            crdt_state=crdt_bytes,
        )
        assert conv.crdt_state == crdt_bytes

    def test_conversation_stores_class_id(self) -> None:
        """Conversation preserves class_id value."""
        class_id = UUID("12345678-1234-5678-1234-567812345678")
        conv = Conversation(
            class_id=class_id,
            owner_id=UUID("87654321-4321-8765-4321-876543218765"),
            raw_text="Test",
        )
        assert conv.class_id == class_id

    def test_conversation_stores_owner_id(self) -> None:
        """Conversation preserves owner_id value."""
        owner_id = UUID("87654321-4321-8765-4321-876543218765")
        conv = Conversation(
            class_id=UUID("12345678-1234-5678-1234-567812345678"),
            owner_id=owner_id,
            raw_text="Test",
        )
        assert conv.owner_id == owner_id
