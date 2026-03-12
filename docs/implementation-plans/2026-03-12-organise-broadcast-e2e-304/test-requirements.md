# Test Requirements — organise-broadcast-e2e-304

## AC1: New broadcast drag test

### organise-broadcast-e2e-304.AC1.1 — Client B sees move within 10 seconds without tab switch or reload

| Field | Value |
|-------|-------|
| **Verification** | Automated test |
| **Type** | E2E (Playwright) |
| **File** | `tests/e2e/test_annotation_drag.py::TestBroadcastDrag::test_organise_auto_refreshes_on_remote_drag` |
| **Description** | Two browser contexts open the same workspace's Organise tab. Client A drags a highlight card from Jurisdiction to Procedural History. Test asserts Client B's view reflects the card in Procedural History within 10 seconds using `expect(...).to_be_visible(timeout=10000)` — no tab switching, no page reload. |

### organise-broadcast-e2e-304.AC1.2 — Client B's source column no longer contains the dragged card

| Field | Value |
|-------|-------|
| **Verification** | Automated test |
| **Type** | E2E (Playwright) |
| **File** | `tests/e2e/test_annotation_drag.py::TestBroadcastDrag::test_organise_auto_refreshes_on_remote_drag` |
| **Description** | Same test as AC1.1. After asserting the card appears in Procedural History on Client B, the test asserts the card is absent from the Jurisdiction column on Client B using `expect(...).to_be_hidden(timeout=5000)`. Confirms the broadcast delivers a move, not a copy. |

### organise-broadcast-e2e-304.AC1.3 — Timeout failure message

| Field | Value |
|-------|-------|
| **Verification** | Automated test |
| **Type** | E2E (Playwright) |
| **File** | `tests/e2e/test_annotation_drag.py::TestBroadcastDrag::test_organise_auto_refreshes_on_remote_drag` |
| **Description** | If the `expect` assertions from AC1.1/AC1.2 do not resolve within the 10-second timeout, Playwright raises `TimeoutError` with a message identifying the locator that was not satisfied (includes column testid and highlight-id). No additional test code needed — Playwright provides the clear failure message. |

## AC2: Refactor existing concurrent drag test

### organise-broadcast-e2e-304.AC2.1 — Polling loops replaced with direct expect assertions

| Field | Value |
|-------|-------|
| **Verification** | Human verification (code review) |
| **Type** | N/A |
| **File** | `tests/e2e/test_annotation_drag.py::TestConcurrentDrag::test_concurrent_drag_produces_consistent_result` |
| **Description** | The refactored test must not contain any `while True` polling loops that switch tabs via `_switch_to_annotate`/`_switch_to_organise`. All broadcast waits use Playwright `expect(locator).to_be_visible(timeout=10000)`. The `import time` statement must be removed. |
| **Justification** | This criterion is about code structure, not runtime behaviour. Verified during PR review by inspecting the diff and confirming no tab-switch polling remains. |

### organise-broadcast-e2e-304.AC2.2 — Refactored test still verifies consistent final state invariant

| Field | Value |
|-------|-------|
| **Verification** | Automated test |
| **Type** | E2E (Playwright) |
| **File** | `tests/e2e/test_annotation_drag.py::TestConcurrentDrag::test_concurrent_drag_produces_consistent_result` |
| **Description** | After both clients perform cross-column drags, the test asserts both pages agree on card positions: Jurisdiction is empty, card X is in Decision, card Y is in Procedural History. The consistency assertions (original lines 452-470) are preserved unchanged through the refactor. |

### organise-broadcast-e2e-304.AC2.3 — Flakiness gate

| Field | Value |
|-------|-------|
| **Verification** | Human verification (repeated runs) |
| **Type** | N/A |
| **File** | `tests/e2e/test_annotation_drag.py::TestConcurrentDrag::test_concurrent_drag_produces_consistent_result` |
| **Description** | Run the refactored test 5 times via `uv run grimoire e2e run -k test_concurrent_drag_produces_consistent_result --count 5` (or equivalent loop). If more than 1 run fails, revert the refactor and investigate the timing gap. |
| **Justification** | Flakiness is a statistical property that cannot be verified by a single test execution. Requires repeated runs and human interpretation before merging. |
