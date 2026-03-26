# Test Requirements: Query Optimisation and Graceful Restart

## Automated Test Coverage

| AC | Description | Test Type | Test File | Phase |
|----|-------------|-----------|-----------|-------|
| AC1.1 | `list_document_headers()` returns all metadata; no `content` transferred | integration | `tests/integration/test_document_headers.py` | 1 |
| AC1.1 | Headers exclude content at query level (single SELECT, no N+1) | integration | `tests/integration/test_query_efficiency.py::TestDocumentHeadersEfficiency` | 2 |
| AC1.2 | Page load callers use `list_document_headers()` | integration | `tests/integration/test_query_efficiency.py::TestDocumentHeadersEfficiency::test_page_load_document_query_count` | 2 |
| AC1.3 | Accessing `.content` on headers-only object raises `DetachedInstanceError` | integration | `tests/integration/test_document_headers.py` | 1 |
| AC1.3 | Deferred content raises error (query-level verification) | integration | `tests/integration/test_query_efficiency.py::TestDocumentHeadersEfficiency` | 2 |
| AC1.4 | `list_documents()` still returns full `content` for export callers | integration | `tests/integration/test_document_headers.py` | 1 |
| AC2.1 | `POST /api/pre-restart` triggers CRDT flush on all connected clients | integration | `tests/integration/test_pre_restart.py` | 3 |
| AC2.2 | Clients navigate to `/restarting?return=<url>` after flush | integration | `tests/integration/test_pre_restart.py` | 3 |
| AC2.3 | Non-admin `POST /api/pre-restart` returns 403 | integration | `tests/integration/test_pre_restart.py` | 3 |
| AC2.4 | Milkdown extraction happens BEFORE persist call (ordering) | integration | `tests/integration/test_pre_restart.py` | 3 |
| AC3.1 | `/restarting` polls `/healthz`, redirects to return URL on 200 | e2e | `tests/e2e/test_restarting_page.py` | 4 |
| AC3.2 | Redirect includes 1-5s random jitter (not instant) | e2e | `tests/e2e/test_restarting_page.py` | 4 |
| AC3.3 | Missing `return` param redirects to `/` | e2e | `tests/e2e/test_restarting_page.py` | 4 |
| AC4.1 | Token extraction from `.env` works correctly | bats | `deploy/tests/test_restart.bats` | 5 |
| AC4.1 | `DRAIN_TIMEOUT` defaults to 30s | bats | `deploy/tests/test_restart.bats` | 5 |
| AC4.2 | `DRAIN_TIMEOUT` is overridable via env var | bats | `deploy/tests/test_restart.bats` | 5 |
| AC4.2 | Missing token warns but does not fail the deploy | bats | `deploy/tests/test_restart.bats` | 5 |
| AC5.1 | `memory_diagnostic` event emitted periodically | unit | `tests/unit/test_diagnostics.py` | 6 |
| AC5.2 | Snapshot contains RSS, client counts, asyncio tasks, CRDT sizes | unit | `tests/unit/test_diagnostics.py` | 6 |
| AC5.2 | `_collect_memory()` returns positive RSS on Linux | unit | `tests/unit/test_diagnostics.py` | 6 |
| AC5.2 | `_collect_memory()` handles missing `/proc` gracefully | unit | `tests/unit/test_diagnostics.py` | 6 |

## Human Verification Required

| AC | Description | Justification | Verification Approach |
|----|-------------|---------------|----------------------|
| AC1.2 | `workspace.py`, `tab_bar.py` x2, `document_management.py` all call `list_document_headers()` | Caller migration is a code-level change verified by reading the diff. Automated query counting (Phase 2) guards the efficiency property, but confirming each specific call site switched requires code review. | Review the Phase 1 diff: grep for remaining `list_documents()` calls in `workspace.py`, `tab_bar.py`, and `document_management.py`. Only `pdf_export.py` and `cli/export.py` should retain `list_documents()`. |
| AC1.4 | Export callers (`pdf_export.py`, `cli/export.py`) still receive full `content` | Export paths are NOT changed and existing export E2E tests cover them, but confirming no accidental migration requires visual diff review. | Verify `pdf_export.py` and `cli/export.py` still import and call `list_documents()` (not `list_document_headers()`). Run existing export E2E tests to confirm exports still produce valid output. |
| AC2.1 | All connected clients flush CRDT state on pre-restart | The integration test uses mocked NiceGUI Client objects. Full end-to-end verification with real WebSocket connections and multiple browser tabs requires manual testing. | UAT Phase 3 step 6: open annotation page, type in Respond editor, call `curl -X POST -H "Authorization: Bearer $token" http://localhost:8080/api/pre-restart`, verify browser navigates away and CRDT state is persisted (reload workspace, confirm response draft content survived). |
| AC2.4 | Mid-edit Milkdown content saved to CRDT before flush | Integration test verifies call ordering on mocks. Real Milkdown editor extraction with JS bridge requires a running browser. | UAT Phase 3 steps 5-7: type new text in Milkdown Respond editor (do NOT click away), trigger pre-restart via curl, restart server, reload workspace, verify the mid-edit text persisted in the response draft. |
| AC3.2 | Redirect jitter is 1-5s (thundering herd prevention) | Timing-based assertions are inherently unreliable in CI. The E2E test verifies the redirect is not instant but cannot assert exact jitter bounds without flakiness. | UAT Phase 4 step 4: open browser dev tools Network tab, navigate to `/restarting?return=/`, observe the delay between the 200 `/healthz` response and the navigation event. Verify it falls within 1-5s. |
| AC4.1 | `restart.sh` calls pre-restart, waits for <=5% connections + 2s grace | Full deploy sequence requires a running server, HAProxy, and systemd -- not available in CI. BATS tests cover token extraction and timeout defaults in isolation. | UAT Phase 5 step 4: run `deploy/restart.sh` on production (or staging). Review the deploy log output for: pre-restart API response with `initial_count`, connection polling with decreasing counts, "Drained to N connections" message, 2s grace period before restart. |
| AC4.3 | HAProxy drain blocks new arrivals during drain window | HAProxy interaction requires the production HAProxy socket and a real HAProxy instance. Cannot be tested in CI. | UAT Phase 5: during a deploy, attempt to open a new browser tab to the application URL after HAProxy drain but before restart. Verify the new request receives the 503 maintenance page (not a connection to the draining server). |
| AC5.1 | `memory_diagnostic` event emitted every 5 minutes | The periodic interval requires a long-running server. Unit tests verify the snapshot collection function; the 5-minute scheduling is a single `asyncio.sleep()` loop that is trivial but not worth a flaky timing test. | UAT Phase 6 steps 2-4: start the app (optionally reduce interval to 10s via code change), wait for the interval, then `tail -f test-debug.log \| jq 'select(.event == "memory_diagnostic")'`. Verify events appear at the expected cadence with all fields populated. |
| AC5.3 | Ported logic matches NiceGUI #5660 draft; swappable when upstream merges | This is a provenance and future-maintenance concern, not a functional property. No test can verify "code was ported correctly from another repo." | Code review: compare `src/promptgrimoire/diagnostics.py` against `nicegui/.worktrees/diagnostics-5660/nicegui/diagnostics.py`. Verify the TODO/docstring references #5660 and describes the swap path. |
