# Causal Analysis: NiceGUI Slot Deletion Race (#369)

Date: 2026-03-20
Investigator: Claude (Opus 4.6)
Status: Awaiting peer review
Codebase: commit `1e2a1df1` (branch `debug/369-slot-deletion-race`), NiceGUI 3.8.0.

## Summary

1,006 JSONL error events across 8 of 14 production epochs (Mar 15-19), caused by NiceGUI weakref invalidation. Two contributing mechanisms identified: a dialog canary destruction path (plausible for Category 3, 73 error-seconds) and a concurrent-clear race (plausible for Category 2, 78 error-seconds). Category 1 (145 error-seconds) has no identified mechanism. A fix has been implemented for Category 3 (reorder `ui.notify()` before `render_tag_list()`).

## Causal Chain

### Mechanism A: Dialog canary (plausible for Category 3)

NiceGUI's `Dialog.__init__` creates a hidden canary element in the caller's slot context (`dialog.py:30-35`). When the caller's container is cleared, the canary is garbage-collected, its `weakref.finalize` callback deletes the dialog, and the dialog's slot context goes stale. Code executing inside NiceGUI's event dispatch wrapper (`events.py:452 with parent_slot:`) then fails when accessing `context.client` (`context.py:41`), which dereferences the stale `Slot._parent` weakref (`slot.py:29-31`).

**Verification path through NiceGUI source:**

| Step | File:Line | What happens |
|------|-----------|-------------|
| Event dispatch | `events.py:440` | `parent_slot = arguments.sender.parent_slot` |
| Async wrapper | `events.py:452` | `with parent_slot:` pushes onto `Slot.stacks` |
| Handler runs | `events.py:454` | `await result` — handler code executes |
| Container clear | `element.py:456` | `self.client.remove_elements(self.descendants())` |
| Canary freed | `dialog.py:33-34` | `weakref.finalize` fires `self.delete()` on dialog |
| Dialog deleted | `client.py:388-391` | `element._deleted = True`, removed from `Client.elements` |
| UI operation | `context.py:41` | `context.client` -> `self.slot.parent.client` |
| Weakref stale | `slot.py:29-31` | `self._parent()` returns `None` -> `RuntimeError` |

**Where dialogs are created:** Code search for `ui.dialog()` in the annotation package finds it only in `tag_management_rows.py:414` and `tag_management.py:271`. It does **not** appear in `cards.py`, `highlights.py`, `workspace.py`, or `css.py`.

### Mechanism B: Concurrent clear + card.delete() (plausible for Category 2)

Production traceback at `2026-03-16T00:08:57Z` shows a `ValueError: list.remove(x): x not in list` at `element.py:504` inside `card.delete()`. This proves a concurrent `container.clear()` already removed the card from its parent slot's children list before `card.delete()` ran. The `RuntimeError` is secondary — it fires during NiceGUI's exception handling (`events.py:456 handle_exception`) which accesses `context.client` through the now-stale slot.

**Production traceback chain (from journal_events at `2026-03-16T00:08:57Z`):**
1. `events.py:454` — `await result` (do_delete handler)
2. `cards.py:404` — `await _delete_highlight(state, hid, c)`
3. `highlights.py:172` — `card.delete()`
4. `element.py:504` — `parent_slot.children.remove(element)` → **`ValueError: list.remove(x): x not in list`**
5. `events.py:456` — `core.app.handle_exception(e)` → secondary `RuntimeError` from stale slot

### What `container.clear()` does NOT do

`container.clear()` removes the container's **children**, not the container itself (`element.py:454-460`). A button directly inside a container retains a valid `parent_slot` after clear — the slot's parent (the container) is still alive. Without a dialog canary or an `element.delete()` or a concurrent clear race, `container.clear()` alone does not stale the weakref.

## Evidence Grading

| # | Finding | Grade | Positive border | Negative border | Production path | Upgrade path |
|---|---------|-------|----------------|-----------------|-----------------|--------------|
| 1 | Dialog canary mechanism triggers `RuntimeError` | **Plausible** | `test_dialog_canary_triggers_slot_deletion`: clear container → canary GC → dialog delete → stale slot → `RuntimeError` | `test_notify_before_rebuild_succeeds`: accessing `context.client` before the clear succeeds | Tests use synthetic setup matching production structure, not actual `_on_tag_deleted` code path | Test the actual production function with a workspace fixture |
| 2 | Concurrent clear causes `ValueError` on `card.delete()` | **Plausible** | `test_card_delete_after_concurrent_clear`: `container.clear()` then `card.delete()` raises `ValueError: list.remove(x)` | Not tested | Test matches production traceback: same `ValueError`, same call chain (`card.delete()` → `element.py:504`) | Test the guard (`if not card.is_deleted:`) prevents the error |
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
**Mechanism:** Concurrent `container.clear()` removes the card before `card.delete()` runs, causing `ValueError` at `element.py:504`. Production traceback directly shows this `ValueError`.
**Evidence grade:** **Plausible.** Positive border reproduced. Production traceback matches. Negative border (guard prevents error) not tested.

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
| `test_card_delete_after_concurrent_clear` | Mechanism B: `container.clear()` then `card.delete()` | **PASS**: `pytest.raises(ValueError)` catches the expected error |

**Note on `test_dialog_canary_during_card_rebuild`:** This test demonstrates Mechanism A works in a container resembling `annotations_container`, but the actual Category 1 production path (`cards.py:558`) does not create dialogs. It demonstrates a NiceGUI framework behaviour, not a reproduction of the Category 1 production bug.

**Note on `test_card_delete_after_concurrent_clear`:** This test uses `pytest.raises(ValueError)` to assert the production-observed error occurs. It demonstrates the race mechanism. It does not yet test the fix (guarding with `is_deleted`).

## Implemented Fix

**Category 3:** `tag_management.py:532-538` — moved `ui.notify()` before `render_tag_list()`. The notification does not depend on the rebuilt tag list. This avoids executing `context.client` after the canary has been destroyed.

**Category 2:** Not yet implemented. Proposed: guard `card.delete()` with `if not card.is_deleted:` in `_delete_highlight`.

## Epistemic Boundary

**Plausible (one or both borders shown, production-like but not production path):**
- Category 3: dialog canary mechanism. Both borders shown on synthetic test. Production traceback corroborates call chain. Fix implemented (reorder notify before clear).
- Category 2: concurrent clear + `card.delete()` race. Positive border shown (test reproduces `ValueError` matching production traceback). Negative border not tested.

**Speculative (untested):**
- Category 1 (145 error-seconds): no mechanism identified. No dialog, no delete in code path.
- Category 4 (38 error-seconds): not investigated.
- Whether NiceGUI 3.9.0 changes the canary or delete behaviour.

**Corrected during investigation:**
- Initial tests called handlers as bare functions, bypassing NiceGUI's `events.py:452` `with parent_slot:` wrapper. All tests failed to reproduce. The wrapper is necessary to put the stale slot on `Slot.stacks`.
- Category 2 was initially hypothesised as a `card.delete()` + reference-drop mechanism. Production traceback analysis revealed the primary error is `ValueError` from concurrent `container.clear()`, not `RuntimeError` from stale weakref. The `RuntimeError` is secondary (exception handling path).
- An earlier test for Category 2 kept a local `card` variable alive, preventing GC and producing an inconclusive result. This was a test artifact.
- The classifier groups all our-code frames from all journal lines within one second. This conflates separate tracebacks that occur in the same second. The distance check (>30 lines between frames) was used to verify that Category 2 tracebacks do contain both `cards.py:404` and `highlights.py:172` in the same traceback (they do — the large `PageState` locals dump spans ~150 lines).

## Proposed Next Steps

1. **Category 2 fix:** Guard `card.delete()` with `if not card.is_deleted:` in `_delete_highlight`. Write green test.
2. **Category 1 investigation:** Search for what stales the weakref for `toggle_detail` when no dialog or delete is involved. Candidates: client disconnection, NiceGUI internal cleanup, indirect dialog creation.
3. **Upstream:** File NiceGUI issue with the canary finding.

## References

- NiceGUI source: `dialog.py:27-35`, `slot.py:22,31`, `element.py:454-460,504,507-511`, `context.py:41`, `events.py:440-458`, `client.py:383-391`
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

*To be populated by Phase 3d subagent audit.*
