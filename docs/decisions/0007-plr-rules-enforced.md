# 0007 — Enforce the Pylint refactor rules; ignores must be scoped and argued

**Status:** Accepted
**Date:** 2026-08-17
**Deciders:** Brian Ballsun-Stanton

## Context

`PLR0913` (too many arguments) and `PLR2004` (magic value comparison) were
globally ignored in the initial project-infrastructure commit and never
revisited. When ruff 0.16 stabilised `PLR0917` (too many positional
arguments), the path of least resistance was to add it to the same list.
The operator rejected that and asked what the existing ignores were hiding.

Measured 2026-08-17 (ruff 0.16.1): PLR2004 suppressed 816 sites — 694 in
tests, and of the 104 in src the bulk are Unicode codepoint boundaries in
`export/unicode_latex.py` and `word_count.py` where the hex literal is the
clearest form. PLR0913 suppressed 118 (85 src). PLR0917 would have
suppressed 55 (39 src).

## Decision

Remove all three from the global ignore list. Ruling: fix everything, with
these scoped exceptions, each carrying its rationale in
`pyproject.toml`:

- `tests/**`: PLR2004 and PLR0913 stay per-file-ignored. Expected-value
  literals in assertions are correct test style — naming them invites
  tautology tests — and factory/fixture functions legitimately take many
  optional arguments. PLR0917 is *not* ignored in tests; keyword-only
  factories are strictly better.
- `export/unicode_latex.py`, `word_count.py`: PLR2004 per-file-ignored;
  Unicode block boundaries stay as hex literals.
- Everything else is fixed, not suppressed: PLR0917 by keyword-only `*`
  markers; PLR0913 by decomposition or cohesive parameter objects; PLR2004
  residue by naming genuine thresholds. Line-level `# noqa: PLR2004` is
  permitted only where a literal is demonstrably clearer than any name.

## Consequences

- ~85 src signatures get restructured — a deliberate campaign accepted with
  eyes open, executed per-module alongside the ADR 0004 query migration and
  the cognitive-complexity reductions so each file is touched once.
- New code cannot silently accumulate fat positional signatures or magic
  thresholds; the gate reports them.
- The per-file-ignore list is the pattern for future rule adoption: a new
  rule is either fixed, or its ignore is scoped and argued in place —
  never added to the global list because a sibling rule was already there.
