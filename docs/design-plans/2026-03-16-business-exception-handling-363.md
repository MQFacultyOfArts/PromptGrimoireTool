# Business Exception Handling Design

**GitHub Issue:** #363

## Summary

PromptGrimoire's database layer raises two categories of exceptions: expected business logic rejections (duplicate names, permission violations, protected resources) and genuine unexpected failures. Currently both categories are handled identically — the generic `get_session()` context manager logs every exception at ERROR level and fires a Discord webhook alert, meaning routine user errors (trying to share a workspace that has sharing disabled, or deleting a document they don't own) generate the same alert noise as real infrastructure problems. This work fixes that signal-to-noise problem.

The approach has four independent parts. First, a `BusinessLogicError` base class is introduced in `db/exceptions.py`, and all ten existing domain exception classes — currently scattered across modules and inheriting from `Exception`, `ValueError`, or Python's built-in `PermissionError` — are reparented under it. Three new named subclasses replace bare `PermissionError` raises in the sharing, ownership, and tag-creation paths. Second, `get_session()` gets a new `except BusinessLogicError` clause that logs at WARNING (no Discord) while keeping the existing ERROR path for unexpected exceptions. Third, a UI guard on the "Share with user" button in `sharing.py` is brought in line with the existing "Share with class" guard — non-staff users see the button only when sharing is permitted. Fourth, the `PlacementContext` default for loose workspaces (those not attached to any activity or course) changes from `allow_sharing=False` to `allow_sharing=True`, since no course policy restricts them.

## Definition of Done

1. A `BusinessLogicError` base class exists in `db/exceptions.py`. All domain exceptions (`DuplicateNameError`, `DeletionBlockedError`, `DuplicateCodenameError`, `ZeroEditorError`, `ProtectedDocumentError`, `DuplicateEnrollmentError`, `StudentIdConflictError`) inherit from it. All bare `PermissionError` raises in `src/promptgrimoire/db/` are replaced with `SharePermissionError`, `OwnershipError`, or `TagCreationDeniedError` (all `BusinessLogicError` subclasses).
2. `get_session()` catches `BusinessLogicError` subclasses at WARNING level (no Discord webhook), while keeping ERROR + Discord for unexpected exceptions.
3. Share button visibility (`sharing.py:68`) guards on `allow_sharing` for non-staff users, with a staff bypass matching the backend contract (`_validate_share_grantor` line 440). Non-staff see the button only when sharing is enabled; staff always see it. Combined with item 4, loose workspace owners can always share.
4. Loose workspaces default `allow_sharing=True` in `PlacementContext` — no course policy applies, so sharing is unrestricted.
5. ~~Discord alert embeds include the exception class name.~~ Already implemented — `logging_discord.py:114-150` includes exception type in dedup key and embed description. No work needed.

## Acceptance Criteria

### business-exception-handling-363.AC1: Exception Taxonomy
- **AC1.1 Success:** All 10 domain exceptions (`DuplicateNameError`, `DeletionBlockedError`, `DuplicateCodenameError`, `ZeroEditorError`, `ProtectedDocumentError`, `DuplicateEnrollmentError`, `StudentIdConflictError`, `SharePermissionError`, `OwnershipError`, `TagCreationDeniedError`) are `isinstance(exc, BusinessLogicError)`
- **AC1.2 Success:** `SharePermissionError` replaces bare `PermissionError` at `acl.py:417`, `acl.py:453`, `acl.py:456`, `acl.py:475`
- **AC1.3 Success:** `OwnershipError` replaces bare `PermissionError` at `workspaces.py:443`, `workspace_documents.py:259`
- **AC1.4 Success:** `TagCreationDeniedError` replaces bare `PermissionError` at `tags.py:53`, `tags.py:716`
- **AC1.5 Success:** `str(SharePermissionError("msg"))` == `"msg"` (user-facing message preservation for `sharing.py:199`)
- **AC1.6 Success (intentional breaking change):** `DuplicateNameError` is NOT `isinstance(exc, ValueError)`. Deliberate reparenting — callers already catch by class name, not via `ValueError`.
- **AC1.7 Success:** `BusinessLogicError`, `SharePermissionError`, `OwnershipError`, `TagCreationDeniedError` exported in `db/__init__.py.__all__`. All existing exception exports preserved.
- **AC1.8 Success:** No bare `PermissionError` raises remain in `src/promptgrimoire/db/`

### business-exception-handling-363.AC2: get_session() Exception Triage
- **AC2.1 Success:** `BusinessLogicError` raised inside `get_session()` → transaction rolled back, `logger.warning()` called (NOT `logger.exception()`), exception re-raised to caller
- **AC2.2 Success:** Unexpected `Exception` raised inside `get_session()` → transaction rolled back, `logger.exception()` (ERROR) called, exception re-raised to caller
- **AC2.3 Success:** Business-exception branch uses a distinct event name (NOT "Database session error, rolling back transaction")
- **AC2.4 Success:** Both branches include `exc_class` field in structured log output
- **AC2.5 Failure:** `BusinessLogicError` does NOT trigger Discord webhook (WARNING level, not ERROR)
- **AC2.6 Integration:** `grant_share(..., sharing_allowed=False)` raises `SharePermissionError` and does NOT produce "Database session error" log event
- **AC2.7 Integration:** `delete_workspace()` by non-owner raises `OwnershipError` and does NOT produce "Database session error" log event

### business-exception-handling-363.AC3: Share Button Visibility
- **AC3.1 Success:** Share button rendered when `allow_sharing=True` and `can_manage_sharing=True`
- **AC3.2 Failure:** Share button NOT rendered when `allow_sharing=False` and `viewer_is_privileged=False`, regardless of `can_manage_sharing`
- **AC3.3 Success:** Share button rendered for staff (`viewer_is_privileged=True`) even when `allow_sharing=False` — staff bypass preserved
- **AC3.4 Success:** "Share with class" toggle still gated on both `allow_sharing` and `can_manage_sharing` (regression guard)

### business-exception-handling-363.AC4: Loose Workspace Sharing Default
- **AC4.1 Success:** `PlacementContext(placement_type="loose").allow_sharing` is `True`
- **AC4.2 Success:** `get_placement_context()` for workspace with no activity and no course returns `allow_sharing=True`
- **AC4.3 Success:** Activity-placed workspace `allow_sharing` still resolved from `resolve_tristate(activity.allow_sharing, course.default_allow_sharing)` — unaffected
- **AC4.4 Success:** Course-placed workspace `allow_sharing` still resolved from `course.default_allow_sharing` — unaffected

## Glossary

- **`BusinessLogicError`**: New base exception class for all expected, user-facing error conditions raised inside the database layer. Distinguishes anticipated rejections from genuine failures.
- **`get_session()`**: Async context manager in `db/engine.py` that wraps every database operation — commit on success, rollback on exception. All 159 DB call sites use it.
- **Discord webhook alerting**: ERROR-level log events are sent to a Discord channel as formatted embeds for production incident alerting. WARNING-level events do not trigger it.
- **Bare `PermissionError`**: Python's built-in `PermissionError`, raised in the DB layer without a project-specific subclass. Replaced by named subclasses so callers and the logger can distinguish share violations from ownership violations from tag denials.
- **`SharePermissionError`**: New exception for sharing policy violations. Replaces bare `PermissionError` in `acl.py`.
- **`OwnershipError`**: New exception for non-owner delete attempts. Replaces bare `PermissionError` in `workspaces.py` and `workspace_documents.py`.
- **`TagCreationDeniedError`**: New exception for tag creation permission denial. Replaces bare `PermissionError` in `tags.py`.
- **Reparenting**: Changing an exception class's base class (e.g. from `ValueError` to `BusinessLogicError`) without moving or renaming it.
- **`PlacementContext`**: Dataclass in `workspaces.py` that describes where a workspace sits in the course/activity/loose hierarchy and what sharing policy applies.
- **Loose workspace**: A workspace not attached to any activity or course. Has no course-level sharing policy to inherit.
- **`allow_sharing`**: Boolean on `PlacementContext` (and `Activity`/`Course` models) controlling whether workspace owners may share with other users.
- **`viewer_is_privileged`**: Boolean indicating a staff member (instructor or admin). Staff bypass sharing restrictions in the UI.
- **`resolve_tristate()`**: Resolves a nullable boolean activity-level field against a course default — activity wins if set, otherwise falls back to course.
- **`exc_class`**: Structured log field added to both `get_session()` exception branches, recording the Python class name for log filtering.
- **`db/__init__.py.__all__`**: Public surface of the `db` package. New exception classes must be added here for UI callers to import.

## Architecture

### Exception Triage in get_session()

`get_session()` (`db/engine.py:266-302`) is the single context manager through which all DB operations flow (159 call sites across 20 files). Its generic `except Exception` handler logs at ERROR level, triggering Discord webhooks for every exception — including expected business logic rejections.

The fix adds a new `except BusinessLogicError` clause **before** the generic handler:

```python
async with session_factory() as session:
    try:
        yield session
        await session.commit()
    except BusinessLogicError as exc:
        logger.warning(
            "Business logic error, rolling back transaction",
            exc_class=type(exc).__name__,
        )
        await session.rollback()
        raise
    except Exception as exc:
        logger.exception(
            "Database session error, rolling back transaction",
            exc_class=type(exc).__name__,
        )
        await session.rollback()
        raise
```

Both branches roll back and re-raise. The only difference is log level: WARNING (no Discord) vs ERROR (Discord webhook fires). The `exc_class` field is added to both branches for structured log enrichment.

### Exception Taxonomy

All domain exceptions inherit from `BusinessLogicError(Exception)` in `db/exceptions.py`:

```
BusinessLogicError(Exception)
├── SharePermissionError     # new: replaces bare PermissionError in acl.py share path
├── OwnershipError           # new: replaces bare PermissionError in delete-ownership checks
├── TagCreationDeniedError   # new: replaces bare PermissionError in tags.py creation guards
├── DuplicateNameError       # reparented from ValueError
├── DuplicateCodenameError   # reparented from Exception
├── ZeroEditorError          # reparented from Exception
├── DeletionBlockedError     # reparented from Exception
├── ProtectedDocumentError   # reparented from Exception
├── DuplicateEnrollmentError # reparented from Exception
└── StudentIdConflictError   # reparented from Exception
```

Bare `ValueError` raises in DB code are **not** reparented — they represent programming errors or unexpected states that should continue to alarm at ERROR level.

### Scope Boundary: Incident-Critical vs Consistency-Only

Only exceptions raised **inside** `get_session()` blocks hit the generic handler. Exceptions raised before entering `get_session()` never reach it.

**In scope (incident-critical — raised inside `get_session()`):**

| Exception | Locations |
|-----------|-----------|
| `PermissionError` → `SharePermissionError` | `acl.py:453`, `acl.py:456`, `acl.py:475` |
| `PermissionError` → `OwnershipError` | `workspaces.py:443`, `workspace_documents.py:259` |
| `DuplicateNameError` | `tags.py:130`, `tags.py:323` |
| `DuplicateCodenameError` | `wargames.py:231`, `wargames.py:753` |
| `ZeroEditorError` | `wargames.py:297`, `wargames.py:369` |
| `DeletionBlockedError` | `courses.py:245`, `weeks.py:275`, `activities.py:207` |
| `ProtectedDocumentError` | `workspace_documents.py:244` |
| `DuplicateEnrollmentError` | `courses.py:275` |
| `StudentIdConflictError` | `enrolment.py:31` |

**Also in scope (consistency — raised before `get_session()`, doesn't hit handler, but avoids sloppy inconsistency):**

| Exception | Locations | Rationale |
|-----------|-----------|-----------|
| `PermissionError` → `SharePermissionError` | `acl.py:417` | Same file as other share raises |
| `PermissionError` → `TagCreationDeniedError` | `tags.py:53`, `tags.py:716` | Complete DB-layer PermissionError elimination |

**Out of scope:**

| Exception | Rationale |
|-----------|-----------|
| All bare `ValueError` in DB code | Want alerting — these are programming errors |

### Share Button Visibility Fix

`sharing.py:68` renders the "Share with user" button when `can_manage_sharing` is true, regardless of `allow_sharing`. Line 48 correctly guards on both for the "Share with class" toggle.

Fix: add `allow_sharing` to the guard at line 68, but preserve the staff bypass. The backend (`_validate_share_grantor` line 440) already allows staff to share when sharing is disabled — the UI must match:

```python
# Before (line 68):
if can_manage_sharing:

# After:
if (allow_sharing or viewer_is_privileged) and can_manage_sharing:
```

This differs from line 48 ("Share with class" toggle) which does NOT have a staff bypass — class-level sharing is a student-facing toggle, not a staff override.

### Loose Workspace Sharing Default

`PlacementContext` (`workspaces.py:142`) defaults `allow_sharing=False`. Loose workspaces (no activity, no course) inherit this default. Since no course policy applies to loose workspaces, sharing should be unrestricted.

Fix: change the default in `PlacementContext` from `allow_sharing: bool = False` to `allow_sharing: bool = True`.

This affects all `PlacementContext(placement_type="loose")` constructions:
- `get_placement_context()` line 279 (intentionally loose) and line 282 (workspace not found)
- `get_workspace_export_metadata()` line 255
- Orphan fallbacks in `_resolve_activity_placement()` lines 324, 327, 330 and `_resolve_course_placement()` line 371

Activity-placed and course-placed workspaces with intact hierarchies are unaffected — they resolve `allow_sharing` explicitly. The orphan/not-found fallbacks are defensive paths for broken hierarchy data; allowing sharing for those is acceptable since there's no course policy to enforce. See Additional Considerations for full blast radius analysis.

## Existing Patterns

**Exception handling pattern:** The codebase already has domain exceptions in `db/exceptions.py` (`DeletionBlockedError`, `ProtectedDocumentError`) and module-local exceptions (`DuplicateNameError` in `tags.py`, `DuplicateCodenameError`/`ZeroEditorError` in `wargames.py`, `DuplicateEnrollmentError` in `courses.py`, `StudentIdConflictError` in `enrolment.py`). This design consolidates them under a common base without changing their locations — exceptions stay where they're defined, just gain a shared parent.

**UI error handling pattern:** Callers catch specific exceptions and call `ui.notify(str(exc))` for user-facing messages (e.g., `sharing.py:198`, `tag_management.py:412`). This pattern is preserved — `str(exc)` continues to work because the new exceptions pass messages through unchanged.

**Sharing guard pattern:** `sharing.py:48` gates on both `allow_sharing and can_manage_sharing`. The fix at line 68 follows this existing pattern.

**Public surface:** `db/__init__.py` exports exceptions via `__all__`. New exceptions (`BusinessLogicError`, `SharePermissionError`, `OwnershipError`, `TagCreationDeniedError`) must be added to both the import list and `__all__`.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Exception Taxonomy
**Goal:** Establish `BusinessLogicError` base class and reparent all domain exceptions.

**Components:**
- `BusinessLogicError` base class in `db/exceptions.py`
- `SharePermissionError(BusinessLogicError)` in `db/exceptions.py` — new
- `OwnershipError(BusinessLogicError)` in `db/exceptions.py` — new
- `TagCreationDeniedError(BusinessLogicError)` in `db/exceptions.py` — new
- `DeletionBlockedError` in `db/exceptions.py` — reparent to `BusinessLogicError`
- `ProtectedDocumentError` in `db/exceptions.py` — reparent to `BusinessLogicError`
- `DuplicateNameError` in `db/tags.py` — reparent from `ValueError` to `BusinessLogicError`
- `DuplicateCodenameError` in `db/wargames.py` — reparent to `BusinessLogicError`
- `ZeroEditorError` in `db/wargames.py` — reparent to `BusinessLogicError`
- `DuplicateEnrollmentError` in `db/courses.py` — reparent to `BusinessLogicError`
- `StudentIdConflictError` in `db/enrolment.py` — reparent to `BusinessLogicError`
- Replace bare `PermissionError` raises: `acl.py:417,453,456,475` → `SharePermissionError`, `workspaces.py:443` → `OwnershipError`, `workspace_documents.py:259` → `OwnershipError`, `tags.py:53,716` → `TagCreationDeniedError`
- Update `db/__init__.py` imports and `__all__`
- Update UI callers that catch `PermissionError`: `sharing.py:198`, `navigator/_cards.py:223`, `document_management.py:315`, `courses.py:319`, `tag_management.py:412`, `tag_management_save.py:137`, `tag_import.py:113`

**Dependencies:** None (first phase)

**Covers:** `business-exception-handling-363.AC1.*`

**Done when:** All domain exceptions inherit from `BusinessLogicError`. No bare `PermissionError` remains in `src/promptgrimoire/db/`. Existing tests updated (`test_sharing_controls.py`, `test_delete_guards.py`, `test_tag_crud.py`, `test_tag_management.py`). New isinstance tests pass for all 10 exception classes. `__str__` preservation verified.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: get_session() Exception Triage
**Goal:** Add `BusinessLogicError` catch clause to `get_session()` with WARNING-level logging.

**Components:**
- `db/engine.py` `get_session()` — new `except BusinessLogicError` clause before generic handler, `exc_class` field on both branches
- New test file `tests/unit/test_db_engine.py` — tests both branches

**Dependencies:** Phase 1 (exception classes must exist)

**Covers:** `business-exception-handling-363.AC2.*`

**Done when:** `BusinessLogicError` inside `get_session()` logs at WARNING with `exc_class`, rolls back, re-raises. Unexpected `Exception` logs at ERROR with `exc_class`, rolls back, re-raises. Both verified by unit tests.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Share Button Visibility Fix
**Goal:** Hide "Share with user" button when sharing is disabled for non-staff users. Staff retain bypass.

**Components:**
- `pages/annotation/sharing.py` line 68 — change guard to `(allow_sharing or viewer_is_privileged) and can_manage_sharing`
- New tests for share button visibility across all combinations of `allow_sharing`, `viewer_is_privileged`, and `can_manage_sharing`

**Dependencies:** None (independent of Phases 1-2, but logically grouped)

**Covers:** `business-exception-handling-363.AC3.*`

**Done when:** Share button hidden for non-staff when `allow_sharing=False`. Share button visible for staff regardless of `allow_sharing`. "Share with class" toggle unchanged (regression guard).
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Loose Workspace Sharing Default
**Goal:** Loose workspaces default `allow_sharing=True`.

**Components:**
- `db/workspaces.py` `PlacementContext` — change `allow_sharing` default from `False` to `True`
- New test: `get_placement_context()` for loose workspace returns `allow_sharing=True`
- New test: `PlacementContext(placement_type="loose").allow_sharing is True`

**Dependencies:** None (independent of Phases 1-3)

**Covers:** `business-exception-handling-363.AC4.*`

**Done when:** Loose workspaces have `allow_sharing=True`. Activity-placed and course-placed workspaces unaffected (their `allow_sharing` is resolved from hierarchy). Tests verify both the default and the `get_placement_context()` path.
<!-- END_PHASE_4 -->

## Additional Considerations

**Caller migration:** All UI callers that catch `PermissionError` from DB functions must be updated to the specific subclass. Share path callers → `SharePermissionError`. Delete path callers → `OwnershipError`. Tag creation callers → `TagCreationDeniedError`.

**Test migration:** `test_sharing_controls.py` (5 sites) → `SharePermissionError`. `test_delete_guards.py` (1 site) → `OwnershipError`. `test_tag_crud.py:499,545,2123` and `test_tag_management.py:130` → `TagCreationDeniedError`.

**Caller found by proleptic challenge:** `courses.py:319` catches `PermissionError` from `delete_workspace()` — must be updated to `OwnershipError`.

**PlacementContext default change blast radius:** Changing `allow_sharing` from `False` to `True` affects ALL `PlacementContext(placement_type="loose")` constructions, including:
- Intentionally loose workspaces (no activity, no course) — desired behaviour change
- Orphan fallbacks in `_resolve_activity_placement()` lines 324, 327, 330 (missing Activity/Week/Course rows) — also gets `allow_sharing=True`
- Orphan fallback in `_resolve_course_placement()` line 371 (missing Course row) — also gets `allow_sharing=True`
- `get_placement_context()` line 282 when workspace is `None` (not found) — also gets `allow_sharing=True`

The orphan and not-found cases are defensive fallbacks for broken hierarchy data. Callers of `get_placement_context()` (`header.py`, `workspace.py`, `tags.py`) are UI-rendering contexts that already require the workspace to exist — the `workspace is None` path is unreachable in normal operation. Allowing sharing for orphaned workspaces is acceptable: if the hierarchy is broken, there's no course policy to enforce.

Activity-placed and course-placed workspaces with intact hierarchies are unaffected — they resolve `allow_sharing` explicitly via `resolve_tristate()` or from `course.default_allow_sharing`.
