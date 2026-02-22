# Workspace Sharing & Visibility — Phase 4: Permission-Aware Rendering

**Goal:** Annotation page respects permission levels. Viewers see read-only UI, peers can annotate/comment but not manage documents, editors can add documents, owners get full control.

**Architecture:** `effective_permission` and derived capability booleans on PageState. UI elements not rendered (not hidden) when permission is insufficient. Anonymisation wired with real values from PageState. Add-document UI extended to workspaces that already have documents (gated by `can_upload`).

**Tech Stack:** NiceGUI, Python

**Scope:** 7 phases from original design (phase 4 of 7)

**Codebase verified:** 2026-02-19

**Dependencies:** Phase 1 (model fields), Phase 2 (peer permission), Phase 3 (anonymisation utility, user_id on PageState, comment UI)

---

## Acceptance Criteria Coverage

This phase implements and tests:

### workspace-sharing-97.AC8: Permission-aware rendering
- **workspace-sharing-97.AC8.1 Success:** Viewer sees read-only UI (no tag toolbar, no highlight menu, no comment input, no document upload)
- **workspace-sharing-97.AC8.2 Success:** Peer sees annotate UI (tag toolbar, highlight menu, comment input) but no document upload
- **workspace-sharing-97.AC8.3 Success:** Editor sees full UI including document upload
- **workspace-sharing-97.AC8.4 Success:** Owner sees full UI plus ACL management controls
- **workspace-sharing-97.AC8.5 Edge:** Permission threaded via PageState.effective_permission to all rendering functions

### workspace-sharing-97.AC3: Annotation comments
- **workspace-sharing-97.AC3.6 Failure:** Viewer cannot add comments

### workspace-sharing-97.AC1: Peer permission level
- **workspace-sharing-97.AC1.2 Success:** Peer can view documents and highlights in shared workspace
- **workspace-sharing-97.AC1.3 Success:** Peer can create highlights and tags in shared workspace
- **workspace-sharing-97.AC1.4 Success:** Peer can add comments on highlights
- **workspace-sharing-97.AC1.6 Failure:** Peer cannot add or delete documents
- **workspace-sharing-97.AC1.7 Failure:** Peer cannot manage ACL (share workspace)

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add permission fields to PageState and compute capabilities

**Verifies:** workspace-sharing-97.AC8.5

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/__init__.py:166-213` (PageState — add permission fields)
- Modify: `src/promptgrimoire/pages/annotation/workspace.py:650-680` (thread permission into PageState)

**Implementation:**

1. Add fields to `PageState` dataclass (after `user_id` added in Phase 3):
   ```python
   effective_permission: str = "viewer"
   can_annotate: bool = False      # peer, editor, owner
   can_upload: bool = False         # editor, owner
   can_manage_acl: bool = False     # owner only
   is_anonymous: bool = False       # from PlacementContext.anonymous_sharing
   viewer_is_privileged: bool = False  # from is_privileged_user
   ```

2. In `workspace.py`, at the PageState construction site (lines 671-674), pass the permission and compute capabilities. The `permission` variable already exists at line 651 and `ctx` (PlacementContext) at line 666. Compute:
   ```python
   can_annotate = permission in ("peer", "editor", "owner")
   can_upload = permission in ("editor", "owner")
   can_manage_acl = permission == "owner"
   is_anonymous = ctx.anonymous_sharing
   viewer_is_privileged = is_privileged_user(auth_user)
   ```

3. Remove the TODO at line 663 (`# TODO(2026-02): Thread read_only for viewer permission -- #172`).

**Testing:**

Unit tests for capability computation — given a permission string, verify the correct boolean flags. Pure logic, no DB needed.

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `feat(annotation): add permission capabilities to PageState`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Wire anonymisation with real PageState values

**Verifies:** workspace-sharing-97.AC4.5 (full integration)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/cards.py` (replace Phase 3 placeholders)
- Modify: `src/promptgrimoire/pages/annotation/organise.py:104,112` (anonymise author in organise cards)

**Implementation:**

1. In `cards.py`, replace the placeholder `anonymous_sharing=False` from Phase 3 Task 5 with actual PageState values:
   ```python
   display_author = anonymise_author(
       author=highlight.get("author", "Unknown"),
       user_id=highlight.get("user_id"),
       viewing_user_id=state.user_id,
       anonymous_sharing=state.is_anonymous,
       viewer_is_privileged=state.viewer_is_privileged,
       viewer_is_owner=state.effective_permission == "owner",
   )
   ```
   Apply to both highlight author (line 135) and comment author display (line 78).

2. In `organise.py`, apply the same pattern at the two author display points (lines 104 and 112). The `state` object needs to be threaded into `_build_highlight_card()` — either pass the full state or pass the anonymisation parameters.

**Testing:**

No new unit tests — anonymisation function tested in Phase 3. This wiring is verified by the E2E tests that will come with UAT.

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass (no regression)

**Commit:** `feat(annotation): wire anonymisation with real permission context`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-5) -->
<!-- START_TASK_3 -->
### Task 3: Gate annotation UI for viewer permission

**Verifies:** workspace-sharing-97.AC8.1, workspace-sharing-97.AC3.6, workspace-sharing-97.AC1.2, workspace-sharing-97.AC1.3, workspace-sharing-97.AC1.4

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/document.py:134` (tag toolbar — conditional on `can_annotate`)
- Modify: `src/promptgrimoire/pages/annotation/document.py:137-146` (highlight menu — conditional on `can_annotate`)
- Modify: `src/promptgrimoire/pages/annotation/document.py:217` (selection handlers — conditional on `can_annotate`)
- Modify: `src/promptgrimoire/pages/annotation/cards.py:85-117` (comment input — conditional on `can_annotate`)
- Modify: `src/promptgrimoire/pages/annotation/cards.py:193-222` (tag dropdown, delete highlight — conditional on `can_annotate`)

**Implementation:**

In each rendering function, wrap interactive elements in `if state.can_annotate:` guards:

1. `document.py` line 134: wrap `_build_tag_toolbar(handle_tag_click)` in `if state.can_annotate:`
2. `document.py` lines 137-146: wrap highlight menu card construction in `if state.can_annotate:`
3. `document.py` line 217: wrap `_setup_selection_handlers(state)` in `if state.can_annotate:` — viewers don't get selection → highlight wiring
4. `cards.py` lines 85-117: wrap comment input + Post button in `if state.can_annotate:` — viewers can see existing comments but not add
5. `cards.py` lines 193-222: wrap tag dropdown and delete highlight button in `if state.can_annotate:`

The `state` parameter is already passed to all these functions. The elements are not rendered at all (approach: don't render, not disabled).

**Testing:**

Unit tests verifying that PageState with `can_annotate=False` results in the correct UI gating. Since NiceGUI renders server-side, these would be integration/E2E tests. For this phase, verify via manual UAT.

Test description for AC8.1: Construct a PageState with `effective_permission="viewer"`. Verify `can_annotate=False`. The rendering functions should skip interactive elements.

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass (no regression from conditional rendering)

**Commit:** `feat(annotation): gate annotation UI for viewer permission`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Gate document upload for peer/viewer and add multi-document upload

**Verifies:** workspace-sharing-97.AC8.2, workspace-sharing-97.AC8.3, workspace-sharing-97.AC1.6

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/workspace.py:772-776` (gate empty-workspace add-content form by `can_upload`)
- Modify: `src/promptgrimoire/pages/annotation/workspace.py` (add "Add Document" button for workspaces with existing documents, gated by `can_upload`)

**Implementation:**

1. At workspace.py line 772-776, the `else: # no documents` branch unconditionally renders `_render_add_content_form()`. Wrap in `if state.can_upload:` — peers and viewers see an empty-state message instead ("No documents in this workspace").

2. For workspaces that already have documents: add an "Add Document" button/expandable section after the document tabs, gated by `if state.can_upload:`. When clicked, render `_render_add_content_form(workspace_id)` in a dialog or expandable panel. This fixes the existing gap where editors couldn't add additional documents.

3. For viewers/peers seeing an empty workspace: render a message like "This workspace has no documents yet." instead of the upload form.

**Testing:**

- AC8.2: Peer PageState → `can_upload=False` → add-content form not rendered, "Add Document" button not rendered
- AC8.3: Editor PageState → `can_upload=True` → both rendered
- AC1.6: Peer cannot add documents (verified by `can_upload=False`)

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `feat(annotation): gate document upload and add multi-document support`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Gate organise tab interactions and refine delete comment ownership

**Verifies:** workspace-sharing-97.AC8.4, workspace-sharing-97.AC1.7

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/organise.py` (disable drag-and-drop for viewer)
- Modify: `src/promptgrimoire/pages/annotation/cards.py` (refine delete button visibility with full permission context)

**Implementation:**

1. In `organise.py`, the drag-and-drop is wired via `on_sort_end` parameter in `_build_tag_column()`. For viewers (`not state.can_annotate`), pass `on_sort_end=None` to disable dragging.

2. In `cards.py`, refine the delete comment button (added in Phase 3 Task 2) to use full permission context:
   - Show delete button if: `comment.get("user_id") == state.user_id` (own comment) OR `state.effective_permission == "owner"` OR `state.viewer_is_privileged` (instructor/admin)
   - Wire the delete call with `is_workspace_owner=(state.effective_permission == "owner")` and `is_privileged=state.viewer_is_privileged`

3. Similarly refine the delete highlight button: only show for owner/privileged or the highlight creator.

**Testing:**

Verify organise tab drag is disabled for viewers. Verify delete buttons respect ownership + permission. Verify that `can_manage_acl=False` for peer permission (AC1.7) — the sharing dialog (Phase 5 Task 4) is not rendered for peers. Add a unit test asserting `PageState(effective_permission="peer").can_manage_acl is False`.

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass

**Commit:** `feat(annotation): gate organise interactions and refine delete ownership`
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->

---

## UAT Protocol

### Permission-Aware Rendering

1. Open a workspace as the owner — verify full UI: tag toolbar, highlight menu, comment input, document upload, ACL management
2. Open the same workspace as an editor (via explicit ACL grant) — verify full UI except ACL management
3. Open the same workspace as a peer (via sharing + enrollment) — verify: tag toolbar, highlight menu, comment input visible; document upload and ACL management NOT visible
4. Open the same workspace as a viewer (via explicit viewer ACL) — verify: no tag toolbar, no highlight menu, no comment input, no document upload, no ACL management
5. As a peer, create a highlight and add a comment — verify both succeed
6. As a peer, attempt to add a document — verify the upload form is not present
7. As a viewer, verify no interactive elements are available — read-only view only
