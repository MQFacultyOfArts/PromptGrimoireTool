# Causal Analysis: NiceGUI Slot Deletion Race (#369)

Date: 2026-03-20
Investigator: Claude (Opus 4.6)
Status: Reviewed (peer review findings resolved)
Codebase: branch `debug/369-slot-deletion-race`, NiceGUI 3.9.0. Line numbers verified against 3.9.0; events.py shifted +5 lines from 3.8.0, all other files unchanged.

## Summary

1,006 JSONL error events across 8 of 14 production epochs (Mar 15-19), caused by NiceGUI weakref invalidation. Two contributing mechanisms identified: a dialog canary destruction path (plausible for Category 3, 73 error-seconds by file aggregation) and a card-already-removed condition (plausible for Category 2, 78 error-seconds by top-chain count; trigger unknown). Category 1 (145 error-seconds by top-chain count) has no identified mechanism. A fix has been implemented for Category 3 (reorder `ui.notify()` before `render_tag_list()`); a fix for Category 2 (guard `card.delete()` with `is_deleted` check) is implemented below.

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

### What `container.clear()` does NOT do

`container.clear()` removes the container's **children**, not the container itself (`element.py:454-460`). A button directly inside a container retains a valid `parent_slot` after clear — the slot's parent (the container) is still alive. Without a dialog canary (whose `weakref.finalize` guard conditions pass) or an `element.delete()` or a concurrent clear race, `container.clear()` alone does not stale the weakref.

## Evidence Grading

| # | Finding | Grade | Positive border | Negative border | Production path | Upgrade path |
|---|---------|-------|----------------|-----------------|-----------------|--------------|
| 1 | Dialog canary mechanism triggers `RuntimeError` | **Plausible** | `test_dialog_canary_triggers_slot_deletion`: clear container → canary GC → dialog delete → stale slot → `RuntimeError` | `test_notify_before_rebuild_succeeds`: accessing `context.client` before the clear succeeds | Tests use synthetic setup matching production structure, not actual `_on_tag_deleted` code path | Test the actual production function with a workspace fixture |
| 2 | Card already removed before `card.delete()` causes `ValueError` | **Plausible** | `test_card_delete_after_concurrent_clear`: `container.clear()` then `card.delete()` raises `ValueError: list.remove(x)` | `test_delete_highlight_survives_pre_cleared_card`: real `_delete_highlight` with pre-cleared card completes, side effects verified | Production traceback demonstrates `ValueError`; negative border exercises actual function with mocked I/O | Fully integrated test with real CRDT and persistence for "demonstrated" |
| 3 | Category 1 (`cards.py:558`) mechanism | **Speculative** | Not identified | — | No dialog, no delete in code path | Investigate what stales the weakref for `toggle_detail` |

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

### Category 1: Card toggle after rebuild (145 error-seconds, top chain)

**Classifier output:** `cards.py:558` (145x as top chain).
**Code:** `toggle_detail()` calls `await ui.run_javascript(...)`. No dialog. No `element.delete()`.
**Mechanism:** Unknown. Evidence grade: **speculative**.
**Existing mitigation:** `cards.py:580-584` wraps the rebuild in `with state.annotations_container:`.

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

**Note on `test_dialog_canary_during_card_rebuild`:** This test demonstrates Mechanism A works in a container resembling `annotations_container`, but the actual Category 1 production path (`cards.py:558`) does not create dialogs. It demonstrates a NiceGUI framework behaviour, not a reproduction of the Category 1 production bug.

**Note on `test_card_delete_after_concurrent_clear`:** This test uses `container.clear()` as a synthetic way to remove the card, then shows `card.delete()` raises the same `ValueError` observed in production. It demonstrates that a pre-removed card produces the observed error, but does not demonstrate that `container.clear()` is the production trigger (see C2.1a).

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

### Where I may be wrong

1. **Category 2 trigger mechanism is speculative (C2.1a):** The production traceback proves the card was removed before `card.delete()` ran (C2.1 — demonstrated). But the *cause* of that removal is unknown. I initially attributed it to a CRDT broadcast arriving during `await pm.force_persist_workspace()` via `asyncio.create_task` at `broadcast.py:118`, but that path (`_notify_other_clients`) is the peer-registration notification, not the CRDT broadcast path. The local `broadcast_update` used by `_delete_highlight` runs AFTER `card.delete()` (line 183). The inbound path from another client's websocket through to `_refresh_annotation_cards` on this client has not been traced. The guard is still correct — it prevents the `ValueError` regardless of *what* removed the card — but the "why" for Category 2 remains: "some async operation removed the card before `card.delete()` ran."

3. **Category 3 canary location (C3.2) — verified:** `_open_confirm_delete` (`tag_management_rows.py:414`) calls `ui.dialog()` in whatever slot context is current at call time. It is called from `_delete_group` (`tag_management.py:461`) and `_on_delete_tag` (`tag_management.py:573`), both of which are event handlers on buttons rendered inside the tag list container by `_render_tag_list_content`. So the canary IS created in the tag list container's slot context, and `render_tag_list()` → `container.clear()` DOES destroy it.

4. **Both fixes are defensive, not demonstrated:** Both fixes are graded "plausible" not "demonstrated" because the tests use synthetic setups, not the actual production code paths. The fixes prevent the errors in synthetic scenarios that match the production structure, but we have not reproduced the actual race on the actual production function.

5. **Adjacent risk in `_on_group_deleted`:** `tag_management.py:397-399` follows the same pattern as `_on_tag_deleted` — it is called from a confirm-delete dialog handler and calls `render_tag_list()`. It avoids the bug only because it has no `ui.notify()` call after the rebuild. If a notification were added after `render_tag_list()` in this function, the same race would recur. The "notify before rebuild" convention established by the Category 3 fix is not yet documented as a project-wide rule.

## Epistemic Boundary

**Plausible (one or both borders shown, production-like but not production path):**
- Category 3: dialog canary mechanism. Both borders shown on synthetic test. Production traceback corroborates call chain. Fix implemented (reorder notify before clear).
- Category 2: the card was removed before `card.delete()` ran — **demonstrated** by production traceback (`ValueError`). The `is_deleted` guard prevents this error regardless of cause. But the *trigger mechanism* (what removes the card) is **speculative** — the CRDT broadcast path initially cited was incorrect, and the actual async interleaving has not been traced. The guard is defensive and correct, but we do not know *why* the race occurs.

**Speculative (untested):**
- Category 1 (145 error-seconds): no mechanism identified. No dialog, no delete in code path.
- Category 4 (38 error-seconds): not investigated.

**Verified after upgrade:** NiceGUI 3.9.0 dialog canary code (`nicegui/elements/dialog.py:30-34`) is identical to 3.8.0. `events.py` shifted +5 lines (cosmetic). No behavioural change to the canary or delete mechanisms.

**Corrected during investigation:**
- Initial tests called handlers as bare functions, bypassing NiceGUI's `events.py:452` `with parent_slot:` wrapper. All tests failed to reproduce. The wrapper is necessary to put the stale slot on `Slot.stacks`.
- Category 2 was initially hypothesised as a `card.delete()` + reference-drop mechanism. Production traceback analysis revealed the primary error is `ValueError` (card already removed from children list), not `RuntimeError` from stale weakref. The `RuntimeError` is secondary (exception handling path). The trigger that removes the card remains unidentified.
- An earlier test for Category 2 kept a local `card` variable alive, preventing GC and producing an inconclusive result. This was a test artifact.
- The classifier groups all our-code frames from all journal lines within one second. This conflates separate tracebacks that occur in the same second. The distance check (>30 lines between frames) was used to verify that Category 2 tracebacks do contain both `cards.py:404` and `highlights.py:172` in the same traceback (they do — the large `PageState` locals dump spans ~150 lines).

## Proposed Next Steps

1. ~~**Category 2 fix:**~~ Done. Guard implemented in `highlights.py:172`; green test written.
2. **Category 1 investigation:** Search for what stales the weakref for `toggle_detail` when no dialog or delete is involved. Candidates: client disconnection, NiceGUI internal cleanup, indirect dialog creation.
3. **Upstream:** File NiceGUI issue with the canary finding.

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
