# Multi-Document Workspace Management (Plan B) Design

**GitHub Issue:** MQFacultyOfArts/PromptGrimoireTool#186

**Supersedes / extends:** [docs/design-plans/2026-03-14-multi-doc-tabs-186.md](2026-03-14-multi-doc-tabs-186.md) — Plan A (Phases 1–7) shipped via PR #433. This design captures the remaining scope plus fixes for Plan A drifts, written under the current design skill.

## Summary

Plan B extends the multi-document workspace feature (Issue #186) beyond what Plan A shipped via PR #433. Plan A laid the tab infrastructure; Plan B completes the remaining scope and corrects several Plan A drifts: the `+` add-document button was never properly decoupled from an always-visible expansion panel, tab labels still render a `Source N:` prefix that was meant to be dropped, and the delete flow still forces a full page navigation. The 8-phase structure opens with a preemptive refactor-and-verify gate (Phase 1) that runs the smell-assessor over the 14 files in the blast radius and confirms the AC11/AC12 card-consistency guarantees before any feature code lands, keeping refactor and feature commits strictly separate.

Architecturally, the key moves are: placing the `+` button adjacent to (not inside) Quasar's QTabs component to avoid ARIA and keyboard-navigation problems; introducing a typed `DocumentEvent` channel over the existing `_RemotePresence` broadcast so peer clients receive surgical updates (soft rebuild of the tab bar, not a full browser reload or `ui.navigate.to()`) that preserve scroll position, unsaved form input, and admission-gate tickets; loading the manage-documents dialog lazily on open to avoid paying DOM cost for rarely-used instructor workflows; and shipping a breaking-change Alembic migration that locks down student uploads by default, forcing instructors to explicitly opt back in.

## Definition of Done

### DoD 1 — Tab bar rendering (Plan A drift fixes)

A workspace with N source documents renders `Source 1: <Title> | Source 2: <Title> | … | + | Organise | Respond`. Tab labels show the user-set title alone (no `Source N:` prefix) when title is set, or the fallback `Source N` when title is NULL. Clicking `+` opens the add-document dialog (not an always-visible expansion panel). Zero-document workspaces render `+ | Organise | Respond`.

**Excludes:** tab bar drag-reorder, mobile-specific tab gestures.

### DoD 2 — Document rename

Users with `can_edit` rename a source document via the management dialog (opened by pencil icon on source tab): empty titles rejected, save sets `workspace.search_dirty=true`, rename is visible immediately for acting user, peers see it after their next workspace reload.

**Excludes:** inline rename on tab itself, bulk rename.

### DoD 3 — Workspace rename from annotation page

Pencil icon in annotation page header (wired to existing `render_inline_title_edit()` helper) lets users rename the workspace in-place. Persists across reload, calls `update_workspace_title()` (sets `search_dirty`), peers see it after reload.

**Excludes:** navigator inline-edit UX (already works, untouched).

### DoD 4 — Source labels in Organise/Respond

Highlight cards in both tabs display subtitle `<Document Title>, para N` identifying source document. Present even in single-document workspaces. Rename updates subtitle on next tab render.

**Open:** anonymisation rules for document titles — resolve in brainstorming.

**Excludes:** Annotate tab card subtitles (unchanged).

### DoD 5 — Cross-tab locate

Locate affordance on a card in Organise/Respond switches to correct source tab (triggers deferred render if unvisited) and scrolls the highlight into view. If the source document was deleted, surfaces a user-visible error (no crash).

**Excludes:** locate from search results, locate across workspaces.

### DoD 6 — Delete + CRDT purge (verify/fix AC9.3–9.4)

Deleting a document removes DB row, purges highlights with that `document_id` from CRDT, removes tab + panel from DOM, switches active tab to next remaining (or `+` if zero), broadcasts to peers. Template-cloned documents stay protected (`ProtectedDocumentError`). Deleting the last document is permitted.

**Excludes:** soft-delete/restore, workspace delete.

### DoD 7 — Instructor controls (breaking change)

Activity gains `max_documents` (int, default **5**) and `allow_student_uploads` (bool, default **False**). Alembic migration flips all existing Activities to these defaults — **explicit breaking change**: instructors must opt in to re-enable student uploads. `+` hidden for students when `allow_student_uploads=False` OR `document_count >= max_documents`. Server-side guard in add-document handler rejects violations with user-visible error.

**Excludes:** Course-level defaults, per-week overrides.

### DoD 8 — Cross-client sync

When any client adds, renames, deletes, or reorders a document, peer clients on the same workspace reload within 5 seconds of the event, preserving persisted CRDT state.

**Open:** soft rebuild vs full browser reload — resolve in brainstorming.

**Excludes:** highlight-level sync (existing CRDT path, unchanged).

### DoD 9 — AC11/AC12 verify-and-refactor

A dedicated phase confirms: (a) Organise/Respond cards use same expandable-text toggle as Annotate; (b) card updates on CRDT change are diff-based (single card mutation, not full rebuild). If broken: fix under fix-hat commit; then refactor any structural mess in a separate refactor-hat commit. If both fine: phase commits verification tests only.

**Excludes:** refactoring unrelated card code; refactoring that changes behaviour.

### DoD 10 — Documentation

`src/promptgrimoire/docs/scripts/using_promptgrimoire.py` (or relevant guide) documents: `+` add, pencil manage/rename/delete, workspace rename via header pencil. Screenshots reflect implemented UI. `uv run grimoire docs build` passes. Each documented behaviour cites the test(s) verifying it.

**Excludes:** internal architecture docs (covered by design plan itself).

### Cross-cutting exclusions

- Mobile/touch-specific gestures
- Bulk document operations (multi-select delete, etc.)
- Document versioning / history
- Soft-delete / restore
- Tab-bar drag reorder (reorder via management dialog only)
- Course- or Week-level instructor controls

## Acceptance Criteria

### multi-doc-plan-b-186.AC1: Tab bar rendering
- **multi-doc-plan-b-186.AC1.1 Success:** Workspace with 3 documents titled "A", "B", "C" renders tab labels `A | B | C | + | Organise | Respond` with no `Source N:` prefix.
- **multi-doc-plan-b-186.AC1.2 Success:** Single-document workspace with a set title renders `<Title> | + | Organise | Respond`.
- **multi-doc-plan-b-186.AC1.3 Success:** Document with NULL title renders fallback label `Source N` (no trailing colon, no empty string).
- **multi-doc-plan-b-186.AC1.4 Success:** Zero-document workspace renders `+ | Organise | Respond` (no placeholder `Source` tab).
- **multi-doc-plan-b-186.AC1.5 Success:** Clicking `+` opens a modal add-document dialog (not an expansion panel).
- **multi-doc-plan-b-186.AC1.6 Failure:** AST guard test fails if the template string `Source {i + 1}: {doc.title}` appears anywhere in `tab_bar.py`.

### multi-doc-plan-b-186.AC2: Document rename in manage dialog
- **multi-doc-plan-b-186.AC2.1 Success:** User with `can_edit` opens the manage-documents dialog, renames document from "Old" to "New"; the corresponding source tab label updates to "New" immediately via surgical DOM update (no tab bar rebuild).
- **multi-doc-plan-b-186.AC2.2 Success:** After a rename, `workspace.search_dirty = true` in the database.
- **multi-doc-plan-b-186.AC2.3 Failure:** Empty title `""` is rejected with a user-visible error; original title is preserved.
- **multi-doc-plan-b-186.AC2.4 Failure:** Whitespace-only title `"   "` is rejected identically.
- **multi-doc-plan-b-186.AC2.5 Failure:** User without `can_edit` receives a `NotPermittedError`; title is not changed.
- **multi-doc-plan-b-186.AC2.6 Edge:** Manage-dialog contents only render after `dialog.on('show', ...)` fires. Page load with unopened dialog shows zero rename-input DOM nodes (verified by DOM count).

### multi-doc-plan-b-186.AC3: Workspace rename from annotation header
- **multi-doc-plan-b-186.AC3.1 Success:** Pencil icon in annotation page header opens inline edit; save persists the new title.
- **multi-doc-plan-b-186.AC3.2 Success:** After save, reloading the annotation page shows the new title.
- **multi-doc-plan-b-186.AC3.3 Success:** Save calls `update_workspace_title()`; `workspace.search_dirty` becomes true.
- **multi-doc-plan-b-186.AC3.4 Failure:** Empty workspace title is rejected; original is preserved.
- **multi-doc-plan-b-186.AC3.5 Edge:** Navigator inline-title-edit (pre-existing) behaves identically to before this change — regression test covers both navigator and annotation-header call sites of the shared helper.

### multi-doc-plan-b-186.AC4: Source labels in Organise / Respond
- **multi-doc-plan-b-186.AC4.1 Success:** Card in Organise shows subtitle `<Document Title>, para N` above the highlight excerpt.
- **multi-doc-plan-b-186.AC4.2 Success:** Card in Respond shows the same subtitle format.
- **multi-doc-plan-b-186.AC4.3 Success:** Subtitle is present even in a single-document workspace (not suppressed as redundant).
- **multi-doc-plan-b-186.AC4.4 Success:** Document titled "My Analysis" shows "My Analysis, para N" verbatim for all viewers (no anonymisation; DR5).
- **multi-doc-plan-b-186.AC4.5 Edge:** Document with NULL title shows fallback `Source N, para P` in the subtitle.
- **multi-doc-plan-b-186.AC4.6 Success:** Renaming a document flips the Organise/Respond dirty flag; next tab switch to either tab rebuilds with the updated subtitle.

### multi-doc-plan-b-186.AC5: Cross-tab locate
- **multi-doc-plan-b-186.AC5.1 Success:** Clicking locate on a card whose source is a different source tab switches the active tab and scrolls the highlight into view.
- **multi-doc-plan-b-186.AC5.2 Success:** Locate into a source tab that has never been visited triggers the tab's deferred render and then scrolls (no timing race).
- **multi-doc-plan-b-186.AC5.3 Failure:** Locate on a card whose source document has been deleted surfaces a `ui.notify(type="warning")`; no tab switch, no exception raised.

### multi-doc-plan-b-186.AC6: Delete document + CRDT purge
- **multi-doc-plan-b-186.AC6.1 Success:** Delete removes the `workspace_document` row.
- **multi-doc-plan-b-186.AC6.2 Success:** Delete purges all CRDT highlights whose `document_id` matches the deleted document (verified by CRDT state inspection).
- **multi-doc-plan-b-186.AC6.3 Success:** Delete removes the corresponding tab and tab panel from the DOM.
- **multi-doc-plan-b-186.AC6.4 Success:** If the acting client was viewing the deleted tab, its active tab switches to the next remaining source tab (or `+` if none remain).
- **multi-doc-plan-b-186.AC6.5 Failure:** Attempting to delete a template-cloned document raises `ProtectedDocumentError`.
- **multi-doc-plan-b-186.AC6.6 Success:** Deleting the last document leaves `+ | Organise | Respond` in the tab bar.
- **multi-doc-plan-b-186.AC6.7 Failure:** No `ui.navigate.to()` appears in the delete code path after this phase — soft rebuild only.

### multi-doc-plan-b-186.AC7: Instructor controls + migration
- **multi-doc-plan-b-186.AC7.1 Success:** Alembic upgrade adds `max_documents` (integer, NOT NULL, server_default=5) and `allow_student_uploads` (boolean, NOT NULL, server_default=false) to `activity`.
- **multi-doc-plan-b-186.AC7.2 Success:** Migration flips all existing `activity` rows to these defaults; a post-migration query returns zero rows with the old implicit values.
- **multi-doc-plan-b-186.AC7.3 Success:** Alembic downgrade drops both columns cleanly.
- **multi-doc-plan-b-186.AC7.4 Success:** Student on Activity with `allow_student_uploads=false` sees `+` button rendered disabled with tooltip "Uploads disabled for students on this activity".
- **multi-doc-plan-b-186.AC7.5 Success:** Student on Activity where `document_count >= max_documents` sees `+` disabled with tooltip "Document limit reached (N/max)".
- **multi-doc-plan-b-186.AC7.6 Success:** Instructor (activity owner or ACL `can_edit`) always sees `+` enabled regardless of these flags.
- **multi-doc-plan-b-186.AC7.7 Failure:** Server-side add-document handler rejects bypass attempts (constructed request without passing through the disabled UI) with `UploadNotPermittedError`.
- **multi-doc-plan-b-186.AC7.8 Failure:** Disabled `+` button cannot be activated via click (per DR7 — disable-don't-hide is enforced in E2E).

### multi-doc-plan-b-186.AC8: Cross-client soft rebuild
- **multi-doc-plan-b-186.AC8.1 Success:** Client A adds a document; Client B (same workspace) sees the new tab within 5 seconds; Client B's active tab is preserved.
- **multi-doc-plan-b-186.AC8.2 Success:** Client A renames a document; Client B's corresponding tab label updates via a surgical DOM update (MutationObserver confirms no tab bar rebuild).
- **multi-doc-plan-b-186.AC8.3 Success:** Client A deletes document X; if Client B was viewing X, B's active tab switches to the next remaining source; if B was on another tab, B's active tab is preserved.
- **multi-doc-plan-b-186.AC8.4 Success:** Client A reorders documents; Client B's tab bar re-sequences; B's active tab is preserved if still present in the new order.
- **multi-doc-plan-b-186.AC8.5 Success:** Client A renames the workspace; Client B's annotation-page header title updates via a surgical DOM update.
- **multi-doc-plan-b-186.AC8.6 Success:** Across all five event types, Client B's unsaved form input, scroll position, admission-gate ticket, and reconnect state are preserved.
- **multi-doc-plan-b-186.AC8.7 Failure:** During a peer broadcast with 10 concurrent clients in the workspace, measured event-loop lag does not exceed the admission gate's `LAG_INCREASE_MS` threshold.

### multi-doc-plan-b-186.AC9: AC11/12 verify-and-refactor
- **multi-doc-plan-b-186.AC9.1 Success:** Organise cards invoke `_build_expandable_text()` (same helper as Annotate cards) for any text longer than the truncation threshold.
- **multi-doc-plan-b-186.AC9.2 Success:** Respond cards invoke `_build_expandable_text()` identically.
- **multi-doc-plan-b-186.AC9.3 Success:** Adding a highlight via CRDT update produces exactly 1 insert mutation in the card container (MutationObserver count = 1, not N).
- **multi-doc-plan-b-186.AC9.4 Success:** Removing a highlight produces exactly 1 removal mutation.
- **multi-doc-plan-b-186.AC9.5 Success:** Updating a tag or comment on a highlight produces mutations on that card's DOM subtree only — sibling cards unaffected.
- **multi-doc-plan-b-186.AC9.6 Edge:** If Phase 1 verification finds no gaps, the phase commits the verification tests and no fix is applied (verification tests remain as regression guards).

### multi-doc-plan-b-186.AC10: Documentation
- **multi-doc-plan-b-186.AC10.1 Success:** `src/promptgrimoire/docs/scripts/using_promptgrimoire.py` documents: `+ add`, manage-documents dialog, document rename, document delete, workspace rename, instructor controls (`max_documents` + `allow_student_uploads`).
- **multi-doc-plan-b-186.AC10.2 Success:** `uv run grimoire docs build` exits 0 after doc changes.
- **multi-doc-plan-b-186.AC10.3 Success:** Screenshots in the generated docs reflect the shipped UI for both student-locked and instructor views where they diverge.
- **multi-doc-plan-b-186.AC10.4 Success:** Each documented behavioural claim cites at least one test file + test name verifying it.
- **multi-doc-plan-b-186.AC10.5 Success:** `docs/architecture/dfd/5-annotate-texts.md` is reviewed against this design and updated to show the tab bar decomposition and broadcast event paths.

## Glossary

- **Workspace**: The top-level container for a user's annotation session. Holds one or more source documents, a shared CRDT state, and access-control entries. Rendered as the annotation page at `/workspace/<id>`.
- **Activity**: An instructor-defined assignment unit (called "Unit" in the UI) that a workspace is created under. Plan B adds `max_documents` and `allow_student_uploads` columns to this model.
- **Source document** (`WorkspaceDocument`): A single text document inside a workspace, displayed as one tab in the tab strip. Multiple source documents per workspace is the core multi-doc feature.
- **CRDT** (Conflict-free Replicated Data Type): The data structure (backed by `pycrdt`) that stores highlights, tags, and comments in a workspace. Changes from multiple clients merge without conflicts. Document deletion must explicitly purge CRDT state for the removed document.
- **`_RemotePresence`**: The per-workspace server-side object that tracks connected clients and fans out broadcast events. Plan B extends its callback signature to carry typed `DocumentEvent` payloads alongside the existing implicit highlight-changed signal.
- **Soft rebuild**: Updating only the affected UI sub-tree (e.g. the tab bar) in-place rather than issuing a full `ui.navigate.to()` or browser `location.reload()`. Preserves ephemeral client state such as scroll position and form input.
- **Two Hats discipline**: The practice of keeping refactoring commits (refactor-hat) strictly separate from feature commits (feature-hat). Enforced here by the Phase 1 smell-assessor gate: all refactors land before any feature code touches the same files.
- **Smell-assessor**: A subagent that evaluates source files against the Mantyla smell taxonomy and Fowler refactoring patterns, producing findings ranked by severity. Used in Phase 1 to clean the blast-radius files before feature work begins.
- **AIMD admission gate**: The server-side concurrency control that queues new browser clients when asyncio event-loop lag exceeds a threshold. Soft rebuild is chosen in part to avoid perturbing a client's admission-gate ticket during peer broadcasts.
- **Quasar QTabs**: The Vue/Quasar component that NiceGUI wraps for the tab strip. It does not expose a native trailing-slot for action buttons, which is why the `+` button must be placed adjacent to the tab strip rather than inside it (DR1).
- **NiceGUI**: The Python web-UI framework used throughout PromptGrimoire. Renders server-side Python as a reactive Vue/Quasar frontend over a WebSocket.
- **Alembic**: The SQLAlchemy migration tool. All schema changes (including Plan B's two new `activity` columns) must go through Alembic migrations — `SQLModel.metadata.create_all()` is never used in production.
- **SQLModel**: The ORM layer (Pydantic + SQLAlchemy) used for all database models. `Activity`, `WorkspaceDocument`, and others are SQLModel classes.
- **`BusinessLogicError`**: The project's base exception class for all domain-level rejections (e.g. `EmptyTitleError`, `UploadNotPermittedError`). Plan B adds two new subclasses.
- **Lazy manage dialog**: The manage-documents dialog whose content is built inside a `dialog.on('show', …)` handler and cleared on close, so it contributes zero DOM nodes on page load when not opened (DR3).
- **AST guard test**: A structural test (following the `test_run_javascript_guard.py` pattern) that fails the test suite if a banned code pattern reappears. Plan B adds one guarding against the `Source N:` double-prefix label string.

## Architecture

This design layers on Plan A's tab infrastructure without restructuring. Work is confined to `src/promptgrimoire/pages/annotation/` (UI) and `src/promptgrimoire/db/` (persistence), with a single Alembic migration for AC14 (instructor controls). The CRDT layer is not modified — document-level events travel a separate typed-event channel over the existing `_RemotePresence` broadcast infrastructure.

**Data flow — user adds a document (happy path):**

1. User clicks the `+` button adjacent to the tab strip in the annotation page.
2. `_open_add_document_dialog()` opens a modal (lifted from the existing `ui.dialog() + ui.card()` pattern) containing `_render_add_content_form()`.
3. On submit, the acting client calls `add_document()` (existing). The call path first checks `_can_add_document(state, activity)` server-side (this design's new guard).
4. Acting client refreshes its local tab bar and auto-selects the new tab.
5. `_notify_other_clients()` broadcasts `DocumentEvent(type="document_added", workspace_id=..., document_id=..., payload={})` to peer clients.
6. Each peer's `_RemotePresence.callback` receives the typed event, rebuilds **only** its tab bar (not the whole workspace), and preserves the peer's active tab.

**Data flow — rename / delete / reorder:** same broadcast pipe, different event types. Surgical handlers pick the minimum-scope update: rename updates one tab label element (no rebuild); delete/add/reorder rebuild the tab bar; workspace rename updates the header title element.

**Boundaries:**

- **CRDT layer:** untouched. Highlight CRDT broadcast continues over the `None`-typed path for backward compatibility.
- **DB layer:** new `rename_document()` in `workspace_documents.py`; two new columns on `activity`; one Alembic migration. No schema changes to `workspace_document` or `workspace`.
- **UI layer:** ≈14 files in the Plan B blast radius. Phase 1 runs a smell-assessor pass over each before feature work begins.

**Event contract** (extends `_RemotePresence`):

```python
from typing import Literal, TypedDict
from uuid import UUID

class DocumentEvent(TypedDict):
    type: Literal[
        "document_added", "document_renamed",
        "document_deleted", "document_reordered",
        "workspace_renamed",
    ]
    workspace_id: UUID
    document_id: UUID | None   # None for document_reordered + workspace_renamed
    payload: dict[str, object]  # event-specific: new_title, new_order, ...
```

`_RemotePresence.callback` signature extends to `Callable[[DocumentEvent | None], Awaitable[None]]`; `None` preserves today's implicit highlight-changed signal. `broadcast.py:_notify_other_clients()` gains an optional `event` kwarg; highlight paths pass nothing, document paths pass the typed event.

**DB contract** (new functions + column additions):

```python
# db/workspace_documents.py
async def rename_document(
    document_id: UUID, new_title: str, actor: AuthUser,
) -> WorkspaceDocument: ...
    # Validates non-empty, checks can_edit_document, updates title,
    # bumps workspace.search_dirty + workspace.updated_at.
    # Raises EmptyTitleError, NotPermittedError.

# db/models.py (Activity, additions)
max_documents: int = Field(default=5, nullable=False)
allow_student_uploads: bool = Field(default=False, nullable=False)
```

**Gating contract:**

```python
# pages/annotation/tab_bar.py
def _can_add_document(state: AnnotationState, activity: Activity | None) -> tuple[bool, str]:
    """Return (allowed, reason). reason is the tooltip shown on the disabled + button."""
    # (True, "") when allowed.
    # (False, "Uploads disabled for students on this activity") when allow_student_uploads=False and not instructor.
    # (False, "Document limit reached (N/max_documents)") when at cap.
```

**Component map:**

```
src/promptgrimoire/
├── pages/annotation/
│   ├── tab_bar.py              # Phase 2: `+` outside QTabs, label rendering, gating
│   ├── document_management.py  # Phase 3: rename field + lazy content
│   ├── document_render.py      # Phase 2: delete expansion panel
│   ├── header.py               # Phase 4: workspace rename pencil
│   ├── organise.py             # Phase 7: source labels + dirty-flag
│   ├── respond.py              # Phase 7: source labels + dirty-flag
│   ├── highlights.py           # Phase 7: cross-tab locate
│   ├── content_form.py         # Phase 5: server-side gate
│   ├── broadcast.py            # Phase 8: typed events
│   ├── card_shared.py          # Phases 3, 7: shared helpers
│   └── __init__.py             # Phase 8: _RemotePresence event type
├── db/
│   ├── workspace_documents.py  # Phase 3: rename_document()
│   └── models.py               # Phase 5: Activity columns
└── alembic/versions/
    └── <hash>_activity_doc_controls.py  # Phase 5: migration
```

## Decision Record

### DR1: Place the `+` button outside QTabs in an adjacent flex row
**Status:** Accepted
**Confidence:** High
**Reevaluation triggers:** If Quasar v2 gains a native trailing-slot affordance for QTabs; if keyboard-arrow expectations change.

**Decision:** We chose to render the `+` add-document button as an adjacent `ui.button` in a `ui.row()` alongside `ui.tabs(stretch=True)`, rather than as a pseudo-tab inside QTabs.

**Consequences:**
- **Enables:** ARIA-clean separation (`role="button"`, not `role="tab"`), browser/editor conventions (Chrome, VS Code, Slack place `+` outside the tablist), no QTabs click-state bleed, no keyboard-arrow trap.
- **Prevents:** Reusing any theoretical QTabs-internal action slot (none exists in Quasar v2).

**Alternatives considered:**
- **Pseudo-tab inside QTabs with click-prevention:** Rejected — fights the framework, Quasar GitHub issue #7104 documents community friction with elements inside QTabs.
- **Dedicated "New Document" button far from the tab strip:** Rejected — loses the visual affordance of "this adds another source tab."

### DR2: Soft rebuild on cross-client document events
**Status:** Accepted
**Confidence:** High
**Reevaluation triggers:** If surgical rebuilds prove too fragile under load; if instrumentation shows rebuild frequency dominates event-loop time.

**Decision:** We chose a soft rebuild (tab bar + document list only, preserving in-memory CRDT state) over a server-triggered `ui.navigate.to()` or a full browser `location.reload()`.

**Consequences:**
- **Enables:** Preserves scroll position, unsaved form input, admission-gate ticket, reconnect state. Aligns with ongoing event-loop / memory performance work.
- **Prevents:** The simplest implementation (full reload). Requires careful coordination to avoid races with in-flight user interactions (established pattern: surgical updates where possible, container-rebuild safety per CLAUDE.md § E2E Race-Condition Patterns).

**Alternatives considered:**
- **Server-triggered `ui.navigate.to(current_url)`:** Rejected — matches today's delete flow but tears down CRDT and forces re-hydration, losing ephemeral state.
- **Full browser `location.reload()`:** Rejected — simplest but most disruptive; loses form input, admission ticket, focus.

### DR3: Lazy-load manage-documents dialog content
**Status:** Accepted
**Confidence:** High
**Reevaluation triggers:** If lazy build introduces perceptible latency (>300 ms) on open; if memory savings prove negligible.

**Decision:** We chose to build manage-documents dialog content inside an async `dialog.on('show', …)` handler and clear it on close, rather than eagerly rendering on every annotation page load.

**Consequences:**
- **Enables:** Zero DOM cost for the dialog when unused (most page loads). Consistent with ongoing perf work.
- **Prevents:** Instantly-available dialog content (≈tens of ms of fetch+render on open).

**Alternatives considered:**
- **Eager rendering on page load:** Rejected — pays DOM cost for all users even though dialog usage is rare (instructors managing content).

### DR4: Single manage-documents entry point in the annotation page header
**Status:** Accepted
**Confidence:** Medium
**Reevaluation triggers:** If users struggle to find the manage dialog; if workflow shows per-tab entry is valuable after all.

**Decision:** We chose one "Manage Documents" button in the annotation page header (alongside the workspace rename pencil) as the sole entry point. Source tabs themselves do not carry per-document pencil icons.

**Consequences:**
- **Enables:** One canonical place to rename/delete/reorder, simpler to test, simpler tab bar.
- **Prevents:** Quick per-tab rename (users must open the dialog first).

**Alternatives considered:**
- **Pencil icon on each source tab:** Rejected — two entry points double the surface to test; the dialog is fast enough that the quick-rename affordance isn't worth the complexity.
- **Inline-edit on tab title (click to edit):** Rejected — tab labels are narrow, clashes with tab-click-to-switch semantics, requires race-safe value-capture flush.

### DR5: No anonymisation for document titles in Organise/Respond subtitles
**Status:** Accepted
**Confidence:** Medium
**Reevaluation triggers:** If students consistently self-identify in document titles during class-share views; if instructor review workflows surface privacy concerns.

**Decision:** We chose to display document titles verbatim in the `<Title>, para N` subtitle on Organise/Respond cards, without applying `anonymise_display_author()` semantics.

**Consequences:**
- **Enables:** Simpler rendering, titles remain meaningful metadata (e.g. "Week 9: Appian Civil Wars") in all views.
- **Prevents:** Automatic privacy protection if a student names a document "My analysis by Jane Student". Trust boundary shifts to title content.

**Alternatives considered:**
- **Anonymise in class-share views only:** Rejected for now — can be added later if real-world usage shows self-identification patterns.
- **Always anonymise for non-owners:** Rejected — over-hides instructor-visible metadata.

### DR6: Instructor-tightened defaults with breaking migration
**Status:** Accepted
**Confidence:** High
**Reevaluation triggers:** If post-deploy audit finds existing Activities with active student-upload workflows silently broken; if instructor configuration burden outweighs benefit.

**Decision:** We chose `allow_student_uploads=False` and `max_documents=5` as the defaults. The Alembic migration flips all existing Activities to these values — explicitly breaking change. Instructors must re-enable student uploads per Activity to restore prior behaviour.

**Consequences:**
- **Enables:** Safe-by-default posture for instructor-curated templates (the dominant use case). Forces intentional opt-in for student uploads.
- **Prevents:** Zero-disruption upgrade. Instructors running workflows that rely on implicit student uploads must reconfigure.

**Alternatives considered:**
- **Defaults preserve today's behaviour (`True` / `NULL`):** Rejected — user decision. Today's behaviour is permissive-by-default, which conflicts with the curated-template use case driving this design.
- **Defer instructor controls entirely:** Rejected — user decision, controls are in scope.

### DR7: Disable (with tooltip) rather than hide the `+` button
**Status:** Accepted
**Confidence:** High
**Reevaluation triggers:** Never (project-wide convention per CLAUDE.md memory rule).

**Decision:** When `_can_add_document()` returns `False`, render the `+` button in a disabled state with a tooltip explaining why, rather than omitting it.

**Consequences:**
- **Enables:** Students learn why they can't add. Discoverability of the constraint.
- **Prevents:** Cleaner tab-bar layout when add is disabled (marginal).

**Alternatives considered:**
- **Hide the button:** Rejected — violates project rule "Disable buttons, don't hide them" (2026-03-24).

### DR8: Run smell-assessor over all Plan B blast-radius files before feature work
**Status:** Accepted
**Confidence:** Medium
**Reevaluation triggers:** If Phase 1 uncovers so many findings that Plan B slips materially; if the approach proves redundant with per-phase review.

**Decision:** We chose to dispatch smell-assessor over every file in Plan B's blast radius in Phase 1, apply refactoring-executor prescriptions one at a time under a refactor hat, then start feature work in Phase 2. This is preemptive rather than reactive.

**Consequences:**
- **Enables:** Two Hats discipline strictly enforced — refactors land as isolated commits before any feature change touches the same files. Feature commits stay small and reviewable.
- **Prevents:** Mixing refactor and feature hats mid-phase (the usual failure mode). Trades Phase 1 cost for clean downstream phases.

**Alternatives considered:**
- **Reactive refactor per-phase:** Rejected — tempts mixing hats within a phase.
- **Skip the scan entirely:** Rejected — file complexity has accumulated since Plan A; touching 14 files without a scan risks compounding smell.

## Existing Patterns

Codebase investigation (Phase 1 of brainstorming) identified the following patterns that this design follows:

- **Dialog pattern:** `with ui.dialog() as dialog, ui.card().classes(...)` — 8+ sites in `src/promptgrimoire/pages/annotation/` (document_management.py, tag_management.py, sharing.py, placement.py, tag_quick_create.py). Phase 3's lazy-loaded manage dialog extends this pattern with `dialog.on('show', …)`.
- **Pencil icon convention:** `ui.icon("edit", size="xs").classes("cursor-pointer text-gray-400 hover:text-primary")` — established in `pages/navigator/_cards.py:169-175`. Phase 3 (document rename inside dialog) and Phase 4 (workspace rename in header) reuse this convention.
- **Inline-edit helper:** `render_inline_title_edit()` at `pages/navigator/_cards.py:152`. This design generalises it to accept an `on_save: Callable[[str], Awaitable[None]]` callback and lifts the shared implementation into `card_shared.py`; the navigator's existing call site wraps it with its current semantics for zero UX drift there.
- **`_RemotePresence` broadcast:** `pages/annotation/__init__.py:100-152` — callback is generic (no signature constraint). Phase 8 extends callback signature to `(event: DocumentEvent | None)` where `None` preserves the current highlight-changed signal.
- **`_notify_other_clients()` fan-out:** `broadcast.py:111-118` — loops through `_workspace_presence[workspace_key]`. Phase 8 adds an optional `event` kwarg.
- **`+ Add` button styling:** `ui.button(..., icon="add").props('flat color=primary dense')` — established in `pages/courses.py` for "New Unit" / "Add Week". Phase 2 reuses for the `+` tab-adjacent button.
- **Confirmation dialog on delete:** `document_management.py:329` — existing pattern, Phase 6 verifies unchanged.
- **ACL check helpers:** `can_edit_document()` (`document_management.py:68-79`) and `check_workspace_access()` (`auth/__init__.py`). Phase 3's `rename_document()` calls `can_edit_document()`; Phase 4's workspace rename uses the same existing check the navigator uses.
- **`ProtectedDocumentError` for template-cloned documents:** existing in `db/`, used by `delete_document()`. Phase 6 verifies unchanged.
- **Paragraph number lookup in CardData:** existing helper used by `organise.py` and `respond.py`. Phase 7 adds a pure helper `resolve_source_label(document, paragraph_index)` to `card_shared.py` using the existing lookup.
- **AST guard tests:** `test_run_javascript_guard.py` pattern. This design adds a guard test asserting the `Source N:` double-prefix string never reappears in `tab_bar.py`.

**Divergence from Plan A:**

- The always-visible "Add Document" expansion panel (`document_render.py:37-65`) is replaced by a modal dialog opened from the `+` button. Phase 2 deletes the expansion panel.
- The zero-document placeholder `Source` tab (`tab_bar.py:832-837`) is deleted; zero-doc state becomes `+ | Organise | Respond`. Phase 2.
- Tab label rendering in `tab_bar.py:822` changes from `f"Source {i+1}: {doc.title}" if doc.title else f"Source {i+1}"` to `doc.title if doc.title else f"Source {i+1}"`. Phase 2.

## Implementation Phases

Eight phases, targeting the 8-phase limit for a single implementation plan. Phase 1 is a refactor-and-verify gate; Phases 2–8 are sequential feature work. Dependencies noted per phase.

<!-- START_PHASE_1 -->
### Phase 1: Preemptive refactor + AC11/12 verify-and-fix

**Goal:** Bring the Plan B blast radius up to current standards before any feature work lands, and confirm (or fix) the AC11/12 card-consistency / diff-based-update behaviour that Plan A was supposed to deliver.

**Components:**
- Smell-assessor dispatched once per file across the blast radius: `tab_bar.py`, `document_management.py`, `document_render.py`, `header.py`, `organise.py`, `respond.py`, `cards.py`, `highlights.py`, `content_form.py`, `broadcast.py`, `annotation/__init__.py`, `card_shared.py`, `db/workspace_documents.py`, `db/workspaces.py`, `db/models.py`.
- Refactoring-executor applies prescriptions one finding at a time; each is its own commit with a refactor-hat message and full test suite green between commits.
- AC11 verification: instrumented test counts toggle buttons in Organise/Respond cards; if missing, migrate both modules to `_build_expandable_text()` under a fix-hat commit.
- AC12 verification: Playwright test with MutationObserver counts DOM mutations on highlight add/remove; if count != 1 (i.e. a full rebuild is happening), migrate `_refresh_annotation_cards()` to a diff-based (added/removed/updated) approach under a fix-hat commit.

**Dependencies:** None (first phase).

**Done when:** All smell-assessor findings in scope are either applied or deliberately rejected; AC11 and AC12 verification tests exist and pass; full suite green; no feature code added.

**Covers:** DoD 9.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Tab bar, `+` pseudo-tab, label rendering

**Goal:** Restore the `+` add-document affordance, remove the expansion panel, fix the double-prefix tab label bug.

**Components:**
- `tab_bar.py` — new `_resolve_tab_label(i, doc)` helper (title verbatim, else `Source N`); `_build_tabs()` restructured into `ui.row()` with `ui.tabs(stretch=True)` + adjacent `ui.button(icon='add', flat, color=primary, dense, round)` with `data-testid="add-document-btn"`; placeholder `Source` tab deleted.
- `tab_bar.py` — new `_open_add_document_dialog(workspace_id)` wrapping existing `_render_add_content_form()` inside `ui.dialog() + ui.card()`.
- `document_render.py` — delete `render_content_form_outside_refreshable()`; call site in `workspace.py` becomes a no-op.
- AST guard test asserting the `Source {i + 1}: {doc.title}` template string does not appear anywhere.
- E2E test confirming: (a) tab label overwrites prefix when title set, (b) fallback `Source N` when title NULL, (c) `+` opens dialog, (d) zero-doc state.

**Dependencies:** Phase 1 (clean codebase).

**Done when:** All tests for DoD 1 acceptance criteria pass; expansion panel removed; double-prefix guard test active.

**Covers:** DoD 1.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Document rename in manage-documents dialog (lazy)

**Goal:** Add the `rename_document()` DB function; extend manage-documents dialog with a per-document inline-edit title field, loaded lazily on dialog open.

**Components:**
- `db/workspace_documents.py` — new `rename_document(document_id, new_title, actor)`; validates non-empty (strip whitespace, reject ""), checks `can_edit_document()`, updates `title`, bumps `workspace.search_dirty` + `workspace.updated_at`. Raises `EmptyTitleError` (new, subclass `BusinessLogicError`).
- `card_shared.py` — generalised `render_inline_title_edit(current_title, on_save, *, testid_prefix)` lifted from navigator usage; navigator's call site wraps the new helper to preserve its existing semantics.
- `document_management.py` — `open_manage_documents_dialog()` refactored to build content inside `dialog.on('show', …)` and clear on close; each document row gains an inline-edit title field wired to `rename_document()`.
- `header.py` — "Manage Documents" button with `data-testid="manage-documents-btn"` added adjacent to workspace rename pencil (Phase 4 wires the pencil; this phase adds the button structure).
- Acting-client tab label surgical update: on save, find tab label element by `data-testid="tab-source-{doc_id}"`, update text in place (no rebuild).
- E2E: rename saves, empty rejected, tab label updates, `search_dirty` set.

**Dependencies:** Phase 2 (tab structure with testids).

**Done when:** All DoD 2 acceptance criteria pass; manage dialog opens lazily (verified by DOM node count on page load vs on dialog open).

**Covers:** DoD 2.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Workspace rename in annotation page header

**Goal:** Wire the generalised `render_inline_title_edit()` helper into the annotation page header for workspace rename.

**Components:**
- `header.py` — pencil icon (Material `edit`, `size="xs"`, hover style matching navigator) next to workspace title; wired to the shared helper from Phase 3 with an `on_save` callback calling `update_workspace_title()` (already exists in `db/workspaces.py:1288`).
- E2E: pencil opens edit mode, save persists across reload, empty title rejected, FTS reindex queued.

**Dependencies:** Phase 3 (shared helper).

**Done when:** All DoD 3 acceptance criteria pass; navigator inline-edit remains unchanged (regression test).

**Covers:** DoD 3.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Instructor controls + Alembic migration

**Goal:** Add `max_documents` and `allow_student_uploads` columns to `Activity`; migrate existing Activities to locked-down defaults; gate the `+` button; add server-side guard.

**Components:**
- `db/models.py` — Activity gains `max_documents: int = Field(default=5, nullable=False)` and `allow_student_uploads: bool = Field(default=False, nullable=False)`.
- `alembic/versions/<hash>_activity_doc_controls.py` — upgrade adds columns with `server_default="5"` and `server_default="false"`; downgrade drops both.
- `tab_bar.py` — `_can_add_document(state, activity)` helper returning `(allowed: bool, reason: str)`; `+` button rendered `disabled` with tooltip when not allowed (per DR7 — disable, don't hide).
- `content_form.py` — server-side guard on the add-document handler; raises `UploadNotPermittedError` (new, subclass `BusinessLogicError`) on violation; user-visible `ui.notify(...)` error surface.
- Activity settings UI (existing activity edit page) extended with max_documents + allow_student_uploads fields.
- Unit test on `_can_add_document` across cartesian product `(is_instructor, allow_student_uploads, doc_count, max_documents)`.
- E2E: disabled button + tooltip for students; server-side rejection on bypass attempt.
- Migration test: existing Activities flip to locked-down.

**Dependencies:** Phase 2 (tab structure).

**Done when:** All DoD 7 acceptance criteria pass; migration applied cleanly on a seeded DB; existing Activities visibly show new defaults.

**Covers:** DoD 7.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Delete + CRDT purge verify-and-complete

**Goal:** Verify Plan A's delete flow (AC9.1–9.6) end-to-end; replace `ui.navigate.to()` in the delete path with the new broadcast + surgical tab-bar rebuild pattern; ensure CRDT purge + template protection intact.

**Components:**
- Instrumented E2E test covering: DB row removed; CRDT highlights with deleted `document_id` purged (call `remove_highlights_for_document()`); tab + panel removed from DOM; active tab switches correctly; template-clone `ProtectedDocumentError` raised; last-document delete leaves `+ | Organise | Respond`.
- `document_management.py:384` — replace `ui.navigate.to(...)` with a call that triggers local soft rebuild + `document_deleted` broadcast (Phase 8 provides the broadcast function; this phase stubs it inline or takes a dependency on Phase 8).
- Any gaps found flipped from fix-hat commit; followup refactor-hat commit for structural cleanup (if any).

**Dependencies:** Phase 2 (tab structure). Also interacts with Phase 8 (broadcast path) — see Additional Considerations for sequencing note.

**Done when:** All DoD 6 acceptance criteria pass; delete flow does not force a full navigation.

**Covers:** DoD 6.
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Organise/Respond source labels + cross-tab locate

**Goal:** Add `<Title>, para N` subtitle to cards in Organise/Respond; wire cross-tab locate so clicking locate on a card switches to the right source tab.

**Components:**
- `card_shared.py` — pure helper `resolve_source_label(document, paragraph_index) -> str`.
- `organise.py` + `respond.py` — card data gains `source_label` field; subtitle rendered above the highlight excerpt; no anonymisation (per DR5); fallback `Source N, para P` for NULL title.
- Dirty-flag pattern: on `document_renamed` event, set a per-tab dirty flag; next tab-switch rebuild refreshes subtitles. No foreground rebuild of non-active Organise/Respond tabs.
- `highlights.py` — `_warp_to_highlight(highlight_id, doc_id)` guarded at entry: if `doc_id != state.active_tab`, call `tabs.set_value(str(doc_id))` first, await tab change via a `Future` resolved inside the tab-change handler, then scroll.
- Deleted-doc guard: if `doc_id not in {d.id for d in state.documents}`, `ui.notify(...)` warning and return.
- Unit tests for `resolve_source_label` (including NULL-title fallback); E2E for cross-tab locate in a 3-document workspace.

**Dependencies:** Phase 1 (AC11/12 card infrastructure must be sound); Phase 3 (rename emits event); Phase 8 (broadcast wiring) — Phase 7 can land with local-only events and Phase 8 extends to peer events, or they can coordinate.

**Done when:** All DoD 4 and DoD 5 acceptance criteria pass.

**Covers:** DoD 4, DoD 5.
<!-- END_PHASE_7 -->

<!-- START_PHASE_8 -->
### Phase 8: Cross-client broadcast + soft rebuild + documentation

**Goal:** Extend `_RemotePresence` callback to carry `DocumentEvent`; route typed events to per-event surgical or soft-rebuild handlers; land user-facing documentation for the full Plan B feature set.

**Components:**
- `annotation/__init__.py` — `_RemotePresence.callback` signature becomes `Callable[[DocumentEvent | None], Awaitable[None]]`; `None` preserves existing highlight path.
- `broadcast.py` — `_notify_other_clients(workspace_id, *, event: DocumentEvent | None = None)`; callers fan events to peers.
- New `handle_document_event(event, state)` async handler with per-event behaviour:
  - `document_renamed` → surgical tab label update; dirty-flag Organise/Respond.
  - `workspace_renamed` → surgical header title update.
  - `document_added` → tab bar rebuild; do not switch peer's active tab.
  - `document_deleted` → tab bar rebuild; if peer's active tab matches deleted `document_id`, switch to next remaining (or `+`); drop the panel.
  - `document_reordered` → tab bar rebuild (affects `Source N` fallback numbering).
- In-flight-interaction safety: `is_deleted` guards on all element operations; side-effects before rebuilds; no `await run_javascript()` in rebuild paths (consistent with CLAUDE.md § E2E Race-Condition Patterns).
- E2E: two-browser-context test confirming each of the five event types produces the expected peer update without losing in-flight fill/click actions.
- `src/promptgrimoire/docs/scripts/using_promptgrimoire.py` — sections for managing sources (+ add, open manage dialog, rename, delete), workspace rename via header pencil, instructor controls (max_documents, allow_student_uploads). Screenshots of the implemented UI in both student-locked and instructor views. Citations to the test(s) verifying each claim.
- `uv run grimoire docs build` passes.
- `docs/architecture/dfd/5-annotate-texts.md` reviewed and updated to show the tab bar decomposition and broadcast event paths (per memory rule "Build architecture docs during design, not after").

**Dependencies:** Phases 2–7 (all feature events must be emitting from acting-client paths before peer fan-out goes live).

**Done when:** All DoD 8 and DoD 10 acceptance criteria pass; architecture DFD reflects the final component shape.

**Covers:** DoD 8, DoD 10.
<!-- END_PHASE_8 -->

## Additional Considerations

**Implementation scoping:** This design has 8 phases. The writing-plans skill limits implementation plans to 8 phases per plan, so Plan B fits a single implementation plan. However, Phase 1 is heavier than a typical feature phase (preemptive refactor + AC11/12 verify across 14 files). If Phase 1 findings are substantial, it may need to split into a standalone predecessor implementation plan (Plan B-prep) followed by the Plan B feature plan covering Phases 2–8. Decision to be taken at impl-plan-write time after Phase 1 scope is actually known.

**Phase 6 / Phase 8 dependency:** Phase 6 (delete refactor) references the broadcast pipe that Phase 8 introduces. Two execution strategies: (a) Phase 6 stubs the broadcast call with a local-only implementation and Phase 8 wires the peer fan-out; (b) Phase 8's broadcast infrastructure lands first under that phase's refactor scope, with Phase 6 filling in the delete use case. The implementation plan picks one; either preserves the design's intent.

**Race condition surface:** The design introduces three new paths that interact with the existing `_RemotePresence` callback fan-out. Each must respect the CLAUDE.md § E2E Race-Condition Patterns: fire-and-forget JS, value-capture on submits, rebuild-epoch awaiting in tests, lightweight peer-left semantics, side-effects before container rebuilds, `is_deleted` guards before explicit `element.delete()`. Phase 8's two-browser-context E2E tests exercise concurrent-peer-action scenarios; the existing `nicegui_user` fixture pattern is reused.

**Breaking change rollout (DR6):** The Alembic migration in Phase 5 flips all existing Activities to `allow_student_uploads=False`. Deploy plan: (1) notify instructors via Discord alert before deploy; (2) run migration as part of `deploy/restart.sh` normal cycle; (3) post-deploy audit query lists Activities whose defaults changed; (4) instructors can opt back in via the Activity settings page. No per-instance toggle for "preserve old behaviour" — a clean-cut migration is simpler to reason about than a feature flag with unclear lifetime.

**Out of scope:** Course-level defaults for instructor controls; per-week overrides; per-student upload quotas; drag-reorder on the tab strip itself (reorder is via manage dialog); soft-delete / restore of documents; bulk document operations; mobile-specific gestures; document versioning or history; per-Activity whitelist of document types.

**Performance posture:** Soft rebuild (DR2), lazy-loaded dialog (DR3), and surgical updates for rename/workspace-rename events all align with ongoing event-loop saturation and memory work. Phase 8's two-browser-context E2E tests additionally capture event-loop lag during broadcast fan-out — if the lag crosses the AIMD threshold during test runs, surface it as a blocker rather than a flake.
