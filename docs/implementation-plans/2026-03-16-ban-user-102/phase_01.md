# Ban User Implementation Plan — Phase 1: Data Model & DB Layer

**Goal:** Add ban fields to User model, Alembic migration, and DB functions for setting/querying ban state.

**Architecture:** Two new columns on User (`is_banned`, `banned_at`), a setter function following the `set_admin()` pattern, and a query function for listing banned users. All following existing conventions in `db/users.py`.

**Tech Stack:** SQLModel, Alembic, PostgreSQL

**Scope:** Phase 1 of 5 from original design

**Codebase verified:** 2026-03-16

---

## Acceptance Criteria Coverage

This phase implements and tests:

### ban-user-102.AC1: Ban command sets persistent state
- **ban-user-102.AC1.1 Success:** `admin ban <email>` sets `is_banned=True` and `banned_at` to current UTC time on User record
- **ban-user-102.AC1.2 Success:** `admin unban <email>` sets `is_banned=False` and `banned_at=None`

### ban-user-102.AC5: List banned users
- **ban-user-102.AC5.1 Success:** `admin ban --list` displays all banned users with email, display name, and `banned_at` timestamp
- **ban-user-102.AC5.2 Success:** `admin ban --list` with no banned users shows empty result message

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Add ban fields to User model and create Alembic migration

**Files:**
- Modify: `src/promptgrimoire/db/models.py` (User class, around line 100-129)
- Create: `alembic/versions/<hash>_add_user_ban_fields.py` (auto-generated)

**Implementation:**

Add two fields to the `User` class in `src/promptgrimoire/db/models.py`, after the existing `is_admin` field (around line 113):

```python
is_banned: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default="false"))
banned_at: datetime | None = Field(
    default=None,
    sa_column=Column(DateTime(timezone=True), nullable=True),
)
```

Follow the same pattern as `is_admin: bool = Field(default=False)` and `created_at: datetime` for column definitions.

Then generate the Alembic migration:

```bash
cd /home/brian/people/Brian/PromptGrimoireTool/.worktrees/ban-user-102
uv run alembic revision --autogenerate -m "add user ban fields"
```

Review the generated migration to confirm it adds:
- `is_banned` column (Boolean, NOT NULL, server_default='false')
- `banned_at` column (DateTime with timezone, nullable)

**Verification:**

```bash
uv run alembic upgrade head
```

Expected: Migration applies cleanly.

**Commit:** `feat(db): add is_banned and banned_at columns to User model`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement `set_banned()`, `is_user_banned()`, and `get_banned_users()`

**Verifies:** ban-user-102.AC1.1, ban-user-102.AC1.2, ban-user-102.AC5.1, ban-user-102.AC5.2

**Files:**
- Modify: `src/promptgrimoire/db/users.py` (add three functions after `set_admin()` at line 216)

**Implementation:**

Add `set_banned()` following the `set_admin()` pattern at `src/promptgrimoire/db/users.py:198-216`:

```python
async def set_banned(user_id: UUID, is_banned: bool) -> User | None:
    """Set or remove ban status for a user.

    When banning, sets banned_at to current UTC time.
    When unbanning, clears banned_at.

    Args:
        user_id: The user's UUID.
        is_banned: Whether user should be banned.

    Returns:
        The updated User or None if not found.
    """
    async with get_session() as session:
        user = await session.get(User, user_id)
        if not user:
            return None
        user.is_banned = is_banned
        user.banned_at = datetime.now(UTC) if is_banned else None
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user
```

Add `is_user_banned()` for lightweight ban checks in `page_route` and the kick endpoint:

```python
async def is_user_banned(user_id: UUID) -> bool:
    """Check if a user is currently banned.

    Lightweight query — returns only the boolean flag, not the full User object.
    Used by page_route decorator and kick endpoint.
    """
    async with get_session() as session:
        result = await session.exec(
            select(User.is_banned).where(User.id == user_id)
        )
        return result.one_or_none() or False
```

Add `get_banned_users()` for the `--list` command:

```python
async def get_banned_users() -> list[User]:
    """Return all currently banned users, ordered by banned_at descending."""
    async with get_session() as session:
        result = await session.exec(
            select(User).where(User.is_banned == True).order_by(User.banned_at.desc())  # noqa: E712
        )
        return list(result.all())
```

Ensure `from datetime import UTC` is imported (add to existing datetime imports at top of file).

**Testing:**

Tests must verify each AC listed above:
- ban-user-102.AC1.1: `set_banned(user_id, True)` sets `is_banned=True` and `banned_at` to a recent UTC datetime
- ban-user-102.AC1.2: `set_banned(user_id, False)` sets `is_banned=False` and `banned_at=None`
- ban-user-102.AC5.1: `get_banned_users()` returns banned users with email, display_name, and banned_at
- ban-user-102.AC5.2: `get_banned_users()` returns empty list when no users are banned

These are integration tests (real database). Place in `tests/integration/test_user_ban.py`. Follow the pattern in `tests/integration/test_user_find_or_create.py` — use `@pytest.mark.asyncio` on async test methods.

**Verification:**

```bash
uv run grimoire test changed
```

Expected: All new ban tests pass.

**Complexipy check:**

```bash
uv run complexipy src/promptgrimoire/db/users.py
```

**Commit:** `feat(db): add set_banned(), is_user_banned(), and get_banned_users() functions`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify set_banned with non-existent user

**Verifies:** ban-user-102.AC1.1, ban-user-102.AC1.2 (edge case: non-existent user returns None)

**Files:**
- Modify: `tests/integration/test_user_ban.py` (add test case)

**Testing:**

Add a test that calls `set_banned()` with a random UUID that doesn't exist in the database. Verify it returns `None` without raising an exception. This follows the `set_admin()` pattern's implicit contract.

**Verification:**

```bash
uv run grimoire test changed
```

Expected: All tests pass.

**Commit:** `test(db): verify set_banned returns None for non-existent user`

<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
