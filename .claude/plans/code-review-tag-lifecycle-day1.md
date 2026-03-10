# Code Review: Tag Lifecycle Refactor (Last Day's Commits)

**Branch:** `tag-lifecycle-235-291`
**Commits reviewed:** `a3ed7690..9bb77612` (10 commits) + uncommitted changes
**Reviewer:** Claude Opus 4.6
**Date:** 2026-03-09

## Executive Summary

Major refactor migrating tag ordering from a separate `tag_order` Map to inline `highlights` arrays within the `tags` Map entries. Also adds a `backfill-tags` CLI migration command, fixes clone workspace group_id remapping, and removes the defunct `import_tags_from_activity` function.

The refactor direction is sound and simplifies the CRDT data model. There is **1 Critical issue**, **2 High priority issues**, and several Medium items.

---

## Critical (Must Fix Before Merge)

### ~~C1: RETRACTED — Python 3.14 allows unparenthesised multi-except (PEP 758)~~

`except ValueError, KeyError:` is valid Python 3.14 syntax per [PEP 758](https://peps.python.org/pep-0758/) and correctly catches both exception types. Not a bug.

---

### C2 (now C1): `list_importable_workspaces` only sees ACL-granted workspaces, misses enrollment-derived access

**File:** `src/promptgrimoire/db/acl.py:515`

This was identified during the earlier debugging session but bears repeating as a review finding.

`list_importable_workspaces` calls `list_accessible_workspaces(user_id)` which only JOINs on `ACLEntry`. Template workspaces (created by `create_activity`) have no ACL entries — instructors access them via enrollment-derived permissions resolved in `resolve_permission()`.

**Impact:** In production, no instructor can see any template workspace in the import dropdown unless they happen to have an explicit ACL entry (e.g., from a share). The feature is non-functional for its primary use case.

**Fix:** `list_importable_workspaces` needs to build its candidate workspace set using enrollment-aware resolution, not just `list_accessible_workspaces`. Options:
1. Add a `list_enrollment_workspaces(user_id)` query and union with ACL results
2. Query template workspaces via `CourseEnrollment -> Week -> Activity -> Workspace` and merge with ACL-derived candidates

Do NOT modify `list_accessible_workspaces` itself — its contract (ACL-only) is used elsewhere and changing it has unpredictable blast radius.

---

## High Priority

### H1: Same-column reorder silently drops changes when tag not in tags Map

**File:** `src/promptgrimoire/pages/annotation/workspace.py:196-207`

```python
tag_data = state.crdt_doc.get_tag(target_tag)
if tag_data is not None:
    state.crdt_doc.set_tag(...)
ui.notify("Reordered", type="info")  # Always notifies, even if no-op
```

If `get_tag(target_tag)` returns `None` (e.g., for the "Untagged" pseudo-tag or any stale reference), the reorder is silently discarded but the user sees "Reordered". The old code wrote to `tag_order` which worked for any key. Now only tags in the `tags` Map can be reordered.

**Questions to resolve:**
- Can the "Untagged" column be reordered? Its `_UNTAGGED_RAW_KEY` probably isn't in the tags Map.
- Should this log a warning or raise?

### H2: `_remap_cloned_tag_highlights` iterates over `list_tags()` while mutating the CRDT

**File:** `src/promptgrimoire/db/workspaces.py:584-595`

```python
for tag_id, tag_data in doc.list_tags().items():
    ...
    doc.set_tag(...)  # Mutates the Map being iterated
```

`list_tags()` returns `dict(self.tags.items())` — a snapshot copy — so this is **safe** because the iteration is over the copy, not the live Map. But it's fragile: if anyone changes `list_tags()` to return a view instead of a copy, this breaks. Worth a comment.

---

## Medium Priority

### M1: Duplicate `set_tag` field-by-field pattern (DRY violation)

The pattern of reading `tag_data` fields and passing them individually to `set_tag()` appears in:
- `workspace.py:198-207` (same-column reorder)
- `workspaces.py:587-595` (`_remap_cloned_tag_highlights`)
- `tags.py:472-482` (`_sync_tag_order_index_to_crdt`)
- `annotation_doc.py:399-410` (`_update_tag_highlights`)

Each call manually copies `name`, `colour`, `order_index`, `group_id`, `description`, `highlights`. If a new field is added to the tag schema, all of these break silently. Consider `_update_tag_highlights` as the canonical "modify one field, preserve the rest" helper and use it consistently.

### M2: `_check_and_fix_workspace` drift fix is destructive — uses hydrate (full overwrite)

**File:** `src/promptgrimoire/cli/migrate.py:148-151`

When drift is detected, the fix calls `hydrate_tags_from_db()` which **overwrites** CRDT tag data with DB values. `hydrate_tags_from_db` is an upsert that preserves extra CRDT entries, but it replaces the `highlights` list for each tag with `[]` (from `_tags_to_dicts`, line 62). This means any highlight ordering stored in the CRDT `tags` Map will be **destroyed** by the migration.

For the initial backfill (empty CRDT), this is fine. For drift correction on workspaces that already have highlight ordering, this loses data.

**Recommendation:** Drift fix should merge only missing entries (which `_reconcile_crdt_with_db` already does correctly). The drift detection + hydrate path should use reconcile, not full hydrate.

### M3: WIP commit in history

**Commit:** `9f46d179 WIP: update clone_workspace to remap highlights in tags Map`

WIP commits should be squashed before merge. This one adds `_remap_cloned_tag_highlights` and `group_id_map` support — real code that should have a proper commit message.

### M4: Deleted test files without replacement

- `tests/integration/test_empty_template_tags.py` — 73 lines deleted
- `tests/integration/test_tag_management.py` — 67 lines deleted

Were the test cases in these files superseded by the new tests, or were they dropped? Need to verify coverage wasn't lost.

### M5: `_ensure_crdt_tag_consistency` called on every cached document access (uncommitted)

**File:** `src/promptgrimoire/crdt/annotation_doc.py:972-974` (uncommitted change)

```python
if doc_id in self._documents:
    doc = self._documents[doc_id]
    await _ensure_crdt_tag_consistency(doc, workspace_id)
    return doc
```

This fires `_ensure_crdt_tag_consistency` on **every** call to `get_or_create_for_workspace` when the document is already cached. That means 3 DB queries (list_tags + list_tag_groups + potential save) per page load/reconnect. The comment says "Re-sync with DB to pick up out-of-band updates (e.g. test seeds)" — this is test infrastructure leaking into production performance.

**Recommendation:** Either gate this behind a dev/test flag, or accept eventual consistency and only reconcile on initial load.

---

## Test Quality

### Good

- `test_migrate_backfill.py` — comprehensive: hydration, idempotency, drift detection, single-workspace filter, no-tags skip. Well structured.
- `test_export_fts_contracts.py` — good contract tests for the export and FTS pipelines.
- `test_tag_management_save.py` — properly tests model-dict based inputs with mocks.

### Concerns

- No test for C1 (the `except ValueError, KeyError` syntax). A test that triggers a KeyError during cleanup would have caught this.
- No test for H1 (same-column reorder of Untagged column).
- The `test_import_tags` test failure (the reason for this review session) is a test that correctly catches C2 — the production bug. Don't "fix" the test; fix the function.

---

## Checklist

### Before Merge (blockers)
- [ ] ~~**C1:** RETRACTED — PEP 758 (Python 3.14)~~
- [ ] **C2:** Fix `list_importable_workspaces` to include enrollment-derived workspaces
- [ ] **H1:** Decide on Untagged column reorder behaviour; at minimum, don't lie to the user with "Reordered" when nothing happened
- [ ] **M3:** Squash WIP commit

### Before Production
- [ ] **M2:** Fix drift correction to preserve highlight ordering
- [ ] **M5:** Remove or gate the per-access consistency check

### Future Work
- [ ] **M1:** Extract a canonical "update one field, preserve rest" helper for tag CRDT writes
- [ ] **M4:** Audit deleted test coverage

---

## Codex Peer Review Commentary

_Added 2026-03-09 from Codex review of the above findings. To be discussed once E2E tests are green._

1. **Important (C2 sharpening):** Claude's import-dropdown finding is correct, but the fix space in the review is still too loose. `list_importable_workspaces():493` is ACL-only today, while enrollment-derived readability lives in `_derive_enrollment_permission():257`. That derived path is not template-only; staff can read any workspace in the course context. So "query template workspaces via enrollment" is only a partial restatement of the real contract.

2. **Important (M2 under-ranked):** Claude's migration-drift finding is valid and under-ranked. In `_check_and_fix_workspace():146`, the drift fix uses `hydrate_tags_from_db()`, and `_tags_to_dicts():45` constructs every tag with `"highlights": []`. `hydrate_tags_from_db():609` overwrites matching CRDT tag entries, so a `--fix` run can wipe stored highlight ordering for drifted workspaces.

3. **High (H1 confirmed):** Claude's same-column reorder finding is real. In `_apply_sort_reorder_or_move():190`, reordering writes back only if `get_tag(target_tag)` returns a real tag. The untagged pseudo-column uses `raw_key=""` in `organise.py:45`, so same-column reorder there is a silent no-op followed by a false "Reordered" toast.

4. **Medium → drop (H2):** Claude's `_remap_cloned_tag_highlights()` concern is not a current bug. The loop in `workspaces.py:579` iterates over `doc.list_tags().items()`, and `list_tags():533` returns a snapshot `dict(...)`. The "this would break if someone later changed list_tags()" part is too speculative to justify a high-priority review finding.

5. **Medium → coverage audit only (M4):** Claude's "deleted test files without replacement" point is overstated. The removed tests were specifically for the deleted `import_tags_from_activity()` path, and replacement coverage exists for the new API in `TestImportTagsFromWorkspace:1866`, plus the UI path in `test_import_tags():418`. That is coverage churn worth auditing, not evidence of an uncovered feature hole by itself.

6. **Low (M5 scope):** Claude's cached-document consistency note is fair on the current uncommitted hunk, but it should have been scoped separately from the "yesterday" commit review. The cache-hit path in `get_or_create_for_workspace():955` now forces `_ensure_crdt_tag_consistency():891`, which is two reads on every hit and a write only if reconcile changes something. Real concern, wrong review scope.

7. **Low (M3):** The WIP-commit complaint is process-valid but not a product bug. The current history does contain a WIP: commit (`90fa2f4d`), so that note is fine as hygiene.

**Net recommendation:** Keep C2, H1, and M2. Drop H2 as non-issue, downgrade M4 to "coverage audit only," and treat M5 as an out-of-scope note on newer uncommitted work.

**Extra miss in current dirty tree:** `list_importable_workspaces():493` has already grown `is_privileged` and `enrolled_course_ids` parameters, but the implementation still builds candidates from ACL-only results and `tag_import.py:59` does not pass the new context. That's not a review of yesterday's commits, but it is the immediate gap in today's worktree.

_Note: The "extra miss" has since been fixed in commit `5e908dd3` — the implementation now uses a raw SQL query with three visibility paths and the caller passes both parameters._

---

## Verification Steps

1. `ruff check src/promptgrimoire/db/tags.py` — should flag the `except` syntax (may not, since it's valid Python 3 syntax, just wrong semantics)
2. `uv run grimoire test all` — run full suite after C1 fix
3. Manual test: create two activities in same course, add tags to one, open the other's template, verify import dropdown shows the source
4. After M5 decision: benchmark page load time with/without per-access consistency check
