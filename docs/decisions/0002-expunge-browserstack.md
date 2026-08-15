# 0002 — Expunge BrowserStack rather than keep it quarantined

**Status:** Accepted
**Date:** 2026-08-06
**Deciders:** Brian Ballsun-Stanton

## Context

BrowserStack was quarantined on 2026-04-30 over a vendor concern: the
`browserstack-sdk` dependency, the `BrowserstackConfig` sub-model and the CI job
were removed, but `_browserstack.py`, the `browserstack/*.yml` profiles, the CLI
handler and the tests were deliberately retained "for revival".

Three months on, nothing had revived. The retained surface was still costing
something: a CLI command that exists only to exit non-zero, a permanently skipped
test module holding a slot on the `page.evaluate()` compliance allowlist, cached
vendor documentation in `docs/`, and — locally — live `BROWSERSTACK__*`
credentials in `.env` that failed the env-sync guard test on every run.

## Decision

Expunge it. Remove `_browserstack.py`, the `browserstack` CLI command, the four
`browserstack/*.yml` profiles, `test_browserstack_diag.py`,
`test_browserstack_cli.py`, the cached vendor docs, the `.env.example` block and
the compliance-allowlist entry.

## Consequences

Cross-browser E2E remains available through Playwright's own browsers —
`grimoire e2e firefox`, `e2e all-browsers`, `e2e run --browser <name>` — which is
what the project has actually used since April.

Recovery is `git` at `3c87e87f`, which is a cheaper thing to maintain than dead
code that looks live. The dependency rationale entry is updated to record the
expunge and that commit.

Live BrowserStack credentials were removed from the local `.env`; they should be
revoked at the vendor as well, since removal from a file is not revocation.
