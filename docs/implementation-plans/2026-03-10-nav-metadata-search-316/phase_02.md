# Navigator Metadata Search Implementation Plan — Phase 2

**Goal:** Validate that metadata search performs acceptably at scale (1k visible workspaces).

**Architecture:** Performance test that queries pre-seeded load data, measuring wall-clock latency of metadata search. Follows the existing scale test pattern in `test_navigator_loader.py` which requires `cli_loadtest.py` seeding and skips when insufficient data is present.

**Tech Stack:** pytest, `time.monotonic()`, PostgreSQL FTS.

**Scope:** 2 phases from original design (phase 2 of 2).

**Codebase verified:** 2026-03-11

---

## Acceptance Criteria Coverage

This phase implements and tests:

### nav-metadata-search-316.AC8: Performance at scale
- **nav-metadata-search-316.AC8.1 Performance:** Metadata search across 1k visible workspaces completes within acceptable latency

---

<!-- START_TASK_1 -->
### Task 1: Performance test for metadata search at 1k scale

**Verifies:** nav-metadata-search-316.AC8.1

**Files:**
- Modify: `tests/integration/test_fts_search.py` — add `TestMetadataSearchPerformance` class

**Verified helper signature:** `_search(query: str, user_id: UUID, *, is_privileged: bool = False, enrolled_course_ids: list[UUID] | None = None) -> list[SearchHit]` (lines 92-107 of `test_fts_search.py`). The call below matches this signature.

**Implementation:**

Add a performance test class to `tests/integration/test_fts_search.py` that:

1. Counts visible workspaces for a privileged user (query the database for total workspace count)
2. Skips with `pytest.skip("Insufficient load data — run cli_loadtest first")` if count < 1000
3. Runs a metadata search query (e.g., searching for a common course code from the seeded data like "LAWS1100")
4. Measures wall-clock latency using `time.monotonic()`
5. Asserts latency < 2.0 seconds

Follow the existing pattern from `tests/integration/test_navigator_loader.py:998-1072` (`TestScaleLoadTest::test_instructor_query_at_scale`):

```python
import time

class TestMetadataSearchPerformance:
    """Metadata search latency at 1k-workspace scale."""

    @pytest.mark.asyncio
    async def test_metadata_search_latency_at_scale(self) -> None:
        """Metadata search across 1k+ visible workspaces completes in <2s."""
        # Count workspaces to guard against missing load data
        async with get_session() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM workspace"))
            ws_count = result.scalar_one()

        if ws_count < 1000:
            pytest.skip(
                f"Only {ws_count} workspaces — run `uv run grimoire loadtest` first"
            )

        # Find a privileged user from load data (instructor)
        async with get_session() as session:
            result = await session.execute(
                text("""
                    SELECT u.id FROM "user" u
                    JOIN course_enrollment ce ON ce.user_id = u.id
                    JOIN course_role cr ON cr.name = ce.role
                    WHERE cr.is_staff = true
                    LIMIT 1
                """)
            )
            row = result.one_or_none()
            if row is None:
                pytest.skip("No staff user found in load data")
            instructor_id = row[0]

        # Get enrolled course IDs for this instructor
        async with get_session() as session:
            result = await session.execute(
                text("""
                    SELECT ce.course_id FROM course_enrollment ce
                    WHERE ce.user_id = :uid
                """),
                {"uid": instructor_id},
            )
            enrolled_ids = [r[0] for r in result.all()]

        # Measure metadata search latency
        start = time.monotonic()
        results = await _search(
            "LAWS",  # Common prefix in seeded course codes
            instructor_id,
            is_privileged=True,
            enrolled_course_ids=enrolled_ids,
        )
        elapsed = time.monotonic() - start

        assert len(results) > 0, "Expected metadata search to return results"
        assert elapsed < 2.0, (
            f"Metadata search took {elapsed:.2f}s (threshold: 2.0s) "
            f"across {ws_count} workspaces"
        )
```

**Key details:**
- Uses `_search()` helper already defined in the file
- Searches for "LAWS" which matches course codes from `cli_loadtest.py` seeded data (LAWS1100, LAWS2200)
- Uses privileged instructor to see all workspaces (maximum FTS workload)
- 2.0s threshold — tighter than the existing 5.0s navigator query threshold since metadata strings are short (~100 chars)
- Skip guard prevents false failures in environments without load data

**Merge gate note:** If this test fails consistently (metadata search > 2s at 1k scale), Phase 1 does not ship. The fallback (per design) is materialising metadata into a new `search_metadata` column with a GIN index, requiring an Alembic migration and search_worker extension.

**Verification:**

Run: `uv run grimoire loadtest` (if not already seeded)
Then: `uv run grimoire test run tests/integration/test_fts_search.py -k metadata_scale`
Expected: Test passes with latency well under 2.0s

Run: `uv run grimoire test all`
Expected: Full suite passes (test skips gracefully if no load data)

**Commit:** `test: add metadata search performance test at 1k scale (#316)`

## UAT Steps

1. [ ] Seed load data: `uv run grimoire loadtest`
2. [ ] Run performance test: `uv run grimoire test run tests/integration/test_fts_search.py -k metadata_scale`
3. [ ] Verify: test passes with reported latency well under 2.0s
4. [ ] If test fails: report latency and discuss materialisation fallback

## Evidence Required

- [ ] Performance test output showing pass with latency figure
- [ ] If latency > 2s: decision on fallback approach documented
<!-- END_TASK_1 -->
