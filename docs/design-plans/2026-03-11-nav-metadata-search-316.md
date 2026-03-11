# Navigator Metadata Search Design

**GitHub Issue:** #316

## Summary

The navigator search bar currently queries only document content and CRDT-serialised annotations. It cannot match on contextual labels like who owns a workspace, which unit or week it belongs to, or what activity it sits under — so a user who remembers "it was in LAWS1000 Week 3" gets no results. This feature closes that gap.

The implementation adds a single new leg to the `UNION ALL` query inside the existing full-text search CTE in `db/navigator.py`. That leg LEFT-JOINs each workspace to its owner, activity, week, and course, concatenates their text fields into one string per workspace, and runs PostgreSQL's standard `to_tsvector` / `websearch_to_tsquery` machinery against that string. The same deduplication and snippet-ranking logic that already handles document content matches will then consider metadata matches fairly — the highest-ranked result per workspace wins, whether it came from document text or a metadata field. No schema changes, no new background worker logic, and no materialised index are required.

## Definition of Done

1. **Plain-text navigator search matches all metadata fields** — owner display name, activity title, week title, course code/name, and workspace title
2. **Snippets indicate what matched** — when a search matches metadata rather than document content, the snippet reflects the matched field
3. **Existing FTS unchanged** — document content and CRDT search_text still work as before
4. **Unit tests** cover each new search path (owner, activity, week, course, workspace title)

## Acceptance Criteria

### nav-metadata-search-316.AC1: Owner name search
- **nav-metadata-search-316.AC1.1 Success:** Searching for a term matching the owner's `display_name` returns their workspaces

### nav-metadata-search-316.AC2: Activity title search
- **nav-metadata-search-316.AC2.1 Success:** Searching for an activity title (or substring) returns workspaces under that activity

### nav-metadata-search-316.AC3: Week title search
- **nav-metadata-search-316.AC3.1 Success:** Searching for a week title returns workspaces in that week

### nav-metadata-search-316.AC4: Course code search
- **nav-metadata-search-316.AC4.1 Success:** Searching for a course code (e.g. "LAWS1000") returns workspaces in that unit

### nav-metadata-search-316.AC5: Course name search
- **nav-metadata-search-316.AC5.1 Success:** Searching for a course name (e.g. "Tort Law") returns workspaces in that unit

### nav-metadata-search-316.AC6: Snippet highlights matched metadata
- **nav-metadata-search-316.AC6.1 Success:** Snippet contains `<mark>` tags around the matched metadata term

### nav-metadata-search-316.AC7: Existing search regression
- **nav-metadata-search-316.AC7.1 Regression:** Document content FTS still returns correct results
- **nav-metadata-search-316.AC7.2 Regression:** CRDT search_text FTS still returns correct results

### nav-metadata-search-316.AC8: Performance at scale
- **nav-metadata-search-316.AC8.1 Performance:** Metadata search across 1k visible workspaces completes within acceptable latency

### nav-metadata-search-316.AC9: Orphan workspace handling
- **nav-metadata-search-316.AC9.1 Edge:** Workspace with no activity/week/course does not cause errors and is still findable by owner name or workspace title

## Glossary

- **Navigator**: The workspace listing page (`/`). Displays workspaces grouped by unit, week, and activity. The search bar at the top triggers `search_navigator()` in `db/navigator.py`.
- **`visible_ws` CTE**: A Common Table Expression that pre-filters workspaces to those the current user is permitted to see. All subsequent search legs filter against it rather than the full table.
- **`fts` CTE**: The full-text search Common Table Expression in `_SEARCH_SQL`. Currently has two `UNION ALL` legs — one for workspace document content, one for CRDT `search_text`. This feature adds a third.
- **`best_fts` CTE**: Downstream of `fts`; deduplicates by workspace, keeping the highest-ranked match across all legs.
- **GIN index**: A Generalized Inverted Index — PostgreSQL's index type for full-text search. The existing document and CRDT legs use GIN indexes; the new metadata leg does not (the pre-filtered row count is small enough).
- **`to_tsvector` / `websearch_to_tsquery`**: PostgreSQL functions that tokenise and stem text into a searchable vector, and parse a user query string into a query against that vector.
- **`ts_headline`**: PostgreSQL function that returns a snippet of the source text with matched terms wrapped in `<mark>` tags.
- **`ts_rank`**: PostgreSQL function that scores how well a `tsvector` matches a `tsquery`. Used to rank results and pick the best match per workspace.
- **CRDT / `search_text`**: Conflict-free Replicated Data Type state. A background `search_worker` periodically extracts human-readable text into `workspace.search_text`, which is FTS-indexed.
- **Activity**: A teaching task within a week — either an annotation activity or a wargame. Workspaces are created under activities.
- **Week / Course (Unit)**: The curriculum hierarchy above activity. A course has weeks; weeks have activities; activities have workspaces.

## Architecture

Add a single new UNION ALL leg to the `fts` CTE in `_SEARCH_SQL` (`src/promptgrimoire/db/navigator.py`). This leg concatenates all metadata fields for each visible workspace into one text value and runs FTS against it.

**Metadata fields concatenated:**
- `workspace.title` (workspace name)
- `"user".display_name` (owner name, via `workspace.owner_id`)
- `activity.title` (activity name, via `workspace.activity_id`)
- `week.title` (week name, via `activity.week_id`)
- `course.code` and `course.name` (unit identifiers, via `week.course_id`)

**Join chain:** `workspace w` → `"user" u` ON `w.owner_id = u.id` → `activity a` ON `w.activity_id = a.id` → `week wk` ON `a.week_id = wk.id` → `course c` ON `wk.course_id = c.id`. All joins are LEFT JOINs to handle workspaces missing activity/week/course.

**Concatenation:** `COALESCE(w.title, '') || ' ' || COALESCE(u.display_name, '') || ' ' || COALESCE(a.title, '') || ' ' || COALESCE(wk.title, '') || ' ' || COALESCE(c.code, '') || ' ' || COALESCE(c.name, '')`. This produces a single string per workspace for `to_tsvector()` and `ts_headline()`.

**Snippet behaviour:** `ts_headline()` on the concatenated string highlights whichever metadata field matched. The existing `best_fts` CTE deduplicates by workspace, keeping the highest `ts_rank()` — so metadata matches compete fairly with document content and CRDT search_text matches.

**No GIN index on metadata.** The `visible_ws` CTE pre-filters to workspaces the user can see. At 1k visible workspaces, computing `to_tsvector()` on ~100-char concatenated strings is approximately 100KB of text — fast enough without an index. Performance validated at 1k scale before closing (see acceptance criteria).

**No schema changes.** No Alembic migration. No search_worker changes.

## Existing Patterns

The new leg follows the exact structure of the two existing `fts` CTE legs:

1. SELECT `ws_id`, `ts_headline(...)` AS `snippet`, `ts_rank(...)` AS `rank`
2. FROM table(s) with joins
3. WHERE `ws_id IN (SELECT workspace_id FROM visible_ws)` AND `to_tsvector(...) @@ websearch_to_tsquery('english', :query)`

The concatenation approach mirrors how `search_worker.py` already concatenates `workspace.title` and `activity.title` into `search_text` (lines 86-88). This design extends the same idea to the query layer, covering all metadata fields without depending on the worker having run.

The `_HEADLINE_OPTIONS` constant (`MaxWords=35, MinWords=15, MaxFragments=3`) is reused unchanged. Metadata strings are short enough that `ts_headline` returns the full string with `<mark>` tags — no fragment truncation issues.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Add Metadata FTS Leg

**Goal:** Make all five metadata fields searchable via plain-text navigator search.

**Components:**
- `src/promptgrimoire/db/navigator.py` — add third UNION ALL leg to `fts` CTE in `_SEARCH_SQL`, joining workspace → user → activity → week → course and concatenating metadata fields
- Unit tests in `tests/unit/test_navigator_search.py` (or existing test file) — one test per metadata field verifying search returns the correct workspace with appropriate snippet

**Dependencies:** None

**Done when:**
- Searching for owner name, activity title, week title, course code, course name, or workspace title returns matching workspaces
- Snippet contains `<mark>` tags around the matched term
- Existing document content and CRDT search_text searches still work
- All unit tests pass
- Covers: nav-metadata-search-316.AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC9
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Performance Validation at Scale

**Goal:** Confirm search latency is acceptable with 1k visible workspaces.

**Components:**
- Performance test in `tests/integration/` — creates 1k workspaces with varied metadata, runs metadata search queries, asserts response time
- Uses existing test data infrastructure for bulk workspace creation

**Dependencies:** Phase 1

**Merge gate:** This phase gates the merge of Phase 1. If performance is unacceptable at 1k scale, Phase 1 does not ship — the fallback is materialising metadata into a new `search_metadata` column with a GIN index (requires Alembic migration and search_worker extension).

**Done when:**
- Metadata search across 1k visible workspaces completes within acceptable latency
- If latency is unacceptable, pivot to materialisation approach before merge
- Covers: nav-metadata-search-316.AC8
<!-- END_PHASE_2 -->

## Additional Considerations

**Partial coverage from search_worker:** The worker already prepends `workspace.title` and `activity.title` to `search_text`. After this change, those fields are searchable via both the worker-materialised path and the new metadata leg. This is harmless — `best_fts` deduplicates by workspace. No worker changes needed.

**Future: faceted search.** This design is plain-text only. Faceted search (`owner:Smith`, `activity:"Week 3"`) would require a query parser and conditional WHERE clauses. The concatenated metadata approach doesn't preclude faceted search — it could be added as a separate feature that bypasses FTS for specific field matches.

**Snippet attribution limitation.** Because all metadata fields are concatenated into a single string, `ts_headline()` cannot indicate *which* field matched — a snippet like `<mark>LAWS3100</mark> Introduction to Tort Law` doesn't distinguish whether the course code or course name was the match target. This is acceptable for MVP: the navigator row already displays the full metadata hierarchy (unit, week, activity, owner), so users can see context. If this proves confusing, the fix is to split into separate UNION ALL legs per field, which gives each leg its own snippet source.
