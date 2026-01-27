---
name: warn-migration-edits
enabled: true
event: file
conditions:
  - field: file_path
    operator: regex_match
    pattern: alembic/versions/.*\.py$
action: warn
---

**Editing Alembic Migration File**

You're modifying a database migration. Please verify:

- [ ] This migration hasn't been applied to production yet
- [ ] If already applied, create a NEW migration instead of editing
- [ ] The `upgrade()` and `downgrade()` functions are inverses
- [ ] All models are imported before schema operations
- [ ] Test with `alembic upgrade head` then `alembic downgrade -1`

**Never edit applied migrations** - create new ones to fix issues.
