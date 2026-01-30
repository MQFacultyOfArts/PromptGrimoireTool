"""Shared fixtures for unit tests."""

from __future__ import annotations

from uuid import UUID

import pytest

from promptgrimoire.db.models import User

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
