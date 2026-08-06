# Root Cause Analysis: httptools Pipelining Context Leak

Date: 2026-04-08
Investigator: Gemini CLI
Status: Phase 3c — Claim Verification

## Narrative Analysis

We investigated the hypothesis that Uvicorn's `httptools` implementation leaks `ContextVar` state between HTTP requests when those requests are pipelined (sent back-to-back on a single keep-alive TCP connection without waiting for the response).

To test this natively, we bypassed standard HTTP clients (which don't easily pipeline) and wrote a raw TCP socket test (`tests/unit/test_httptools_pipelining_leak.py`) that sent two HTTP/1.1 requests in a single socket write.

The test proved that **when Uvicorn uses `httptools`, a pipelined request executes within the `Context` of the preceding request**. This means any `ContextVar` set by Request 1 is visible to Request 2 at the start of its ASGI cycle. When Uvicorn was configured to use `http="h11"`, the context isolation worked perfectly and no leak occurred.

This demonstrates a plausible parser-specific Uvicorn bug demonstrating a context boundary leak in test conditions. However, we could not make this leak cross NiceGUI's actual session boundary in our application. With NiceGUI's real `RequestTrackingMiddleware`, the request context was overwritten correctly before the page or background-task path read `app.storage.user`. This bug did not reproduce the "User A sees User B's session data" issue.

---

## Claim Verification (Toulmin Analysis)

### Claim 1: `httptools` leaks `ContextVar` state to pipelined requests
| Field | Content |
|-------|---------|
| **Claim** | Uvicorn running with `httptools` fails to isolate `ContextVar` state when processing pipelined HTTP requests on a keep-alive connection. |
| **Data** | Test execution in `tests/unit/test_httptools_pipelining_leak.py` (which explicitly forces `http="httptools"`). The custom `ContextSettingMiddleware` recorded the `ContextVar` value at the start of the `dispatch` method. For Request 2 (pipelined), the value was `/request1` (the value set by Request 1), instead of `None`. |
| **Warrant** | In `uvicorn/protocols/http/httptools_impl.py:335`, pipelined requests are started via `self.loop.create_task(cycle.run_asgi(app))`. This callback is executed from within `on_response_complete` of the *first* request. Because `create_task` inherits the current `Context`, the new task inherently starts with Request 1's mutated context rather than a clean one. (Unlike the initial request, which uses `contextvars.Context().run()` at line 295). |
| **Qualifier** | **Confirmed** (in isolation). The test failed natively with an assertion error printing the leaked context. |
| **Rebuttal** | If a different HTTP parser is used (e.g., `h11`), the leak does not occur. We verified this by running the same test with `http="h11"` and it passed. |
| **Result** | **Confirmed** (as an isolated parser bug). |

### Claim 2: The `httptools` leak causes NiceGUI session contamination (#438)
| Field | Content |
|-------|---------|
| **Claim** | The pipelined context leak translates directly into the cross-user data leak reported in #438. |
| **Data** | We could not reproduce the data leak across NiceGUI's actual session boundary. The incident (#438) strongly correlated with a server restart, and there is no production config evidence proving that HAProxy pipelines HTTP requests on the #438 production path. |
| **Warrant** | NiceGUI's `RequestTrackingMiddleware` unconditionally overwrites `request_contextvar` with the current request object early in the ASGI cycle. This overwrite protects `app.storage.user` lookups from the leaked context. Furthermore, this hypothesis fails to account for the restart correlation established in Phase 1. |
| **Qualifier** | **Falsified**. |
| **Rebuttal** | If there was a race condition that allowed `app.storage.user` to be read *before* `RequestTrackingMiddleware` could overwrite the context, the leak might manifest. However, we have found no evidence of such a path. |
| **Result** | **Falsified**. |

---

## Epistemic Boundary

- **High confidence:** Uvicorn 0.40.0 with `httptools` contains a real `ContextVar` leak for pipelined HTTP requests in isolation. We have a committed test (`tests/unit/test_httptools_pipelining_leak.py`) demonstrating this.
- **High confidence:** This `httptools` bug did not reproduce "User A sees User B's session data" because NiceGUI's `RequestTrackingMiddleware` correctly overwrites the context before it is read.
- **High confidence:** The `httptools` pipelining leak is **not** the root cause of #438.

## Next Steps

1. **Bug Report (Optional):** We can report the `httptools` context leak to the Uvicorn maintainers, as it is a real framework bug, even if it didn't cause our specific incident.
2. **Return to Phase 1:** What remains unresolved is the actual cause of #438. The current evidence still points more toward some restart/reconnect/session-persistence path than this parser bug, but it is not fully proven yet. We must return to Phase 1 and investigate how sessions persist and route during a restart.
