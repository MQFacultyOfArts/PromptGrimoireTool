# 0006 — Lint/type toolchain versions live in uv.lock and nowhere else

**Status:** Accepted
**Date:** 2026-08-17
**Deciders:** Brian Ballsun-Stanton

## Context

The ty version was pinned as a `uvx ty@0.0.24` literal in eight places:
pre-commit, two CI workflows, two Claude Code hooks, CLAUDE.md (twice) and
AGENTS.md. Every bump was a sweep, sweeps get missed, and this branch exists
because one was overdue by forty-one releases. ruff and complexipy had the
same disease in different forms: ruff's pre-commit hook came from the
external `ruff-pre-commit` repo at its own rev, which drifts from the
uv-locked ruff the hooks and developers actually run; complexipy was a dev
dependency at 5.2.0 while pre-commit ran an external hook at 5.1.0.

Separately, `uvx ty@<version>` is subject to the global uv `exclude-newer`
cooldown at every invocation, which made "run the latest ty" fail in
confusing ways unrelated to the project lockfile.

## Decision

ty, ruff and complexipy are uv dev dependencies, resolved in `uv.lock`, and
every consumer invokes them as `uv run ty check`, `uv run ruff ...`,
`uv run complexipy ...`. Pre-commit uses `repo: local` hooks for all three.
No external pre-commit repos for tools we lock; no `uvx <tool>@<version>`
literals anywhere.

ty is exact-pinned (`ty==0.0.72`): it is pre-1.0 and its diagnostic set
changes per release, so it moves only deliberately. ruff and complexipy use
`>=` floors and move with deliberate relocks under the cooldown.

Adopting the current releases required piercing the 14-day cooldown:
by operator ruling (2026-08-17), a 3-day gate is acceptable for the
lint/type toolchain being refactored around. Recorded as bounded
`exclude-newer-package` entries (the ADR 0003 / nicegui precedent), each
cut immediately after its release's last wheel upload so nothing later is
admitted accidentally. Versions taken: ty 0.0.72, ruff 0.16.3,
complexipy 7.0.1.

In the same pass, ruff 0.16's new markdown code-block formatting is disabled
(`[tool.ruff.format] exclude = ["*.md"]`): it rewrote deliberate fragments in
historical plan documents, in one case changing an excerpt's meaning.

## Consequences

- A toolchain bump is now one pyproject edit plus `uv lock`; CI, pre-commit,
  hooks and docs follow automatically. The eight-site sweep cannot recur.
- Developers and CI cannot disagree about tool versions: there is one
  resolved copy.
- The Claude Code hook and CLAUDE.md now describe `uv run ty check` with no
  version literal; documentation goes stale one place fewer.
- The `exclude-newer-package` entries are standing exceptions and must be
  pruned when the packages age past the global cooldown — they are harmless
  left in place but accumulate as noise; whoever next touches `[tool.uv]`
  may delete any entry older than the cooldown window.
