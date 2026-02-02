# Fix ty Type Checker Errors for Alembic

## Problem

`uvx ty check` reports 3 errors, all related to Alembic's dynamic module imports:

```
error[unresolved-import]: Module `alembic` has no member `context`
  --> alembic/env.py:18:21

error[unresolved-import]: Module `alembic` has no member `op`
  --> alembic/versions/59d4ef6caf5d_create_user_class_conversation_tables.py:15:21

error[unresolved-import]: Module `alembic` has no member `op`
  --> alembic/versions/995de44465b7_add_cascade_delete_to_foreign_keys.py:18:21
```

## Root Cause

`alembic.context` and `alembic.op` are **runtime-injected modules** - they don't exist as regular Python modules. Alembic dynamically creates these when running migrations. This is by design and works correctly at runtime, but static type checkers cannot resolve them.

## Solution

Add a `[tool.ty]` configuration section to `pyproject.toml` to exclude the `alembic/` directory from type checking.

## Files to Modify

- [pyproject.toml](pyproject.toml) - Add ty configuration

## Implementation

Add the following to `pyproject.toml`:

```toml
[tool.ty]
exclude = ["alembic/"]
```

## Verification

Run `uvx ty check` - should report 0 diagnostics.
