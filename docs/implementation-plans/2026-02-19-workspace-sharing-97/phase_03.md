# Workspace Sharing & Visibility — Phase 3: CRDT User Identity & Comments

**Goal:** User identity on annotations/comments, anonymisation utility, and comment UI with ownership-gated deletion.

**Architecture:** `user_id` field added to highlight and comment dicts alongside existing `author` display name. Anonymisation utility as a pure function in `auth/anonymise.py`. Comment delete ownership guard at the CRDT layer (defense-in-depth). `PageState` extended with `user_id`.

**Tech Stack:** pycrdt, NiceGUI, Python hashlib (for deterministic anonymisation)

**Scope:** 7 phases from original design (phase 3 of 7)

**Codebase verified:** 2026-02-19

**Dependencies:** Phase 1 (model fields), Phase 2 (peer permission path for testing context)

---

## Acceptance Criteria Coverage

This phase implements and tests:

### workspace-sharing-97.AC3: Annotation comments
- **workspace-sharing-97.AC3.1 Success:** User can add flat reply to any highlight
- **workspace-sharing-97.AC3.2 Success:** Multiple replies on same highlight shown chronologically
- **workspace-sharing-97.AC3.3 Success:** Comment stored with user_id, author display name, text, timestamp
- **workspace-sharing-97.AC3.4 Success:** Comment creator can delete own comment
- **workspace-sharing-97.AC3.5 Success:** Workspace owner can delete any comment
- **workspace-sharing-97.AC3.7 Edge:** Existing highlights without user_id display 'Unknown' for instructors

### workspace-sharing-97.AC4: Anonymity control
- **workspace-sharing-97.AC4.3 Success:** Instructor always sees true author regardless of anonymity flag
- **workspace-sharing-97.AC4.4 Success:** Owner viewing own workspace sees true author names
- **workspace-sharing-97.AC4.5 Success:** Peer sees own annotations with real name, others' with anonymised label
- **workspace-sharing-97.AC4.6 Success:** Anonymised labels are adjective-animal names deterministic per user_id (stable across sessions and page reloads)

### workspace-sharing-97.AC1: Peer permission level
- **workspace-sharing-97.AC1.5 Success:** Peer can delete own comments
- **workspace-sharing-97.AC1.8 Failure:** Peer cannot delete others' comments

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Add `user_id` to PageState and thread through highlight/comment creation

**Verifies:** workspace-sharing-97.AC3.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/__init__.py:174` (PageState — add `user_id` field)
- Modify: `src/promptgrimoire/pages/annotation/workspace.py:671-674` (pass `user_id` to PageState constructor)
- Modify: `src/promptgrimoire/crdt/annotation_doc.py:216` (`add_highlight` — add `user_id` parameter)
- Modify: `src/promptgrimoire/crdt/annotation_doc.py:246` (highlight dict — add `user_id` key)
- Modify: `src/promptgrimoire/crdt/annotation_doc.py:432` (`add_comment` — add `user_id` parameter)
- Modify: `src/promptgrimoire/crdt/annotation_doc.py:457` (comment dict — add `user_id` key)
- Modify: `src/promptgrimoire/pages/annotation/highlights.py:242` (pass `user_id=state.user_id` to `add_highlight`)
- Modify: `src/promptgrimoire/pages/annotation/cards.py:94` (pass `user_id=state.user_id` to `add_comment`)

**Implementation:**

1. Add `user_id: str | None = None` field to `PageState` dataclass (after `user_name` line 174).

2. In `workspace.py` PageState construction (line 671), pass `user_id`:
   ```python
   user_id=str(auth_user.get("user_id", "")) if auth_user else None
   ```

3. In `annotation_doc.py`, add `user_id: str | None = None` parameter to `add_highlight()` and `add_comment()` signatures. Add `"user_id": user_id` to both dicts. Parameters are optional with default `None` for backwards compatibility (existing callers without `user_id` still work).

4. In `highlights.py` line 242, add `user_id=state.user_id` to the `add_highlight()` call.

5. In `cards.py` line 94, add `user_id=state.user_id` to the `add_comment()` call.

**Testing:**

Unit tests for `add_highlight` and `add_comment` verifying `user_id` is stored in the dict. Follow existing CRDT test patterns.

- AC3.3: Comment dict contains `user_id`, `author`, `text`, `created_at` fields
- Backwards compat: calling `add_highlight()` without `user_id` stores `None`

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `feat(crdt): add user_id to highlight and comment dicts`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add comment delete ownership guard

**Verifies:** workspace-sharing-97.AC3.4, workspace-sharing-97.AC3.5, workspace-sharing-97.AC1.5, workspace-sharing-97.AC1.8

**Files:**
- Modify: `src/promptgrimoire/crdt/annotation_doc.py:475-507` (`delete_comment` — add ownership parameters and guard)
- Modify: `src/promptgrimoire/pages/annotation/cards.py:77-82` (add delete button with ownership gating)

**Implementation:**

1. Extend `delete_comment()` signature:
   ```python
   def delete_comment(
       self,
       highlight_id: str,
       comment_id: str,
       requesting_user_id: str | None = None,
       is_workspace_owner: bool = False,
       is_privileged: bool = False,
       origin_client_id: str | None = None,
   ) -> bool:
   ```

2. Before removing the comment, check authorisation:
   - If `is_workspace_owner` or `is_privileged`: allow (owner/instructor/admin can delete any comment)
   - Else if `requesting_user_id` and `comment.get("user_id") == requesting_user_id`: allow (own comment)
   - Else: return `False` (denied)

3. In `cards.py`, inside the comment rendering loop (lines 77-82), add a delete button that is only visible when:
   - The comment's `user_id` matches `state.user_id` (own comment), OR
   - The viewer is the workspace owner (Phase 4 will add `effective_permission` to PageState; for now, this can check if `state.user_id` is the owner — but the full permission check comes in Phase 4)

   Note: For Phase 3, the delete button can be shown for own comments unconditionally. The owner/privileged gating will be refined in Phase 4 when `effective_permission` is available on PageState.

4. Wire the delete button's click handler to call `state.crdt_doc.delete_comment()` with `requesting_user_id=state.user_id`.

**Testing:**

Unit tests for `delete_comment` ownership guard:
- AC3.4: Creator (matching `user_id`) can delete own comment → returns True
- AC3.5: Workspace owner (`is_workspace_owner=True`) can delete any comment → returns True
- Privileged user (`is_privileged=True`) can delete any comment → returns True
- AC1.8: Peer (non-matching `user_id`, not owner, not privileged) cannot delete → returns False
- AC1.5: Peer can delete own comment (matching `user_id`) → returns True
- Legacy comment without `user_id` (None) → only owner/privileged can delete

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `feat(crdt): add comment delete ownership guard`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Comment display — chronological ordering and existing comment rendering

**Verifies:** workspace-sharing-97.AC3.1, workspace-sharing-97.AC3.2, workspace-sharing-97.AC3.7

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/cards.py:62-117` (`_build_comments_section`)

**Implementation:**

1. Verify comments are already displayed in chronological order (they are — comments list is appended to, so insertion order = chronological). Add a sort by `created_at` as a safety measure: `sorted(comments, key=lambda c: c.get("created_at", ""))`.

2. For AC3.7: existing highlights/comments without `user_id` display author as-is (the `author` field). When `user_id` is `None`, instructors see the stored `author` value (or "Unknown" if that's also missing). No special handling needed — the existing `comment.get("author", "Unknown")` already does this.

3. The comment input field (lines 85-117) already exists and works. Verify it passes `user_id` (from Task 1). No additional UI changes needed for basic comment functionality.

**Testing:**

This task's ACs are verified by integration through the existing comment rendering. Unit tests:
- AC3.1: `add_comment` on a highlight appends to `comments` list
- AC3.2: Two comments on same highlight appear in chronological order
- AC3.7: Highlight with no `user_id` renders author as stored or "Unknown"

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `feat(cards): chronological comment display with legacy author handling`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->
<!-- START_TASK_4 -->
### Task 4: Create anonymisation utility

**Verifies:** workspace-sharing-97.AC4.3, workspace-sharing-97.AC4.4, workspace-sharing-97.AC4.5, workspace-sharing-97.AC4.6

**Files:**
- Create: `src/promptgrimoire/auth/anonymise.py`
- Create: `tests/unit/test_anonymise.py`

**Implementation:**

Create a pure function:

```python
def anonymise_author(
    author: str,
    user_id: str | None,
    viewing_user_id: str | None,
    anonymous_sharing: bool,
    viewer_is_privileged: bool,
    viewer_is_owner: bool,
) -> str:
```

Logic:
1. If `not anonymous_sharing`: return `author` (no anonymisation active)
2. If `viewer_is_privileged` or `viewer_is_owner`: return `author` (AC4.3 — instructors/admins always see real names)
3. If `user_id == viewing_user_id` and both are not None: return `author` (AC4.5 — own annotations show real name)
4. If `user_id is None`: return `"Unknown"` (legacy data)
5. Return deterministic adjective-animal label from `user_id` hash (AC4.6)

Deterministic mapping: `hashlib.sha256(user_id.encode()).digest()` → first 4 bytes for adjective index, next 4 for animal index. Module-level `ADJECTIVES` and `ANIMALS` tuples (50 each, audited for appropriateness — no negative or offensive terms).

Also add a convenience wrapper for contexts where only a deterministic label is needed (e.g., broadcast cursor labels, peer discovery list):

```python
def anonymise_display_name(user_id: str | None) -> str:
    """Return the deterministic adjective-animal label for a user_id.

    Unlike anonymise_author(), this does not check permissions or viewing
    context — it always returns the anonymised label. Callers are responsible
    for gating when to use this vs the real name.

    Returns "Unknown" if user_id is None.
    """
    if user_id is None:
        return "Unknown"
    # Same hash → adjective-animal logic as anonymise_author step 5
    ...
```

Export both functions from `auth/anonymise.py`.

**Testing:**

Unit tests (pure function, no DB needed):
- AC4.3: `viewer_is_privileged=True` → returns real `author`
- AC4.4: `viewer_is_owner=True` → returns real `author`
- AC4.5: `user_id == viewing_user_id` → returns real `author`
- AC4.5: `user_id != viewing_user_id` + `anonymous_sharing=True` → returns adjective-animal
- AC4.6: Same `user_id` called twice → same label (deterministic)
- AC4.6: Different `user_id` → different label (with high probability)
- `anonymous_sharing=False` → returns real `author` regardless
- `user_id=None` + `anonymous_sharing=True` → returns "Unknown"
- `viewing_user_id=None` (unauthenticated) + `anonymous_sharing=True` → returns adjective-animal for others

**Verification:**
Run: `uv run pytest tests/unit/test_anonymise.py -v`
Expected: All tests pass

**Commit:** `feat(auth): add deterministic anonymisation utility`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Wire anonymisation into comment and highlight author display

**Verifies:** workspace-sharing-97.AC4.5 (render-time application)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/cards.py:135` (highlight author display)
- Modify: `src/promptgrimoire/pages/annotation/cards.py:78` (comment author display)

**Implementation:**

Note: Full anonymisation wiring requires `anonymous_sharing` and `effective_permission` on PageState, which come in Phase 4. This task prepares the call sites by importing `anonymise_author` and calling it with placeholder values that preserve current behaviour.

1. Import `anonymise_author` from `promptgrimoire.auth.anonymise`.

2. In `_build_annotation_card` (line 135), replace direct `author` usage:
   ```python
   display_author = anonymise_author(
       author=highlight.get("author", "Unknown"),
       user_id=highlight.get("user_id"),
       viewing_user_id=state.user_id,
       anonymous_sharing=False,  # TODO: Phase 4 threads this from PageState
       viewer_is_privileged=False,  # TODO: Phase 4 threads this from PageState
       viewer_is_owner=False,  # TODO: Phase 4 threads this from PageState
   )
   ```
   With `anonymous_sharing=False`, the function returns the real author — preserving current behaviour until Phase 4 enables it.

3. Same pattern in `_build_comments_section` for comment author display.

This task creates the call sites. Phase 4 replaces the placeholders with actual PageState values.

**Testing:**

Verify existing annotation rendering still works (authors display correctly). No new tests — the anonymisation function is already tested in Task 4, and Phase 4 will test the full integration.

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass (no regression)

**Commit:** `feat(cards): wire anonymisation utility at author display points`
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->
