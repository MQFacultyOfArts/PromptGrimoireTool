# Test Requirements

**Issue:** #316 — Navigator Metadata Search
**Design:** `docs/design-plans/2026-03-11-nav-metadata-search-316.md`
**Phases:** 2 (Phase 1: metadata FTS leg + tests; Phase 2: performance validation)

## Automated Tests

All automated tests are integration tests because they exercise `search_navigator()` against a live PostgreSQL instance via the existing `_search()` helper. Unit tests are not feasible here — the feature is a single SQL query leg, and mocking PostgreSQL FTS would not verify correctness. This matches the existing test pattern in `test_fts_search.py`.

| AC | Criterion | Test Type | Test Class | Test File |
|----|-----------|-----------|------------|-----------|
| AC1.1 | Owner `display_name` search returns their workspaces | Integration | `TestMetadataSearchOwnerName` | `tests/integration/test_fts_search.py` |
| AC2.1 | Activity title search returns workspaces under that activity | Integration | `TestMetadataSearchActivityTitle` | `tests/integration/test_fts_search.py` |
| AC3.1 | Week title search returns workspaces in that week | Integration | `TestMetadataSearchWeekTitle` | `tests/integration/test_fts_search.py` |
| AC4.1 | Course code search (e.g. "LAWS3100") returns workspaces in that unit | Integration | `TestMetadataSearchCourseCode` | `tests/integration/test_fts_search.py` |
| AC5.1 | Course name search (e.g. "Environmental Regulation") returns workspaces in that unit | Integration | `TestMetadataSearchCourseName` | `tests/integration/test_fts_search.py` |
| AC6.1 | Snippet contains `<mark>` tags around the matched metadata term | Integration | `TestMetadataSearchSnippetHighlight` | `tests/integration/test_fts_search.py` |
| AC7.1 | Document content FTS still returns correct results (regression) | Integration | `TestMetadataSearchRegressionDocumentContent` | `tests/integration/test_fts_search.py` |
| AC7.2 | CRDT `search_text` FTS still returns correct results (regression) | Integration | `TestMetadataSearchRegressionCRDTSearchText` | `tests/integration/test_fts_search.py` |
| AC8.1 | Metadata search across 1k visible workspaces completes within 2s | Integration | `TestMetadataSearchPerformance` | `tests/integration/test_fts_search.py` |
| AC9.1 | Orphan workspace (no activity/week/course) findable by owner name or title | Integration | `TestMetadataSearchOrphanWorkspace` | `tests/integration/test_fts_search.py` |
| — | Workspace title search returns matching workspace (implied by AC1-AC5 pattern) | Integration | `TestMetadataSearchWorkspaceTitle` | `tests/integration/test_fts_search.py` |

### Implementation Notes

**Helper function:** A new `_create_workspace_with_metadata()` async helper creates the full hierarchy (course, week, activity, workspace, owner ACL, document). Tests AC1-AC6 and AC9 use this helper; AC7.1 and AC7.2 reuse the existing `_create_owned_workspace_with_document()` helper since they verify the pre-existing FTS legs, not the new metadata leg.

**AC8.1 skip guard:** The performance test uses `pytest.skip()` when fewer than 1000 workspaces exist in the database. This prevents false failures in CI or dev environments without load data. The test requires prior execution of `uv run grimoire loadtest` to seed 1k+ workspaces. This is consistent with the existing pattern in `test_navigator_loader.py::TestScaleLoadTest`.

**AC7.1 and AC7.2 rationale:** These regression tests are technically redundant with the existing FTS tests already in `test_fts_search.py`. They are included explicitly because the Phase 1 implementation modifies `_SEARCH_SQL` — the shared SQL constant — so a targeted regression check against each existing leg confirms the UNION ALL modification did not break query parsing or result deduplication.

**AC9.1 approach:** Uses `_create_owned_workspace_with_document()` (not `_create_workspace_with_metadata()`) with a distinctive `title`, since orphan workspaces by definition lack the activity/week/course hierarchy. The test confirms LEFT JOINs produce NULLs without errors and that owner name or workspace title still match.

**No E2E tests.** The navigator search bar is a plain text input that calls `search_navigator()` server-side. The integration tests verify the database query directly. An E2E test would add Playwright overhead to confirm what is essentially a text-in, results-out function — the UI binding is trivial (existing search bar, existing result rendering). The existing E2E coverage of the search bar (`test_navigator.py`) implicitly exercises the rendering path.

## Human Verification

| AC | Criterion | Justification | Verification Approach |
|----|-----------|---------------|----------------------|
| AC6.1 | Snippet highlights are visually correct in the navigator UI | Automated test verifies `<mark>` tags in the snippet string, but cannot verify browser rendering (CSS styling, readability, truncation behaviour in the actual navigator card layout) | UAT step: search for a known course code in the running app, visually confirm the matched term is highlighted in the search result snippet. Check that long metadata strings do not overflow the result card. |
| AC8.1 | Performance is acceptable under real-world conditions | The automated test measures raw query latency in an isolated test database. Production has concurrent users, connection pool contention, and different PostgreSQL `work_mem`/`shared_buffers` settings that affect FTS performance | UAT step: with load data seeded (`uv run grimoire loadtest`), search for a common course code in the running app and subjectively assess response time. If noticeably slow (>1s perceived), investigate `EXPLAIN ANALYZE` on the metadata leg. |
| — | Snippet attribution is not confusing to users | Design acknowledges that concatenating all metadata into one string means `ts_headline` cannot indicate *which* field matched. This is a UX judgement call that cannot be automated | UAT step: search for terms that match different metadata fields (owner name, course code, activity title). Review the resulting snippets for clarity. If users cannot tell why a result matched, consider splitting into per-field UNION ALL legs (noted as future improvement in design). |
| — | Metadata search integrates correctly with ACL filtering | Integration tests create per-test users with explicit permissions. They do not test the interaction between metadata search and complex ACL scenarios (e.g., a student searching for an instructor's name should only see workspaces they have permission to view, not all workspaces owned by that instructor) | UAT step: log in as a student enrolled in one unit. Search for an instructor name who teaches multiple units. Verify results only include workspaces the student has access to, not workspaces from other units. |

### Rationale for Human Verification Scope

The design explicitly states "No schema changes, no new background worker logic, and no materialised index." This keeps the automated test surface small — the feature is a single SQL fragment inserted into an existing query. The human verification items above cover the gaps that SQL-level tests cannot: visual rendering, production-like performance, UX clarity of concatenated snippets, and ACL interaction under realistic multi-tenant conditions.

The ACL filtering concern is worth calling out specifically: the `visible_ws` CTE pre-filters workspaces, so metadata search inherits ACL enforcement. But the integration tests use privileged users or single-workspace scenarios — they do not exercise the case where metadata matches a workspace the user cannot see. A dedicated integration test for this could be added, but it would duplicate the existing `visible_ws` ACL tests in `test_navigator_loader.py`. Manual verification during UAT is sufficient.
