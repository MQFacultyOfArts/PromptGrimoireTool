# EXPLAIN ANALYZE Results — Navigator Query

Generated: 2026-02-25
Dataset: Phase 2 load-test data (~1100 students, 2 courses, ~2200 workspaces)

## Summary

| Scenario | Planning | Execution | Total | Seq Scans |
|----------|----------|-----------|-------|-----------|
| 1. Student first page | 2.3ms | 9.7ms | 12.0ms | week (12 rows), course (2 rows) |
| 2. Student second page | 1.5ms | 5.4ms | 6.9ms | week (12 rows), course (2 rows) |
| 3. Instructor first page | 1.7ms | 18.4ms | 20.1ms | None |
| 4. Instructor second page | 1.5ms | 18.8ms | 20.3ms | None |
| 5. Multi-enrolled student (2 courses) | 1.6ms | 7.0ms | 8.6ms | week (12 rows), course (2 rows) |

**All queries under 35ms** — well within the 200ms acceptance threshold.

## Sequential Scans

Sequential scans appear only on `week` (12 rows) and `course` (2 rows). These are tiny lookup tables where sequential scan is optimal — PostgreSQL correctly prefers seq scan over index scan when the table fits in a single page. No seq scans on large tables (workspace, acl_entry, user).

**No additional indexes needed.**

## Index Usage

Key indexes confirmed in use:
- `ix_acl_entry_user_id` — Bitmap Index Scan for "find my workspaces" (section 1)
- `workspace_pkey` — Index Scan for workspace lookups
- `activity_template_workspace_id_key` — Index Scan for template exclusion anti-join
- `user_pkey` — Index Scan for owner display name lookups
- `ix_workspace_activity_id` — Index Scan for workspace-to-activity
- `uq_acl_entry_workspace_user` — Index Scan for ACL permission checks

## Observations

- **Instructor queries (18ms)** are ~2x student queries (7-10ms) because `is_privileged=true` disables the `shared_with_class` filter, returning all student workspaces in the course (~1100 rows scanned before LIMIT).
- **Second page** is faster than first page for students (5.4ms vs 9.7ms) because the cursor WHERE clause skips earlier sections entirely.
- **Top-N heapsort** used for the final sort (76kB memory) — efficient for LIMIT 51 over ~1100 candidate rows.
- **All buffer hits are shared** (no disk reads) — data is fully cached. Production cold-cache performance may be ~2x slower on first query.

## Test Parameters

```
Student: loadtest-1@test.local (enrolled in LT-LAWS1100 + LT-LAWS2200)
Instructor: lt-instructor-torts@test.local (enrolled in LT-LAWS1100)
Page size: 51 (limit + 1 for next-page detection)
```
