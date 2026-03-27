# Test Requirements: Annotation Deferred Load (#377)

## Automated Tests

| AC | Criterion | Test Type | Test File | Implementation Phase |
|----|-----------|-----------|-----------|---------------------|
| AC1.1 | `annotation_page()` handler completes in <50ms (responseEnd via Performance API) | E2E | `tests/e2e/test_browser_perf_377.py` (update existing) | Phase 4, Task 4 |
| AC1.2 | Loading spinner visible before DB work begins (`workspace-loading-spinner` visible before `__loadComplete`) | E2E | `tests/e2e/test_deferred_load.py` | Phase 2, Task 4 |
| AC2.1 | `resolve_annotation_context()` executes in a single DB session | Integration | `tests/integration/test_annotation_context.py` | Phase 1, Task 5 |
| AC2.2 | Workspace row fetched exactly once per page load (verified by query count or mock) | Integration | `tests/integration/test_annotation_context.py` | Phase 1, Task 5 |
| AC2.3 | Activity -> Week -> Course hierarchy resolved via JOIN, not sequential selects | Integration | `tests/integration/test_annotation_context.py` | Phase 1, Task 5 |
| AC2.4 (activity-placed) | Correct results for activity-placed workspace: `placement_type == "activity"`, correct course_code, week_number, activity_title | Integration | `tests/integration/test_annotation_context.py` | Phase 1, Task 5 |
| AC2.4 (course-placed) | Correct results for course-placed workspace: `placement_type == "course"`, correct course fields, no activity/week | Integration | `tests/integration/test_annotation_context.py` | Phase 1, Task 5 |
| AC2.4 (standalone) | Correct results for standalone workspace: `placement_type == "loose"`, all hierarchy fields None | Integration | `tests/integration/test_annotation_context.py` | Phase 1, Task 5 |
| AC2.4 (template, activity-placed) | `placement.is_template == True` when `activity.template_workspace_id == workspace_id` | Integration | `tests/integration/test_annotation_context.py` | Phase 1, Task 5 |
| AC2.4 (template, standalone) | `placement.is_template == True` via reverse lookup for standalone workspace referenced as template | Integration | `tests/integration/test_annotation_context.py` | Phase 1, Task 5 |
| AC2.4 (nonexistent) | Returns `None` for nonexistent workspace_id | Integration | `tests/integration/test_annotation_context.py` | Phase 1, Task 5 |
| AC2.4 (permission) | `context.permission` matches ACL entry; admin bypass returns `"owner"` | Integration | `tests/integration/test_annotation_context.py` | Phase 1, Task 5 |
| AC2.4 (privileged users) | `context.privileged_user_ids` contains staff user IDs as strings | Integration | `tests/integration/test_annotation_context.py` | Phase 1, Task 5 |
| AC2.4 (tags) | `context.tags` and `context.tag_groups` match DB records in order | Integration | `tests/integration/test_annotation_context.py` | Phase 1, Task 5 |
| AC2.5 (CRDT registry) | `get_or_create_for_workspace(workspace_id, workspace=ws)` hydrates from pre-fetched workspace without redundant fetch | Integration | `tests/integration/test_crdt_prefetch.py` | Phase 1, Task 6 |
| AC2.5 (CRDT tag consistency) | `_ensure_crdt_tag_consistency(doc, ws_id, tags=..., tag_groups=...)` uses pre-fetched data, skips internal DB fetch | Integration | `tests/integration/test_crdt_prefetch.py` | Phase 1, Task 6 |
| AC2.5 (backward compat) | Both CRDT functions work unchanged when called without new kwargs | Integration | `tests/integration/test_crdt_prefetch.py` | Phase 1, Task 6 |
| AC3.1 | After background task completes, spinner hidden and workspace content visible | E2E | `tests/e2e/test_deferred_load.py` | Phase 2, Task 4 |
| AC3.2 | On background task failure (invalid workspace_id), error notification appears and spinner hidden | E2E | `tests/e2e/test_deferred_load.py` | Phase 2, Task 4 |
| AC4.1 | No `logging.getLogger(__name__).setLevel()` calls in `src/promptgrimoire/` | Unit | `tests/unit/test_setlevel_guard.py` | Phase 3, Task 2 |
| AC4.2 | `logger.debug()` produces output when structlog configured at DEBUG level (not suppressed by stdlib level gate) | Unit | `tests/unit/test_structlog_debug_output.py` | Phase 3, Task 3 |
| AC6.1 | `uv run grimoire test all` passes (3,573+ tests) | Full suite | N/A (run existing suite) | Phase 4, Task 2 |
| AC6.2 | `grimoire e2e perf` shows responseEnd improvement (before/after documented) | E2E | `tests/e2e/test_browser_perf_377.py` (update existing) | Phase 4, Tasks 3-4 |

## Human Verification

| AC | Criterion | Why Not Automated | Verification Approach |
|----|-----------|-------------------|----------------------|
| AC1.3 | NiceGUI "Response not ready after 3.0 seconds" warning does not appear under normal conditions | The warning is emitted by NiceGUI internals to stderr/stdout with timing dependent on server load and connection latency. Reliably asserting its absence in CI is fragile -- the warning is a symptom of slow response, not a deterministic output. A false negative (warning not appearing due to fast CI hardware) would make the test vacuous. | During Phase 4 perf measurement, manually inspect server logs (`journalctl` or terminal output) during `grimoire e2e perf` runs. Confirm no "Response not ready" warnings appear. Document presence/absence in the #377 results comment. |
| AC3.3 | Client disconnect during DB work cancels background task via `on_disconnect` handler + `client._deleted` guard | NiceGUI's `on_disconnect` fires on WebSocket closure, which Playwright cannot reliably simulate mid-background-task. Forcing a disconnect at the exact moment the background task is between yield points is non-deterministic. The belt-and-suspenders pattern (`on_disconnect` + `_deleted` guard) has two independent mechanisms, neither of which can be reliably exercised under test timing constraints. | Code review during PR: (1) verify `client.on_disconnect(lambda: task.cancel())` is wired in the page handler, (2) verify `if client._deleted: return` guards exist at yield points in `_load_workspace_content()`. Both patterns are structural and can be confirmed by reading the diff. |
| AC5.1 | Only `__init__.py` and `workspace.py` modified in `pages/annotation/` | This is a constraint on the changeset, not on runtime behavior. It describes which files the PR diff should touch, not what the code does. | Verify via `git diff main --name-only -- src/promptgrimoire/pages/annotation/` during PR review. Only `__init__.py` and `workspace.py` should appear. |
| AC5.2 | `cards.py`, `document.py`, `highlights.py`, `organise.py`, `respond.py`, `tab_bar.py` are unchanged | Same as AC5.1 -- constraint on the changeset. Note: Phase 3 modifies `organise.py` and `respond.py` to remove `setLevel` lines, but that is a mechanical logging cleanup, not an annotation UI logic change. The AC intent is that annotation UI behavior in these modules is not altered. | Verify via `git diff main -- src/promptgrimoire/pages/annotation/` during PR review. Changes to `organise.py`, `respond.py` etc. should be limited to `setLevel` removal (Phase 3). No logic changes. |
| AC6.2 (documentation) | Before/after comparison documented on issue #377 | The comparison requires human judgment to interpret timing numbers in context (CI variability, baseline conditions, whether improvement is meaningful). | Post before/after table as a comment on GitHub issue #377 (Phase 4, Task 5). Include responseEnd, page_load_total, resolve_step, render_phase, and "Response not ready" status. |
