"""Tests for per-user PDF export lock.

Verifies that _get_user_export_lock returns consistent locks per user
and that the locked() guard in _handle_pdf_export prevents a user
from stacking concurrent exports.

Regression test for 2026-03-15 production OOM outage.
"""

from __future__ import annotations

import pytest

from promptgrimoire.pages.annotation.pdf_export import (
    _get_user_export_lock,
    _user_export_locks,
)


@pytest.fixture(autouse=True)
def _clean_lock_registry() -> None:
    """Clear the global lock registry between tests."""
    _user_export_locks.clear()


def test_same_user_gets_same_lock() -> None:
    """Same user_id must return the same Lock instance."""
    lock_a = _get_user_export_lock("user-1")
    lock_b = _get_user_export_lock("user-1")
    assert lock_a is lock_b


def test_different_users_get_different_locks() -> None:
    """Different user_ids must return independent Lock instances."""
    lock_a = _get_user_export_lock("user-1")
    lock_b = _get_user_export_lock("user-2")
    assert lock_a is not lock_b


@pytest.mark.asyncio
async def test_lock_blocks_concurrent_export_for_same_user() -> None:
    """When a user's lock is held, lock.locked() returns True.

    This is the condition _handle_pdf_export checks before proceeding.
    A second export attempt for the same user should see locked()=True
    and return early.
    """
    lock = _get_user_export_lock("user-1")

    async with lock:
        # While held, another check for the same user sees it locked
        assert lock.locked(), "Lock should be held during export"
        same_lock = _get_user_export_lock("user-1")
        assert same_lock.locked(), (
            "Re-fetching the lock for the same user must return the same held lock"
        )

        # Different user is unaffected
        other_lock = _get_user_export_lock("user-2")
        assert not other_lock.locked(), "Different user's lock must be independent"

    # After release, same user can export again
    assert not lock.locked()
