---
name: block-create-all
enabled: true
event: file
conditions:
  - field: new_text
    operator: regex_match
    pattern: (SQLModel\.)?metadata\.create_all\(
  - field: file_path
    operator: not_contains
    pattern: alembic/versions/
action: warn
---

**SQLModel create_all() Detected Outside Migrations**

Per CLAUDE.md: **Alembic is the ONLY way to create/modify schema.**

Never use `SQLModel.metadata.create_all()` except in Alembic migrations themselves.

**Correct approach:**
1. Create a migration: `alembic revision --autogenerate -m "description"`
2. Review the generated migration
3. Apply with: `alembic upgrade head`

This ensures schema changes are tracked and reproducible.
