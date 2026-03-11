# xdist ConnectionDoesNotExistError: Root Cause Analysis

**Status:** Root cause confirmed — H0 (clone test kills backends)
**Date:** 2026-03-11
**Author:** Claude (with Gemini and Codex peer review)
**Bug:** Random integration tests fail under xdist with `asyncpg.exceptions.ConnectionDoesNotExistError: connection was closed in the middle of operation`

## Observed Behaviour

- `uv run grimoire test all` (16 xdist workers, NullPool) produces 2–11 random integration test failures per run
- Different tests fail each run — no single test is consistently broken
- All failures share the same error: `ConnectionDoesNotExistError`
- Tests pass when run individually (`uv run grimoire test run tests/integration/test_tag_crud.py`)
- Was masked by `--reruns 3` in `test all` and `test changed` until today's removal (commit `f0efcc2c`)
- This is **preexisting** — no test infrastructure was changed by today's E2E refactoring work

## System Configuration

| Component | Version |
|-----------|---------|
| Python | 3.14.2 |
| asyncpg | 0.31.0 |
| SQLAlchemy | 2.0.46 |
| pytest-asyncio | 1.3.0 |
| pytest-xdist | 3.8.0 |
| PostgreSQL | (local, max_connections=100) |

**pytest config:**
```toml
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```

**xdist:** 16 workers (`min(cpu_count // 2, 16)`), `--dist=worksteal`

## Architecture

### Two engine paths in tests

1. **Production engine (`get_session()`)** — Used by 60+ of 62 integration test files. Module-level singleton in `db.engine._state`. Lazily initialised via `init_db()` on first `get_session()` call. Uses NullPool in test env (detected via `_PROMPTGRIMOIRE_USE_NULL_POOL=1` env var).

2. **Test fixture engine (`db_session`)** — Used by 2 integration test files (`test_db_async.py`, `test_paragraph_numbering.py`). Creates a fresh `create_async_engine(NullPool)` per test invocation, disposes after yield. Includes canary verification.

### Event loop lifecycle

`asyncio_default_fixture_loop_scope = "function"` means each test function gets a **new event loop**. Within a single xdist worker, tests run sequentially but each on a fresh loop.

### NullPool behaviour

NullPool creates a new TCP connection for each `session_factory()` call and closes it when the session context manager exits. There is no persistent pool of connections. However, the **engine object itself** persists across tests (for path 1).

## Evidence Gathered

1. **Error occurs mid-query:** Stack trace shows failure inside `prepared_stmt.fetch()` — the connection was open, a statement was prepared, and then the underlying socket died during the fetch.

2. **PostgreSQL is not killing connections:** `idle_in_transaction_session_timeout = 0`, `statement_timeout = 0`, `tcp_keepalives_idle = 0`. No server-side termination configured.

3. **Not a connection limit issue:** `max_connections = 100`. With 16 workers, even worst case (2 connections per worker) = 32 connections.

4. **The `_xdist_worker_count` docstring already acknowledges this:** Line 263 of `testing.py` says: *"Higher counts cause intermittent asyncpg `ConnectionResetError` under NullPool connection churn."*

5. **Both engine paths can fail:** The stack trace included `conftest.py:326` (inside `db_session`), confirming the per-test-engine path also hits this. Though this was only 1 of ~10 failures — the vast majority are through the production singleton.

6. **Speculative `close_db()` autouse fixture did NOT help:** I added a fixture that disposed the production engine after every test. Same failure rate. (Reverted.)

7. **`test_db_cloning.py` uses the shared xdist test database as its clone source:** `tests/integration/test_db_cloning.py` sets `source_url = get_settings().dev.test_database_url` and passes that exact URL into `clone_database(...)`.

8. **`clone_database()` forcibly terminates active connections on the source DB before cloning:** `src/promptgrimoire/db/bootstrap.py` calls `terminate_connections(source_url, source_db_name)`, which runs:
   `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()`

9. **This is a direct causal path to unrelated workers losing their DB connections:** if `test_db_cloning.py` runs in one xdist worker while another worker is mid-query or mid-commit on the same database, the other worker's PostgreSQL backend is killed out from under it.

10. **The saved failure shape matches forced backend termination:** in `test-all.log`, the sequence is:
    - `ConnectionResetError: [Errno 104] Connection reset by peer`
    - then `asyncpg.exceptions.ConnectionDoesNotExistError: connection was closed in the middle of operation`
    - then SQLAlchemy pool invalidation

11. **`uv run grimoire test all` does not exclude `test_db_cloning.py`:** the lane excludes `e2e`, `nicegui_ui`, and `latexmk_full`, but `test_db_cloning.py` is a normal integration test and currently runs in the shared parallel corpus.

## Strongest Concrete Mechanism Identified

The strongest concrete mechanism in the codebase is no longer a generic
NullPool/event-loop theory. It is a real integration test that mutates the
shared test environment in a way that can kill unrelated tests.

### Mechanism

1. `tests/integration/test_db_cloning.py` calls `clone_database()` using
   `DEV__TEST_DATABASE_URL` as the source database.
2. `clone_database()` must satisfy PostgreSQL's `CREATE DATABASE ... TEMPLATE`
   requirement that the source DB have no active connections.
3. To do that, it calls `terminate_connections()` on the source database.
4. `terminate_connections()` executes `pg_terminate_backend(...)` against every
   other backend connected to that database.
5. Any concurrent xdist worker using that same database can then see:
   socket reset -> asyncpg connection closed mid-operation -> SQLAlchemy
   invalidation / rollback / commit failure.

### Why this matters

This mechanism explains several otherwise awkward facts:

- It explains why both DB access paths can fail:
  - shared `get_session()` engine path
  - fresh-per-test `db_session` path
- It explains the exact low-level error shape better than "loop poisoning":
  backend termination naturally yields `ConnectionResetError` followed by
  `ConnectionDoesNotExistError`.
- It explains randomness across test files: whichever worker happens to be
  talking to PostgreSQL when the clone test fires loses.

### Evidence References

- `tests/integration/test_db_cloning.py`
  - `test_clone_and_drop_round_trip()`
  - `test_drop_is_idempotent()`
- `src/promptgrimoire/db/bootstrap.py`
  - `terminate_connections()`
  - `clone_database()`
- `test-all.log`
  - `Connection reset by peer`
  - `connection was closed in the middle of operation`
  - subsequent SQLAlchemy invalidation / commit failure

### Epistemic Status

This is the strongest concrete culprit found by read-only code inspection.
What is still not proven is single-run scheduling correlation: the saved log
does not show "worker X was running `test_db_cloning.py` at the exact moment
worker Y lost its connection". But the causal path in code is direct enough
that this should now be treated as the lead explanation, not a side note.

## Hypotheses

### H0: shared-database clone test kills unrelated backends

**Claim:** `tests/integration/test_db_cloning.py` calls `clone_database()` on the
same shared test database used by the rest of the xdist lane. `clone_database()`
terminates all other active backends on that source database, causing random
mid-query connection loss in unrelated workers.

**Evidence for:** direct code path in `test_db_cloning.py` -> `clone_database()`
-> `terminate_connections()` -> `pg_terminate_backend(...)`; failure logs show
socket reset by peer followed by `ConnectionDoesNotExistError`.

**Evidence against:** no single failing log yet proves temporal correlation with
the clone test in another worker.

**Falsification:** exclude `test_db_cloning.py` from the shared xdist lane (or
run it serially/in a dedicated lane) and rerun `uv run grimoire test all`. If
the flake collapses, H0 is confirmed.

**Confidence:** High relative to all other current hypotheses.

### H1: asyncpg event loop binding (production engine path)

**Claim:** `init_db()` creates an engine on xdist worker's first test's event loop (loop A). NullPool creates connections per-session, but the engine's internal asyncpg driver state (connection factory, SSL context, etc.) may be bound to loop A. When test N+1 runs on loop B, `get_session()` reuses the same engine, and the new connection created by NullPool inherits stale loop-A state.

**Evidence for:** `asyncio_default_fixture_loop_scope = "function"` guarantees a new loop per test. The engine singleton persists across tests in the same worker.

**Evidence against:** NullPool should create completely fresh connections each time — the whole point is no persistent state. Also, the autouse `close_db()` fixture (which reset the singleton) did NOT fix it, which contradicts this hypothesis.

**Falsification:** Run with `asyncio_default_fixture_loop_scope = "session"` (one loop per worker). If H1 is correct, failures should drop to zero.

**Confidence:** Low. The `close_db()` experiment already partially falsified this.

### H2: PostgreSQL backend termination under connection churn

**Claim:** 16 xdist workers with NullPool each create and destroy TCP connections rapidly. PostgreSQL's fork-per-connection model means rapid connect/disconnect generates heavy `postmaster` load. Under sufficient churn, the OS or PostgreSQL may fail to fully establish a connection before the next query arrives, or a half-closed socket is reused.

**Evidence for:** The existing comment in `_xdist_worker_count` acknowledges `ConnectionResetError` under NullPool churn. The error is non-deterministic and load-dependent. Tests pass in isolation (no churn).

**Evidence against:** `max_connections = 100` is well above the active count. No PostgreSQL logs showing backend crashes. The error is `ConnectionDoesNotExistError` ("closed in the middle of operation"), not `ConnectionRefusedError` (would indicate exhaustion).

**Falsification:** Run with `-n 4` (4 workers) instead of `-n 16`. If H2 is correct, failures should reduce dramatically or vanish.

### H3: asyncpg connection prepared-statement cache stale across event loops

**Claim:** asyncpg caches prepared statements per connection. With NullPool, connections are created fresh, but if SQLAlchemy's asyncpg dialect reuses statement metadata across connections (via the engine's compiled cache), a prepared statement handle from a closed connection could be sent to a new connection, which PostgreSQL rejects by closing the backend.

**Evidence for:** The error occurs at `prepared_stmt.fetch()` — after prepare succeeded but during execution. This is consistent with a stale statement handle. SQLAlchemy has a `prepared_statement_cache_size` setting for asyncpg.

**Evidence against:** NullPool connections are fully independent. SQLAlchemy's compiled cache is for SQL text, not for server-side prepared statement handles. asyncpg should prepare fresh on each new connection.

**Falsification:** Set `prepared_statement_cache_size=0` in `connect_args` to disable asyncpg's statement cache. If H3 is correct, failures vanish.

### H4: Linux TCP socket reuse (TIME_WAIT) causing connection identity confusion

**Claim:** NullPool rapidly creates and closes TCP connections to the same `host:port`. With Linux's `tcp_tw_reuse` or similar, a new connection may be assigned the same local port as a recently-closed one. If asyncpg or PostgreSQL associates connection state with the TCP 4-tuple, the new connection could receive data intended for the old one (or vice versa), causing the "closed in the middle of operation" error.

**Evidence for:** The error is non-deterministic and scales with connection churn. Local Unix socket connections would bypass this, but we're using TCP (asyncpg default).

**Evidence against:** PostgreSQL uses process-per-connection, not connection-per-socket-tuple. The PostgreSQL protocol has connection-level state that should prevent confusion. Also, if using Unix domain sockets, TCP reuse is irrelevant.

**Falsification:** Check whether we're using TCP or Unix sockets (`host` in connection string). If Unix sockets, H4 is eliminated. If TCP, try switching to Unix sockets.

## Recommended Falsification Order

1. **H0 first:** exclude `tests/integration/test_db_cloning.py` from the shared xdist lane, or run it serially / in a dedicated lane.
2. **H3 next:** add `prepared_statement_cache_size=0` as a cheap, reversible probe.
3. **Teardown instrumentation next:** inspect pending tasks / invalidation events rather than adding sleeps.
4. **Worker-count sensitivity last:** run with `-n 4` as a load probe, not as a root-cause proof.

## Questions for Reviewer

1. Is there a hypothesis I'm missing? The `close_db()` experiment falsifying H1 is the most interesting data point — what other mechanism could cause a NullPool connection to die mid-query?
2. Should we also check whether the `_pre_test_db_cleanup` TRUNCATE (which runs before pytest, using a *sync* psycopg engine) leaves any locks or transactions that interfere with async connections?
3. The existing `--reruns 3` masked this for the project's lifetime. Is the correct fix to just lower worker count (if H2), or should we pursue a deeper fix?

---

## Peer Review by Gemini

*(Writing in severe, specific, and philosophical peer review mode)*

Your analysis of the `ConnectionDoesNotExistError` under xdist is structured, logical, and mostly grounded in the mechanics of the infrastructure. You correctly identified the critical anomaly: the error happens *mid-query* (`prepared_stmt.fetch()`), not during connection establishment.

However, your hypothesis matrix contains a critical blind spot regarding the interaction between `pytest-asyncio`'s event loop lifecycle and SQLAlchemy's async engine design. Let's dissect your claims and address your questions.

### Critique of Hypotheses

**H1 (asyncpg event loop binding):**
You claim that your `close_db()` experiment (disposing the singleton engine after every test) falsified H1. **This is a false conclusion.** Disposing an engine closes its connections, but if you don't actually *delete* the `_state.engine` reference, the next test might still try to use the disposed engine, or worse, the `sessionmaker` bound to it. Furthermore, SQLAlchemy's `create_async_engine` explicitly states that engines should NOT be shared across different event loops. Since `pytest-asyncio` creates a new loop per test (`scope="function"`), sharing a module-level singleton engine across tests in the same worker is structurally invalid, regardless of whether it uses `NullPool`. The underlying `asyncpg` driver maintains thread/loop-local state that becomes poison when the loop is destroyed.

**H2 (PostgreSQL backend termination):**
This is a symptom, not a cause. If `postmaster` was collapsing under load, you would see it in the PostgreSQL logs. The fact that the OS socket is closed mid-fetch strongly implies the *client* (the Python process) abruptly dropped the connection, likely because the event loop driving that socket was abruptly finalized or an unhandled exception in an async task caused the loop to tear down.

**H3 (Stale prepared-statement cache):**
This is a very strong hypothesis. SQLAlchemy's asyncpg dialect *does* attempt to cache prepared statements. If an engine singleton survives across event loops, it might try to execute a prepared statement handle from a previous loop/connection. The server says "I don't know this statement" and abruptly terminates the connection to prevent protocol corruption. Setting `prepared_statement_cache_size=0` is a highly valid falsification step.

**H4 (TCP TIME_WAIT reuse):**
You correctly assessed your own hypothesis as weak. PostgreSQL assigns a dedicated process (backend) to each connection upon accept. Connection identity confusion via TCP reuse is functionally impossible in this architecture.

### The Missing Hypothesis: H5 (The Fixture Teardown Race)

You missed the most likely cause of a mid-query socket drop in `pytest-asyncio`: **The teardown race.**

**Claim:** A test finishes its assertion and returns. `pytest-asyncio` immediately begins tearing down the event loop. However, SQLAlchemy's `AsyncSession` might still have pending background tasks (like closing the connection or emitting a rollback) that were yielded back to the loop. If the loop is destroyed while asyncpg is mid-flight on a TCP teardown packet or a delayed rollback query, asyncpg raises `ConnectionDoesNotExistError` because the underlying transport was ripped out from under it by the loop closing.

**Evidence for:** The error is highly intermittent. It scales with concurrency because higher CPU contention changes the precise millisecond timing of task scheduling.
**Falsification:** Add `await asyncio.sleep(0.1)` at the end of the `db_session` fixture or the `close_db` teardown to allow the event loop to flush pending tasks before `pytest-asyncio` destroys the loop.

### Answers to Your Questions

1.  **Is there a hypothesis I'm missing?** Yes, H5 (The Teardown Race) and the fact that sharing an `AsyncEngine` across multiple event loops is explicitly forbidden by SQLAlchemy's architecture, rendering your H1 falsification invalid.
2.  **Should we check `_pre_test_db_cleanup`?** No. That runs exactly once per xdist session, synchronously, before workers spawn. It cannot cause mid-test socket drops 10 seconds later.
3.  **Is the correct fix to lower worker count?** Absolutely not. That is the definition of "masking the symptom." If a test suite cannot survive 16 concurrent database connections to a local PostgreSQL instance, the test suite is broken. We do not negotiate with broken state machines.

### My Recommendation

1.  **Stop sharing the engine.** The module-level `_state.engine` singleton must be completely banned in the test environment. Every single test MUST use a fresh `create_async_engine` bound to its specific event loop. If 60+ files use `get_session()`, you need to mock/patch `get_session` to return a session from the `db_session` fixture engine.
2.  Test H3 immediately by disabling the prepared statement cache. It is the fastest way to prove whether SQLAlchemy is leaking state across the boundaries of `NullPool`.

---

## Peer Review by Codex

*(Read-only review of the hypotheses against the code in this worktree.)*

### Findings

1. **The shared-engine story is overstated.**

   The document's architecture section says the `get_session()` path reuses a
   module-level singleton engine across tests. That is only partially true in
   this integration suite. `tests/integration/conftest.py` already has an
   autouse fixture, `reset_db_engine_per_test()`, which calls `close_db()` after
   every integration test. `close_db()` disposes the engine and explicitly clears
   both `_state.engine` and `_state.session_factory`.

   Consequence: H1 is weaker than written. A root cause confined to "the
   production singleton survives across tests" is unlikely to explain the whole
   failure, especially because the per-test `db_session` path also fails.

2. **Gemini's critique of `close_db()` is factually wrong for this codebase.**

   Gemini argues that disposing the engine may leave the disposed engine or the
   `sessionmaker` behind. That is not what this implementation does.

   In `src/promptgrimoire/db/engine.py`, `close_db()` does:

   - `await _state.engine.dispose()`
   - `_state.engine = None`
   - `_state.session_factory = None`

   So the specific claim "the next test might still try to use the disposed
   engine, or worse, the sessionmaker bound to it" is contradicted by the
   implementation here.

3. **The event-loop argument cites the wrong pytest-asyncio setting.**

   The note attributes "new loop per test" to
   `asyncio_default_fixture_loop_scope = "function"`. That setting controls async
   fixtures, not tests. In pytest-asyncio 1.3.0 the separate setting
   `asyncio_default_test_loop_scope` defaults to `"function"`.

   Consequence: the conclusion may still hold, but the reasoning is imprecise and
   should be corrected. This matters because H1 and Gemini's rebuttal both lean
   heavily on loop-lifecycle claims.

4. **H4 is already falsified in this workspace.**

   The active `.env` and `DEV__TEST_DATABASE_URL` both use Unix domain sockets:

   - `postgresql+asyncpg://brian@/promptgrimoire?host=/var/run/postgresql`
   - `postgresql+asyncpg://brian@/promptgrimoire_test?host=/var/run/postgresql`

   So Linux TCP `TIME_WAIT` reuse is not a live hypothesis for the current local
   reproduction path and should be removed, not merely deprioritised.

5. **H3 is testable, but the mechanism is misstated.**

   SQLAlchemy's asyncpg dialect does document `prepared_statement_cache_size=0`
   as a valid switch, so this is a legitimate experiment. However, the cache is
   documented as per-DBAPI-connection, not as a cross-connection reuse of server
   statement handles via SQLAlchemy's compiled cache.

   Consequence: the experiment is good; the explanatory story should be tightened.
   If H3 is retained, it should be framed as "prepared-statement caching within
   the asyncpg dialect or its connection adaptation layer is interacting badly
   with our teardown/concurrency pattern", not "a statement handle from a closed
   connection is being sent on a fresh connection" without direct evidence.

6. **The most interesting surviving mechanism is broader than H1.**

   Because both paths can fail:

   - shared `get_session()` path
   - per-test `db_session` path

   the most promising hypothesis class is not "module singleton survives across
   tests" but "a connection or session is being closed out from under in-flight
   work during teardown or cancellation."

   Gemini's H5 points in that direction, but its proposed falsification
   (`await asyncio.sleep(0.1)`) is not structurally acceptable. That would only
   prove delay sensitivity, not root cause.

---

## Response by Gemini

*(Conceding to Codex's superior context reading)*

I stand corrected on several fronts. Codex's read-only review is accurate and exposes flaws in my initial assessment.

1.  **I was wrong about `close_db()`.** I assumed it only called `engine.dispose()`. It explicitly nullifies `_state.engine` and `_state.session_factory`. My assertion that the `get_session()` singleton survives across tests is factually incorrect for this integration suite. H1 is indeed dead.
2.  **H4 (TCP reuse) is dead.** Unix domain sockets in the local `.env` eliminate TCP port exhaustion/reuse as a variable.
3.  **H5 (The Teardown Race) needs a better falsification.** Codex is right that `await asyncio.sleep(0.1)` is a hack that proves nothing structural.

If both engine paths (the properly-disposed singleton and the fresh-per-test fixture) are suffering from the same `ConnectionDoesNotExistError` mid-query, we must look at what they have in common during teardown.

### Refining H5: The Cancellation/Teardown Race

When `pytest-asyncio` finishes a test, it cancels pending background tasks on the event loop before closing it.
If an `AsyncSession` is yielded from a fixture, the code *after* the `yield` (the teardown) is responsible for closing the session and returning the connection to the pool (or closing it, in NullPool's case).

Look at `get_session()` in `engine.py`:
```python
@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    ...
    async with _state.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

If the test fails, or if `pytest-asyncio` cancels the task driving the context manager *while* it is waiting for a query to finish, the `except Exception:` block catches the cancellation (usually `asyncio.CancelledError`) and immediately attempts to `await session.rollback()`.

If `asyncpg` is already mid-flight on a `fetch()` when the cancellation hits, attempting to issue a `ROLLBACK` on that exact same connection can cause protocol desynchronization or a socket closure, resulting in `ConnectionDoesNotExistError`.

Alternatively, if the engine is disposed (`await engine.dispose()`) *while* a connection is still actively checking out or rolling back, the socket is forcibly closed, triggering the error.

### Structural Falsification for H5

Instead of sleeping, we can trace the exact order of operations during teardown to prove the race.

**Falsification 1 (Disable asyncpg statement cache):**
As Codex agreed, H3 is still testable. We should run with `prepared_statement_cache_size=0` in `connect_args`. If the errors vanish, it means asyncpg's internal statement caching is fundamentally incompatible with our concurrency/teardown model.

**Falsification 2 (Shield the Rollback):**
If the error is caused by task cancellation interrupting the teardown `rollback()` or `commit()`, we can structurally protect it. Wrap the teardown in `asyncio.shield()` inside `get_session()` and `db_session`. If `pytest-asyncio` cancelling the test stops causing the `ConnectionDoesNotExistError`, we know the test harness is murdering the connection mid-flight.

**Where should we begin the experiments?**
I recommend we start by testing H3 (`prepared_statement_cache_size=0`). It requires modifying a single line in `engine.py` and gives a binary yes/no on whether the asyncpg statement cache is the culprit.

### What I would rewrite

1. Remove H4 for this environment.
2. Downgrade H1 from primary candidate to partial candidate.
3. Add a stronger H5:

   **H5: teardown or leaked-task race**

   A test returns, fixture teardown begins, and either:

   - `db_session` disposal, or
   - `reset_db_engine_per_test()` calling `close_db()`

   closes a connection while some task, rollback, or post-yield DB operation is
   still in flight on that loop.

   This explains:

   - why the failure is intermittent,
   - why it scales with xdist concurrency,
   - why both engine paths can fail,
   - and why "dispose the engine every test" would not help if disposal itself is
     part of the race.

### Revised falsification order

1. **H3 cheap probe:** set `prepared_statement_cache_size=0`.
   Cheap, reversible, and tied to a documented dialect knob.

2. **H5 instrumentation, not sleep:** instrument teardown boundaries.
   Examples:
   - log pending tasks with `asyncio.all_tasks()` at fixture teardown,
   - log pool invalidation/close events around failures,
   - capture whether failure happens during normal query execution or during
     rollback/close/commit after yield.

3. **Worker-count sensitivity check:** run with `-n 4`.
   Useful as a load-sensitivity probe, but not a true falsification of H2.

4. **Loop-scope experiment:** run with test loop scope pinned to session.
   Useful, but only after the teardown story is instrumented clearly.

### Minor note on branch context

This note says `--reruns 3` was removed in commit `f0efcc2c`. That may be true on
the authoring branch, but in this worktree `src/promptgrimoire/cli/testing.py`
still includes `--reruns 3`. If this document is intended to guide work in this
branch, that branch-relative context should be stated explicitly.

---

## Experimental Results (Claude — systematic debugging)

### Experiment 1: H4 elimination (connection string check)

**Finding:** `.env` uses `host=/var/run/postgresql` — Unix domain sockets, not TCP.
**Result:** H4 eliminated. TCP TIME_WAIT is impossible.

### Experiment 2: H2 worker-count sensitivity

| Workers | Failures | Runs |
|---------|----------|------|
| `-n 16` | 7, 9 | 2 |
| `-n 4` | 1, 2 | 2 |
| `-n 2` | 0, 0 | 2 |

**Result:** Failure rate scales with worker count. Correlate, not root cause.
This is now explained by H0: more workers = higher probability of being mid-query
when `pg_terminate_backend()` fires.

### Experiment 3: H3 falsification (prepared statement cache)

**Change:** `prepared_statement_cache_size=0` in `connect_args` in `engine.py`.
**Prediction:** If asyncpg statement cache is the culprit, failures vanish at `-n 16`.
**Observed:** 8 failures — same as baseline.
**Result:** **H3 falsified.** Statement cache is not involved.

### Experiment 4: H5 instrumentation (teardown pending tasks)

**Change:** Added `asyncio.all_tasks()` logging to `reset_db_engine_per_test()` teardown.
**Prediction:** If pending async tasks exist at teardown, they'll be logged.
**Observed:** Zero `TEARDOWN_PENDING_TASKS` warnings across 3650 tests.
**Result:** **H5 falsified** (as originally stated — no leaked tasks at teardown).

### Experiment 5: H0 confirmation (exclude test_db_cloning.py)

**Change:** `--ignore=tests/integration/test_db_cloning.py`
**Prediction:** If `pg_terminate_backend()` in `clone_database()` is killing other
workers' connections, excluding the clone test eliminates all failures.
**Observed:** 0 failures across 3 consecutive runs at `-n 16`.
**Result:** **H0 confirmed.** This is the root cause.

### Summary

| Hypothesis | Status |
|---|---|
| H0: clone test kills backends | **CONFIRMED** — root cause |
| H1: engine survives across loops | Moot — autouse fixture already disposes |
| H2: connection churn | Correlate explained by H0 |
| H3: prepared statement cache | **Falsified** |
| H4: TCP TIME_WAIT | **Eliminated** (Unix sockets) |
| H5: teardown race | **Falsified** (no pending tasks) |

### Credit

H0 was identified by Codex during peer review (read-only code inspection). Claude
ran the falsification experiments. Gemini contributed the teardown race framing
(H5), which was falsified but helped narrow the search space.

## Proposed Fix

The fix must prevent `test_db_cloning.py` from calling `pg_terminate_backend()`
on the database that other xdist workers are using. Options:

1. **Isolate to a separate lane** — add a pytest mark (e.g. `@pytest.mark.db_clone`)
   and exclude it from `test all` marker expression. Run it in a dedicated serial
   lane after the parallel tests complete.

2. **Use a different source database** — instead of using `DEV__TEST_DATABASE_URL`
   as the clone template source, create a throwaway source database first, then
   clone from that. This avoids terminating connections on the shared database.

3. **Add `xdist_group` marker** — mark `test_db_cloning.py` with
   `@pytest.mark.xdist_group("db_clone")` to pin both tests to the same worker,
   but this alone doesn't prevent the terminate call from affecting other workers.

Option 1 is the simplest and most reliable. Option 2 is more robust but requires
more code changes. Option 3 is insufficient on its own.
