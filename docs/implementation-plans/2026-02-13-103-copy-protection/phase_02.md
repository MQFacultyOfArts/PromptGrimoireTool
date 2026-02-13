# Per-Activity Copy Protection Implementation Plan — Phase 2

**Goal:** `create_activity()` and `update_activity()` support the nullable `copy_protection` field.

**Architecture:** Add `copy_protection` parameter to both CRUD functions using the existing Ellipsis sentinel pattern for tri-state handling. `create_activity()` defaults to `None` (inherit from course). `update_activity()` uses Ellipsis sentinel to distinguish "not provided" from explicit `None` (reset to inherit).

**Tech Stack:** SQLModel, PostgreSQL, Python 3.14

**Scope:** Phase 2 of 6 from original design

**Codebase verified:** 2026-02-13

---

## Acceptance Criteria Coverage

This phase does not introduce new ACs — it extends the CRUD layer to support the `copy_protection` field added in Phase 1. Phase 1 integration tests already cover field storage/retrieval via direct model operations. This phase ensures the service-layer CRUD functions also support the field.

---

## Reference Files

The executor should read these files for context:

- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/src/promptgrimoire/db/activities.py` — Current CRUD functions
- `/home/brian/people/Brian/PromptGrimoireTool/.worktrees/103-copy-protection/tests/integration/test_activity_crud.py` — Existing CRUD test patterns

---

<!-- START_TASK_1 -->
### Task 1: Add copy_protection to create_activity() and update_activity()

**Verifies:** None new (extends Phase 1 AC1 coverage through CRUD layer)

**Files:**
- Modify: `src/promptgrimoire/db/activities.py:21-25` (`create_activity()` — add parameter)
- Modify: `src/promptgrimoire/db/activities.py:74-97` (`update_activity()` — add parameter with Ellipsis sentinel)
- Test: `tests/integration/test_activity_crud.py` (integration — add copy_protection CRUD tests)

**Implementation:**

In `create_activity()`, add parameter after `description`:

```python
async def create_activity(
    week_id: UUID,
    title: str,
    description: str | None = None,
    copy_protection: bool | None = None,
) -> Activity:
```

Pass `copy_protection=copy_protection` when constructing the Activity instance.

In `update_activity()`, add parameter using the existing Ellipsis sentinel pattern:

```python
async def update_activity(
    activity_id: UUID,
    title: str | None = None,
    description: str | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel
    copy_protection: bool | None = ...,  # type: ignore[assignment]  -- Ellipsis sentinel
) -> Activity | None:
```

In the update body, add the same pattern as `description`:

```python
if copy_protection is not ...:
    activity.copy_protection = copy_protection
```

**Testing:**

Add tests to `TestActivityCRUD` class:
- Create activity with `copy_protection=True` — verify field persists
- Create activity with default (no `copy_protection` arg) — verify field is `None`
- Update activity `copy_protection` from `None` to `True` — verify round-trip
- Update activity `copy_protection` from `True` to `None` (reset to inherit) — verify field is `None`
- Update activity with only `title` (don't pass `copy_protection`) — verify `copy_protection` unchanged

**Verification:**

Run:
```bash
uv run pytest tests/integration/test_activity_crud.py -v
```

Expected: All existing and new tests pass.

**Commit:**

```bash
git add src/promptgrimoire/db/activities.py tests/integration/test_activity_crud.py
git commit -m "feat: add copy_protection parameter to create_activity and update_activity"
```

**UAT Steps (end of Phase 2):**

1. [ ] Verify tests: `uv run test-all` — all pass, including new CRUD round-trip tests
2. [ ] Start the app: `uv run python -m promptgrimoire`
3. [ ] Seed data: `uv run seed-data` — completes without error

**Evidence Required:**
- [ ] Test output showing all `TestActivityCRUD` copy_protection tests green
<!-- END_TASK_1 -->
