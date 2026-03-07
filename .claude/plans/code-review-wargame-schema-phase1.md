# Code Review: Wargame Schema #294 — Full Implementation

**Reviewer:** Claude Opus 4.6
**Date:** 2026-03-07
**Scope:** All uncommitted changes on `wargame-schema-294` branch (Codex implementation)
**Design doc:** `docs/design-plans/2026-03-06-wargame-schema-294.md`
**Implementation plans:** `docs/implementation-plans/2026-03-07-wargame-schema-294/phase_01.md` through `phase_05.md`

## Executive Summary

Codex implemented all 5 phases in a single combined changeset. The Activity discriminator, wargame tables (WargameConfig, WargameTeam, WargameMessage), and ACL extension are all present. The migration is well-structured with a clean downgrade path. Test coverage is thorough for what's implemented.

**One critical gap:** The discriminator-enforcing composite FK (phase 2's entire purpose) is not implemented. WargameConfig and WargameTeam both use simple single-column FKs to `activity.id`, meaning the database does NOT reject a WargameConfig attached to an annotation activity. The design doc was specifically updated to require this pattern.

**Overall:** Solid work with one architectural omission that undermines the type-safety guarantee.

## Critical Issues

### C1: Composite FK not implemented (phase 2)

**Design doc requires:** `activity_type` column on WargameConfig and WargameTeam, composite FK `(activity_id, activity_type) REFERENCES activity(id, type)`, `UNIQUE(id, type)` on Activity, CHECK constraining `activity_type = 'wargame'`.

**Actual:** Simple `ForeignKey("activity.id")` on both tables.

**Impact:** The database accepts a WargameConfig row pointing at an annotation activity. The entire discriminator-enforcement pattern is absent.

**Files:**
- `src/promptgrimoire/db/models.py:258` — Activity missing `UniqueConstraint("id", "type")` in `__table_args__`
- `src/promptgrimoire/db/models.py:357-393` — WargameConfig missing `activity_type` field, composite FK, CHECK
- `src/promptgrimoire/db/models.py:395-424` — WargameTeam missing `activity_type` field, composite FK, CHECK
- `alembic/versions/1b59ab790954_add_wargame_schema.py:47-65` — Migration creates simple FK, not composite
- `alembic/versions/1b59ab790954_add_wargame_schema.py:67-101` — Same for wargame_team

**Fix:** Implement phase 2 as specified in `phase_02.md`.

---

## High Priority Issues

### H1: Activity `__table_args__` missing entirely

**File:** `src/promptgrimoire/db/models.py:258-354`

Activity has three CHECK constraints in the migration (`ck_activity_type_known`, `ck_activity_annotation_requires_template`, `ck_activity_wargame_no_template`) but no `__table_args__` declaring them in SQLModel metadata. Every other model with constraints (WargameConfig, ACLEntry, Permission, Tag, etc.) declares its CHECKs in `__table_args__`.

**Impact:** Metadata inconsistency. SQLModel's metadata won't reflect the actual DB schema for Activity. Won't cause runtime failures (the DB enforces it), but breaks the pattern and could confuse future schema introspection or Alembic autogenerate.

**Fix:**
```python
__table_args__ = (
    CheckConstraint(
        "type IN ('annotation', 'wargame')",
        name="ck_activity_type_known",
    ),
    CheckConstraint(
        "type != 'annotation' OR template_workspace_id IS NOT NULL",
        name="ck_activity_annotation_requires_template",
    ),
    CheckConstraint(
        "type != 'wargame' OR template_workspace_id IS NULL",
        name="ck_activity_wargame_no_template",
    ),
)
```

### H2: Two ACLEntry creation sites don't pass `team_id=None` explicitly

**Files:**
- `src/promptgrimoire/db/workspaces.py:725-729`
- `src/promptgrimoire/db/acl.py:439-443`

Both create `ACLEntry(workspace_id=..., user_id=..., permission=...)` without `team_id=None`. Works because model default is `None`, but is implicit. The `grant_share()` function at `acl.py:46-48` correctly passes `team_id=None` — these two sites should match for consistency and safety.

**Fix:** Add `team_id=None` to both call sites.

### H3: Test references nonexistent constraint name

**File:** `tests/integration/test_wargame_schema.py:115`

```python
with pytest.raises(IntegrityError, match="ck_activity_type_known"):
```

The `ck_activity_type_known` constraint exists in the migration but NOT in the Activity model's `__table_args__` (see H1). The test is correct — it proves the DB-level constraint works — but the model metadata mismatch should be fixed (see H1).

---

## Medium Priority Issues

### M1: `# noqa: E711` comments lack context

**Files:** `src/promptgrimoire/db/acl.py:139,222,536,583`

Four instances of `ACLEntry.workspace_id != None  # noqa: E711`. The noqa is correct (SQLAlchemy needs `!=` not `is not` for SQL IS NOT NULL), but a brief note explaining WHY null filtering is needed here would help future readers:

```python
ACLEntry.workspace_id != None,  # noqa: E711 -- exclude team-target ACL rows
```

### M2: No test for WargameMessage sequence ordering

Tests verify uniqueness constraint (`uq_wargame_message_team_sequence`) but don't test that messages can be retrieved in `sequence_no` order. Not blocking — ordering is a query concern, not a schema concern — but the schema exists to support ordered retrieval.

---

## Good Things (no action needed)

1. **Migration structure** — Clean, well-ordered. Downgrade path is sensible (deletes wargame data before restoring NOT NULL on template_workspace_id).
2. **ACL null-safety** — All 4 workspace-query sites in `acl.py` patched with `workspace_id != None` filter. Thorough.
3. **`grant_share` upsert** — Correctly switched from named constraint to `index_elements` + `index_where` to match the partial unique index. (`acl.py:53-55`)
4. **Timer exclusivity** — Both model validation and DB CHECK constraint work correctly. Belt and braces.
5. **ACL target exclusivity** — `num_nonnulls` CHECK + model validator + partial unique indexes all present.
6. **Cascade chains** — activity->team->message and team->ACL entry cascades all tested.
7. **Legacy row proof (AC1.1)** — Raw SQL INSERT without `type` column proves server_default works. Good test technique.
8. **Unknown type rejection** — `ck_activity_type_known` CHECK constraint prevents garbage discriminator values.
9. **Codename uniqueness** — Per-activity uniqueness constraint tested with positive and negative cases.
10. **`create_activity()` explicit type** — Now passes `type="annotation"` explicitly. (`activities.py:63`)
11. **db/__init__.py exports** — All 3 new models properly exported and listed in `__all__`.
12. **Schema registration test** — Updated from 12 to 15 tables with all 3 new tables verified.
13. **Integration test for `list_peer_workspaces`** — The null-subquery test (`test_workspace_owner_subquery_ignores_team_entries`) proves team ACL rows don't poison workspace queries. Defensive and valuable.

---

## Checklist

### Must fix before merge
- [ ] **C1:** Implement composite FK (phase 2) — `activity_type` column, composite FK, UNIQUE on Activity, CHECK constraints on WargameConfig and WargameTeam
- [ ] **H1:** Add `__table_args__` to Activity with all 3 CHECK constraints
- [ ] **H3:** Verify `ck_activity_type_known` test passes (depends on H1 being consistent)

### Should fix before merge
- [ ] **H2:** Add `team_id=None` to `workspaces.py:725` and `acl.py:439`
- [ ] **M1:** Add context to `# noqa: E711` comments

### Can defer
- [ ] **M2:** Sequence ordering test (query concern, not schema)

## Verification Steps

After fixes:
```bash
# Unit + integration tests
uv run grimoire test all -k "wargame_schema or db_schema or activity_crud"

# Type checking
uvx ty check

# Lint
uv run ruff check .

# Complexipy on modified files
uv run complexipy src/promptgrimoire/db/models.py src/promptgrimoire/db/acl.py
```

## Notes for Phase 2 Implementation

The composite FK work is well-specified in `phase_02.md`. Key steps:
1. Add `UniqueConstraint("id", "type")` to Activity's `__table_args__`
2. Add `activity_type` VARCHAR(50) NOT NULL DEFAULT 'wargame' to WargameConfig and WargameTeam
3. Add `CHECK (activity_type = 'wargame')` to both
4. Replace simple FK with composite `FOREIGN KEY (activity_id, activity_type) REFERENCES activity(id, type)`
5. Update migration to match
6. Add negative test: WargameConfig pointing at annotation activity must fail
