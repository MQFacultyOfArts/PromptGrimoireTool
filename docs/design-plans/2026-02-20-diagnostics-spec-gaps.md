# Diagnostics Endpoint: Gaps Identified from E2E Investigation

**Date:** 2026-02-20
**Context:** NiceGUI discussion #5660 proposed a `/_nicegui/diagnostics` endpoint.
This document identifies capabilities missing from that spec, derived from the
11-phase E2E debugging investigation documented in `docs/e2e-debugging.md`.

**Status:** Notes for future spec revision. Not yet posted upstream.

## Background: What the Investigation Needed vs What the Spec Provides

The E2E investigation (`docs/e2e-debugging.md`) found three root causes:

1. `loop.set_debug(True)` blocks the event loop via `linecache.checkcache()` (Phase 5)
2. NiceGUI `page.py` leaks `Event.wait` tasks on every async page request (Phase 10)
3. `Outbox.stop()` doesn't wake the sleeping loop (Phase 11)

The current spec covers asyncio task inventory grouped by qualname (which found #2)
and client/element counts. The event loop blocking watcher was added separately
(already in `cli.py`'s `_watchdog_loop`). Three capabilities are still missing.

## Gap 1: On-Demand Thread Stack Dump

### What happened without it

Phase 3 of the investigation was **five consecutive failed attempts** at capturing
thread stacks during event loop blocks:

| Attempt | Method | Why It Failed |
|---------|--------|---------------|
| 1 | `faulthandler.dump_traceback(StringIO())` | `StringIO` has no `fileno()`, faulthandler silently does nothing |
| 2 | `faulthandler.dump_traceback(TemporaryFile("w+"))` | C-level write to fd, Python-level read-back gets empty bytes |
| 3 | `sys._current_frames()` + `logging.warning()` | Logger buffer not flushed before daemon thread killed by `process.terminate()` |
| 4 | `sys._current_frames()` + `os.open()/os.write()` to `/tmp/` | File never created — daemon killed before syscall completes |
| 5 | Canary test (`open("/tmp/wd-canary.txt", "w").write("reached")`) | Also never created |

**Root cause of all failures:** The watchdog is a daemon thread. When the test
suite completes and calls `process.terminate()`, all daemon threads are killed
immediately. Log messages reach the buffer (they were queued before the kill),
but code that runs *after* the log call never executes.

### What it would look like

An HTTP endpoint triggered by the test process (which is alive) rather than a
daemon thread (which gets killed). Two stack sources:

#### Thread stacks (`sys._current_frames()`)

```python
@app.get("/_nicegui/diagnostics/stacks")
async def _stacks():
    import sys
    import traceback
    import threading

    thread_map = {t.ident: t.name for t in threading.enumerate()}
    frames = sys._current_frames()

    threads = {}
    for tid, frame in frames.items():
        name = thread_map.get(tid, f"unknown-{tid}")
        stack = traceback.format_stack(frame)
        threads[name] = {
            "tid": tid,
            "stack": [line.strip() for line in stack],
        }

    return {"threads": threads}
```

**Critical subtlety:** This endpoint is an async handler running on the event
loop. If the event loop is blocked, the request itself will hang — you can't
dump the stack of a blocked event loop from within that event loop.

Two solutions:

**Option A: Separate thread-based HTTP server.** Run a minimal HTTP server
(e.g., `http.server.HTTPServer`) on a background thread listening on a
different port. This is the approach the watchdog thread already uses
(it runs independently of the event loop). The diagnostics server would
accept stack dump requests even when the main event loop is frozen.

```python
import http.server
import json
import sys
import threading
import traceback

class _DiagHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/stacks":
            thread_map = {t.ident: t.name for t in threading.enumerate()}
            result = {}
            for tid, frame in sys._current_frames().items():
                name = thread_map.get(tid, f"unknown-{tid}")
                result[name] = [
                    f"{entry.filename}:{entry.lineno} in {entry.name}: {entry.line}"
                    for entry in traceback.extract_stack(frame)
                ]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress request logging

def _start_diag_server(port: int = 9091):
    server = http.server.HTTPServer(("127.0.0.1", port), _DiagHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server
```

This is ugly but solves the fundamental problem: you can dump the main
thread's stack even when the event loop is completely frozen. The test
process hits `http://localhost:9091/stacks` and gets the frames.

**Option B: Watchdog-triggered dump with shared state.** The existing
watchdog thread detects the block and writes stacks to a shared data
structure. The main diagnostics endpoint (when it eventually responds)
includes the most recent block's stacks. This is less useful for live
debugging but captures historical blocks.

```python
_last_block_stacks: dict | None = None
_last_block_time: float | None = None

def _watchdog_loop():
    global _last_block_stacks, _last_block_time
    # ... existing watchdog code ...
    if not responded:
        frames = sys._current_frames()
        _last_block_stacks = {
            thread_map.get(tid, f"unknown-{tid}"): traceback.format_stack(frame)
            for tid, frame in frames.items()
        }
        _last_block_time = time.monotonic()
```

Then the diagnostics endpoint includes:
```json
{
  "last_block": {
    "age_s": 12.4,
    "duration_s": 5.7,
    "main_thread_stack": [
      "linecache.py:171 in checkcache: ...",
      "traceback.py:211 in extract_stack: ...",
      "asyncio/tasks.py:452 in create_task: ..."
    ]
  }
}
```

**Option A is strictly more useful** — it answers "what is blocking RIGHT NOW?"
rather than "what blocked last time?" But Option B is simpler and doesn't
require a second HTTP server.

#### Asyncio coroutine stacks (`task.get_stack()`)

For async tasks, `task.get_stack()` returns the coroutine's current stack
frames. This is available from within the event loop (no blocking issue):

```python
async def _async_stacks():
    stacks = {}
    for task in asyncio.all_tasks():
        coro = task.get_coro()
        qn = getattr(coro, '__qualname__', str(coro)) if coro else task.get_name()
        frames = task.get_stack(limit=5)
        stacks[qn] = [
            f"{f.f_code.co_filename}:{f.f_lineno} in {f.f_code.co_name}"
            for f in frames
        ]
    return stacks
```

### Impact estimate

If this had existed at Phase 0, root cause #1 (`linecache.checkcache()`) would
have been found immediately when the watchdog detected the first block. Instead
it took until Phase 5 (after the PySnooper monkey-patch in Phase 8 happened to
capture it). Phases 3 and 8 would have been unnecessary — roughly 40% of the
investigation effort eliminated.


## Gap 2: Task Age (Creation Time)

### What happened without it

Phase 10 found 19 `Event.wait` tasks accumulated across the test run. The
qualname grouping showed *what* they were, but not *how long they'd been alive*.
Normal `Event.wait` tasks (e.g., inside `Outbox.loop`) resolve in milliseconds.
Leaked ones from `page.py` live forever.

Without age, distinguishing normal from leaked requires reading NiceGUI source
to understand which code paths create `Event.wait` tasks and whether they're
expected to persist. With age, the leak is self-evident.

### What it would look like

Monkey-patch `asyncio.create_task` (or `background_tasks.create`) to record
creation time:

```python
import time as _time

_task_birth: dict[int, float] = {}  # task id -> monotonic creation time

_orig_create_task = asyncio.get_event_loop().create_task

def _tracking_create_task(coro, **kwargs):
    task = _orig_create_task(coro, **kwargs)
    _task_birth[id(task)] = _time.monotonic()
    task.add_done_callback(lambda t: _task_birth.pop(id(t), None))
    return task
```

Or more conservatively, compute age at query time without patching:

```python
def _task_summary_with_age(tasks):
    from collections import defaultdict
    now = _time.monotonic()
    groups = defaultdict(lambda: {"count": 0, "oldest_age_s": 0.0})
    for t in tasks:
        coro = t.get_coro()
        qn = getattr(coro, '__qualname__', str(coro)) if coro else t.get_name()
        parts = qn.rsplit('.', 2)
        name = '.'.join(parts[-2:]) if len(parts) >= 2 else qn
        birth = _task_birth.get(id(t))
        age = (now - birth) if birth else None
        g = groups[name]
        g["count"] += 1
        if age is not None and age > g["oldest_age_s"]:
            g["oldest_age_s"] = round(age, 1)
    return dict(groups)
```

Output:

```json
{
  "asyncio_task_summary": {
    "Event.wait": {"count": 19, "oldest_age_s": 142.3},
    "Outbox.loop": {"count": 3, "oldest_age_s": 0.8},
    "refresh_loop": {"count": 3, "oldest_age_s": 0.9}
  }
}
```

`Event.wait` with `oldest_age_s: 142.3` is unmistakably a leak. No source
reading required.

### Consideration: `background_tasks.create` vs `asyncio.create_task`

NiceGUI's `background_tasks.create()` wraps `asyncio.create_task()` and adds
the task to `background_tasks.running_tasks`. The page.py leak goes through
this path. Patching at the `background_tasks` level is more targeted and less
likely to break anything than patching `asyncio.create_task` globally. The
`running_tasks` set already provides the task references; adding a parallel
dict for birth times is minimal overhead.


## Gap 3: Client Lifecycle Event Counters

### What happened without it

Phase 7 discovered that `on_disconnect` fires on **every** socket disconnect,
including temporary reconnects during page navigation. Our cleanup code was in
`on_disconnect`, running heavy operations (CRDT persistence, presence removal,
JS broadcasts to remaining clients) on every reconnect — not just final
departure.

The fix was to move cleanup to `on_delete` (fires only after
`reconnect_timeout` expires with no reconnection). But finding this required
reading NiceGUI lifecycle documentation (cached in `docs/nicegui/lifecycle.md`)
to understand the semantic difference.

### What it would look like

```json
{
  "client_lifecycle": {
    "connects_total": 52,
    "disconnects_total": 47,
    "reconnects_total": 35,
    "deletes_total": 12,
    "active_reconnect_windows": 3
  }
}
```

`disconnects: 47` vs `deletes: 12` immediately reveals that disconnect-based
cleanup fires ~4x more often than delete-based cleanup. The 35 reconnects
explain the gap. `active_reconnect_windows: 3` shows how many clients are
currently in the "disconnected but might reconnect" limbo state.

This requires incrementing counters in NiceGUI's `Client` class:

```python
# In Client.__init__ or a module-level counter
_lifecycle_counters = {
    "connects": 0,
    "disconnects": 0,
    "reconnects": 0,
    "deletes": 0,
}

# In handle_handshake():
_lifecycle_counters["connects"] += 1
if was_disconnected:
    _lifecycle_counters["reconnects"] += 1

# In handle_disconnect():
_lifecycle_counters["disconnects"] += 1

# In delete():
_lifecycle_counters["deletes"] += 1
```

Low overhead (atomic integer increments), high diagnostic value.


## Gap 4: Delta Mode

### What happened without it

The accumulation pattern was the key signal in Phase 6. The investigation had
to manually hit `/api/test/diagnostics` after each test and build a comparison
table by hand:

| Test | clients | delete_tasks | asyncio_tasks |
|------|---------|-------------|---------------|
| Early | 0 | 0 | 11 |
| test_cards | 1 | 0 | 25 |
| test_drag | 1 | 1 | 23 |
| ... | ... | ... | ... |
| test_session | 9 | 6 | 96 |

Monotonic growth was the pattern, but seeing it required comparing rows.

### What it would look like

`GET /_nicegui/diagnostics?delta=true`

The endpoint remembers the previous response and returns both current values
and deltas:

```json
{
  "asyncio_tasks": 55,
  "asyncio_tasks_delta": "+11",
  "nicegui_clients": 5,
  "nicegui_clients_delta": "+2",
  "since_last_query_s": 4.2
}
```

Implementation: store a module-level dict of the previous snapshot's values.
On each request with `?delta=true`, compute `current - previous` for each
numeric field. Negligible overhead.

Accumulation becomes visible at a glance: every delta positive, nothing
returning to zero.


## Gap 5: Socket.IO / Engine.IO Session Counts

### What happened without it

The cleanup endpoint (`cli.py:517-523`) had to iterate `core.sio.eio.sockets`
to disconnect orphan engine.io sessions — WebSocket receive tasks from
connections whose NiceGUI client was already deleted through the normal
disconnect → delete_content → delete path.

The current spec counts NiceGUI clients but not the lower-level socket
sessions. A discrepancy between the two flags orphan sockets.

### What it would look like

```json
{
  "nicegui_clients": 3,
  "engineio_sessions": 7,
  "orphan_sessions": 4
}
```

`orphan_sessions = engineio_sessions - nicegui_clients` (simplified; the
actual relationship is more complex because one client can have multiple
socket reconnections).


## Priority Ranking (by investigation time saved)

1. **Thread stack dump** — eliminates Phases 3 + 8, finds root cause #1 immediately
2. **Task age** — makes leaks self-evident without source reading
3. **Client lifecycle counters** — reveals on_disconnect/on_delete semantic confusion
4. **Delta mode** — makes accumulation visible without manual comparison
5. **Socket.IO session counts** — catches orphan sockets


## Relationship to Existing Instrumentation

The PromptGrimoireTool repo already has:

| Capability | Location | Status |
|-----------|----------|--------|
| Event loop watchdog | `cli.py:315-414` | Built during investigation, operational |
| 12-axis diagnostics | `cli.py:425-470` | Built during investigation, operational |
| Cleanup endpoint | `cli.py:492-554` | Built during investigation, operational |
| Task qualname grouping | `cli.py:472-487` | Built during investigation, operational |
| Client delete timing | `broadcast.py` | Built during investigation, operational |
| py-spy integration | `cli.py` (`--py-spy` flag) | Available but untested on Python 3.14 |

The gaps identified above would extend both the upstream NiceGUI spec and our
local instrumentation. The event loop watchdog is already addressed locally
(and mentioned in the #5660 discussion as implemented). The remaining gaps
are candidates for either upstream contribution or local additions.
