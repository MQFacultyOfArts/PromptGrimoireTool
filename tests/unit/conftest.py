"""Shared fixtures for unit tests."""

from __future__ import annotations

from uuid import UUID

import pytest

from promptgrimoire.db.models import Class, Conversation, User

# Standard UUIDs for test references
SAMPLE_USER_ID = UUID("12345678-1234-5678-1234-567812345678")
SAMPLE_OWNER_ID = UUID("87654321-4321-8765-4321-876543218765")


@pytest.fixture
def make_user():
    """Factory for User instances."""

    def _make(
        email: str = "test@example.com", display_name: str = "Test User", **kwargs
    ):
        return User(email=email, display_name=display_name, **kwargs)

    return _make


@pytest.fixture
def make_class():
    """Factory for Class instances."""

    def _make(
        name: str = "Test Class",
        owner_id: UUID = SAMPLE_USER_ID,
        invite_code: str = "ABC123",
        **kwargs,
    ):
        return Class(name=name, owner_id=owner_id, invite_code=invite_code, **kwargs)

    return _make


@pytest.fixture
def make_conversation():
    """Factory for Conversation instances."""

    def _make(
        class_id: UUID = SAMPLE_USER_ID,
        owner_id: UUID = SAMPLE_OWNER_ID,
        raw_text: str = "Human: Hello\n\nAssistant: Hi!",
        **kwargs,
    ):
        return Conversation(
            class_id=class_id, owner_id=owner_id, raw_text=raw_text, **kwargs
        )

    return _make
