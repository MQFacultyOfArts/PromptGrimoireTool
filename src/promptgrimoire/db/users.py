"""CRUD operations for User management.

Provides async database functions for user lookup, creation, and updates.
Handles the hybrid model where users may exist before their first login.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlmodel import select

if TYPE_CHECKING:
    from uuid import UUID

from promptgrimoire.db.engine import get_session
from promptgrimoire.db.models import User


async def get_user_by_id(user_id: UUID) -> User | None:
    """Get a user by their primary key.

    Args:
        user_id: The user's UUID.

    Returns:
        The User or None if not found.
    """
    async with get_session() as session:
        return await session.get(User, user_id)


async def get_user_by_email(email: str) -> User | None:
    """Get a user by their email address.

    Args:
        email: The user's email (case-insensitive lookup).

    Returns:
        The User or None if not found.
    """
    async with get_session() as session:
        result = await session.exec(select(User).where(User.email == email.lower()))
        return result.first()


async def get_user_by_stytch_id(stytch_member_id: str) -> User | None:
    """Get a user by their Stytch member ID.

    Args:
        stytch_member_id: The Stytch member_id.

    Returns:
        The User or None if not found.
    """
    async with get_session() as session:
        result = await session.exec(
            select(User).where(User.stytch_member_id == stytch_member_id)
        )
        return result.first()


async def create_user(
    email: str,
    display_name: str,
    *,
    stytch_member_id: str | None = None,
    is_admin: bool = False,
) -> User:
    """Create a new user.

    Args:
        email: The user's email address.
        display_name: Human-readable name for display.
        stytch_member_id: Optional Stytch member ID if already authenticated.
        is_admin: Whether user has org-level admin rights.

    Returns:
        The created User with generated ID.
    """
    async with get_session() as session:
        user = User(
            email=email.lower(),
            display_name=display_name,
            stytch_member_id=stytch_member_id,
            is_admin=is_admin,
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user


async def find_or_create_user(
    email: str,
    display_name: str,
    *,
    stytch_member_id: str | None = None,
) -> tuple[User, bool]:
    """Find an existing user by email or create a new one.

    Args:
        email: The user's email address.
        display_name: Name to use if creating new user.
        stytch_member_id: Stytch ID to link if creating new user.

    Returns:
        Tuple of (User, created) where created is True if new user was made.
    """
    async with get_session() as session:
        result = await session.exec(select(User).where(User.email == email.lower()))
        existing = result.first()
        if existing:
            return existing, False

        user = User(
            email=email.lower(),
            display_name=display_name,
            stytch_member_id=stytch_member_id,
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user, True


async def link_stytch_member(user_id: UUID, stytch_member_id: str) -> User | None:
    """Link a Stytch member ID to an existing user.

    Called when a pre-enrolled user logs in for the first time.

    Args:
        user_id: The user's UUID.
        stytch_member_id: The Stytch member_id to link.

    Returns:
        The updated User or None if user not found.
    """
    async with get_session() as session:
        user = await session.get(User, user_id)
        if not user:
            return None
        user.stytch_member_id = stytch_member_id
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user


async def update_last_login(user_id: UUID) -> User | None:
    """Update the user's last_login timestamp to now.

    Args:
        user_id: The user's UUID.

    Returns:
        The updated User or None if not found.
    """
    async with get_session() as session:
        user = await session.get(User, user_id)
        if not user:
            return None
        user.last_login = datetime.now(UTC)
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user


async def set_admin(user_id: UUID, is_admin: bool) -> User | None:
    """Set or remove admin status for a user.

    Args:
        user_id: The user's UUID.
        is_admin: Whether user should be an admin.

    Returns:
        The updated User or None if not found.
    """
    async with get_session() as session:
        user = await session.get(User, user_id)
        if not user:
            return None
        user.is_admin = is_admin
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user


async def update_display_name(user_id: UUID, display_name: str) -> User | None:
    """Update a user's display name.

    Args:
        user_id: The user's UUID.
        display_name: The new display name.

    Returns:
        The updated User or None if not found.
    """
    async with get_session() as session:
        user = await session.get(User, user_id)
        if not user:
            return None
        user.display_name = display_name
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user


async def list_users(*, include_inactive: bool = False) -> list[User]:
    """List all users.

    Args:
        include_inactive: If False, only return users who have logged in.

    Returns:
        List of User objects ordered by email.
    """
    async with get_session() as session:
        query = select(User).order_by("email")
        if not include_inactive:
            query = query.where(User.last_login != None)  # noqa: E711
        result = await session.exec(query)
        return list(result.all())


async def list_all_users() -> list[User]:
    """List all users including those who haven't logged in yet.

    Returns:
        List of User objects ordered by email.
    """
    async with get_session() as session:
        result = await session.exec(select(User).order_by("email"))
        return list(result.all())


async def upsert_user_on_login(
    email: str,
    stytch_member_id: str,
    display_name: str | None = None,
    is_admin: bool | None = None,
) -> User:
    """Find or create user on login, update stytch_id and last_login.

    This is the main entry point for the auth callback.

    Args:
        email: User's email from Stytch auth.
        stytch_member_id: Stytch member_id from auth.
        display_name: Optional name from Stytch (falls back to email prefix).
        is_admin: If True, grant admin rights. If None, preserve existing value.

    Returns:
        The User record (created or updated).
    """
    name = display_name or email.split("@", maxsplit=1)[0]

    async with get_session() as session:
        # Try to find by email first (may be pre-enrolled)
        result = await session.exec(select(User).where(User.email == email.lower()))
        user = result.first()

        if user:
            # Update existing user
            if not user.stytch_member_id:
                user.stytch_member_id = stytch_member_id
            user.last_login = datetime.now(UTC)
            if display_name and user.display_name == email.split("@", maxsplit=1)[0]:
                # Update name if it was just the email prefix
                user.display_name = display_name
            # Update admin status if explicitly provided
            if is_admin is not None:
                user.is_admin = is_admin
            session.add(user)
        else:
            # Create new user
            user = User(
                email=email.lower(),
                display_name=name,
                stytch_member_id=stytch_member_id,
                last_login=datetime.now(UTC),
                is_admin=is_admin or False,
            )
            session.add(user)

        await session.flush()
        await session.refresh(user)
        return user
