# Value-Capture Hardening for NiceGUI Input+Button Race

**GitHub Issue:** None (internal reliability finding from E2E test investigation)

## Summary

An intermittent E2E test failure revealed that an async button-click handler sometimes reads `inp.value` as empty despite the client having sent the correct value. Client-side tracing confirmed the value update is emitted correctly; server-side diagnostics confirmed the handler reads empty. Any timing perturbation (even a `logger.warning`) eliminates the flake.

**Probable mechanism (not directly observed):** python-socketio defaults `async_handlers=True`, dispatching each incoming socket.io event as a separate asyncio task via `ensure_future`. NiceGUI's `AsyncServer` construction does not override this default. Two events from the same client — a value update and a button click — may therefore be processed concurrently, with no guarantee the value-update task completes before the click handler reads `inp.value`.

**Epistemic status:** The concurrent-dispatch mechanism is structurally present in the code (confirmed by inspection of `async_server.py:604-608` and `base_server.py:17`). It is consistent with all observations. However, we have not directly observed out-of-order task execution for this specific failure — the observer effect (any instrumentation eliminates the flake) makes direct observation impractical. An alternative explanation we haven't considered may exist.

**The fix is sound regardless of exact root cause.** Capturing the input's DOM value client-side at event time and passing it with the click event eliminates any server-side race between value-update and click processing, whether the race is caused by `async_handlers`, asyncio task scheduling, or something else entirely.

This design hardens the four highest-risk call sites in PromptGrimoire using this value-capture pattern. An ast-grep structural guard prevents reintroduction of the vulnerable pattern.

**This is targeted mitigation for adjacent-submit paths, not a comprehensive fix.** The underlying framework behaviour remains. Medium-risk sites (course dialogs, auth forms) are not addressed here because they have larger time gaps between last keystroke and submit.

## Definition of Done

1. A reusable helper wires button click (and optionally `keydown.enter`) handlers to capture a sibling input's DOM value client-side, passing it as the event argument.
2. The four high-risk sites use this helper instead of reading `inp.value`.
3. An ast-grep structural guard (run as a unit test) detects the vulnerable `.value` read pattern inside async handlers.
4. The pattern is documented in CLAUDE.md so future code uses the safe pattern.
5. `test_emoji_export.py` achieves ≤2 failures in 50 runs (see AC4.1 decision bands).

## Acceptance Criteria

### value-capture.AC1: Helper captures DOM value client-side at event time

- **value-capture.AC1.1 Success:** Button click handler receives the input's current DOM text as its argument, not by reading `inp.value`.
- **value-capture.AC1.2 Success:** `keydown.enter` on the input also captures and passes the DOM value (for roleplay send-on-enter path).
- **value-capture.AC1.3 Success:** Helper uses `input_el.html_id` (public API, `element.py:559`) not the internal numeric ID.
- **value-capture.AC1.4 Edge:** If the native `<input>` or `<textarea>` element is not found inside the Quasar wrapper, the JS guard fails loudly (emits empty string or null that the Python handler can detect) rather than silently passing `undefined`.
- **value-capture.AC1.5 Success:** The helper supports both `ui.input` and `ui.textarea` via `querySelector('input,textarea')`.
- **value-capture.AC1.6 Success:** After the handler processes the value, the input can be cleared server-side via `inp.value = ""` without interference.

### value-capture.AC2: High-risk sites are hardened

- **value-capture.AC2.1 Success:** `cards.py` add-comment handler receives comment text from event args.
- **value-capture.AC2.2 Success:** `sharing.py` share handler receives email from event args.
- **value-capture.AC2.3 Success:** `tag_quick_create.py` save handler receives tag name from event args.
- **value-capture.AC2.4 Success:** `roleplay.py` send handler receives message text from event args, for both button click and enter-key paths.
- **value-capture.AC2.5 Success:** All four sites still clear the input after successful processing.

### value-capture.AC3: Structural guard prevents reintroduction

- **value-capture.AC3.1 Success:** An ast-grep rule (or equivalent structural test) flags `async def` handlers that read `.value` from a captured `ui.input` parameter.
- **value-capture.AC3.2 Success:** The guard runs as part of the unit test suite.
- **value-capture.AC3.3 Edge:** The guard does not false-positive on legitimate `.value` reads outside of event handler contexts (e.g., initialisation, server-side-only logic).

### value-capture.AC4: E2E test stability

- **value-capture.AC4.1 Success:** `test_emoji_export.py` achieves 0-2 failures in 50 runs (strong evidence of improvement against 14% baseline; see decision bands below).
- **value-capture.AC4.2 Success:** Diagnostic instrumentation is removed from `cards.py` and `annotation_helpers.py`.

## Investigation Summary

### What we proved empirically

| Finding | Method |
|---|---|
| Client sends value update correctly | Monkeypatched `window.socket.emit`; captured `update:value` event with correct text on both passing and failing runs |
| `emitting` flag never suppressed | `Object.defineProperty` trap on Vue component's `emitting`; no `false` transitions during fill→click sequence |
| Server reads empty on failure | `os.write(2, ...)` diagnostic in `cards.py` confirmed `inp.value=''` on failing runs |
| Any timing perturbation eliminates flake | `logger.warning` in handler: 15/15 pass. `page.evaluate` traces: 20/20 pass |
| DOM element is stable (no rebuild) | Element ID comparison before/after fill: identical on both passing and failing runs |

### What we confirmed by code inspection

| Finding | Location |
|---|---|
| `async_handlers` defaults `True` | `socketio/base_server.py:17` |
| NiceGUI doesn't override it | `nicegui/nicegui.py:51` |
| Each event dispatched as `ensure_future` task | `socketio/async_server.py:604-608` |
| Async UI handlers create additional background task | `nicegui/events.py:458` via `background_tasks.create()` |

### What we have NOT proven

- That concurrent task dispatch is the actual cause of *this specific* flake. We have a plausible mechanism consistent with all observations, but we haven't directly observed out-of-order task execution. The observer effect (any instrumentation eliminates the flake) makes direct observation impractical.
- That the MWE reliably reproduces. The ~15-20% failure rate was observed only without instrumentation, and the race window appears to be fixture-dependent and extremely narrow.
- That there isn't a simpler explanation we've missed.

### Hypothesised race timeline (not directly observed)

```
Client:  fill("text") ──► socket.emit("event", {update:value, "text"})
         click()       ──► socket.emit("event", {click, post-btn})
                            ↓ WebSocket delivers both in order

Server:  socketio.async_server._handle_event():
         ┌─ Task A = ensure_future(value update handler)
         └─ Task B = ensure_future(click handler)

         If Task B executes first (asyncio scheduling):
           → NiceGUI handle_event → async handler → background_tasks.create(Task C)
         Task C reads inp.value → "" (Task A hasn't run yet)
```

### Baseline failure rate

With all diagnostic instrumentation removed, 50 consecutive runs of `test_emoji_survives_export`:

- **43 pass, 7 fail (14% failure rate)**
- Failures at runs: 2, 11, 24, 30, 33, 38, 46 (no clustering pattern)

This is the "before" measurement. Decision bands for the post-fix 50-run retest (predeclared):

| Failures in 50 | Interpretation | Action |
|---|---|---|
| 0-2 | Strong evidence of improvement (P ≤ 2.2% under unchanged 14% rate) | Accept fix |
| 3 | Inconclusive (P ≈ 6.7%) | Investigate further |
| 4+ | Weak or no evidence of improvement | Revise hypothesis |

### Hypotheses tested and falsified

- H1 (emitting flag race wipes DOM value): DOM value correct on failing runs
- H2 (socket.io message reordering): Socket.IO guarantees ordering per connection
- H3 (emoji-specific issue): Other tests post emoji comments without flaking
- H4 (search_worker contention): No causal path to empty `.value`
- H5 (stale DOM element from card rebuild): Element ID stable on failing runs
- H6 strong (card construction triggers `run_method('updateValue')` suppressing emit): `BindableProperty.__set__` doesn't call change handler on first assignment
- H6 weak (emitting flag suppressed during fill): Client-side trap showed no `emitting` transitions

## Architecture

### The helper

Location: `src/promptgrimoire/ui_helpers.py` (new file, or in an existing shared module).

```python
def on_submit_with_value(
    trigger: ui.element,
    input_el: ui.input,
    handler: Callable[[str], Awaitable[None] | None],
    *,
    event: str = "click",
) -> None:
```

The helper:
1. Builds a `js_handler` string that reads the input's DOM value via `document.getElementById('{input_el.html_id}').querySelector('input,textarea').value`
2. Includes a fail-fast guard: if no native field found, emits `""` (not `undefined`)
3. Registers the handler on the trigger element for the specified event type
4. The Python handler receives the value as `e.args` (a string)

### Call site transformation

Before:
```python
async def add_comment(inp=comment_input):
    if inp.value and inp.value.strip():  # RACE
        do_work(inp.value.strip())
        inp.value = ""
```

After:
```python
async def add_comment(text: str, inp=comment_input):
    if text and text.strip():
        do_work(text.strip())
        inp.value = ""  # Server-side clear is safe
```

## Existing Patterns

- `respond.py:500-507` documents the stale `.value` issue and reads `e.args` instead
- `navigator/_page.py:56` uses `js_handler` for client-side argument transformation
- `element.py:338` documents `js_handler` as the supported mechanism for client-side event arg transformation

## Implementation Phases

### Phase 1: Helper + cards.py hardening + test stabilisation

1. Create the helper function
2. Apply to `cards.py` add-comment handler
3. Remove diagnostic code from `cards.py` and `annotation_helpers.py`
4. Verify `test_emoji_export.py` stability (20+ runs)

### Phase 2: Remaining high-risk sites

5. Apply to `sharing.py` email share handler
6. Apply to `tag_quick_create.py` tag name handler
7. Apply to `roleplay.py` send message handler (both click and enter paths)

### Phase 3: Guards and documentation

8. Write ast-grep structural guard as unit test
9. Add CLAUDE.md note about the pattern

## Additional Considerations

- **Upstream issue:** A minimal reproducer (8-line NiceGUI app + Playwright trigger) should be filed against NiceGUI, framed as a documentation/API request, not a bug report demanding `async_handlers=False`.
- **Multi-input forms:** The `courses.py` dialog handlers read multiple `.value` fields in a single submit. These need a different pattern (e.g., `js_handler` that emits a JSON object of all field values). Out of scope for this design.
- **NiceGUI version dependency:** The helper uses `html_id` (public API) and `querySelector('input,textarea')` (standard DOM). The `c` prefix on element IDs is not relied upon.

## Glossary

| Term | Definition |
|---|---|
| `async_handlers` | python-socketio server option controlling whether event handlers run as concurrent asyncio tasks (`True`, the default) or sequentially (`False`) |
| `js_handler` | NiceGUI's `element.on()` parameter for client-side JavaScript that transforms event arguments before sending to server |
| `html_id` | NiceGUI `Element` property returning the element's DOM `id` attribute (public API) |
| value-capture | Pattern of reading an input's value on the client side at event time and sending it with the event, rather than reading the server-side `.value` property in the handler |
