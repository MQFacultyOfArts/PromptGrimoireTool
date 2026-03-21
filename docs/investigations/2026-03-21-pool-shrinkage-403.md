# Causal Analysis: Connection Pool Shrinkage Under CancelledError (#403)

Date: 2026-03-21
Investigator: Claude (Opus 4.6)
Status: Core claim falsified. Pool self-heals. response_timeout increased to 30s.

## Summary

The #403 hypothesis — that `CancelledError` from NiceGUI's `response_timeout` permanently shrinks the SQLAlchemy QueuePool — is **not supported by evidence**. The pool self-heals after cancellation-induced invalidations and maintains full capacity.

Two distinct cancellation scenarios were tested:

1. **Idle connection** (CancelledError during `asyncio.sleep`): No invalidation. Connection returned normally. No capacity effect.
2. **Active query** (CancelledError during `pg_sleep`): Connection invalidated (INVALIDATE event fires with `CancelledError`). Connection recreated on next checkout. **No capacity loss.**

In both cases, after repeated cancellations, the pool can still serve its full `pool_size` simultaneous connections.

## Dead Ends — Do NOT Repeat

### 1. QueuePool.overflow() is NOT a capacity proxy

`QueuePool._overflow` starts at `0 - pool_size` and increments when connections are *created* (`impl.py:173`). It does NOT decrement on normal return (`impl.py:142`). A shift from -5 to -4 is the first connection being created — **normal warm-up**, not shrinkage.

**The mistake:** Measuring overflow before and after cancellation without a non-cancelled control. The control produces the identical shift. Any investigation that uses `overflow()` as evidence of capacity loss without comparing against normal usage is repeating this error.

**The discriminating test:** "Can the pool serve N simultaneous connections after the event?" — not "did a counter move?"

### 2. Explicit `except BaseException` does not change overflow accounting

Adding `except BaseException: await session.rollback(); await session.close()` inside the session context manager returns the connection (checked_in=1, checked_out=0) but the overflow counter still shifts identically. This is because the overflow shift is from connection *creation*, not from failure to return. Don't pursue application-level BaseException handling as a fix for overflow counter movement.

### 3. Production overflow=-29 is normal warm-up, not degradation

With pool_size=80, overflow=-29 means 51 connections exist (80 + (-29) = 51, matching checked_in=49 + checked_out=2 from the #403 issue). This is the pool's steady-state under ~50 concurrent students — peak demand created 51 connections. It is NOT evidence of 29 "permanently lost" slots.

### 4. "Concurrent cancellations amplify the leak" — not demonstrated

The original test compared 10 sequential cancellations against 5 concurrent ones — different workload sizes. Even with matched sizes, both cases show full capacity preservation. There is no amplification effect to investigate.

### 5. SQLAlchemy issues #6652, #8145 — cited but not applicable here

These issues describe asyncpg connections not being returned to the pool on task cancellation. Our tests show connections ARE returned (or invalidated and recreated). The `asyncio.shield` in `AsyncSession.__aexit__` (added in response to those issues) appears to work correctly in our scenario. Don't cite these as evidence of a current problem without reproducing the specific failure they describe.

## Falsified Claims

| Claim from #403 | Status | Evidence |
|-----------------|--------|----------|
| "Pool permanently shrinks by one slot per timeout event" | **Falsified** | Capacity tests show full pool_size available after 10 cancellations |
| "overflow counter goes negative and never recovers" | **Falsified** | Overflow movement is normal warm-up accounting; control test produces identical shift |
| "29 pool slots permanently lost" | **Not supported** | overflow=-29 with pool_size=80 means 51 connections exist — consistent with normal warm-up under 50-student load |
| "only a process restart resets it" | **Not supported** | Pool self-heals via connection recreation on checkout |

## What IS Real

| Finding | Grade | Evidence |
|---------|-------|----------|
| `except Exception` at `engine.py:320` does not catch `CancelledError` | Confirmed | Language spec: `CancelledError` is `BaseException` |
| NiceGUI cancels **page load handler** AND deletes client at `response_timeout` | Confirmed | `nicegui/page.py:184-186`. Note: this is the page load handler only. Button click handlers are dispatched as independent `background_tasks.create()` tasks (`nicegui/events.py:463`) and are NOT subject to `response_timeout`. |
| `page_route` used NiceGUI default 3.0s `response_timeout` | Confirmed (now fixed) | `registry.py:175`: no `response_timeout` kwarg. Fixed to 30s in commit `28eefd31`. |
| Active-query cancellation triggers connection INVALIDATE | Confirmed | Test: 5 cancellations during `pg_sleep` → INVALIDATE events with `CancelledError` |
| Pool capacity is preserved after invalidations | Confirmed | Test: 5 simultaneous checkouts succeed after 5 active-query cancellations |
| `AsyncSession.__aexit__` shields `self.close()` | Code-verified | `session.py:1069-1071` (SQLAlchemy 2.0.46) |
| PDF export runs as click handler, not page handler | Code-verified | `nicegui/events.py:463` dispatches via `background_tasks.create()`. **Inference** that exports are therefore not cancelled by `response_timeout` — not yet proven by production log correlation. |
| Per-user export lock prevents same-user stacking | Code-verified | `pdf_export.py:51-58`, module-level dict keyed by `user_id`. Not proven by a discriminating concurrency test. |
| Pandoc/latexmk use `asyncio.create_subprocess_exec` | Code-verified | `pdf.py:141`, `pdf_export.py:202`. Rules out direct event loop blocking from sync subprocess calls. Does NOT rule out CPU saturation, I/O contention, or reconnect storms from invalidated connections. |

## The Real Problem

The 3.0s `response_timeout` is too low for the annotation page, which performs 10 sequential DB sessions per load (#377 Finding 3). Under production load, this causes:

1. **Broken pages** — NiceGUI deletes the client, the user sees a blank or broken page
2. **Wasted work** — all DB queries and CRDT operations are thrown away
3. **Connection churn** — active-query cancellations invalidate connections (though the pool self-heals, the churn is unnecessary overhead)

None of these cause permanent pool degradation, but they all degrade user experience.

## Changes Made

1. **`response_timeout` increased to 30s** in `page_route` at `registry.py:176`. All routes using `page_route` now have 30s instead of NiceGUI's 3.0s default.

## Remaining Questions

The 2026-03-21 export cascade (postmortem: `docs/postmortems/2026-03-21-export-failure-pii-leak.md`) saw 1,428 page load timeouts across 68 users in 15 minutes. The pool shrinkage hypothesis is falsified. The 3.0s `response_timeout` on page loads is now 30s, which eliminates this specific cascade mechanism. But the **root cause of why page loads exceeded 3s during the export window** is not fully explained. Hypotheses not yet tested:

- **CPU saturation** from concurrent latexmk + pandoc processes on 4 vCPU (unverified — no CPU telemetry from incident)
- **Connection reconnect storms** from INVALIDATE events causing bursts of new TCP/TLS/auth handshakes (pool self-heals, but the reconnect overhead under 68-user load is unmeasured)
- **Event loop contention** from synchronous CPU-bound work in the export pipeline (`preprocess_for_export`, `compute_highlight_spans` — sync, on the event loop, but likely single-digit seconds)

Ruled out:
- ~~Sync subprocess blocking~~ — pandoc and latexmk use `asyncio.create_subprocess_exec` (code-verified)
- ~~Export holding DB connections during compile~~ — `_run_pdf_export` acquires and releases sessions before the 85s compile phase (code-verified)
- ~~Pool capacity loss~~ — falsified

This is #402's territory (decouple export from NiceGUI client lifecycle), not #403.

## Regression Tests

Refactored 2026-03-22 from 5 investigation tests to 2 keepers:

| File | Test | What it guards |
|------|------|---------------|
| `tests/unit/test_pool_overflow_accounting.py` | `test_overflow_shifts_on_normal_checkout_and_stays` | `overflow()` is a creation counter — shifts on checkout, does not shift on checkin. No Postgres required. |
| `tests/integration/test_pool_cancellation.py` | `test_active_query_cancellation_self_heals` | Active-query cancellation triggers INVALIDATE but pool still serves full `pool_size`. Guards against future SQLAlchemy/asyncpg regressions. |

## Review Log

### External Review (2026-03-21)

Reviewer ran a control test showing normal session use produces the same overflow shift as cancellation. Falsified the core claim. All findings accepted; document revised.

### Key Lesson

`QueuePool.overflow()` is a connection-creation counter, not a capacity indicator. Measuring it without a control led to interpreting normal warm-up as pathological shrinkage. The discriminating test is: "can the pool serve N simultaneous connections after the event?" — not "did a counter move?"
