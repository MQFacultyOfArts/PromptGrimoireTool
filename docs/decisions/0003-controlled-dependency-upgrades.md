# 0003 — Upgrade dependencies one package at a time, transitives included

**Status:** Accepted
**Date:** 2026-08-07
**Deciders:** Brian Ballsun-Stanton

## Context

Returning to the project after three months, `pip-audit` reported 56
advisories across 12 packages, 55 of which CI treated as actionable. That
gate is the only thing standing between the repository and green CI, so it
had to be cleared before any other work.

The obvious move, `uv lock --upgrade`, was tried and rejected. It wanted to
move `stytch` 14.3.0 → 15.3.0 — a major version of the authentication
provider — along with `uvicorn`, `rich`, `structlog` and `virtualenv`, none
of which were vulnerable. Clearing a security gate is not a licence to
re-resolve the world, and a broken auth provider at the start of semester is
a far worse outcome than a stale one.

A second question surfaced during planning and is the reason this record
exists. The supervising instructions asserted that transitive dependencies
must be upgraded *through their parent, never directly*. Applied here that
would have meant moving `typer` in order to reach `click` — reintroducing
exactly the collateral we had just ruled out.

## Decision

**Per-package.** `uv lock --upgrade-package '<name>==<version>'`, one package
per command, one commit each, in patch → minor → major order. Never
`uv lock --upgrade`.

**Transitives directly.** `--upgrade-package` unlocks the named package while
retaining every other locked version, which is precisely the operation
wanted. Do not route a transitive upgrade through its parent. Verify instead
that the parent's declared constraint admits the target; if it does not, stop
and escalate the parent as a separate decision rather than moving it
silently.

**Stop on collateral.** Any movement of a package outside the intended set,
even a patch, halts the step pending a ruling.

**Evidence per package.** Name the lane that actually exercises the code, and
where no lane does, say so. A green suite that never loads the upgraded
package is not evidence about it. The per-package `pip-audit` delta carries
its own positive control: the other packages must still be reported, or the
audit did not really run.

**Target the scoped fix, not the newest release.** `click` went to 8.3.3
rather than the latest available, because 8.3.3 is the security fix and
anything beyond it is unrequested change.

## Consequences

56 advisories → 1, across 12 controlled steps. The survivor is
`PYSEC-2026-3552` in `cryptography`, fixed only in 50.0.0; taking a fourth
major unreviewed was declined, and the deferral is dated in
`docs/dependency-rationale.md` because CI's grace period expires around
2026-08-14.

The instruction that transitives go through their parent is **wrong for uv**
and is not followed here. It guards against `uv add`-style constraint edits
and against yanking a transitive out from under a parent's declared range —
neither of which is what `--upgrade-package` does. This was caught by the
drafting model pushing back on the supervisor's framing with uv's own
documentation, and the pushback was correct.

## A trap worth naming

`[tool.uv] exclude-newer` is a cooldown that delays *adopting* any new release.
The 14 days in the CI `pip-audit` gate is a different mechanism that delays
*failing the build* on a known fix. They are independent; change one without
the other freely. Conflating them on 2026-08-06 nearly tightened the cooldown
fivefold under the description of a "revert".

**Amended 2026-08-07:** the cooldown was 3 days when this was written and is
now 14, by operator ruling — three days is not a meaningful quarantine for a
repository worked in bursts months apart. The two values now coincide, which
makes the distinction above easier to lose, not less real.

Related: `exclude-newer` must be a relative span or a timezone-explicit
RFC 3339 instant. A bare date resolves as end-of-day in *local* time, so one
string means different cutoffs on an AEST machine and in CI's UTC container,
and `uv sync --locked` fails there with "lockfile needs to be updated".
