# Investigation: NiceGUI Slot Deletion Race (#369)

*Investigation date: 2026-03-20. Investigator: Claude (with Brian Ballsun-Stanton).*
*Status: Root cause confirmed for Category 3. Category 2 mechanism demonstrated but not proven as production path. Categories 1 and 4 unexplained.*
*Codebase: commit `1e2a1df1` (branch `debug/369-slot-deletion-race`), NiceGUI 3.8.0.*

## Summary

1,006 JSONL error events across 8 of 14 production epochs (Mar 15-19). 1,000 are from `Slot._parent` weakref invalidation; 6 from `Element._parent_slot`. Journal traceback classification identifies four trigger sites in our code (550 distinct error-seconds, 96 call chain variants).

**Two mechanisms discovered:**

1. **Dialog canary** (`dialog.py:30-35`): NiceGUI's `Dialog` creates a hidden canary element in the caller's slot context. When the caller's container is cleared, the canary is garbage-collected, its `weakref.finalize` callback deletes the dialog, and the dialog's slot context goes stale. Reproduced in tests. **Confirmed as the production mechanism for Category 3** (tag management, 73 error-seconds by file aggregation).

2. **Element.delete() + reference drop**: Calling `element.delete()` removes the element from `Client.elements`. Once all local strong references are dropped, the element is GC'd and `Slot._parent` goes stale. Reproduced in tests. **However, the production Category 2 callback (`_delete_highlight`) keeps a strong reference to the card alive while it continues `_update_highlight_css()` and `broadcast_update()` after `card.delete()`.** The test only reproduces by explicitly dropping local references, which the production code does not do at the point of failure. This mechanism is therefore demonstrated in NiceGUI but not proven as the production Category 2 path.

**What is not explained:** Category 1 (145 error-seconds, top chain) uses neither `ui.dialog()` nor `element.delete()`. Category 4 (38 error-seconds, top chain) is not investigated in detail. Because the four categories use mixed counting methods and their chains overlap, no valid "remaining uncategorised" figure can be computed by subtraction.

## Data Sources

| Source | Path | Window | Reproducibility |
|--------|------|--------|-----------------|
| Incident DB | `incident.db` (local, gitignored) | Mar 15 00:00 - Mar 19 21:30 AEDT | Not checked in. See Appendix A for re-creation. |
| Journal tracebacks | `journal_events` table in above | Same | Full Rich tracebacks with locals |
| JSONL events | `jsonl_events` table in above | Same | Structured log events (no tracebacks for this error class) |
| NiceGUI source | `.venv/.../nicegui/` | nicegui==3.8.0 | `slot.py`, `element.py`, `events.py`, `dialog.py`, `context.py` |
| Reproduction tests | `tests/integration/test_slot_deletion_race_369.py` | N/A | See Reproduction Tests section |

**Note on units:** "JSONL events" are rows in `jsonl_events` (one per structured log emission). "Journal error-seconds" are distinct seconds in `journal_events` containing the error string. The two counts measure different things and are not expected to match.

**Note on category counts:** This document uses two counting methods from the classifier (`scripts/classify_slot_errors.py`):
- **Top-chain count**: the number of error-seconds whose exact frame chain matches a specific pattern. Used for Categories 1, 2, 4.
- **File aggregation** (`--aggregate`): the number of error-seconds where ANY frame references a given file. Used for Category 3 because its chains span multiple `tag_management.py` line numbers. File-aggregate counts are always >= top-chain counts because one error-second can reference multiple files.

These two methods are not directly comparable. Category counts do not sum to 550 because chains overlap between categories, some chains are uncategorised, and 30 error-seconds are NiceGUI-internal-only.

## Production Error Rate

**Source:** `jsonl_events` table in `incident.db`.

**Error string breakdown:**
```sql
SELECT count(*) FROM jsonl_events WHERE event LIKE '%parent element this slot%'
-- Result: 1000 (Slot._parent)

SELECT count(*) FROM jsonl_events WHERE event LIKE '%parent slot of the element%'
-- Result: 6 (Element._parent_slot)
```

**Per-epoch query (E9 as example):**
```sql
SELECT count(*) FROM jsonl_events
WHERE (event LIKE '%parent element this slot%'
   OR event LIKE '%parent slot of the element%')
AND ts_utc >= '2026-03-16T04:02:31.284100Z'
AND ts_utc <= '2026-03-17T09:23:49.569869Z'
-- Epoch bounds from: extract_epochs(conn) in scripts/incident/analysis.py
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

## Discovered Mechanisms

### Mechanism A: Dialog canary (applies to Category 3)

NiceGUI 3.8.0 `Dialog.__init__` (`dialog.py:27-35`):

```python
with context.client.layout:
    super().__init__(value=value, on_value_change=None)

# create a canary element in the current context to trigger
# the deletion of the dialog when its parent is deleted
canary = Element()
canary.visible = False
weakref.finalize(
    canary,
    lambda: self.delete() if not self.is_deleted
            and self._parent_slot and self._parent_slot() else None
)
```

The dialog itself is created in `context.client.layout` (line 27), but the canary is created in the **caller's current slot context** (line 31). When the caller's container is later cleared:

1. `container.clear()` removes all children including the canary (`element.py:454-460`)
2. `client.remove_elements(descendants)` pops elements from `Client.elements` (`client.py:391`)
3. Canary has no more strong references; `gc.collect()` frees it
4. `weakref.finalize` callback fires `dialog.delete()`
5. The dialog's `default_slot._parent` weakref now points to a deleted element
6. Any code still in `with parent_slot:` (from `events.py:452`) that calls `context.client` (`context.py:41`) triggers `self.slot.parent.client` -- stale weakref
7. `RuntimeError`

**Where dialogs are created in this codebase:** A code search for `ui.dialog()` in the annotation package finds it only in `tag_management_rows.py:414` and `tag_management.py:271`. It does **not** appear in `cards.py`, `highlights.py`, `workspace.py`, or `css.py`.

### Mechanism B: element.delete() + reference drop (demonstrated, not proven for production Category 2)

`element.delete()` removes the element from `Client.elements` and marks `_deleted=True` (`client.py:388-391`). If all remaining strong references to the element are dropped, `gc.collect()` frees it and the weakref in `Slot._parent` goes stale.

**Test evidence:** `test_card_delete_stales_child_slot` reproduces the error by calling `card.delete()`, then explicitly deleting local variables (`del card; del btn`), then `gc.collect()`. The weakref goes stale and `context.client` raises `RuntimeError`.

**Gap between test and production:** The production `_delete_highlight` callback (`highlights.py:155-178`) keeps `card` alive as a parameter while it continues with `_update_highlight_css()` and `broadcast_update()` after `card.delete()`. The test only reproduces by dropping references that the production code still holds at the point of failure. This means the test demonstrates that the mechanism *exists* in NiceGUI, but does not prove it is what fires in production. The production Category 2 error may require an additional condition (client disconnection, GC pressure, or a different reference-drop path).

### What `container.clear()` does NOT do

`container.clear()` removes the container's **children**, not the container itself. A button directly inside a container retains a valid `parent_slot` after clear -- the slot's parent (the container) is still alive. Without a dialog canary or an `element.delete()`, `container.clear()` alone does not stale the weakref.

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

This wraps the rebuild in the container's slot context. The comment describes a mechanism where the caller's slot is destroyed -- but as established above, `container.clear()` alone does not destroy the container (the slot's parent). The mitigation may address a condition not yet reproduced in tests.

## Trigger Site Classification

**Source:** `journal_events` table in `incident.db`.

**Distinct error-seconds query:**
```sql
SELECT count(DISTINCT substr(ts_utc, 1, 19)) FROM journal_events
WHERE message LIKE '%parent element this slot%'
   OR message LIKE '%parent slot of the element%'
-- Result: 550
```

**Reproduction:**
- Individual chains: `uv run scripts/classify_slot_errors.py --db incident.db`
- File aggregation: `uv run scripts/classify_slot_errors.py --db incident.db --aggregate`

**Important caveat on line numbers:** Journal tracebacks were emitted by production deploys at various commits. Line numbers are from those deploys, not from current HEAD (`1e2a1df1`).

### Category 1: Card toggle after rebuild (145 error-seconds, top chain)

**Classifier output:** `cards.py:558` (145x as top chain).

**Code:** `toggle_detail()` calls `await ui.run_javascript(...)`. No dialog is created in this code path. No `element.delete()` call.

**Mechanism:** Unknown. Neither Mechanism A (no dialog) nor Mechanism B (no delete) applies.

**Confidence:** Low. Trigger site confirmed, mechanism not identified.

### Category 2: Highlight deletion (78 error-seconds, top chain)

**Classifier output:** `cards.py:404` -> `highlights.py:172` (78x as top chain).

**Code:** `do_delete()` calls `_delete_highlight()` which calls `card.delete()` then `_update_highlight_css()` and `broadcast_update()`. No dialog in this path.

**Mechanism:** Mechanism B (element.delete() + reference drop) is demonstrated in tests but not proven for this production path. The production callback keeps `card` alive as a function parameter during the post-delete work. See "Gap between test and production" under Mechanism B above.

**Confidence:** Corroborated. The delete mechanism works in NiceGUI (test proves this). Whether the production Category 2 errors fire via this mechanism or via an additional condition is unresolved.

### Category 3: Tag management callback (73 error-seconds, file aggregation)

**Classifier output:** `uv run scripts/classify_slot_errors.py --db incident.db --aggregate` reports 73 error-seconds for `tag_management.py`. Individual chains: `tag_management.py:53` (48x), `tag_management.py:51` (23x), plus 2 chains at other depths (1x each).

**Code (`tag_management.py:532-535`):**
```python
async def _on_tag_deleted(tag_name: str) -> None:
    await _refresh_tag_state(state, reload_crdt=True)
    await render_tag_list()
    ui.notify(f"Tag '{tag_name}' deleted", type="positive")
```

**Journal evidence:** Full traceback at `2026-03-19T08:46:38Z` shows `_open_confirm_delete.<locals>._do_delete` as the handler. The confirm-delete dialog is created in `tag_management_rows.py:414`.

**Mechanism:** Confirmed as Mechanism A (dialog canary). The confirm-delete dialog's canary lives in the tag list container. `render_tag_list()` clears the container, destroying the canary, triggering `dialog.delete()` via `weakref.finalize`. The `with parent_slot:` wrapper from `events.py:452` holds the dialog button's stale slot. `ui.notify()` dereferences it.

**Confidence:** Confirmed. Reproduced in `test_dialog_canary_triggers_slot_deletion`.

### Category 4: CSS/workspace highlight rebuild (38 error-seconds, top chain)

**Classifier output:** `css.py:377` -> `workspace.py:453` -> `highlights.py:283` (38x). No dialog in these files.

**Mechanism:** Unknown. Not investigated in detail.

**Confidence:** Low. Trigger site confirmed, mechanism not identified.

## Reproduction Tests

`tests/integration/test_slot_deletion_race_369.py`:

| Test | What it tests | Result |
|------|---------------|--------|
| `test_dialog_canary_triggers_slot_deletion` | Mechanism A: dialog canary in container; clear container; access `context.client` from dialog button's slot | **Passes: RuntimeError raised** |
| `test_dialog_canary_during_card_rebuild` | Mechanism A in an annotations-like container (synthetic -- no dialog in actual Category 1 path) | **Passes: RuntimeError raised** |
| `test_card_delete_stales_child_slot` | Mechanism B: `card.delete()` + drop local refs + `gc.collect()`; access `context.client` | **Passes: RuntimeError raised** |

**Note on `test_dialog_canary_during_card_rebuild`:** This test proves Mechanism A works in a container resembling `annotations_container`, but the actual Category 1 production path (`cards.py:558`) does not create dialogs. This test demonstrates a NiceGUI framework behaviour, not a reproduction of the Category 1 production bug. It is labelled "synthetic" to make this explicit.

**Note on `test_card_delete_stales_child_slot`:** This test explicitly drops local references (`del card; del btn`) before `gc.collect()`. The production `_delete_highlight` callback does NOT drop the `card` reference at the point where subsequent code executes. The test demonstrates that Mechanism B exists in NiceGUI, but does not match the production reference-lifetime pattern. An earlier version of this test (before adding `del card`) kept the reference alive, preventing GC and producing an inconclusive result -- that was a test artifact.

### Epistemic boundary

**Confirmed (mechanism proven and matches production path):**
- Category 3 (73 error-seconds, file aggregation): Mechanism A (dialog canary). Production traceback shows the confirm-delete dialog path. Test reproduces with matching structure.

**Corroborated (mechanism demonstrated but production path not fully matched):**
- Category 2 (78 error-seconds, top chain): Mechanism B works in NiceGUI when references are dropped. Production callback keeps references alive during post-delete work. The error may fire later when the callback returns and locals go out of scope, or via an additional condition.

**Not explained (trigger site known, mechanism unknown):**
- Category 1 (145 error-seconds, top chain): no dialog, no delete in code path
- Category 4 (38 error-seconds, top chain): not investigated in detail
- 30 error-seconds are NiceGUI-internal-only (no our-code frames); other chains not assigned to a category

**Not tested:**
- Whether NiceGUI 3.9.0 changes the canary or delete behaviour
- The mechanism for Category 1
- What concrete dereference path triggers Category 2 in production, given that the callback keeps `card` alive through post-delete work

## Proposed Fixes

**Category 3 (confirmed, can fix now):**

1. Move `ui.notify()` before `render_tag_list()` in `_on_tag_deleted`. The notification does not depend on the rebuilt tag list.
2. Or: create the confirm-delete dialog in `context.client.layout` instead of in the tag list container's context, so the canary is not a child of the container that gets cleared.

**Category 2 (corroborated, fix is low-risk):**

3. In `_delete_highlight()`, do all UI work (`_update_highlight_css`, `broadcast_update`) before `card.delete()`. This reorders to avoid operating in a potentially stale context. Even though the production mechanism is not fully proven, this reordering has no functional downside.

**Categories 1 and 4 (mechanism unknown):**

4. Investigate Category 1's production path for indirect dialog creation or other mechanisms.
5. File an upstream NiceGUI issue with the canary and delete findings.

## References

- NiceGUI source: `dialog.py:27-35`, `slot.py:22,31`, `element.py:454-460`, `context.py:41`, `events.py:440-458`, `client.py:383-391`
- Production traceback: `journal_events` at `2026-03-19T08:46:38Z`
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
# Top 3 individual chains:
#   cards.py:558 (145x)
#   cards.py:404 -> highlights.py:172 (78x, with chain repetition)
#   tag_management.py:53 (48x)

# 7. Reproduce file-level aggregation
uv run scripts/classify_slot_errors.py --db incident.db --aggregate
# Expected: 550 distinct error-seconds, 24 files referenced
# Key files:
#   cards.py (360x), highlights.py (276x), css.py (93x),
#   workspace.py (75x), tag_management.py (73x)
```

**Note:** The tarball is not checked in (387 MB). If unavailable, re-collect from the server.
