# Workspace Sharing & Visibility — Phase 7: PDF Export Anonymity & Broadcast Labels

**Goal:** PDF export respects anonymity flag. Broadcast cursor/selection labels anonymised per-recipient based on viewer permission.

**Architecture:** Pre-process highlights list before passing to export pipeline — replace author names using `anonymise_author()` from Phase 3. Export pipeline stays pure (renders what it receives). Broadcast refactored from "same JS to all" to per-recipient dispatch: `_RemotePresence` gains `effective_permission` field, broadcast functions check recipient permission and send real or anonymised name accordingly.

**Tech Stack:** NiceGUI, Python, pycrdt

**Scope:** 7 phases from original design (phase 7 of 7)

**Codebase verified:** 2026-02-19

**Dependencies:** Phase 3 (`anonymise_author` utility in `auth/anonymise.py`), Phase 4 (`PageState.is_anonymous`, `viewer_is_privileged`, `effective_permission`, `user_id`)

---

## Acceptance Criteria Coverage

This phase implements and tests:

### workspace-sharing-97.AC4: Anonymity control
- **workspace-sharing-97.AC4.3 Success:** Instructor always sees true author regardless of anonymity flag (broadcast labels)
- **workspace-sharing-97.AC4.5 Success:** Peer sees own annotations with real name, others' with anonymised label (PDF export)
- **workspace-sharing-97.AC4.7 Success:** PDF export respects anonymity flag — peer export shows anonymised names
- **workspace-sharing-97.AC4.8 Success:** Instructor PDF export shows true names
- **workspace-sharing-97.AC4.9 Edge:** Broadcast cursor/selection labels anonymised for peer viewers

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Anonymise highlights in PDF export

**Verifies:** workspace-sharing-97.AC4.7, workspace-sharing-97.AC4.8, workspace-sharing-97.AC4.5 (export aspect)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/pdf_export.py:30-99` (`_handle_pdf_export`)

**Implementation:**

In `_handle_pdf_export(state, workspace_id)`, between fetching highlights (line 51) and passing them to `export_annotation_pdf` (line 91), add a pre-processing step that anonymises author names.

After line 51 (`highlights = state.crdt_doc.get_highlights_for_document(...)`):

```python
from promptgrimoire.auth.anonymise import anonymise_author

# Anonymise author names for peer viewers on anonymous workspaces
if state.is_anonymous:
    highlights = _anonymise_highlights(
        highlights,
        viewing_user_id=state.user_id,
        viewer_is_privileged=state.viewer_is_privileged,
        viewer_is_owner=(state.effective_permission == "owner"),
    )
```

Add the helper function in the same file:

```python
import copy

def _anonymise_highlights(
    highlights: list[dict[str, Any]],
    *,
    viewing_user_id: str | None,
    viewer_is_privileged: bool,
    viewer_is_owner: bool,
) -> list[dict[str, Any]]:
    """Return a copy of highlights with author names anonymised.

    Privileged users and workspace owners see real names.
    Other viewers see anonymised labels for all authors except themselves.
    """
    if viewer_is_privileged or viewer_is_owner:
        return highlights

    anonymised = []
    for hl in highlights:
        hl_copy = copy.deepcopy(hl)
        hl_copy["author"] = anonymise_author(
            author=hl_copy.get("author", "Unknown"),
            user_id=hl_copy.get("user_id"),
            viewing_user_id=viewing_user_id,
            anonymous_sharing=True,  # already gated by caller
            viewer_is_privileged=False,
            viewer_is_owner=False,
        )
        # Anonymise comment authors within this highlight
        for comment in hl_copy.get("comments", []):
            comment["author"] = anonymise_author(
                author=comment.get("author", "Unknown"),
                user_id=comment.get("user_id"),
                viewing_user_id=viewing_user_id,
                anonymous_sharing=True,
                viewer_is_privileged=False,
                viewer_is_owner=False,
            )
        anonymised.append(hl_copy)
    return anonymised
```

Key design points:
- `copy.deepcopy` ensures the original CRDT-backed highlights are not mutated
- `anonymise_author` (Phase 3) returns real name when `user_id == viewing_user_id` (own annotations keep real name per AC4.5)
- The guard `if viewer_is_privileged or viewer_is_owner` short-circuits for instructors (AC4.8) and owners (AC4.3)
- The outer `if state.is_anonymous` guard means non-anonymous workspaces skip this entirely

**Testing:**

Unit tests for `_anonymise_highlights`:

- Create: `tests/unit/test_pdf_anonymise.py`
- `TestAnonymiseHighlightsPrivileged` — privileged viewer gets unmodified highlights
- `TestAnonymiseHighlightsOwner` — owner gets unmodified highlights
- `TestAnonymiseHighlightsPeer` — peer viewer gets anonymised author names on other people's highlights and comments, but own highlights retain real name
- `TestAnonymiseHighlightsNoUserIdFallback` — highlight without `user_id` gets anonymised (not crash)
- `TestAnonymiseHighlightsNonAnonymous` — function not called when `is_anonymous=False` (tested via the caller guard, not the function itself)

Note: these test `_anonymise_highlights` directly, not the full PDF pipeline. The full pipeline test requires LaTeX compilation which is an E2E concern.

**Verification:**
Run: `uv run pytest tests/unit/test_pdf_anonymise.py -v`
Expected: All tests pass

**Commit:** `feat(export): anonymise highlight and comment authors in PDF export for peers`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add `effective_permission` to broadcast presence registry

**Verifies:** workspace-sharing-97.AC4.9 (prerequisite — permission tracking for per-recipient dispatch)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/broadcast.py` (`_RemotePresence` dataclass, presence registration)

**Implementation:**

1. Extend `_RemotePresence` (currently stores `name`, `color`, cursor/selection state) with `effective_permission`:

```python
@dataclass
class _RemotePresence:
    name: str
    color: str
    effective_permission: str = "viewer"
    cursor_index: int | None = None
    selection_start: int | None = None
    selection_end: int | None = None
```

2. Where `_RemotePresence` is created (line 179, inside the connection handler), populate from `state`:

```python
_workspace_presence[workspace_key][client_id] = _RemotePresence(
    name=state.user_name,
    color=state.user_color,
    effective_permission=state.effective_permission,
)
```

This is a backwards-compatible change — existing presence entries without the field default to `"viewer"`.

**Testing:**

No dedicated tests — this is an internal data structure change. Verified by Task 3's broadcast tests.

**Verification:**
Run: `uv run test-debug`
Expected: All tests pass (no regressions)

**Commit:** `refactor(broadcast): add effective_permission to presence registry`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Per-recipient broadcast anonymisation

**Verifies:** workspace-sharing-97.AC4.9, workspace-sharing-97.AC4.3 (instructor sees true names in cursor labels)

**Files:**
- Modify: `src/promptgrimoire/pages/annotation/broadcast.py` (`broadcast_cursor`, `broadcast_selection`, `_broadcast_js_to_others`, initial state replay)

**Implementation:**

1. Modify `_broadcast_js_to_others` to accept a per-recipient JS builder instead of a static JS string. Current signature (approximate):

```python
async def _broadcast_js_to_others(
    workspace_key: str,
    sender_client_id: str,
    js: str,
) -> None:
```

New signature:

```python
async def _broadcast_js_to_others(
    workspace_key: str,
    sender_client_id: str,
    js_builder: Callable[[_RemotePresence], str],
) -> None:
```

The inner loop changes from sending `js` to every recipient to calling `js_builder(recipient_presence)` per recipient:

```python
for client_id, client in nicegui_clients.items():
    if client_id == sender_client_id:
        continue
    presence = _workspace_presence[workspace_key].get(client_id)
    if presence is None:
        continue
    js = js_builder(presence)
    await client.run_javascript(js)
```

2. In `broadcast_cursor` (line 120), build per-recipient JS:

```python
async def broadcast_cursor(char_index: int | None) -> None:
    ...
    if char_index is not None:
        real_name = state.user_name
        anon_name = (
            anonymise_display_name(state.user_id)
            if state.is_anonymous
            else real_name
        )

        def build_js(recipient: _RemotePresence) -> str:
            # Owners and editors see real names; peers/viewers see anonymised
            # Note: instructors get "owner" via admin bypass in check_workspace_access,
            # so they are covered by the "owner" check. Staff enrolled as editors
            # are covered by "editor".
            name = (
                real_name
                if recipient.effective_permission in ("owner", "editor")
                or not state.is_anonymous
                else anon_name
            )
            color = state.user_color
            return _render_js(
                t"renderRemoteCursor("
                t"document.getElementById('doc-container')"
                t", {client_id}, {char_index}"
                t", {name}, {color})"
            )

        await _broadcast_js_to_others(workspace_key, client_id, build_js)
```

Note: the permission check uses `recipient.effective_permission` — instructors have either "owner" (admin bypass) or a staff-derived permission. The check `in ("owner", "editor")` covers instructors since `is_privileged_user` gives them owner-level access in `check_workspace_access`. If needed, add an `is_privileged` field to `_RemotePresence` for explicitness.

3. Apply the same pattern to `broadcast_selection` (line 140).

4. For initial state replay (lines 197-218), when a new client connects and receives existing presence state, apply the same per-recipient logic. The replaying client is the recipient — check its `state.effective_permission` to decide whether to show real or anonymised names for each existing presence.

5. Import `anonymise_display_name` from `promptgrimoire.auth.anonymise` (Phase 3).

**Testing:**

Unit tests for the per-recipient logic:

- Create: `tests/unit/test_broadcast_anonymise.py`
- `TestBroadcastCursorAnonymised` — mock two clients: one peer, one owner. Peer receives anonymised cursor label, owner receives real name.
- `TestBroadcastSelectionAnonymised` — same pattern for selection labels.
- `TestBroadcastNonAnonymousWorkspace` — when `is_anonymous=False`, all recipients see real names regardless of permission.
- `TestBroadcastReplayAnonymised` — new peer client connecting receives anonymised names for existing peer presences, real names for owner presence.

Note: broadcast tests require mocking NiceGUI client objects (`run_javascript`). Follow any existing broadcast test patterns. If no broadcast tests exist, create minimal mocks.

**Verification:**
Run: `uv run pytest tests/unit/test_broadcast_anonymise.py -v`
Expected: All tests pass

**Commit:** `feat(broadcast): per-recipient cursor/selection label anonymisation`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

---

## UAT Protocol

### PDF Export Anonymity

1. Create a workspace on an activity with `anonymous_sharing=True` and `allow_sharing=True`
2. As the owner, add some highlights and comments, then share with class
3. As a peer student, open the shared workspace, add your own highlights and comments
4. As the peer student, click "Export PDF"
5. Verify: Your own highlight/comment authors show your real name
6. Verify: The owner's highlight/comment authors show anonymised labels (e.g. "Cheerful Penguin")
7. As an instructor, open the same workspace, click "Export PDF"
8. Verify: ALL highlight/comment authors show real names (instructor bypass)
9. As the owner, export — verify all names are real (owner bypass)

### Broadcast Cursor Anonymity

10. Open the same anonymous workspace in three browser windows: owner, instructor, peer student
11. Move cursor as the peer student
12. Verify in the owner's window: cursor label shows the peer's real name
13. Verify in the instructor's window: cursor label shows the peer's real name
14. Move cursor as a second peer student (if available) or the owner
15. Verify in the first peer's window: other peer's cursor shows anonymised label; owner's cursor shows real name (owner is not anonymised)

### Non-Anonymous Workspace Baseline

16. Repeat steps 10-15 on a workspace with `anonymous_sharing=False`
17. Verify: All cursor labels show real names for all viewers
