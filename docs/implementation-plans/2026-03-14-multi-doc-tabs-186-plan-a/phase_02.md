## Phase 2: Card Consistency Fixes

### Acceptance Criteria Coverage

This phase implements and tests:

### multi-doc-tabs-186.AC11: Card Consistency
- **multi-doc-tabs-186.AC11.1 Success:** Organise cards use `_build_expandable_text()` (80-char truncate with toggle)
- **multi-doc-tabs-186.AC11.2 Success:** Respond cards use `_build_expandable_text()` (80-char truncate with toggle)
- **multi-doc-tabs-186.AC11.3 Success:** Respond cards use `anonymise_author()` for highlight authors
- **multi-doc-tabs-186.AC11.4 Success:** All three tabs use identical expandable text behaviour

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Replace organise.py snippet truncation with expandable text

**Verifies:** multi-doc-tabs-186.AC11.1, multi-doc-tabs-186.AC11.4

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/organise.py` (remove `_SNIPPET_MAX_CHARS`, truncation logic, and plain label rendering in `_build_highlight_card()`)
- Test: `tests/integration/test_organise_charac.py` (update characterisation tests)

**Implementation:**
1. Add import at top of `organise.py`: `from .cards import _build_expandable_text`
2. Remove the `_SNIPPET_MAX_CHARS = 100` constant
3. Remove the truncation logic (the `snippet = full_text[:_SNIPPET_MAX_CHARS]` block):
   ```python
   # REMOVE these lines:
   snippet = full_text[:_SNIPPET_MAX_CHARS]
   if len(full_text) > _SNIPPET_MAX_CHARS:
       snippet += "..."
   ```
4. Replace the plain label rendering (`ui.label(f'"{snippet}"')` in `_build_highlight_card()`) with `_build_expandable_text()`:
   ```python
   # REPLACE: ui.label(f'"{snippet}"').classes("text-sm italic mt-1")
   # WITH:
   if full_text:
       _build_expandable_text(full_text)
   ```

**Testing:**
- Update Phase 1 characterisation tests to expect expandable text (80-char truncation with toggle) instead of 100-char static truncation
- AC11.1: Organise card with >80 char text shows expand chevron, clicking toggles full/truncated view
- AC11.4: Behaviour matches cards.py Annotate tab

**Verification:**
Run: `uv run grimoire test run tests/integration/test_organise_charac.py`
Expected: Updated tests pass with new expandable text behaviour

**Commit:** `fix: replace organise tab static truncation with expandable text`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Replace respond.py snippet truncation with expandable text

**Verifies:** multi-doc-tabs-186.AC11.2, multi-doc-tabs-186.AC11.4

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/respond.py` (remove `_SNIPPET_MAX_CHARS`, truncation logic, and plain label rendering in `_build_reference_card()`)
- Test: `tests/integration/test_respond_charac.py` (update characterisation tests)

**Implementation:**
1. Add import at top of `respond.py`: `from .cards import _build_expandable_text`
2. Remove the `_SNIPPET_MAX_CHARS = 100` constant
3. Remove the truncation logic (the `snippet = full_text[:_SNIPPET_MAX_CHARS]` block)
4. Replace the plain label rendering (`ui.label(f'"{snippet}"')` in `_build_reference_card()`) with:
   ```python
   if full_text:
       _build_expandable_text(full_text)
   ```

**Testing:**
- Update Phase 1 characterisation tests to expect expandable text (80-char truncation with toggle)
- AC11.2: Respond card with >80 char text shows expand chevron
- AC11.4: Behaviour matches cards.py and organise.py

**Verification:**
Run: `uv run grimoire test run tests/integration/test_respond_charac.py`
Expected: Updated tests pass

**Commit:** `fix: replace respond tab static truncation with expandable text`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add anonymise_author() to respond.py reference cards

**Verifies:** multi-doc-tabs-186.AC11.3

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/respond.py` (add `state` param to `_build_reference_card()`, add `anonymise_author()` for both highlight and comment authors)
- Test: `tests/integration/test_respond_charac.py` (update characterisation tests)

**Implementation:**
1. Add import: `from promptgrimoire.auth.anonymise import anonymise_author`
2. Modify `_build_reference_card()` signature to accept `state` parameter (needed for anonymisation context: `state.user_id`, `state.is_anonymous`, `state.viewer_is_privileged`, `state.privileged_user_ids`)
3. In `_build_reference_card()`, replace the raw author display (`ui.label(f"by {author}")`) with anonymised version:
   ```python
   # REPLACE: ui.label(f"by {author}").classes("text-xs text-gray-500")
   # WITH:
   display_author = anonymise_author(
       author=author,
       user_id=hl_user_id,
       viewing_user_id=state.user_id,
       anonymous_sharing=state.is_anonymous,
       viewer_is_privileged=state.viewer_is_privileged,
       author_is_privileged=(
           hl_user_id is not None and hl_user_id in state.privileged_user_ids
       ),
   )
   ui.label(f"by {display_author}").classes("text-xs text-gray-500")
   ```
4. Also anonymise comment authors in the comment rendering loop within `_build_reference_card()` — the raw `comment_author` is also displayed without anonymisation
5. Update all call sites of `_build_reference_card()` to pass `state`

**Testing:**
- Update Phase 1 characterisation test that documented "displays raw author" — it should now expect anonymised author
- AC11.3: Respond cards show anonymised author when anonymous sharing is enabled; show real name for own highlights and when viewer is privileged

**Verification:**
Run: `uv run grimoire test run tests/integration/test_respond_charac.py`
Expected: Anonymisation test now passes with correct author display

Run: `uv run grimoire test all`
Expected: All tests pass (no regressions)

**Commit:** `fix: add anonymise_author to respond tab reference cards`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
