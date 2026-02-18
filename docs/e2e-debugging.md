# E2E Test Suite Debugging: Server State Accumulation

## Problem Statement

E2E tests pass individually but fail when run as a full suite. The failure
point is non-deterministic — it varies between `test_instructor_workflow`
subtest 1, subtest 6, `test_law_student`, or `test_highlight_rendering`
across runs.

The NiceGUI server becomes unresponsive for 5-7 seconds during the test
run. A watchdog thread (daemon, pings the event loop via
`call_soon_threadsafe` every 2 seconds) confirms the event loop does not
respond within the 5-second timeout.

## Resolution Summary

Three root causes identified and fixed. Suite now passes 24 tests with 62
subtests, task count stable at 12-20 after cleanup, zero watchdog blocks.

| Root Cause | Impact | Fix |
|---|---|---|
| `loop.set_debug(True)` blocks event loop | 5-7s blocks from `linecache.checkcache()` | Removed debug mode |
| NiceGUI `page.py` leaks `Event.wait` tasks | Unbounded task growth (11→96+) | Cancel orphans in cleanup endpoint |
| NiceGUI `Outbox.stop()` doesn't wake loop | 1s delay per client deletion | Monkey-patch to set `_enqueue_event` |
| NiceGUI lifecycle: cleanup in `on_disconnect` | State accumulation on reconnects | Moved to `on_delete` |
| `init_db()` creating multiple engines | 15 connection pools | Re-entrance guard |

## Root Finding: Server State Accumulation

Expanded diagnostics (12 axes, reported per-test via
`/api/test/diagnostics`) show that NiceGUI `Client.instances` and
`asyncio.all_tasks()` grow monotonically across the test run and never
fully reclaim:

| Test (chronological) | clients | delete_tasks | asyncio_tasks |
|---|---|---|---|
| Early tests (no DB) | 0 | 0 | 11 |
| test_cards_are_draggable | 1 | 0 | 25 |
| test_drag_between_columns | 1 | 1 | 23 |
| test_full_flow_select | 1 | 0 | 34 |
| test_tab_headers | 2 | 1 | 44 |
| test_callback_token | 3 | 1 | 55 |
| test_sso_authentication | 3 | 1 | 61 |
| test_protected_page_auth | 7 | 4 | 79 |
| test_session_persists | 9 | 6 | 96 |
| test_highlights_paint | 3 | 0 | 82 |

All other axes (CRDT docs, dirty state, pending saves, presence entries,
workspace registry) stay clean or return to zero promptly.

### Interpretation

- **`Client.instances` never fully drains.** NiceGUI's `delete_content()`
  sleeps `reconnect_timeout` seconds before cleaning up, creating a race
  with the next test's connection. Stale client objects accumulate.
- **`asyncio_tasks` grows without bound.** Background tasks created by
  NiceGUI (outbox, binding, `delete_content` deferred cleanup) and our
  code (CRDT persistence debounce) are not cancelled when tests end.
- **`engine_is_none=True` for all early tests.** The database engine
  (`_state.engine`) appears as `None` to the diagnostics endpoint for
  tests that don't trigger auth. This is expected — `init_db()` is only
  called lazily on first DB operation. Once triggered, it stays.

## Investigation Timeline

### Phase 1: init_db() Resource Leak (Fixed)

`init_db()` in `engine.py` was called unconditionally from `auth.py:168`
(every auth callback) and `courses.py` (6 page handlers). Each call
created a new `create_async_engine()` with its own connection pool
(`pool_size=5, max_overflow=10`). Over a test run, 15 engines were
created.

**Fix:** Added re-entrance guard at `engine.py:142`:
```python
if _state.engine is not None:
    return
```
This reduced engines from 15 to 1 and partially improved reliability.

### Phase 2: Watchdog Thread

Added a daemon thread in `_E2E_SERVER_SCRIPT` (cli.py) that pings the
event loop every 2 seconds via `call_soon_threadsafe()`. Reports
responsiveness.

**Key finding:** Event loop blocks confirmed. Block duration is 5-7
seconds, happening between test boundaries (after client disconnect,
before next test's page load).

**Pitfall:** Getting `asyncio.get_running_loop()` from a non-main thread
fails in Python 3.14. Fixed by capturing the loop reference in an
`@app.on_startup` handler and passing via a global.

### Phase 3: Stack Dump Attempts (All Failed)

Five attempts to capture thread stacks during the event loop block:

1. `faulthandler.dump_traceback(file=io.StringIO())` — StringIO has no
   `fileno()`, faulthandler silently does nothing.
2. `faulthandler.dump_traceback(file=TemporaryFile("w+"))` — C-level
   write to fd, Python-level read-back gets nothing.
3. `sys._current_frames()` + `logging.warning()` — Logger buffer not
   flushed before process termination.
4. `sys._current_frames()` + `os.open()/os.write()` to `/tmp/` — File
   never created.
5. Canary test (`open("/tmp/wd-canary.txt", "w").write("reached")`) —
   Also not created.

**Root cause of all failures:** The watchdog thread is a daemon thread.
When the test suite completes and `_stop_e2e_server()` calls
`process.terminate()`, all daemon threads are killed immediately. The
"BLOCKED" log message reaches the file because it's already in the
logger's buffer, but the stack dump code runs after the log call and is
killed before completing.

### Phase 4: CLIENT_DELETE Timing (Falsified)

Hypothesis: `client.delete()` → `remove_all_elements()` is synchronous
and blocks the event loop.

Monkey-patched `Client.delete()` in the E2E server script to measure time
and element count. All deletions completed in 0.000-0.001s with at most
122 elements. **Falsified.**

### Phase 5: asyncio Debug Mode — THE FIRST ROOT CAUSE

Enabled `loop.set_debug(True)` with `slow_callback_duration = 0.5`.

**Root cause found:** asyncio debug mode causes **every** `create_task()`
call to invoke `traceback.extract_stack()`, which calls
`linecache.checkcache()`. This performs O(n) filesystem `stat()` calls per
stack frame per task. With many imported modules and frequent task
creation, this blocks the event loop for 5-7 seconds.

Evidence from watchdog stack dump:
```
MainThread blocked in:
  linecache.checkcache()
  ← traceback.extract_stack()
  ← asyncio.create_task()
```

**Fix:** Removed `loop.set_debug(True)` from E2E server startup.

**Pitfall:** Setting `PYTHONASYNCIODEBUG=1` as an env var caused the
server to block within seconds of startup. The `loop.set_debug(True)`
approach is marginally better but still causes the same fundamental
problem.

### Phase 6: Multi-Axis Diagnostics

Expanded `/api/test/diagnostics` endpoint to report 12 axes:

- `pool` — SQLAlchemy connection pool status
- `engine_is_none` — whether `_state.engine` is None
- `nicegui_clients` — `len(Client.instances)`
- `nicegui_delete_tasks` — sum of pending delete tasks across clients
- `crdt_docs` — persistence manager document registry size
- `crdt_dirty` / `crdt_pending_saves` — dirty workspace count
- `presence_workspaces` / `presence_total_clients` — presence dict sizes
- `ws_registry` — annotation document registry size
- `asyncio_tasks` — `len(asyncio.all_tasks())`

This revealed the accumulation pattern documented above.

### Phase 7: NiceGUI Lifecycle Violation (Fixed)

NiceGUI 3.0.0 changed the semantics of `on_disconnect`: it now fires on
**every** socket disconnect, including temporary reconnects during page
navigation and network blips. A new event `on_delete` was added for final
cleanup — it fires only after `reconnect_timeout` expires with no
reconnection. See `docs/nicegui/lifecycle.md` for full reference.

Our `_setup_client_sync()` in `broadcast.py` put all heavy cleanup in
`client.on_disconnect`:
- Presence removal from `_workspace_presence`
- `run_javascript()` calls to remaining clients (cursor/selection removal)
- `force_persist_workspace()` — CRDT database write
- CRDT document eviction from memory registries

This meant every temporary disconnect (including the browser navigating
away during test teardown) triggered full cleanup and re-setup, creating
accumulated state and background tasks that never fully drained.

**Fix:** Moved the entire cleanup handler from `client.on_disconnect` to
`client.on_delete`. The handler is now named `on_client_delete` and
registered via `client.on_delete(on_client_delete)`. This ensures heavy
cleanup only runs when the client is permanently removed.

**Reference:** `docs/nicegui/lifecycle.md` (cached from NiceGUI 3.6.0
documentation via Context7 MCP).

### Phase 8: PySnooper Instrumentation

Monkey-patched `Client.delete()` with PySnooper line-by-line tracing to
identify exactly where time was spent during cleanup.

**Finding:** `client.delete()` takes ~1ms. NOT the blocker. But the
PySnooper session's watchdog stack dump captured the smoking gun: the
`loop.set_debug(True)` / `linecache.checkcache()` chain (Phase 5 above).

### Phase 9: Fixture Restructuring

**Problem:** `pytest_runtest_teardown` hook runs BEFORE fixture teardowns.
So the cleanup endpoint was force-deleting NiceGUI clients whose
WebSockets were still open (browser contexts hadn't navigated away yet).

**Fix:** Restructured test cleanup:
1. All fixture teardowns now navigate to `about:blank` before closing
   browser contexts (clean WebSocket disconnect)
2. Converted `pytest_runtest_teardown` hook to `_e2e_post_test_cleanup`
   autouse fixture (reverse setup order = runs AFTER per-test fixtures)
3. Added 2s sleep between tests for NiceGUI cleanup chain
   (0.5s reconnect_timeout + 1.0s outbox wait timeout)

### Phase 10: Event.wait Task Leak — THE SECOND ROOT CAUSE

After all prior fixes, `Event.wait` tasks still accumulated
monotonically: 5 → 10 → 14 → 19 across 4 tests. NiceGUI clients cleaned
up (clients=0), but `asyncio.Event.wait()` tasks persisted in
`asyncio.all_tasks()`.

#### Root Cause: NiceGUI `page.py:174-176` Task Leak

For every async page handler, NiceGUI creates two competing tasks:

```python
# page.py:171-180
task = background_tasks.create(wait_for_result(), ...)
task_wait_for_connection = background_tasks.create(
    client._waiting_for_connection.wait(),  # <-- asyncio.Event.wait()
)
await asyncio.wait([task, task_wait_for_connection],
                   timeout=self.response_timeout,
                   return_when=asyncio.FIRST_COMPLETED)
if not task_wait_for_connection.done() and not task.done():
    task_wait_for_connection.cancel()
    task.cancel()
```

**The bug:** Line 181 only cancels both tasks when NEITHER has completed
(timeout case). When `task` (wait_for_result) completes first — which is
the normal case for pages that don't call `await client.connected()` —
`task_wait_for_connection` is **never cancelled**.

`client._waiting_for_connection` is only `.set()` inside `connected()`
when `has_socket_connection` is False. If the socket connected before
`connected()` was called, or if `connected()` was never called at all,
the event is never set. Furthermore, `handle_handshake()` at line 298
**clears** `_waiting_for_connection` (not sets it), so the task will never
complete through that path either.

Each page navigation creates one leaked `Event.wait` task in
`background_tasks.running_tasks` and `asyncio.all_tasks()`. Over a test
run with many page navigations, these accumulate to 40-100+ tasks and
slow the server.

**This is a NiceGUI bug** (version 3.6.0, `page.py:181-183`). The fix
would be to always cancel `task_wait_for_connection` after `asyncio.wait`
returns, not just on the timeout path.

#### Workaround

Our cleanup endpoint cancels orphan `Event.wait` tasks from
`background_tasks.running_tasks` after deleting stale clients:

```python
from nicegui import background_tasks as _bt
orphan_wait = 0
for t in list(_bt.running_tasks):
    if not t.done():
        coro = t.get_coro()
        qn = getattr(coro, '__qualname__', '') if coro else ''
        if qn == 'Event.wait':
            t.cancel()
            orphan_wait += 1
await asyncio.sleep(0)  # let cancellations propagate
```

This is safe because:
- The binding loop's `Event.wait` is inside `refresh_loop` (different
  qualname at the task level)
- The outbox loop's `Event.wait` is inside `Outbox.loop` (different
  qualname at the task level)
- The only standalone `Event.wait` tasks are from `page.py`'s leaked
  `task_wait_for_connection`

### Phase 11: Outbox Stop Monkey-Patch

`Outbox.stop()` only sets `_should_stop = True` but doesn't wake the
sleeping `asyncio.wait_for(Event.wait(), timeout=1.0)`. This means deleted
clients' outbox loops linger for up to 1 second after deletion.

**Fix:** Monkey-patch `Outbox.stop()` to also set `_enqueue_event`:

```python
from nicegui.outbox import Outbox as _Outbox
_orig_outbox_stop = _Outbox.stop
def _fast_outbox_stop(self):
    _orig_outbox_stop(self)
    if self._enqueue_event is not None:
        self._enqueue_event.set()
_Outbox.stop = _fast_outbox_stop
```

## NiceGUI Upstream Bugs

### Bug 1: `page.py` `task_wait_for_connection` leak

**Affected version:** NiceGUI 3.6.0 (and likely all versions since
`page.py` adopted `asyncio.wait` for the page rendering flow)

**File:** `nicegui/page.py`, lines 171-190 in the `decorated()` function

**Bug:** After `asyncio.wait([task, task_wait_for_connection], ...)` returns
with `FIRST_COMPLETED`, only the timeout path (lines 181-183) cancels both
tasks. When `task` completes first (normal case), `task_wait_for_connection`
is never cancelled and persists in `background_tasks.running_tasks` and
`asyncio.all_tasks()` forever.

**Impact:** Each async page request leaks one `asyncio.Event.wait()` task.
In long-running servers this is a slow memory/task leak. In E2E test
suites with many rapid page navigations, it accumulates to 40-100+ tasks
and degrades server performance.

**Suggested fix:** After line 190, add:
```python
if not task_wait_for_connection.done():
    task_wait_for_connection.cancel()
```

### Bug 2: `Outbox.stop()` doesn't wake sleeping loop

**File:** `nicegui/outbox.py`, `stop()` method

**Bug:** `stop()` sets `self._should_stop = True` but does not wake the
loop if it is sleeping in `asyncio.wait_for(self._enqueue_event.wait(),
timeout=1.0)`. This means the outbox loop can linger for up to 1 second
after `stop()` is called.

**Suggested fix:** Add `self._enqueue_event.set()` to `stop()`:
```python
def stop(self) -> None:
    self._should_stop = True
    if self._enqueue_event is not None:
        self._enqueue_event.set()
```

## Instrumentation Added

### Delete Handler Timing (broadcast.py)

Every `on_client_delete()` call now logs timing for each phase:
- `DELETE[client_id] ws=workspace_id start`
- `DELETE[client_id] total: <elapsed>s last=<bool>`

### py-spy Integration (cli.py)

`uv run test-e2e --py-spy` launches `py-spy record` against the server
process in the background, producing a speedscope JSON flamegraph in
`logs/py-spy-{timestamp}.json`.

**Prerequisite:** `sudo sysctl kernel.yama.ptrace_scope=0` (resets on
reboot). The `--py-spy` flag checks `/proc/sys/kernel/yama/ptrace_scope`
and exits with instructions if not set.

**Python 3.14 note:** py-spy 0.4.1 officially supports up to Python 3.13.
It may or may not work on 3.14 — untested as of this writing.

### PySnooper (Available)

`pysnooper` is installed as a dev dependency. Useful for line-by-line
execution tracing of specific functions. Apply `@pysnooper.snoop()` to
targeted functions when needed.

### Server Log

Server subprocess stdout/stderr now redirected to `test-e2e-server.log`
(was piped to subprocess.PIPE, invisible during test runs). Contains
watchdog output, client delete timing, and cleanup endpoint logs.

## Hypotheses (Status)

| # | Hypothesis | Status | Evidence |
|---|---|---|---|
| H1 | Event loop blocks due to synchronous code | Superseded by H5 | Watchdog detects 5-7s blocks. |
| H2 | Tests don't clean up server state | **Confirmed** | Client.instances and asyncio_tasks accumulate monotonically. |
| H3 | `reconnect_timeout` race with next test | **Confirmed** (subsumed by H5) | `delete_tasks` > 0 between tests. |
| H4 | Unrelated to event loop — timing/resource issue | Possible | Non-deterministic failure point suggests timing sensitivity. |
| H5 | NiceGUI lifecycle violation: heavy cleanup in `on_disconnect` instead of `on_delete` | **Root cause — fixed** | NiceGUI 3.0+ fires `on_disconnect` on reconnects. |
| H6 | `loop.set_debug(True)` blocks via `linecache.checkcache()` | **Root cause — fixed** | Watchdog stack dump showed MainThread in `linecache.checkcache`. |
| H7 | NiceGUI `page.py` leaks `Event.wait` tasks per page request | **Root cause — workaround** | Upstream bug, cancelled in cleanup endpoint. |
| H8 | `Outbox.stop()` doesn't wake sleeping loop | **Confirmed — workaround** | Upstream bug, monkey-patched. |

## Key Files

| File | Role |
|---|---|
| `src/promptgrimoire/cli.py` | E2E server script, watchdog, diagnostics endpoint, cleanup endpoint, py-spy integration |
| `src/promptgrimoire/db/engine.py` | init_db() guard, pool instrumentation |
| `src/promptgrimoire/pages/annotation/broadcast.py` | Disconnect handler with timing instrumentation |
| `src/promptgrimoire/crdt/persistence.py` | CRDT persistence manager (force_persist, evict) |
| `tests/e2e/conftest.py` | Per-test diagnostics, cleanup fixture, fixture teardown with about:blank navigation |
