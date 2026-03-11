# Value-Capture Hardening: Peer Review Brief #2

**Date:** 2026-03-11
**Session context:** Continuation of value-capture-hardening implementation (design doc committed earlier today)

## What was done this session

### 1. Helper built (`src/promptgrimoire/ui_helpers.py`)

`on_submit_with_value(trigger, input_el, handler, *, event="click")` wires a client-side JS handler that reads the input's DOM value at event time and passes it as `e.args` to the Python handler.

### 2. Four call sites transformed

| File | Handler | Change |
|------|---------|--------|
| `cards.py` | `_make_add_comment_handler` | Now accepts `text: str` instead of reading `inp.value`; button wired via `on_submit_with_value` |
| `sharing.py` | `_on_share` | Now accepts `text: str` instead of reading `email_input.value`; button wired via `on_submit_with_value` |
| `tag_quick_create.py` | `_quick_create_save` + `_save` | Now accepts `tag_name: str` instead of reading `name_input.value`; button wired via `on_submit_with_value` |
| `roleplay.py` | `_handle_send` + `on_send` | Now accepts `user_message: str` instead of reading `input_field.value`; both click AND `keydown.enter` wired via `on_submit_with_value` |

All four sites still clear the input server-side after processing (`inp.value = ""`).

### 3. Critical bug found and fixed in the JS handler

**Original JS (from design doc):**
```javascript
const el = document.getElementById('{html_id}');
const f = el && el.querySelector('input,textarea');
emit(f ? f.value : '');
```

**Problem:** NiceGUI puts `html_id` (e.g. `id="c4"`) directly on the **native `<input>` element**, not on a wrapper `<div>`. So `getElementById` returns the `<input>` itself, and `querySelector('input,textarea')` looks for a *child* input inside the input — which doesn't exist. The handler always emitted empty string.

**Evidence:** DOM inspection via Playwright showed:
```html
<input class="q-field__native q-placeholder" tabindex="0"
       id="c4" type="text" value="" data-testid="test-input" ...>
```
No wrapper div. The `id` is on the native element directly.

**Fix:**
```javascript
const el = document.getElementById('{html_id}');
if(!el){emit('');return;}
const t = el.tagName.toLowerCase();
const f = (t==='input'||t==='textarea') ? el : el.querySelector('input,textarea');
emit(f ? f.value : '');
```

Check if the element IS already an input/textarea before trying querySelector.

### 4. Stability test results

**Baseline (pre-fix, established earlier today):** 43 pass, 7 fail out of 50 (14% failure rate)

**Post-fix:** 44 pass, 6 fail out of 50 (12% failure rate)
Failures at runs: 25, 27, 33, 40, 44, 46

**Against predeclared decision bands:**

| Failures in 50 | Interpretation | Action |
|---|---|---|
| 0-2 | Strong evidence of improvement | Accept fix |
| 3 | Inconclusive | Investigate further |
| **4+ (we got 6)** | **Weak or no evidence of improvement** | **Revise hypothesis** |

## What this means

The value-capture hardening is **structurally sound** — it eliminates the server-side `.value` race by construction. But it **did not measurably improve test stability**. This has two possible interpretations:

### Interpretation A: The original race was real but not the dominant failure mode

The server-side concurrent dispatch race IS structurally present (confirmed by code inspection). However, this test's ~14% failure rate may be dominated by a *different* race or timing issue that the value-capture pattern doesn't address. The original race may have caused a subset of failures that's too small to distinguish statistically (e.g., 1-2 out of 7).

### Interpretation B: The original race was never the actual cause

The concurrent dispatch race may be present in the code but never actually triggered for this specific test. The ~14% failure rate could be entirely caused by something else — perhaps a Playwright↔server timing issue, a card rebuild race, or a CRDT persistence race.

## What I have NOT done yet (was about to start investigating)

I was about to capture the actual failure output from a failing run to determine:
1. Is the failure still "comment count stays at 0" (same as baseline)?
2. Or is it a different failure mode (e.g., export-related)?

**This is critical** because if the failure mode has changed, interpretation A is more likely. If it's identical, interpretation B is more likely.

## Hypotheses for the remaining ~12% failure rate

These are UNTESTED hypotheses. I have not investigated any of them.

### H7: Card rebuild race
After `add_comment_to_highlight` clicks Post and waits for comment count to increase, the server calls `refresh_annotations()` which destroys and rebuilds all cards. The Playwright `expect(comments).to_have_count(before_count + 1)` locator may resolve against the old DOM briefly during the rebuild, see the count drop to 0, and fail.

**Evidence for:** The E2E helper has a re-expand step after the comment count check, suggesting card rebuild is known to happen.
**Evidence against:** The timeout is 10 seconds, which should be ample for a rebuild.
**Testable by:** Checking whether failing runs show the comment in the CRDT state but not in the DOM.

### H8: CRDT persistence race
`force_persist_workspace` is awaited, but `refresh_annotations()` triggers a full card rebuild from CRDT state. If the rebuild reads CRDT state before the comment is flushed, the card would rebuild without the comment.

**Evidence for:** Would explain consistent ~14% rate regardless of value-capture fix.
**Evidence against:** `force_persist_workspace` is awaited before `refresh_annotations()` is called.
**Testable by:** Adding CRDT state logging in the server to verify comment is present before rebuild.

### H9: Playwright fill+click timing
Playwright's `fill()` dispatches `input` and `change` events but the NiceGUI value-update event may not reach the server before the click event. Even with value-capture, if the fill itself hasn't completed its DOM update...

**Evidence against:** Value-capture reads the DOM value at click time, so the fill should have completed by then. Also, Playwright's `fill()` is synchronous from the browser's perspective.

### H10: Animation frame wait is insufficient
`card_helpers.py:93` does `page.wait_for_function("new Promise(r => requestAnimationFrame(r))")` between fill and click. This waits one frame. But Quasar's `q-input` may need more than one frame to process the fill.

**Evidence for:** rAF wait was noted as "does NOT guarantee the server has received the value."
**Evidence against:** The value-capture JS reads the DOM value at click time, which should reflect the fill regardless of server state.

### H11: Multiple cards cause locator ambiguity
If more than one annotation card exists, the locator `page.locator(ANNOTATION_CARD).nth(card_index)` with `card_index=0` might resolve differently during rebuild.

**Evidence for:** Cards are rebuilt from CRDT state; ordering could change.
**Evidence against:** Test creates only one highlight, so there should be only one card.

## Questions for the reviewer

1. Given 6/50 failures post-fix vs 7/50 baseline, do you agree this falls in the "revise hypothesis" band? (The statistical power is low — we can't distinguish 12% from 14% with n=50.)

2. Should we keep the value-capture hardening regardless? It IS structurally sound — it eliminates a real (if possibly rare) race condition. The question is whether we should also investigate the dominant failure mode.

3. Which hypothesis (H7-H11) would you prioritise investigating? My instinct is H7 (card rebuild race) because the E2E helper already has workaround code for it.

4. The JS handler bug (getElementById returning the native input, not a wrapper) was a real bug in our design. The design doc's architecture section assumed a Quasar wrapper div exists around the native input. Should we update the design doc to reflect the actual DOM structure?

## Files changed

```
src/promptgrimoire/ui_helpers.py          — helper (new file)
src/promptgrimoire/pages/annotation/cards.py — add_comment handler
src/promptgrimoire/pages/annotation/sharing.py — share handler
src/promptgrimoire/pages/annotation/tag_quick_create.py — tag create handler
src/promptgrimoire/pages/roleplay.py       — send message handler (click + enter)
tests/e2e/card_helpers.py                  — extracted from annotation_helpers.py (earlier)
tests/e2e/annotation_helpers.py            — re-exports from card_helpers.py (earlier)
```

## Unit test status

3540 passed, 1 skipped, 4 rerun — all green.
