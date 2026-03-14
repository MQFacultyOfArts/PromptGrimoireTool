# Phase 1 Characterisation Test Audit

## Scope

- Audited the current worktree on 2026-03-14.
- `HEAD` is `f47b5868fbc8579eea5c501b736407a531701b32`.
- The worktree is dirty. Relevant delta: `tests/integration/test_respond_charac.py` has an uncommitted rename/docstring tweak relative to `HEAD`.
- Verified current behaviour on the live worktree:
  - `uv run grimoire test run tests/unit/test_card_functions.py tests/unit/test_annotation_doc.py` -> `113 passed in 0.51s`
  - `uv run grimoire test run tests/integration/test_annotation_cards_charac.py tests/integration/test_organise_charac.py tests/integration/test_respond_charac.py` -> `20 passed in 17.62s`

## Verdict

- `tests/unit/test_annotation_doc.py` is effective characterisation for `get_highlights_for_document()`.
- `tests/integration/test_organise_charac.py` and `tests/integration/test_respond_charac.py` do lock down the current `100`-character static truncation strongly enough that a Phase 2 switch to `80`-character expandable text would fail.
- The two most important claimed safeguards are not real yet:
  - `test_respond_shows_raw_author_to_viewer` does not enable anonymous sharing, so it will still pass after the intended Phase 2 bugfix.
  - No Phase 1 test currently characterises `cards_epoch` or any diff-based incremental card update semantics.

## Highest-Severity Findings

### 1. Critical: the Respond anonymisation characterisation test will not fail when `respond.py` is fixed

The key test is `tests/integration/test_respond_charac.py:324`. Its core assertion is:

```python
assert found_raw_author
```

with the failure text:

```python
"a different viewer with anonymous_sharing=True ..."
```

at `tests/integration/test_respond_charac.py:376`.

That claim is inconsistent with the setup:

- The course helper calls `create_course(code, name, semester)` without setting anonymous sharing at `tests/integration/test_respond_charac.py:50`, and `create_course()` only populates those three fields at `src/promptgrimoire/db/courses.py:26`.
- `Course.default_anonymous_sharing` defaults to `False` at `src/promptgrimoire/db/models.py:164`.
- The activity helper calls `create_activity(week_id, title)` at `tests/integration/test_respond_charac.py:90`, and `create_activity()` does not expose or set `anonymous_sharing` at `src/promptgrimoire/db/activities.py:24`.
- Placement context resolves `activity.anonymous_sharing` against `course.default_anonymous_sharing` at `src/promptgrimoire/db/workspaces.py:342`.
- The annotation page copies that into `state.is_anonymous` at `src/promptgrimoire/pages/annotation/workspace.py:415`.
- `anonymise_author()` returns the real author whenever `anonymous_sharing` is false at `src/promptgrimoire/auth/anonymise.py:78`.

So:

- Yes, the viewer is a genuinely different user. The test creates `viewer_email`, grants explicit `viewer` ACL, and opens the page as that viewer at `tests/integration/test_respond_charac.py:348`, `tests/integration/test_respond_charac.py:358`, and `tests/integration/test_respond_charac.py:361`.
- Yes, the viewer enters the real annotation-page code path that would call `anonymise_author()` if `respond.py` used it.
- No, this test would not fail merely because `respond.py` changed from:

```python
ui.label(f"by {author}")
```

at `src/promptgrimoire/pages/annotation/respond.py:155` to a normal `anonymise_author(...)` call, because the test setup leaves `state.is_anonymous == False`.

This means the coverage doc overstates the protection at `docs/implementation-plans/2026-03-14-multi-doc-tabs-186-plan-a/phase_01_coverage.md:88` and `:105`.

### 2. Critical: there is no real `cards_epoch` or diff-update characterisation yet

The coverage doc claims:

- `_build_expandable_text` 80-char threshold at `phase_01_coverage.md:27`
- ``cards_epoch` incremented after rendering` at `phase_01_coverage.md:28`
- AC12/diff-based update protection in the new integration suites at `tests/integration/test_annotation_cards_charac.py:11`, `tests/integration/test_organise_charac.py:10`, and `tests/integration/test_respond_charac.py:10`

But the actual annotate implementation only increments/publishes epoch inside the refresh path:

```python
state.cards_epoch += 1
ui.run_javascript(f"window.__annotationCardsEpoch = {state.cards_epoch}")
```

at `src/promptgrimoire/pages/annotation/cards.py:604`.

None of the new tests ever read `state.cards_epoch`, `window.__annotationCardsEpoch`, or perform a second render after a CRDT mutation. The new suites all follow the same pattern:

- seed CRDT state before opening the page
- open once
- assert a static DOM snapshot

Examples:

- `tests/integration/test_annotation_cards_charac.py:272`
- `tests/integration/test_organise_charac.py:269`
- `tests/integration/test_respond_charac.py:257`

Even the new E2E flow tests mutate on Annotate and only then navigate to Organise/Respond (`tests/e2e/test_organise_respond_flow.py:73` and `:127`), which exercises initial render after navigation, not live incremental update of an already-rendered card list.

So the answer to the Phase 5 question is: no, these tests do not depend on rebuild semantics and they would not detect a missing epoch bump.

### 3. Important: the Annotate truncation test does not actually pin the `80`-character boundary

`tests/integration/test_annotation_cards_charac.py:303` is meant to lock down `_build_expandable_text()` from `src/promptgrimoire/pages/annotation/cards.py:44`.

The current implementation truncates at exactly `80`:

```python
truncated_text = full_text[:80] + "..."
```

at `src/promptgrimoire/pages/annotation/cards.py:48`.

But the test only checks for any visible descendant with quotes and an ellipsis:

```python
if "..." in text_val and text_val.startswith('"'):
    return True
```

at `tests/integration/test_annotation_cards_charac.py:333`.

It never asserts the actual length, the actual threshold, or the actual truncated payload. If Phase 3 or Phase 5 changed Annotate from `80` to `100`, this test would still pass because the seeded text is `120` characters long and would still render with `...`.

That makes `phase_01_coverage.md:27` too strong. The test proves “long text is truncated somewhere”, not “the shared widget truncates at 80”.

### 4. Important: the Organise anonymisation test is vacuous for the behaviour it claims

`tests/integration/test_organise_charac.py:386` is described as:

```python
"""Author display uses anonymise_author (own name shown)."""
```

Its operative check is:

```python
if f"by {user_name}" in str(desc.text):
    found_author = True
```

at `tests/integration/test_organise_charac.py:400`.

This does not distinguish between:

- the current correct code path, which calls `anonymise_author(...)` in `src/promptgrimoire/pages/annotation/organise.py:110`, and
- a broken implementation that simply rendered the raw author string directly.

Why: `anonymise_author()` deliberately returns the real author when viewing your own highlight at `src/promptgrimoire/auth/anonymise.py:84`.

So `phase_01_coverage.md:48` overstates what this test proves. It only proves “the author sees their own name”, not “Organise calls `anonymise_author()`”.

## Direct Answers by File

### `tests/unit/test_card_functions.py`

- `_author_initials()` tests are effective for current pure behaviour.
- `anonymise_author()` tests mostly cover the utility well, but `test_other_user_anonymised` (`tests/unit/test_card_functions.py:97`) is still broad: `assert result != "Alice Smith"` plus `assert " " in result` would allow many incorrect pseudonym formats.
- `group_highlights_by_tag()` is only partially characterised. `test_multiple_tags` (`tests/unit/test_card_functions.py:176`) checks bucket counts, not that the correct highlight text landed in the correct bucket, and it does not assert ordering.
- Phase 3 extraction caveat: this file imports the functions from their current modules at `tests/unit/test_card_functions.py:17` and `:18`. Moving them to `card_shared.py` without compatibility re-exports will break imports mechanically even if behaviour is unchanged.

### `tests/unit/test_annotation_doc.py`

- Effective.
- `test_filters_by_document_id`, `test_ordered_by_start_char`, `test_no_cross_contamination`, and `test_highlights_without_document_id_excluded` at `tests/unit/test_annotation_doc.py:1462`, `:1487`, `:1513`, and `:1557` directly bind to `get_highlights_for_document()` at `src/promptgrimoire/crdt/annotation_doc.py:365`.
- These should fail on the document-filtering regressions that Phase 7 would risk.

### `tests/integration/test_annotation_cards_charac.py`

- Effective for: initial card count, DOM ordering by `start_char`, comment-count badge presence, locate button presence, expand button presence, and collapsed-by-default detail state.
- Not effective for: exact `80`-character threshold, tag label rendering, `cards_epoch`, or diff-based update semantics.

### `tests/integration/test_organise_charac.py`

- Effective for the planned Phase 2 truncation change. `test_snippet_truncated_at_100_chars` asserts:

```python
assert len(inner) == 103
```

at `tests/integration/test_organise_charac.py:300`, so switching to `80 + "..."` will fail.
- Effective for short-text non-truncation, locate-button presence, comment visibility, and tag-column existence.
- Not effective for proving `anonymise_author()` is actually called.

### `tests/integration/test_respond_charac.py`

- Effective for the planned Phase 2 truncation change. `test_snippet_truncated_at_100_chars` asserts:

```python
assert len(inner) == 103
```

at `tests/integration/test_respond_charac.py:283`, so switching to `80 + "..."` will fail.
- Effective for locate-button presence, comment visibility, and tag-group existence.
- Not effective for locking down the raw-author bug, for the reasons in Finding 1.

### `tests/e2e/test_organise_respond_flow.py`

- Effective as a broad smoke test for cross-tab propagation of one highlight and one comment.
- Not effective as characterisation for truncation, anonymisation, ordering, grouping correctness, or diff-based updates. `test_highlight_appears_across_all_three_tabs` only proves that one highlight text is visible after tab switches at `tests/e2e/test_organise_respond_flow.py:98`.

## Vacuous or Over-Broad Assertions

- `tests/integration/test_annotation_cards_charac.py:333` only checks for any quoted text containing `...`.
- `tests/integration/test_organise_charac.py:400` proves own-name display, not `anonymise_author()` usage.
- `tests/unit/test_card_functions.py:188` and `:189` only check bucket lengths in `test_multiple_tags`, not highlight identity.
- `tests/integration/test_respond_charac.py:376` claims an `anonymous_sharing=True` boundary that the setup never creates.

## Isolation Assessment

- Test state is well isolated overall.
- Each integration test creates a fresh course/activity/workspace; course codes are unique via `uuid4()` in `tests/integration/test_annotation_cards_charac.py:51`, `tests/integration/test_organise_charac.py:47`, and `tests/integration/test_respond_charac.py:48`.
- Per-test student emails are distinct enough for xdist. Reuse of `coordinator@uni.edu` is not a collision problem because courses/workspaces are unique and `find_or_create_user()` is expected to reuse the same user safely.
- The CRDT setup matches what production code reads:
  - Annotate tests populate `document_id=str(document_id)` at `tests/integration/test_annotation_cards_charac.py:193`, and `cards.py` filters via `get_highlights_for_document(str(state.document_id))` at `src/promptgrimoire/pages/annotation/cards.py:585`.
  - Organise/Respond tests populate real tags/comments in the CRDT registry, and production reads them from `get_all_highlights()` in `src/promptgrimoire/pages/annotation/organise.py:283` and `src/promptgrimoire/pages/annotation/respond.py:88`.
- Remaining isolation/flakiness risk: both tab-open helpers still use bare sleeps:
  - `await asyncio.sleep(0.3)` in `tests/integration/test_organise_charac.py:256`
  - `await asyncio.sleep(0.3)` in `tests/integration/test_respond_charac.py:243`

These are not order-dependence bugs, but they are still timing guesses and violate the project’s stated testing standard.

## Cross-User Anonymisation Assessment

- Different authenticated user: yes.
- Correct viewer code path: yes. The test goes through the real `/annotation` access path and the real Respond tab rendering path.
- Would the assertion fail if `respond.py` started using `anonymise_author()` today: no.
- Why not: the test never enables anonymous sharing, so the expected output of a correct `anonymise_author()` call is still the raw author name.

## Highest-Risk Gaps for Phases 2-7

1. No test exercises add/remove/change on already-rendered cards or asserts `cards_epoch`. This is the biggest missing guardrail for Phase 5.
2. No valid anonymous-sharing viewer scenario exists in the integration suites. Both `phase_01_coverage.md:48` and `:88` overstate anonymisation coverage.
3. Annotate’s shared expandable-text widget is not pinned to the `80`-character boundary, despite `phase_01_coverage.md:27`.
4. There is still no integration or E2E test proving document-scoped Annotate filtering versus aggregate Organise/Respond rendering in a multi-document workspace. `phase_01_coverage.md:136` acknowledges this gap, and it remains high risk for Phase 7.
5. The current characterisation tests only check locate-button presence in Organise/Respond (`tests/integration/test_organise_charac.py:334` and `tests/integration/test_respond_charac.py:291`), not the cross-document locate behaviour that later phases will change.

## Coverage-Doc Accuracy

`phase_01_coverage.md` is directionally useful, but it is not fully accurate about what is actually locked down.

Accurate omissions:

- Multi-document filtering gap at `phase_01_coverage.md:136`
- Concurrent-editing/diff-update gap at `phase_01_coverage.md:137`

Overstatements:

- `_build_expandable_text` `80`-char threshold at `phase_01_coverage.md:27`
- `cards_epoch` coverage at `phase_01_coverage.md:28`
- Tag-name-on-header coverage at `phase_01_coverage.md:29`
- Organise `anonymise_author()` coverage at `phase_01_coverage.md:48`
- Respond raw-author bug lock-in at `phase_01_coverage.md:88`
- “Full cross-tab content consistency” at `phase_01_coverage.md:71`
