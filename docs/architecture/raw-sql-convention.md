# Raw SQL convention

Decision authority: [ADR 0004](../decisions/0004-raw-sql-for-reads.md) (raw
SQL for reads) and [ADR 0005](../decisions/0005-sqlalchemy-21-beta-override.md)
(SQLAlchemy 2.1 for `tstring()`).

## The split

- **Query-shaped reads: raw SQL via `tstring(t"...")`.** New reads are
  written this way; existing ORM reads migrate when touched.
- **Schema, migrations, simple writes: SQLModel/ORM.** Model classes own the
  tables and Alembic autogeneration. `session.add()` / `session.get()` /
  `session.delete()` / attribute-mutation-then-commit stay as they are.
- Not a target: rewriting working ORM writes into hand-rolled `UPDATE`
  statements, or migrating reads that nothing currently touches.

## The idiom

```python
from sqlalchemy import tstring

user_id = ...  # UUID
rows = (
    await session.execute(
        tstring(
            t"""
            SELECT w.id, w.name, a.permission
            FROM workspace w
            JOIN acl_entry a ON a.workspace_id = w.id
            WHERE a.user_id = {user_id}
            ORDER BY w.created_at
            """
        )
    )
).all()
```

Interpolated Python values become bound parameters automatically (`{user_id}`
renders as `:param_1`); there is no params dict to keep in sync. SQLAlchemy
expressions interpolate as clause elements. Never pre-render a value into the
string with an f-string — the t-string is the safety mechanism.

**Identifiers are the one exception.** Postgres cannot bind table/column
names. Interpolating an identifier is permitted only when it comes from a
trusted catalog source (e.g. `pg_tables`), is individually quoted, and the
site carries a comment saying so. Existing example:
`cli/_shared.py` TRUNCATE helper.

## Row handling

- Result stays inside one function → use the `Row` tuple directly
  (`row[0]`, or `row.name` by label). No wrapper.
- Result crosses a module boundary → a frozen slots dataclass plus one
  mapping function (`NavigatorRow` in `db/navigator.py` is the model).
  Boilerplate is deliberate and visible; do not build a generic mapper.
- Need hydrated model instances (identity map, later mutation)? That's a
  sign the site is a write path or genuinely relational — leave it ORM.
- **ORDER BY is a raw-SQL signal** (Brian's rule, 2026-08-17): an ordered
  query is a display read, and display reads migrate. Unit-of-work fetches
  (get-to-mutate, get-to-delete) don't order. Named exceptions: ordered
  queue-claiming (`ORDER BY ... FOR UPDATE SKIP LOCKED`), and reads that
  depend on ORM-only loading machinery — `defer()`ed columns or
  identity-map instance sharing (workspace_documents.py's header reads are
  the live example). Those stay ORM, fetch unordered, and sort in Python;
  a string `.order_by("col")` is never the answer.

## Tests

Every migrated query gets (or keeps) integration coverage that executes the
SQL against Postgres. A column rename breaks a SQL string at runtime, not at
type-check; the test is what turns that into a CI failure. A migration PR
that removes the last executing test for a query is wrong by definition.

## ty gotchas (measured on ty 0.0.72, 2026-08-17)

- **Read raw-SQL rows by attribute, never by index or destructuring.**
  SQLModel's `session.execute()` stub returns `Result[Any]`, which ty binds
  as a 1-tuple: `row[1]` and `for a, b in rows:` are flagged as
  out-of-bounds regardless of the actual SELECT width. `row.column_label`
  is clean.
- **Use `session.exec()`, not `session.execute()`, when you need
  `.rowcount`** (INSERT/UPDATE). It is also the non-deprecated SQLModel API
  and types as `CursorResult[Any]`.
- **`sqlmodel.select` and `sqlalchemy.select` are not interchangeable.**
  Only the SQLModel wrapper types `Model.field == x` in `.where()`. An
  accidental `from sqlalchemy import select` produces spurious diagnostics.
- **For sites that legitimately stay ORM** (hydrated instances needed for
  `session.delete()` etc.): `Model.metadata.tables[Model.__tablename__].c.field`
  is a real Core `Column` (not a cast trick) for `.in_()`/`.is_()`/
  `.returning()`; single-arg `.join(Target)` auto-infers a real FK. The
  Core-column form is the ONLY sanctioned stay-ORM idiom — and a stay-ORM
  site never orders (see the ORDER BY rule above). `sqlmodel.delete` is a
  bare re-export of the Core `delete` — its `.where()` always needs the
  Core-column form.
- **Sentinel defaults:** ty narrows `is not _UNSET` only when the sentinel
  is an enum literal, not a module-level `object()`. Use a single-member
  `Enum` token, or type the union honestly with `EllipsisType`.
- **Monkey-patching a module function:** ty pins a module `async def`'s
  attribute type to that exact function object, rejecting even a
  signature-identical replacement via `mod.name = fn`. Use
  `setattr(mod, "name", fn)` (with `# noqa: B010` so ruff doesn't autofix it
  back). Test-harness pattern; see cli/e2e/_server_script.py.
- **`to_jsonb(table.*)` hydration: allowlist, not "scalar-only"** (DBA
  review 2026-08-17 — every excluded type below is also a scalar, so
  "scalar-only" is the wrong predicate). Safe through to_jsonb →
  `model_validate`: **uuid, text/varchar, bool, int, timestamptz, date.**
  Excluded, with mechanism:
  - `bytea`: hex text representation (2n+2 chars) → pydantic lax str→bytes
    coerces the hex TEXT to bytes — silent corruption (verified on
    `Workspace.crdt_state`, 181,257 real bytes → 362,516 garbage).
  - `numeric`: to_jsonb emits a full-precision JSON number, but the
    driver's `json.loads` collapses it to float BEFORE pydantic sees it —
    silent precision loss on Decimal fields.
  - `float` NaN/Infinity: rendered as JSON strings; round-trips only by
    coincidence of two lax layers.
  - `interval`: text form pydantic rejects — loud, but still a trap.
  Entities owning excluded types hydrate from real columns
  (`w.*` + `Model.model_validate(row, from_attributes=True)`). A guard test
  enforces the allowlist for to_jsonb-hydrated models.
  Timezone note: to_jsonb yields fixed-offset tzinfo (session TZ), the
  direct-column path yields UTC tzinfo — same instant, different tzinfo
  object; never compare tzinfo identity across the two paths.

## Lint/type interplay

The migration exists partly because ty cannot type SQLModel column
expressions (`Model.field` in `.where()` / `.order_by()` / `.in_()`), and
will not before its 1.0 (astral-sh/ty#3421). Do not "fix" those diagnostics
with `# ty: ignore` or `sqlmodel.col()` in new code — migrate the query.
`col()` is tolerated only inside a function already scheduled for migration.
