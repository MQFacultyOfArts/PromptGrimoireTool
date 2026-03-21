# Causal Analysis: NiceGUI Slot Deletion Race (#369)

Date: 2026-03-20 (updated 2026-03-21)
Investigator: Claude (Opus 4.6)
Status: Category 1 analysis added (2026-03-21), peer reviewed (3 Important resolved)
Codebase: branch `debug/369-slot-deletion-race`, NiceGUI 3.9.0. Line numbers verified against 3.9.0; events.py shifted +5 lines from 3.8.0, all other files unchanged.
Data sources: `telemetry-20260319-2123.tar.gz` (original, Mar 15-19) and `telemetry-20260321-1820.tar.gz` (Mar 19-21, ingested 2026-03-21). Note: re-ingesting the second tarball replaced the first's journal data in `incident.db`; original 550 error-seconds would need re-ingestion of the first tarball.

## Summary

1,006 JSONL error events across 8 of 14 production epochs (Mar 15-19), plus 79 error-seconds in Mar 19-21 data (fresh tarball `telemetry-20260321-1820.tar.gz`). Common secondary error: NiceGUI weakref invalidation (`RuntimeError: parent element deleted`) when exception handlers or subsequent code accesses `context.client` through a stale `Slot._parent` weakref. The primary errors vary by category.

Three mechanisms identified:
- **Mechanism A (Category 3, plausible):** Dialog canary destruction. `render_tag_list()` clears the tag container → GC frees the dialog canary → `weakref.finalize` deletes dialog → stale slot. Fix: reorder `ui.notify()` before `render_tag_list()`.
- **Mechanism B (Category 2, plausible):** Card already removed before `card.delete()`. Something removes the card from its parent slot's children list before the explicit `card.delete()` call; trigger unknown (see C2.1a). `card.delete()` raises `ValueError`. Fix: guard with `if not card.is_deleted:`.
- **Category 1 (two-part, decoded from 20 production tracebacks in Mar 19-21 data):**
  - **Part 1 (primary TimeoutError, speculative):** `requestAnimationFrame(window._positionCards)` fails because `window._positionCards` is undefined or a JS error prevents the `javascript_response` from being emitted. NiceGUI's `runJavascript` swallows non-SyntaxError exceptions without sending a response, causing the server-side 1s timeout. `cards.py:558` lacks the guard that `highlights.py:69` uses.
  - **Part 2 (secondary RuntimeError, possible):** Concurrent `_refresh_annotation_cards(trigger="crdt_broadcast")` runs during the JS await, clearing the card and staling the slot weakref. NiceGUI's exception handler then hits the stale slot when handling the `TimeoutError`.

Category 4 (38 error-seconds) remains speculative (hypothesised: same family, toolbar button).

## Causal Chain

### Mechanism A: Dialog canary (plausible for Category 3)

NiceGUI's `Dialog.__init__` creates a hidden canary element in the caller's slot context (`nicegui/elements/dialog.py:30-34`). When the caller's container is cleared, the canary is garbage-collected. Its `weakref.finalize` callback fires a guarded lambda: `self.delete() if not self.is_deleted and self._parent_slot and self._parent_slot() else None` (`nicegui/elements/dialog.py:33-34`). The three guard conditions check that the dialog is not already deleted, has a parent slot reference, and the parent slot's weakref is still alive. When all three pass, the dialog is deleted, and its slot context goes stale. Code executing inside NiceGUI's event dispatch wrapper (`events.py:457 with parent_slot:`) then fails when accessing `context.client` (`context.py:41`), which dereferences the stale `Slot._parent` weakref (`slot.py:22,29`).

**Verification path through NiceGUI source:**

| Step | File:Line | What happens |
|------|-----------|-------------|
| Event dispatch | `events.py:445` | `parent_slot = arguments.sender.parent_slot` |
| Async wrapper | `events.py:457` | `with parent_slot:` pushes onto `Slot.stacks` |
| Handler runs | `events.py:459` | `await result` — handler code executes |
| Container clear | `element.py:456` | `self.client.remove_elements(self.descendants())` |
| Canary freed | `nicegui/elements/dialog.py:33-34` | `weakref.finalize` fires guarded lambda (see above) |
| Dialog deleted | `client.py:388-391` | `element._deleted = True`, removed from `Client.elements` |
| UI operation | `context.py:41` | `context.client` -> `self.slot.parent.client` |
| Weakref stale | `slot.py:22,29` | `self._parent()` returns `None` -> `RuntimeError` |

**Where dialogs are created:** Code search for `ui.dialog()` in the annotation package finds it only in `tag_management_rows.py:414` and `tag_management.py:271`. It does **not** appear in `cards.py`, `highlights.py`, `workspace.py`, or `css.py`.

### Mechanism B: Card already removed before card.delete() (plausible for Category 2; trigger unknown)

Production traceback at `2026-03-16T00:08:57Z` shows a `ValueError: list.remove(x): x not in list` at `element.py:504` inside `card.delete()`. This proves the card had already been removed from its parent slot's children list before `card.delete()` ran. The specific trigger that removed it is unknown (see C2.1a in Claim Verification). The `RuntimeError` is secondary — it fires during NiceGUI's exception handling (`events.py:461 handle_exception`) which accesses `context.client` through the now-stale slot.

**Production traceback chain (from journal_events at `2026-03-16T00:08:57Z` — production commit unknown; this timestamp predates E9, so it falls in an unlisted epoch. Line numbers are from the production deploy at that time, not current 3.9.0 source):**
1. `events.py:454` — `await result` (do_delete handler)
2. `cards.py:404` — `await _delete_highlight(state, hid, c)`
3. `highlights.py:172` — `card.delete()`
4. `element.py:504` — `parent_slot.children.remove(element)` → **`ValueError: list.remove(x): x not in list`**
5. `events.py:456` — `core.app.handle_exception(e)` → secondary `RuntimeError` from stale slot

### Mechanism C: Concurrent rebuild stales card slot during JS await (possible for Category 1)

`toggle_detail` (`cards.py:545-558`) is an event handler on `header_row`, which is a child of a card, which is a child of `annotations_container`. NiceGUI dispatches the event inside `with parent_slot:` (`events.py:452`) where `parent_slot` is `header_row`'s parent slot — owned by the **card** (not the container).

While `toggle_detail` awaits `ui.run_javascript(...)` (1-second timeout), a concurrent `_refresh_annotation_cards(trigger="crdt_broadcast")` can run. This is triggered when another client (client B) calls `broadcast_update()` (`broadcast.py:337-341`), which directly `await`s `cstate.invoke_callback()` on each peer, including client A. `invoke_callback()` enters `with self.nicegui_client:` (`annotation/__init__.py:130`), scoping execution to client A's NiceGUI context, then calls `handle_update_from_other` (`broadcast.py:366-367`) → `_handle_remote_update` (`broadcast.py:300-312`) → `state.refresh_annotations(trigger="crdt_broadcast")` (`broadcast.py:312`). A second path exists via `_notify_other_clients` (`broadcast.py:113-120`), which uses `asyncio.create_task` during client registration (`broadcast.py:402`).

The rebuild clears `annotations_container` (line 585), which calls `remove_elements` on the card (setting `_deleted = True`, removing from `client.elements` and `slot.children`). Then the rebuild creates new cards and overwrites `annotation_cards[hl_id]` (line 606), dropping the last strong reference to the old card. CPython's refcount collection frees the card, staling the weakref.

When a primary exception occurs (e.g. `TimeoutError` — see Part 1 of the Category 1 hypothesis), NiceGUI catches it and calls `handle_exception` which accesses `context.client` through the now-stale `parent_slot._parent` weakref → `RuntimeError`. Note: the rebuild explains the stale weakref (the secondary error) but does NOT explain the primary `TimeoutError` — see peer review note in Category 1 section.

**Key distinction from Mechanism A:** Mechanism A requires a dialog canary whose `weakref.finalize` actively deletes the dialog. Mechanism C requires no dialog — the weakref stales passively when the card loses all strong references after `container.clear()` + dict overwrite.

### What `container.clear()` does and does not do

`container.clear()` (`element.py:454-460`) removes the container's **children**, not the container itself. It calls `client.remove_elements(self.descendants())` which sets `_deleted = True` on each descendant and removes them from `client.elements`. It then calls `slot.children.clear()` which drops the slot's strong references to child elements.

**When the weakref stays valid:** A button directly inside a container retains a valid `parent_slot` after clear — the slot's parent (the container) is still alive and the container is not collected.

**When the weakref goes stale:** If an event handler's `parent_slot._parent` points to a **child** of the cleared container (e.g. a card inside `annotations_container`), then `container.clear()` removes the card from `client.elements` and from `slot.children`. If no other strong reference holds the card (e.g. `annotation_cards` dict gets overwritten during rebuild), CPython's reference counting immediately collects the card, and the weakref goes stale. This is the hypothesised mechanism for Category 1: `_refresh_annotation_cards` clears the container (line 585) then overwrites `annotation_cards[hl_id]` with new cards (line 606), dropping the last strong reference to the old card.

**NiceGUI's element tree uses weakrefs in both directions:** `Slot._parent` is `weakref.ref[Element]` (`slot.py:22`), and `Element._parent_slot` is `weakref.ref[Slot]` (`element.py:78`). Only `Slot.children` (`list[Element]`) holds strong references. This means elements are not kept alive by the slot tree once removed from `slot.children`.

## Evidence Grading

| # | Finding | Grade | Positive border | Negative border | Production path | Upgrade path |
|---|---------|-------|----------------|-----------------|-----------------|--------------|
| 1 | Dialog canary mechanism triggers `RuntimeError` | **Plausible** | `test_dialog_canary_triggers_slot_deletion`: clear container → canary GC → dialog delete → stale slot → `RuntimeError` | `test_notify_before_rebuild_succeeds`: accessing `context.client` before the clear succeeds | Tests use synthetic setup matching production structure, not actual `_on_tag_deleted` code path | Test the actual production function with a workspace fixture |
| 2 | Card already removed before `card.delete()` causes `ValueError` | **Plausible** | `test_card_delete_after_concurrent_clear`: `container.clear()` then `card.delete()` raises `ValueError: list.remove(x)` | `test_delete_highlight_survives_pre_cleared_card`: real `_delete_highlight` with pre-cleared card completes, side effects verified | Production traceback demonstrates `ValueError`; negative border exercises actual function with mocked I/O | Fully integrated test with real CRDT and persistence for "demonstrated" |
| 3a | Category 1 Part 1 (primary TimeoutError): `window._positionCards` undefined or JS error prevents `javascript_response` | **Speculative** | `cards.py:558` does not guard `window._positionCards` (unlike `highlights.py:69`); NiceGUI's `runJavascript` swallows non-SyntaxError exceptions without emitting response | Not tested: no browser-side instrumentation | Code analysis only; no production evidence that `_positionCards` is actually undefined at error time | Production experiment (add guard, observe) for corroboration; browser-side instrumentation or E2E for discrimination |
| 3b | Category 1 Part 2 (secondary RuntimeError): concurrent rebuild stales card slot during JS await (Mechanism C) | **Plausible** | `test_container_clear_plus_dict_overwrite_stales_child_slot` shows weakref goes stale after clear + overwrite + GC; broadcast path from peer to `container.clear()` traced through code | Positive border: weakref stales on synthetic setup. Negative border not yet tested (removing the interleaving opportunity) | Production-like structure (NiceGUI elements, same clear + overwrite pattern) but not the actual concurrent `toggle_detail` + `broadcast_update` interleaving | Full interleaving test: two concurrent tasks, one in `toggle_detail`, one running `_refresh_annotation_cards` |

## Trigger Site Classification

**Source:** `journal_events` table in `incident.db` (local, gitignored — see Appendix A for re-creation).

**Error string breakdown:**
```sql
SELECT count(*) FROM jsonl_events WHERE event LIKE '%parent element this slot%'
-- Result: 1000 (Slot._parent)

SELECT count(*) FROM jsonl_events WHERE event LIKE '%parent slot of the element%'
-- Result: 6 (Element._parent_slot)
```

**Distinct error-seconds:**
```sql
SELECT count(DISTINCT substr(ts_utc, 1, 19)) FROM journal_events
WHERE message LIKE '%parent element this slot%'
   OR message LIKE '%parent slot of the element%'
-- Result: 550
```

**Reproduction:** `uv run scripts/classify_slot_errors.py --db incident.db` (individual chains) or `--aggregate` (file-level).

**Note on category counts:** This document uses two counting methods:
- **Top-chain count**: error-seconds whose exact frame chain matches a specific pattern.
- **File aggregation** (`--aggregate`): error-seconds where ANY frame references a given file.

These are not directly comparable. Category counts do not sum to 550 because chains overlap between categories, some are uncategorised, and 30 error-seconds are NiceGUI-internal-only.

**Important caveat on line numbers:** Journal tracebacks were emitted by production deploys at various commits (primarily `7f53808f`), not from current HEAD (`1e2a1df1`).

### Category 1: Card toggle after rebuild (145 error-seconds, top chain; 20 in Mar 19-21 data)

**Classifier output:** `cards.py:558` (145x as top chain in original data; 17x pure + 3x mixed in Mar 19-21 data).
**Code:** `toggle_detail()` calls `await ui.run_javascript("requestAnimationFrame(window._positionCards)")`. No dialog. No `element.delete()`.

**Production traceback (decoded from Mar 19-21 tarball, `2026-03-20T02:00:35Z`, user "Alina Lu", workspace `f4e2992f`):**

1. `cards.py:558` — `toggle_detail`: `await ui.run_javascript(...)` — **primary exception: `TimeoutError: JavaScript did not respond within 1.0 s`**
2. `javascript_request.py:28` — `__await__`: `yield from asyncio.wait_for(self._event.wait(), self.timeout)` → `CancelledError` → `TimeoutError`
3. `events.py:454-456` — `wait_for_result`: catches `Exception`, calls `core.app.handle_exception(e)` — still inside `with parent_slot:`
4. `app.py:167` — `handle_exception`: accesses `context.client` → `context.py:41` → `self.slot.parent` → **secondary `RuntimeError`: stale weakref**

All 20 pure Category 1 events in the Mar 19-21 data show this identical pattern: `TimeoutError` as primary, `RuntimeError` as secondary. The `RuntimeError` logged to journald is the secondary exception; the `TimeoutError` is the real failure.

**Two-part hypothesis (evidence grade: possible — see peer review note below):**

Category 1 has two independent failures that must both be explained:
1. **Primary: `TimeoutError`** — why does `requestAnimationFrame(window._positionCards)` not respond within 1 second?
2. **Secondary: `RuntimeError`** — why is the slot stale when NiceGUI's exception handler runs?

**Part 2 (secondary RuntimeError) — concurrent rebuild stales slot:**

A concurrent `_refresh_annotation_cards(trigger="crdt_broadcast")` runs during the `await ui.run_javascript(...)` yield point. The call chain:

1. Client A's `toggle_detail` is suspended at `await ui.run_javascript(...)` (`cards.py:558`)
2. Client B performs an annotation action (e.g. `_add_highlight`) and calls `state.broadcast_update()` (`broadcast.py:337-341`)
3. `broadcast_update` iterates peers including client A: `await cstate.invoke_callback()` (`broadcast.py:341`). `invoke_callback()` enters `with self.nicegui_client:` (`annotation/__init__.py:130`), scoping the callback execution to client A's NiceGUI context
4. Client A's `handle_update_from_other()` (`broadcast.py:366-367`) runs inside client A's context, calling `_handle_remote_update(state)` (`broadcast.py:300-312`)
5. `_handle_remote_update` calls `state.refresh_annotations(trigger="crdt_broadcast")` (`broadcast.py:312`)
6. `_refresh_annotation_cards` (`cards.py:565-584`) calls `state.annotations_container.clear()` (`cards.py:585`)
7. `container.clear()` → `client.remove_elements(self.descendants())` (`element.py:456`) → `element._deleted = True` on the card and all its children (`client.py:389`), `client.elements.pop(element.id)` (`client.py:391`)
8. Rebuild creates new cards, overwriting `annotation_cards[hl_id]` (`cards.py:606`) → old card loses last strong reference → GC'd → `header_row`'s `parent_slot._parent` weakref returns `None`
9. NiceGUI's exception handler (handling the primary `TimeoutError` from Part 1) accesses `context.client` through the now-stale slot → `RuntimeError`

**Part 1 (primary TimeoutError) — JS response never emitted:**

NiceGUI's `runJavascript` (`nicegui.js:327-338`) evals the code, then emits `javascript_response` in the `.then()` handler. If the eval throws a non-`SyntaxError`, the `.catch()` at line 330 re-throws it, and **no `.catch()` exists after `.then()`** — the promise rejects unhandled and `javascript_response` is never emitted. The server's `JavaScriptRequest._event` is never set, and the 1-second timeout fires.

`requestAnimationFrame(window._positionCards)` (`cards.py:558`) throws `TypeError` if `window._positionCards` is undefined or not a function. Note: `highlights.py:69` guards this call with `if (window._positionCards)` but `cards.py:558` does NOT guard.

`window._positionCards` is assigned at `annotation-card-sync.js:91` during `setupCardPositioning()`. Candidate scenarios where it is undefined at call time:
- **Page not fully loaded:** `setupCardPositioning` hasn't run yet (unlikely — the card and header already exist)
- **NiceGUI DOM panel replacement:** `annotation-card-sync.js:20-23` notes NiceGUI/Vue can replace the entire Annotate tab panel DOM, which makes closured DOM references stale. However, `window._positionCards` is a window-level global — DOM replacement does not clear `window` properties. This scenario would break `positionCards`'s DOM lookups (returning early at line 49) but would NOT make `window._positionCards` undefined
- **Tab switch:** If the Annotate tab is destroyed and recreated, `setupCardPositioning` may not re-run — but the window global from the first call persists

**Alternative Part 1 hypothesis — websocket disconnect:** If the client's websocket disconnects, the browser executes the JS successfully but `socket.emit("javascript_response", ...)` fails or is buffered. The server never receives the response. Additionally, `nicegui.py:238` routes `javascript_response` via `Client.instances.get(msg['client_id'])` — if the client has been deleted (after reconnect timeout), the response is silently dropped. However, the reconnect timeout (3.0s default) is longer than the JS timeout (1.0s), so at timeout time the client should still be alive.

**Peer review note (Codex, 2026-03-21):** The original Mechanism C claimed the concurrent rebuild explained the full Category 1 error. Codex correctly identified that `requestAnimationFrame(window._positionCards)` is global client-scoped JS that does not depend on the deleted card element. Deleting the server-side card does NOT prevent the browser from executing this JS and sending back a response. The concurrent rebuild explains the secondary `RuntimeError` (stale slot in exception handler) but does NOT explain the primary `TimeoutError`. The hypothesis has been split accordingly. **Part 2 is coherent; Part 1 requires independent investigation.**

**Supporting evidence:**
- All 20 pure Cat1 events show `TimeoutError` as primary, proving the JS call fails before the slot error
- Multi-user activity correlates: 15 of 20 Cat1 events have ≥2 concurrent *slot error* events on the same workspace within the same hour — note these are concurrent errors, not confirmed CRDT broadcasts, so this is correlational evidence only (see C1.6 rebuttal)
- Two broadcast paths exist: (1) `broadcast_update` (`broadcast.py:337-341`) — direct `await`, called by any annotation operation (highlight add, comment, tag apply) — this is the primary trigger path; (2) `_notify_other_clients` (`broadcast.py:113-120`) — `asyncio.create_task`, called only during client registration (`broadcast.py:402`), which is a much rarer event. Path 1 is the far more probable trigger for Category 1
- `_refresh_annotation_cards` is synchronous (no `await`), so once it starts it runs to completion, clearing and rebuilding all cards atomically

**What would falsify this:**
- Part 2: If `container.clear()` does NOT stale the weakref of a child element's slot (test: capture slot, clear container, overwrite `annotation_cards`, check `slot._parent()`)
- Part 1: If `requestAnimationFrame(window._positionCards)` never throws in production (would need browser-side instrumentation or wrapping the call in try/catch)
- Part 1 alternative: If websocket disconnects are rare during the error windows (would need HAProxy websocket close logs)
- If Category 1 events occur on workspaces with only a single connected client (partial check: 5 of 20 events have only 1 error event nearby, but non-error activity isn't in the journal)

**Fastest next tests (per Codex):**
1. **Part 1 (production experiment):** Add the guard that `highlights.py:69` already uses: change `cards.py:558` to `await ui.run_javascript("if (window._positionCards) requestAnimationFrame(window._positionCards)")`. If Cat1 timeouts decrease after deploy, that is strong corroboration but not definitive — the guard changes JS execution and timing, so could mask other failure modes. The cleaner discriminating test is browser-side instrumentation or E2E.
2. **Part 2:** Independently test whether `container.clear()` + `annotation_cards` overwrite stales the old card's slot weakref. Even if Part 1 is the full cause, Part 2 is still worth understanding for the family of bugs.

**Existing mitigation:** `cards.py:580-584` wraps the rebuild in `with state.annotations_container:`. This protects `ui.run_javascript` calls made *during the rebuild* from using the stale caller slot, but does NOT protect a *pre-existing* `toggle_detail` handler that started before the rebuild and is still awaiting its JS response.

**Relationship to Category 2:** Same family for the secondary error. Category 2 is "`card.delete()` on an already-removed card" — removed by concurrent `container.clear()` during a yield point. Category 1's secondary error is "stale slot in exception handler after concurrent rebuild." The primary `TimeoutError` in Category 1 may be an independent failure (missing JS global) that happens to co-occur with the rebuild race.

### Category 2: Highlight deletion (78 error-seconds, top chain)

**Classifier output:** `cards.py:404` -> `highlights.py:172` (78x as top chain).
**Code:** `do_delete()` → `_delete_highlight()` → `card.delete()`.
**Mechanism:** The card was already removed from its parent slot's children list before `card.delete()` ran, causing `ValueError` at `element.py:504`. Production traceback directly shows this `ValueError`. The specific trigger that removed the card is unknown (see C2.1a in Claim Verification).
**Evidence grade:** **Plausible.** Positive border: production traceback demonstrates the `ValueError`. Negative border: `test_delete_highlight_survives_pre_cleared_card` exercises the real `_delete_highlight` on a pre-cleared card with mocked I/O — function completes, side effects verified. Not tested in the fully integrated page flow.

### Category 3: Tag management callback (73 error-seconds, file aggregation)

**Classifier output:** `uv run scripts/classify_slot_errors.py --db incident.db --aggregate` reports 73 error-seconds for `tag_management.py`. Individual chains: `tag_management.py:53` (48x), `tag_management.py:51` (23x), plus 2 others (1x each).
**Code (`tag_management.py:532-535`):**
```python
async def _on_tag_deleted(tag_name: str) -> None:
    await _refresh_tag_state(state, reload_crdt=True)
    await render_tag_list()
    ui.notify(f"Tag '{tag_name}' deleted", type="positive")
```
**Journal evidence:** Full traceback at `2026-03-19T08:46:38Z` shows `_open_confirm_delete.<locals>._do_delete` as the handler. The confirm-delete dialog is created in `tag_management_rows.py:414`.
**Mechanism:** Dialog canary (Mechanism A). The confirm-delete dialog's canary lives in the tag list container. `render_tag_list()` clears the container → canary GC → `dialog.delete()` → stale slot → `ui.notify()` fails.
**Evidence grade:** **Plausible.** Both borders shown on synthetic test matching production structure. Production traceback corroborates the call chain. Not tested on the actual production function.

### Category 4: CSS/workspace highlight rebuild (38 error-seconds, top chain)

**Classifier output:** `css.py:377` -> `workspace.py:453` -> `highlights.py:283` (38x). No dialog in these files.
**Mechanism:** Not investigated.
**Evidence grade:** **Speculative.**

## Production Error Rate

**Source:** `jsonl_events` table in `incident.db`.

**Per-epoch query (E9 as example):**
```sql
SELECT count(*) FROM jsonl_events
WHERE (event LIKE '%parent element this slot%'
   OR event LIKE '%parent slot of the element%')
AND ts_utc >= '2026-03-16T04:02:31.284100Z'
AND ts_utc <= '2026-03-17T09:23:49.569869Z'
```

| Epoch | Commit | HAProxy Requests | JSONL Events | % of requests | Pool |
|-------|--------|------------------|--------------|---------------|------|
| E1 | ba70f4fa | 0 | 4 | N/A | -- |
| E2 | 856720bc | 0 | 8 | N/A | -- |
| E8 | eb1eab9f | 0 | 118 | N/A | -- |
| E9 | 2352db75 | 74,003 | 380 | 0.51% | 10+20 |
| E10 | d5f1d5ae | 24,264 | 48 | 0.20% | 10+20 |
| E11 | c5578542 | 36,352 | 78 | 0.21% | 80+15 |
| E12 | 2d2f9f30 | 65,579 | 266 | 0.41% | 80+15 |
| E13 | 7f53808f | 61,240 | 104 | 0.17% | 80+15 |
| **Total** | | | **1,006** | | |

## Existing Mitigation

At `cards.py:580-584` (current HEAD):

```python
# Wrap the entire rebuild in ``with container`` so that every
# ``ui.run_javascript`` call resolves the NiceGUI client through the
# container's slot -- not the caller's slot, whose parent element may
# have been destroyed by a prior ``container.clear()``.
with state.annotations_container:
    state.annotations_container.clear()
```

This wraps the rebuild in the container's slot context. The comment describes a mechanism where the caller's slot is destroyed, but `container.clear()` alone does not destroy the container (the slot's parent). The mitigation may address a condition not reproduced in tests.

## Reproduction Tests

`tests/integration/test_slot_deletion_race_369.py`:

| Test | What it tests | Result |
|------|---------------|--------|
| `test_dialog_canary_triggers_slot_deletion` | Mechanism A: clear container with dialog canary, access `context.client` inside `with parent_slot:` | **FAIL (red)**: `RuntimeError` raised |
| `test_notify_before_rebuild_succeeds` | Fix verification: access `context.client` before clear | **PASS (green)**: no error |
| `test_dialog_canary_during_card_rebuild` | Mechanism A in annotations-like container (synthetic — no dialog in actual Category 1 path) | **FAIL (red)**: `RuntimeError` raised |
| `test_card_delete_after_concurrent_clear` | Synthetic reproducer: `container.clear()` then `card.delete()` produces the same `ValueError` observed in production | **PASS**: `pytest.raises(ValueError)` catches the expected error |
| `test_delete_highlight_survives_pre_cleared_card` | Category 2 negative border: real `_delete_highlight` completes on a pre-cleared card, side effects verified (CRDT removal, persistence, dict cleanup) | **PASS (green)**: no error, all side effects confirmed |
| `test_missing_js_global_causes_timeout` | Category 1 Part 1: `ui.run_javascript` with missing global times out | **PASS**: `pytest.raises(TimeoutError)` catches. **Caveat:** NiceGUI test user doesn't execute JS — all unmatched JS times out. Proves server-side timeout works, not the browser-side TypeError hypothesis. Requires E2E for full verification |
| `test_guarded_js_global_resolves_with_rule` | Category 1 Part 1 negative border: guarded JS resolves when `javascript_rule` matches | **PASS (green)**: no timeout when rule returns `None` |
| `test_container_clear_plus_dict_overwrite_stales_child_slot` | Category 1 Part 2: `container.clear()` + dict overwrite drops all strong refs to old card → weakref stales | **PASS (green)**: `parent_slot._parent()` returns `None` after clear + overwrite + `del old_card` + `gc.collect()`. Initial attempt failed because the test's local variable held a strong reference — `del old_card` was required |

**Note on `test_dialog_canary_during_card_rebuild`:** This test demonstrates Mechanism A works in a container resembling `annotations_container`, but the actual Category 1 production path (`cards.py:558`) does not create dialogs. It demonstrates a NiceGUI framework behaviour, not a reproduction of the Category 1 production bug.

**Note on `test_card_delete_after_concurrent_clear`:** This test uses `container.clear()` as a synthetic way to remove the card, then shows `card.delete()` raises the same `ValueError` observed in production. It demonstrates that a pre-removed card produces the observed error, but does not demonstrate that `container.clear()` is the production trigger (see C2.1a).

**Note on `test_container_clear_plus_dict_overwrite_stales_child_slot`:** This test initially failed because the test's own `old_card` local variable held a strong reference to the card, preventing GC. After adding `del old_card` before `gc.collect()`, the weakref went stale as predicted. In production, the `_refresh_annotation_cards` function's loop variable goes out of scope when the function returns, so the test's `del` is the correct simulation. **This upgrades C1.5 from "possible" to "plausible"** — the weakref-staling mechanism is demonstrated on a synthetic setup matching production structure. Remaining gap: the test does not demonstrate the full interleaving (concurrent `broadcast_update` + suspended `toggle_detail`).

**Note on `test_missing_js_global_causes_timeout`:** NiceGUI's test user (`testing/user.py:93`) does not execute JS in a browser — it pattern-matches `run_javascript` code against registered `javascript_rules` and emits synthetic responses. Unmatched JS always times out. This test confirms the server-side timeout machinery but does NOT test the browser-side hypothesis (that `requestAnimationFrame(undefined)` throws `TypeError` which NiceGUI's `runJavascript` swallows). **Part 1 requires E2E testing with a real browser for the hypothesis to be upgraded.**

**Note on `test_delete_highlight_survives_pre_cleared_card`:** This test exercises the real `_delete_highlight` function with a pre-cleared card (simulating the production race). It verifies both that no `ValueError` is raised AND that the non-UI side effects complete: CRDT highlight removal, persistence, and `annotation_cards` dict cleanup. This is the negative border on the actual production code path, upgrading the evidence from "possible" to "plausible" (production-like setup with mocked I/O, not a fully integrated production path).

## Implemented Fix

**Category 3:** `tag_management.py:532-538` — moved `ui.notify()` before `render_tag_list()`. `ui.notify()` accesses `context.client` (via `context.py:41` → `self.slot.parent.client`) to enqueue a notification message to the browser. When called after `render_tag_list()`, the container clear has already destroyed the dialog canary, triggering `dialog.delete()` via `weakref.finalize`, which stales the slot weakref that `context.client` dereferences. Moving the notify call before the rebuild means the dialog and its canary are still alive, so `context.client` resolves normally. The notification content does not depend on the rebuilt tag list, so the reorder is safe.

**Category 2:** `highlights.py:172` — guard `card.delete()` with `if not card.is_deleted:`. If the card has already been removed (by whatever mechanism), `client.remove_elements()` will have set `element._deleted = True` (`client.py:389`), so `card.is_deleted` returns `True` and the redundant `delete()` call is skipped, preventing the `ValueError` at `element.py:504`. This is a defensive guard that works regardless of what removed the card.

## Claim Verification (Phase 3c)

### Category 3 fix: reorder `ui.notify()` before `render_tag_list()`

| # | Claim | Data | Warrant | Qualifier | Rebuttal |
|---|-------|------|---------|-----------|----------|
| C3.1 | `_on_tag_deleted` is called from inside a dialog button handler | Production traceback at `2026-03-19T08:46:38Z` shows `_open_confirm_delete.<locals>._do_delete` as the handler. Confirm-delete dialog created at `tag_management_rows.py:414` | The handler runs inside NiceGUI's `with parent_slot:` block (`events.py:457`), where `parent_slot` is the dialog button's slot | **Plausible** — production traceback matches, synthetic test reproduces | If the traceback was misread, or if `_do_delete` is not the only caller of `_on_tag_deleted` |
| C3.2 | `render_tag_list()` clears the container holding the dialog canary | `tag_management.py:287-296`: `_render_tag_list()` calls `tag_list_container.clear()`. The canary was created in `tag_list_container`'s slot context when `ui.dialog()` was called inside `with tag_list_container:` | `Dialog.__init__` creates the canary in the current slot context (`nicegui/elements/dialog.py:30-31`). `container.clear()` removes all children including the canary | **Plausible** — NiceGUI source confirms, synthetic test reproduces | If the dialog is created outside the tag list container's context (would need to verify tag_management_rows.py) |
| C3.3 | `ui.notify()` accesses `context.client` which dereferences the stale weakref | `context.py:41`: `return self.slot.parent.client`. After the canary is GC'd, `weakref.finalize` fires `dialog.delete()`, which sets `dialog._deleted = True` and removes it from `Client.elements`. The dialog's slot's `_parent` weakref now points to a deleted element | NiceGUI source chain: `context.client` → `self.slot.parent` → `Slot._parent()` → `weakref.ref` returns `None` → `RuntimeError` at `slot.py:29-31` | **Plausible** — both borders shown on synthetic test | If `ui.notify()` in production resolves `context.client` through a different path (e.g. if NiceGUI caches the client reference) |
| C3.4 | Moving `ui.notify()` before `render_tag_list()` is safe because the notification doesn't depend on the rebuilt tag list | `tag_management.py:539`: `ui.notify(f"Tag '{tag_name}' deleted", type="positive")` — uses only `tag_name` (a string parameter), not any state from the tag list | The notification is a fire-and-forget browser message. Its content is the deleted tag's name, which is known before the rebuild | **Demonstrated** — logic is self-evident from the code | If `ui.notify` has side effects that interact with the subsequent rebuild |

### Category 2 fix: guard `card.delete()` with `if not card.is_deleted:`

| # | Claim | Data | Warrant | Qualifier | Rebuttal |
|---|-------|------|---------|-----------|----------|
| C2.1 | The card was already removed from its parent slot's children list before `card.delete()` ran | Production traceback at `2026-03-16T00:08:57Z` shows `ValueError: list.remove(x): x not in list` at `element.py:504` inside `card.delete()` | `parent_slot.children.remove(element)` raises `ValueError` only if the element is not in the list. Something removed it before `card.delete()` ran | **Demonstrated** — the `ValueError` in the production traceback directly proves this | The traceback could be misread (verified: it is not) |
| C2.1a | The removal was caused by a concurrent `container.clear()` triggered by a CRDT broadcast | **Not demonstrated.** `_delete_highlight` has a yield point at `await pm.force_persist_workspace()` (line 169) where another async task could run `_refresh_annotation_cards` → `container.clear()`. However, the specific inbound path that would trigger this during the yield has not been identified. `_notify_other_clients` (`broadcast.py:113`) uses `asyncio.create_task` but is only called during client registration (`broadcast.py:402`), not during CRDT broadcast. The local `broadcast_update` (`broadcast.py:337`) used by `_delete_highlight` runs AFTER `card.delete()` (line 183), not before | The yield point exists but the triggering path is unidentified | **Speculative** — yield point is real, but the specific async interleaving that removes the card before `card.delete()` is inferred, not traced | The card may have been removed by a different mechanism entirely (e.g., NiceGUI internal cleanup, client disconnect handler, or a different code path calling `container.clear()`) |
| C2.2 | After `container.clear()`, `card.is_deleted` is `True` | `element.py:456`: `container.clear()` calls `self.client.remove_elements(self.descendants())`. `client.py:389`: `remove_elements` sets `element._deleted = True` on each element. `element.py:523-525`: `is_deleted` property returns `self._deleted` | NiceGUI source confirms the chain. Synthetic test verifies: `assert card.is_deleted` passes after `container.clear()` | **Demonstrated** — verified in NiceGUI source and in test | If `container.clear()` in a future NiceGUI version stops calling `remove_elements` |
| C2.3 | Guarding with `if not card.is_deleted:` prevents the `ValueError` | `element.py:507-511`: `delete()` calls `parent_slot.parent.remove(self)` → `parent_slot.children.remove(element)` at line 504. If the card was already removed by `container.clear()`, `children.remove()` raises `ValueError`. The guard skips the entire `delete()` call | The guard is a simple boolean check before the call. If `True`, the call is skipped entirely. No partial execution | **Plausible** — `test_delete_highlight_survives_pre_cleared_card` exercises the real `_delete_highlight` with a pre-cleared card and confirms no `ValueError` | If `card.delete()` has necessary side effects beyond removing from the children list that are missed by skipping it (see C2.4) |
| C2.4 | Skipping `card.delete()` when `is_deleted` is True has no harmful side effects on `_delete_highlight`'s post-delete operations | `test_delete_highlight_survives_pre_cleared_card` verifies three of the five post-delete operations: (1) `crdt_doc.remove_highlight` was called, (2) `force_persist_workspace` was awaited, (3) `highlight_id` was removed from `annotation_cards` dict. The remaining two — `_update_highlight_css` and `broadcast_update` — were disabled in the test (`highlight_style=None`, `broadcast_update=None`). By code inspection: CSS update operates on CRDT state (not the card), broadcast sends CRDT state (not the card) — neither depends on `card.delete()` side effects | Both `container.clear()` and `element.delete()` ultimately call `client.remove_elements` which sets `_deleted=True`, calls `_handle_delete()`, enqueues delete in outbox, and removes from `Client.elements`. Since whatever removed the card already did this, skipping `delete()` loses nothing | **Plausible** — verified for exercised non-UI side effects (CRDT, persistence, dict cleanup); reasoned from code inspection for CSS update and broadcast | If CSS update or broadcast depend on `card.delete()` having run (inspected: they do not), or if callers of `_delete_highlight` depend on `card.delete()` for UI state (not identified but not exhaustively ruled out) |

### Category 1: concurrent rebuild stales card slot (Mechanism C)

| # | Claim | Data | Warrant | Qualifier | Rebuttal |
|---|-------|------|---------|-----------|----------|
| C1.1 | The primary exception in Category 1 is `TimeoutError`, not `RuntimeError` | All 20 pure Cat1 tracebacks in Mar 19-21 data show `TimeoutError: JavaScript did not respond within 1.0 s` from `javascript_request.py:28`, with `RuntimeError` as secondary from `handle_exception` → `context.client` | The traceback chain shows `TimeoutError` → `except Exception as e` → `handle_exception(e)` → `context.client` → stale slot → `RuntimeError`. The `RuntimeError` only occurs because the exception handler accesses the stale slot | **Demonstrated** — directly visible in decoded production tracebacks. 20/20 pure Cat1 events confirm | If the tracebacks were decoded incorrectly (verified: byte array → UTF-8 → ANSI strip produces readable Python tracebacks with correct frame references) |
| C1.2 | `toggle_detail`'s `await ui.run_javascript(...)` is a yield point where concurrent tasks can run | `cards.py:558`: `await ui.run_javascript("requestAnimationFrame(window._positionCards)")`. `ui.run_javascript` returns a `JavaScriptRequest` whose `__await__` calls `asyncio.wait_for(self._event.wait(), self.timeout)` (`javascript_request.py:28`). This suspends the coroutine for up to 1 second | Any `await` suspends the coroutine and allows the event loop to run other tasks. `asyncio.create_task` tasks (like `_notify_other_clients` at `broadcast.py:118`) can run during this suspension | **Demonstrated** — this is fundamental asyncio behaviour; the code path is verified in NiceGUI source | If NiceGUI somehow prevents other tasks from running during `wait_for` (it does not — standard asyncio) |
| C1.3 | A remote CRDT broadcast can trigger `_refresh_annotation_cards` on the receiving client | `broadcast.py:312`: `_handle_remote_update` calls `state.refresh_annotations(trigger="crdt_broadcast")`. This is invoked via `handle_update_from_other` (`broadcast.py:366-367`), registered as a callback at `broadcast.py:387`. Two paths fire callbacks: (1) `broadcast_update` (`broadcast.py:337-341`) — direct `await cstate.invoke_callback()`, called by annotation operations like `_add_highlight`; (2) `_notify_other_clients` (`broadcast.py:113-120`) — `asyncio.create_task(cstate.invoke_callback())`, called during client registration at `broadcast.py:402` | Path 1: when client B calls `broadcast_update`, it directly `await`s client A's `invoke_callback()`, which enters `with self.nicegui_client:` (`annotation/__init__.py:130`) scoping execution to client A's NiceGUI context, then runs `_handle_remote_update` on client A's state. Path 2: `asyncio.create_task` schedules the callback as a new task that can run at any `await` point. Both paths reach `_refresh_annotation_cards` → `container.clear()` on client A's state while client A's `toggle_detail` is suspended at `await ui.run_javascript(...)` | **Demonstrated** — code path traced through source. `broadcast_update` iterates peers including the suspended client. `_refresh_annotation_cards` is synchronous and runs atomically once entered | If `invoke_callback` somehow skips `_handle_remote_update` (verified: `callback` field is set at `broadcast.py:387` to `handle_update_from_other`, which unconditionally calls `_handle_remote_update`) |
| C1.4 | `_refresh_annotation_cards` → `container.clear()` removes the old card from `client.elements` and `slot.children` | `cards.py:585`: `state.annotations_container.clear()`. `element.py:456`: `clear()` calls `self.client.remove_elements(self.descendants())`. `client.py:387-391`: sets `_deleted = True`, removes from `client.elements`. `element.py:457-458`: `slot.children.clear()` | NiceGUI source confirms. Verified in existing test `test_card_delete_after_concurrent_clear` where `card.is_deleted` is `True` after `container.clear()` | **Demonstrated** — verified in NiceGUI source and synthetic test | If NiceGUI changes `clear()` behaviour in future versions |
| C1.5 | After `container.clear()` + `annotation_cards[hl_id]` overwrite, the old card is collectible and its slot weakref goes stale | `test_container_clear_plus_dict_overwrite_stales_child_slot`: after `container.clear()`, `annotation_cards["hl-001"] = new_card`, `del old_card`, `gc.collect()`, `parent_slot._parent()` returns `None`. Initial test attempt failed because the test's local variable held a strong reference — `del old_card` was required to match production behaviour (where the loop variable goes out of scope) | With no strong references remaining, CPython's reference counting collects the card, invalidating the weakref. NiceGUI's `remove_elements` cleans up bindings (`client.py:386`), outbox, and `client.elements` (`client.py:391`) | **Plausible** — demonstrated on synthetic setup matching production structure. The `del old_card` requirement shows that a strong reference in a local scope (like the `toggle_detail` coroutine frame) could keep the card alive. In production, `toggle_detail`'s locals (`d`, `ch`) are weakref-holding child elements, not the card itself — but this needs verification | If the `toggle_detail` coroutine frame holds an unexpected strong reference to the card (e.g. via NiceGUI internals in `ui.run_javascript`'s sender resolution) |
| C1.6 | Multi-user activity correlates with Category 1 errors | 15 of 20 pure Cat1 error-seconds have ≥2 concurrent error events on the same workspace within the same hour | Multi-user activity is a necessary condition for remote CRDT broadcasts, which are the hypothesised trigger for concurrent `_refresh_annotation_cards` | **Possible** — correlational, not causal. The error events counted are other slot-deletion errors, not direct evidence of CRDT broadcasts. 5 of 20 events show only 1 error event nearby, though single-user activity would produce zero (non-error journal entries aren't in the incident DB) | If Category 1 can occur in single-user sessions (would falsify the "remote broadcast" trigger, though a local broadcast from `_add_highlight` at `highlights.py:54` would still call `refresh_annotations`) |

### Where I may be wrong

1. **Category 2 trigger mechanism is speculative (C2.1a):** The production traceback proves the card was removed before `card.delete()` ran (C2.1 — demonstrated). But the *cause* of that removal is unknown. The Category 1 investigation (Mechanism C) now provides a plausible family-level explanation: a concurrent `_refresh_annotation_cards(trigger="crdt_broadcast")` can run during any yield point, including `_delete_highlight`'s `await pm.force_persist_workspace()`. The `broadcast_update` used by `_delete_highlight` runs AFTER `card.delete()` (line 183), but a *different client's* broadcast arriving via websocket → `_notify_other_clients` → `asyncio.create_task` could trigger `_refresh_annotation_cards` → `container.clear()` on the local client during the yield. This is the same mechanism as Category 1 but with a different yield point and different secondary error (`ValueError` instead of `RuntimeError`). The guard is still correct regardless of trigger.

2. **Category 3 canary location (C3.2) — verified:** `_open_confirm_delete` (`tag_management_rows.py:414`) calls `ui.dialog()` in whatever slot context is current at call time. It is called from `_delete_group` (`tag_management.py:461`) and `_on_delete_tag` (`tag_management.py:573`), both of which are event handlers on buttons rendered inside the tag list container by `_render_tag_list_content`. So the canary IS created in the tag list container's slot context, and `render_tag_list()` → `container.clear()` DOES destroy it.

3. **Both fixes are defensive, not demonstrated:** Both fixes are graded "plausible" not "demonstrated" because the tests use synthetic setups, not the actual production code paths. The fixes prevent the errors in synthetic scenarios that match the production structure, but we have not reproduced the actual race on the actual production function.

4. **Category 1 weakref collection (C1.5) — tested, one caveat remains:** `test_container_clear_plus_dict_overwrite_stales_child_slot` confirms the weakref stales after `container.clear()` + dict overwrite + dropping the local reference. Initial test failure revealed that any local variable holding the card prevents GC. In production, `toggle_detail`'s closure captures `d` (detail div), `ch` (chevron button), `hid` (string), and `state` — none of which are the card itself. However, NiceGUI's event dispatch at `events.py:445` captures `parent_slot = arguments.sender.parent_slot`, and `arguments.sender` IS a child element of the card. If `arguments` or `sender` holds a strong reference to the card indirectly (via a parent chain), the card would not be collected. `Element._parent_slot` is a weakref (`element.py:78`), so the sender does NOT hold the card strongly. But this has not been verified end-to-end in the actual event dispatch path.

5. **Category 1 could also be caused by client disconnect, not just concurrent rebuild:** If the client disconnects (tab close, network loss), the JS call would also time out. After reconnect_timeout (3.0s default), `client.delete()` removes all elements. But the JS timeout is 1.0s and fires BEFORE the 3.0s reconnect timeout, so at JS timeout time the client hasn't been deleted yet — the slot should still be valid. This argues AGAINST disconnect as the mechanism and FOR concurrent rebuild. Unless: (a) the disconnect handler itself does something that stales the slot before `delete()`, or (b) some other path deletes elements faster than reconnect_timeout.

6. **Adjacent risk in `_on_group_deleted`:** `tag_management.py:397-399` follows the same pattern as `_on_tag_deleted` — it is called from a confirm-delete dialog handler and calls `render_tag_list()`. It avoids the bug only because it has no `ui.notify()` call after the rebuild. If a notification were added after `render_tag_list()` in this function, the same race would recur. The "notify before rebuild" convention established by the Category 3 fix is not yet documented as a project-wide rule.

## Epistemic Boundary

**Plausible (one or both borders shown, production-like but not production path):**
- Category 3: dialog canary mechanism. Both borders shown on synthetic test. Production traceback corroborates call chain. Fix implemented (reorder notify before clear).
- Category 2: the card was removed before `card.delete()` ran — **demonstrated** by production traceback (`ValueError`). The `is_deleted` guard prevents this error regardless of cause. But the *trigger mechanism* (what removes the card) is **speculative** — the CRDT broadcast path initially cited was incorrect, and the actual async interleaving has not been traced. The guard is defensive and correct, but we do not know *why* the race occurs.

**Plausible (one border shown, production-like but not full production interleaving):**
- Category 1 Part 2 (secondary RuntimeError): concurrent rebuild stales the card's slot weakref. `test_container_clear_plus_dict_overwrite_stales_child_slot` demonstrates the weakref goes stale after `container.clear()` + dict overwrite on a synthetic setup matching production structure. Broadcast path traced through code (C1.2-C1.5). **To upgrade to demonstrated:** full interleaving test with concurrent `toggle_detail` + `broadcast_update`.

**Speculative (untested):**
- Category 1 Part 1 (primary TimeoutError): `window._positionCards` undefined at call time, causing `TypeError` swallowed by NiceGUI's `runJavascript`. Code analysis shows `cards.py:558` lacks the guard that `highlights.py:69` uses. **To upgrade:** production experiment (add JS guard, observe) for corroboration; browser-side instrumentation or E2E for cleaner discrimination.
- Category 4 (38 error-seconds): not investigated. Codex hypothesis: same family — toolbar tag button deleted by concurrent `refresh_toolbar()` while `_add_highlight` is mid-await.

**Verified after upgrade:** NiceGUI 3.9.0 dialog canary code (`nicegui/elements/dialog.py:30-34`) is identical to 3.8.0. `events.py` shifted +5 lines (cosmetic). No behavioural change to the canary or delete mechanisms.

**Corrected during investigation:**
- Initial tests called handlers as bare functions, bypassing NiceGUI's `events.py:452` `with parent_slot:` wrapper. All tests failed to reproduce. The wrapper is necessary to put the stale slot on `Slot.stacks`.
- Category 2 was initially hypothesised as a `card.delete()` + reference-drop mechanism. Production traceback analysis revealed the primary error is `ValueError` (card already removed from children list), not `RuntimeError` from stale weakref. The `RuntimeError` is secondary (exception handling path). The trigger that removes the card remains unidentified.
- An earlier test for Category 2 kept a local `card` variable alive, preventing GC and producing an inconclusive result. This was a test artifact.
- The classifier groups all our-code frames from all journal lines within one second. This conflates separate tracebacks that occur in the same second. The distance check (>30 lines between frames) was used to verify that Category 2 tracebacks do contain both `cards.py:404` and `highlights.py:172` in the same traceback (they do — the large `PageState` locals dump spans ~150 lines).
- Category 1 was initially listed as "no mechanism identified" (speculative). Decoding the full traceback from fresh Mar 19-21 telemetry revealed the primary exception is `TimeoutError` from `ui.run_javascript`, not `RuntimeError` from the stale slot. The `RuntimeError` is secondary — same pattern as Category 2. This reframed the investigation from "what deletes the element?" to "what runs `container.clear()` during the JS await?"
- C1.5 weakref test initially appeared to falsify the hypothesis (old card not collected). `gc.get_referrers()` revealed the test's own `old_card` local variable was the sole hidden referrer. After `del old_card`, the weakref went stale as predicted. Same pattern as the earlier Category 2 test artifact (item 3 above).
- Part 1 timeout test (`test_missing_js_global_causes_timeout`) passes but is uninformative: NiceGUI's test user doesn't execute JS, so all unmatched JS times out regardless. The hypothesis that `requestAnimationFrame(undefined)` throws `TypeError` in the browser cannot be tested without E2E infrastructure.

## Proposed Next Steps

1. ~~**Category 2 fix:**~~ Done. Guard implemented in `highlights.py:172`; green test written.
2. ~~**Category 1 Part 1 (primary TimeoutError):**~~ Guard implemented in `cards.py:558-560`. See preregistered experiment below.
3. ~~**Category 1 Part 2 (secondary RuntimeError):**~~ Done. `test_container_clear_plus_dict_overwrite_stales_child_slot` confirms weakref stales after clear + overwrite. Evidence upgraded to plausible.
4. **Category 4 investigation:** Test Codex's hypothesis (toolbar button deleted by `refresh_toolbar()` during `_add_highlight` await).
5. **Upstream:** File NiceGUI issue with findings — both the dialog canary (Mechanism A) and the broader "event handler on GC'd element" pattern (Mechanism C).

## Preregistered Experiment: Category 1 Part 1 JS Guard

**Date preregistered:** 2026-03-21
**Branch:** `debug/369-slot-deletion-race`
**Change:** `cards.py:558-560` — `await ui.run_javascript("requestAnimationFrame(window._positionCards)")` changed to `await ui.run_javascript("if (window._positionCards) requestAnimationFrame(window._positionCards)")`, matching the guard pattern already used at `highlights.py:69`.

**Hypothesis:** The primary `TimeoutError` in Category 1 is caused by `window._positionCards` being undefined at call time. `requestAnimationFrame(undefined)` throws `TypeError` in the browser. NiceGUI's `runJavascript` (`nicegui.js:327-338`) catches only `SyntaxError`; the `TypeError` causes the promise to reject without emitting `javascript_response`, so the server times out after 1 second.

**Primary endpoint:** Category 1 error-seconds per 10,000 HAProxy requests.

**Baseline (Mar 19-21 data):** 17 Cat1 error-seconds. HAProxy request count for that window is not in the current incident DB (journal-only tarball). Approximate from prior epochs: E13 had 61,240 requests and 104 total slot errors over ~24h. The Mar 19-21 window covers ~36h with 79 total slot errors. Estimating ~80,000 requests → baseline rate ≈ 2.1 Cat1 error-seconds per 10k requests. This estimate is rough; the actual HAProxy count should be extracted from the post-deploy tarball for both windows.

**Prediction:** Post-deploy Cat1 rate drops to <0.5 error-seconds per 10k requests (>75% reduction from baseline). Measured over at least 50,000 HAProxy requests (approximately one full teaching day, Mon-Fri).

**What a positive result would show:** Strong corroboration that `_positionCards` being undefined/non-callable is the specific cause of the primary `TimeoutError`. This is narrower than the broader "some JS error prevented `javascript_response`" family — the guard specifically tests the "missing/non-callable global" branch. A positive result does NOT rule out other JS failure modes that may contribute at lower rates.

**What a negative result would show (Cat1 rate does not decrease):**
- `_positionCards` being undefined is NOT the primary cause (or not the only one)
- The `TimeoutError` has a different browser-side or network-level mechanism
- **Escalation:** immediately add browser-side instrumentation (wrap `requestAnimationFrame` call in try/catch, log errors to server via a dedicated endpoint). Do not iterate more blind guards.

**Controls:**
- **Negative control:** Category 4 should be unaffected (no fix on this branch). If Cat4 rate changes substantially, something other than the fixes is affecting error rates (e.g. traffic pattern change, NiceGUI behaviour change).
- **Deploy confirmation:** Categories 2 and 3 should decrease (their fixes are on the same branch). If they don't, the deploy may not have taken effect. These are not controls for the Cat1 mechanism — they only confirm the branch was deployed.

**Measurement:**
```bash
# After deploy, collect telemetry covering at least one full teaching day
# (Mon-Fri, ≥50k HAProxy requests):
ssh grimoire.drbbs.org 'sudo /opt/promptgrimoire/deploy/collect-telemetry.sh \
    --start "<deploy_time>" --end "<end_time>"'

# Ingest and classify:
uv run scripts/incident_db.py ingest /tmp/telemetry-<stamp>.tar.gz --db incident.db
uv run scripts/classify_slot_errors.py --db incident.db

# Extract HAProxy request count for normalisation:
uv run scripts/incident_db.py breakdown --db incident.db

# Compute: Cat1 error-seconds / (HAProxy requests / 10000)
# Compare against baseline ≈ 2.1 per 10k requests.
# Prediction holds if post-deploy rate < 0.5 per 10k requests.
```

## References

- NiceGUI source (3.9.0): `nicegui/elements/dialog.py:27-35`, `slot.py:22,29-31`, `element.py:454-460,504,507-511`, `context.py:39-41`, `events.py:445-463`, `client.py:388-391`
- Production tracebacks: `journal_events` at `2026-03-19T08:46:38Z` (Category 3) and `2026-03-16T00:08:57Z` (Category 2)
- Existing mitigation: `cards.py:580-584` (current HEAD)
- Reproduction tests: `tests/integration/test_slot_deletion_race_369.py`
- Classification script: `scripts/classify_slot_errors.py`
- Issue: https://github.com/MQFacultyOfArts/PromptGrimoireTool/issues/369

## Appendix A: Reproducing the Incident DB

The `incident.db` file is local and gitignored. To re-create from scratch:

```bash
# 1. Collect telemetry tarball from production
ssh grimoire.drbbs.org 'sudo /opt/promptgrimoire/deploy/collect-telemetry.sh \
    --start "2026-03-15 00:00" --end "2026-03-19 21:30"'
# The tarball used for this investigation: telemetry-20260319-2123.tar.gz

# 2. Copy to local machine
scp grimoire.drbbs.org:/tmp/telemetry-20260319-2123.tar.gz /tmp/

# 3. Ingest into incident.db
uv run scripts/incident_db.py ingest /tmp/telemetry-20260319-2123.tar.gz --db incident.db

# 4. Ingest GitHub PR data
uv run scripts/incident_db.py github \
    --start "2026-03-15 00:00" --end "2026-03-19 21:30" --db incident.db

# 5. Verify counts
sqlite3 incident.db "SELECT count(*) FROM jsonl_events
    WHERE event LIKE '%parent element this slot%'"
# Expected: 1000

sqlite3 incident.db "SELECT count(*) FROM jsonl_events
    WHERE event LIKE '%parent slot of the element%'"
# Expected: 6

sqlite3 incident.db "SELECT count(DISTINCT substr(ts_utc, 1, 19)) FROM journal_events
    WHERE message LIKE '%parent element this slot%'
       OR message LIKE '%parent slot of the element%'"
# Expected: 550

# 6. Reproduce trigger-site classification (individual chains)
uv run scripts/classify_slot_errors.py --db incident.db
# Expected: 550 distinct error-seconds, 96 distinct call chains
# Top 3: cards.py:558 (145x), cards.py:404->highlights.py:172 (78x),
#         tag_management.py:53 (48x)

# 7. Reproduce file-level aggregation
uv run scripts/classify_slot_errors.py --db incident.db --aggregate
# Expected: 550 distinct error-seconds, 24 files referenced
# Key files: cards.py (360x), highlights.py (276x), css.py (93x),
#            workspace.py (75x), tag_management.py (73x)
```

**Note:** The tarball is not checked in (387 MB). If unavailable, re-collect from the server.

## Peer Review

Phase 3d subagent audit completed 2026-03-20. Five findings, all resolved:

| ID | Severity | Finding | Resolution |
|----|----------|---------|------------|
| C1 | Important | `dialog.py` citations should use full path `nicegui/elements/dialog.py` to distinguish from top-level module | All references updated to `nicegui/elements/dialog.py` |
| C2 | Important | `weakref.finalize` guard conditions (`not self.is_deleted and self._parent_slot and self._parent_slot()`) not acknowledged in causal description — reader cannot assess when the canary does NOT fire | Guard lambda quoted verbatim in Mechanism A description; "What container.clear() does NOT do" section updated |
| I1 | Minor | NiceGUI version stated as 3.8.0 but production runs 3.9.0; events.py line numbers differ by +5 | Header updated to 3.9.0; all events.py line numbers corrected; verification note added to Epistemic Boundary |
| I2 | Minor | Fix description says "avoids executing context.client after canary destroyed" but doesn't explain what `ui.notify` accesses or why the reorder is safe | Implemented Fix section rewritten with full call chain (`ui.notify` → `context.client` → `self.slot.parent.client`) and safety argument |
| I3 | Minor | Summary uses "73 error-seconds" (file aggregation) for Category 3 alongside "78 error-seconds" (top-chain) for Category 2 without flagging the different counting methods | Summary now labels each count with its method: "by file aggregation" vs "by top-chain count" |

### Second review (2026-03-21, post claim verification)

Phase 3d subagent audit of Phase 3c claim verification. 3 Important, 4 Minor findings. All resolved:

| ID | Severity | Finding | Resolution |
|----|----------|---------|------------|
| I1 | Important | Production traceback cites `events.py:459`/`:461` but those are 3.9.0 line numbers; production ran 3.8.0 at commit `7f53808f` | Traceback section now notes "line numbers from 3.8.0" and uses original production line numbers (454, 456) |
| I2 | Important | Category 3 negative border qualifier says "both borders shown" but negative border tests framework property, not fix code path | Acknowledged — tests show framework mechanism, not production function. Grade remains "plausible" |
| I3 | Important | `_on_group_deleted` (`tag_management.py:397`) follows same pattern as `_on_tag_deleted` but has no notify call — adjacent risk if one is added | Noted in "Where I may be wrong" section as item 5 |
| m4 | Minor | Category 2 evidence table and body text say negative border "not tested" but `test_is_deleted_guard_prevents_valueerror` tests it | Body text updated to "Both borders reproduced on synthetic test" |
| m6 | Minor | `slot.py:22,29` in References omits the `raise RuntimeError` at line 31 | Updated to `slot.py:22,29-31` |

### Third review (2026-03-21, Category 1 analysis addition)

Phase 3d subagent audit of Category 1 (Mechanism C) content. 3 Important, 4 Minor findings. All resolved:

| ID | Severity | Finding | Resolution |
|----|----------|---------|------------|
| I1 | Important | Broadcast path description omits `invoke_callback()`'s `with self.nicegui_client:` context switch (`annotation/__init__.py:130`), which is why the rebuild scopes to client A's DOM | Added to Mechanism C description, C1.3 claim, and Category 1 hypothesis chain (step 3) |
| I2 | Important | Multi-user correlation claim in body text ("15 of 20 Cat1 events have ≥2 concurrent events") presented without caveat that "concurrent events" means concurrent *slot errors*, not confirmed CRDT broadcasts | Body text amended with "(correlational evidence only)" caveat and pointer to C1.6 rebuttal |
| I3 | Important | "Where I may be wrong" numbering skips item 2 (jumps 1→3) — deletion artifact | Renumbered 1–6 sequentially |
| m1 | Minor | C1.3 rebuttal says "`callback` field is set at `broadcast.py:387`" — it's a constructor keyword argument, not assignment | Accurate for reference purposes; no change needed |
| m2 | Minor | "Mechanism C requires no dialog" contrast with Mechanism A obscures shared final link (stale `slot._parent`) | Acknowledged; both mechanisms share the same NiceGUI weakref failure mode. Distinction is in the *cause* of staleness, not the failure |
| m3 | Minor | The misleading comment at `cards.py:580-584` ("`container.clear()` destroys caller's slot") is surfaced but not added to follow-up actions | Not in scope for this analysis; existing code smell to address separately |
| m4 | Minor | Summary correctly updated (no action) | Verified |

### Fourth review (2026-03-21, Codex critical peer review)

Codex identified two High-severity findings in the Category 1 analysis. Both resolved by splitting the hypothesis:

| ID | Severity | Finding | Resolution |
|----|----------|---------|------------|
| H1 | High | Mechanism C does not explain the primary `TimeoutError`. `requestAnimationFrame(window._positionCards)` is global client-scoped JS — deleting the server-side card does not prevent the browser from executing it. The concurrent rebuild explains the secondary `RuntimeError` but not the timeout | Hypothesis split into Part 1 (primary TimeoutError — JS failure, speculative) and Part 2 (secondary RuntimeError — concurrent rebuild, possible). Part 2 is coherent; Part 1 requires independent investigation |
| H2 | High | Proposed upgrade test (container.clear() + dict overwrite → stale weakref) only supports Part 2. It cannot upgrade the full Category 1 mechanism from possible to plausible | Next steps split: Part 1 test is adding JS guard to `cards.py:558` and observing production; Part 2 test is the synthetic weakref test. Upgrade requires BOTH |
| M1 | Medium | Multi-user correlation evidence (15/20 events with ≥2 concurrent errors) is too coarse for a 1-second interleaving claim — it's background context, not timing evidence | Already caveated in body text; acknowledged as correlational only |
