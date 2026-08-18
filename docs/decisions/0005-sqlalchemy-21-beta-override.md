# 0005 — Run SQLAlchemy 2.1.0b3 under SQLModel via a bounded uv override

**Status:** Accepted
**Date:** 2026-08-17
**Deciders:** Brian Ballsun-Stanton

## Context

ADR 0004 adopts `tstring(t"...")` as the raw-SQL idiom. tstring exists only in
SQLAlchemy 2.1 (landed 2.1.0b1, January 2026); stable is 2.0.x. SQLModel —
including latest 0.0.39 — pins `SQLAlchemy >=2.0.14,<2.1.0`, so the two are
formally incompatible.

Evidence gathered 2026-08-17 before deciding:

- The SQLModel cap is stated precaution, not known breakage: the maintainers
  closed a pin-relaxation PR (fastapi/sqlmodel#1884) with "until SQLAlchemy
  2.1 released, they can still break things... Let's wait for the release."
  The same PR's author self-reports SQLModel 0.0.38 on 2.1.0b2 in production.
- The 2.1 beta tracker has no open correctness or data-integrity bugs; the
  GA-blocking milestone holds two internal refactors. The one 2.1-introduced
  regression found (dataclass validation, #13227) was fixed 2026-08-07.
- The asyncpg cancellation bug (#13381 — connection returned to the pool with
  an open transaction after task cancellation in a cursor-execute hook, a
  real risk on this stack) is fixed in 2.1.0b3 itself; the fix is not
  confirmed backported to 2.0.x. On this point b3 is *safer* than stable.
- Local smoke: SQLModel 0.0.38 imports, model classes register, and selects
  compile on 2.1.0b3.
- Honest caveat: tstring's clean bug record partly reflects thin adoption —
  it requires Python 3.14 to exercise. This project has run 3.14 since
  before GA and accepts early-adopter position knowingly.

## Decision

Override SQLModel's cap with `[tool.uv] override-dependencies =
["sqlalchemy==2.1.0b3"]` — an exact pin, so no later beta is admitted
silently. The operator accepts a beta dependency that has been in
release-candidate state since June with GA targeted "end of summer 2026".

Gate: the full suite (`uv run grimoire e2e all`) must be green on 2.1.0b3
before this ships. If the suite exposes SQLModel-on-2.1 breakage that cannot
be trivially resolved, this ADR is reversed: fall back to stable 2.0.x and
`text()` per ADR 0004's fallback clause.

## Consequences

- We run an upstream-declared incompatibility in production, on our own test
  evidence rather than SQLModel's. The mitigation is the suite plus the
  exact pin.
- When SQLAlchemy 2.1 goes GA and SQLModel lifts its cap, the override is
  deleted and the dependency moves to a normal constraint. Whoever bumps
  either package checks this ADR.
- Until then, `uv lock` output must show sqlalchemy 2.1.0b3 exactly; any
  resolver movement of it is collateral in the ADR 0003 sense and halts the
  step.
