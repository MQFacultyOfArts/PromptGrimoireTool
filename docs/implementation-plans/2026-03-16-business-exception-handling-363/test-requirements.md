# Test Requirements — Business Exception Handling (#363)

**Design plan:** `docs/design-plans/2026-03-16-business-exception-handling-363.md`
**Implementation plans:** `docs/implementation-plans/2026-03-16-business-exception-handling-363/phase_01.md` through `phase_04.md`

## Methodology

Every acceptance criterion from the design plan maps to either an automated test or a documented human verification step. Automated tests are classified by lane (unit, integration, E2E) following the project's test lane model. Human verification is reserved for criteria that require production environment state, visual inspection, or external system interaction that cannot be reliably automated.

Implementation plan decisions that affect testing are noted where they diverge from the original design (e.g., consolidation of exceptions into `db/exceptions.py` rather than in-place reparenting).

---

## AC1: Exception Taxonomy

### AC1.1 — All 10 domain exceptions are `isinstance(exc, BusinessLogicError)`

| Aspect | Value |
|--------|-------|
| Test type | Unit |
| Test file | `tests/unit/test_exception_taxonomy.py` |
| Strategy | Instantiate each of the 10 exception classes with valid constructor arguments. Assert `isinstance(exc, BusinessLogicError)` for each. |
| Implementation note | Phase 1 Task 2 consolidates all exceptions into `db/exceptions.py` (design divergence approved during planning). Tests import from `db.exceptions` directly. |

### AC1.2 — `SharePermissionError` replaces bare `PermissionError` at acl.py:417, 453, 456, 475

| Aspect | Value |
|--------|-------|
| Test type | Unit (structural) |
| Test file | `tests/unit/test_exception_taxonomy.py` |
| Strategy | ast-grep structural assertion: `sg run -p 'raise PermissionError($$$)' -l py src/promptgrimoire/db/acl.py` returns zero matches. Complementary positive assertion: `sg run -p 'raise SharePermissionError($$$)'` returns 4 matches. |
| Existing coverage | `tests/unit/test_sharing_controls.py` (5 sites at lines 196, 214, 232, 252, 269) already tests the share rejection paths. Phase 1 Task 4 updates these to assert `SharePermissionError` instead of `PermissionError`. |

### AC1.3 — `OwnershipError` replaces bare `PermissionError` at workspaces.py:443, workspace_documents.py:259

| Aspect | Value |
|--------|-------|
| Test type | Unit (structural + behavioural) |
| Test file | `tests/unit/test_exception_taxonomy.py` (structural), `tests/unit/test_delete_guards.py` (behavioural) |
| Strategy | Structural: ast-grep confirms zero `raise PermissionError` in `workspaces.py` and `workspace_documents.py`. Behavioural: `test_delete_guards.py` line 346 updated to assert `OwnershipError`. |

### AC1.4 — `TagCreationDeniedError` replaces bare `PermissionError` at tags.py:53, 716

| Aspect | Value |
|--------|-------|
| Test type | Unit (structural + behavioural) |
| Test file | `tests/unit/test_exception_taxonomy.py` (structural), `tests/unit/test_tag_crud.py` + `tests/unit/test_tag_management.py` (behavioural) |
| Strategy | Structural: ast-grep confirms zero `raise PermissionError` in `tags.py`. Behavioural: `test_tag_crud.py` lines 499, 545, 2123 and `test_tag_management.py` line 130 updated to assert `TagCreationDeniedError`. |

### AC1.5 — `str(SharePermissionError("msg"))` == `"msg"`

| Aspect | Value |
|--------|-------|
| Test type | Unit |
| Test file | `tests/unit/test_exception_taxonomy.py` |
| Strategy | Construct `SharePermissionError("user-facing message")` and assert `str(exc) == "user-facing message"`. Critical because `sharing.py:199` displays `str(exc)` via `ui.notify()`. |

### AC1.6 — `DuplicateNameError` is NOT `isinstance(exc, ValueError)`

| Aspect | Value |
|--------|-------|
| Test type | Unit |
| Test file | `tests/unit/test_exception_taxonomy.py` |
| Strategy | `assert not isinstance(DuplicateNameError("test"), ValueError)`. Verifies intentional reparenting from `ValueError` to `BusinessLogicError`. |

### AC1.7 — New exceptions exported in `db/__init__.py.__all__`

| Aspect | Value |
|--------|-------|
| Test type | Unit |
| Test file | `tests/unit/test_exception_taxonomy.py` |
| Strategy | `from promptgrimoire.db import BusinessLogicError, SharePermissionError, OwnershipError, TagCreationDeniedError` — import succeeds. Also verify all 11 exceptions appear in `promptgrimoire.db.__all__`. |

### AC1.8 — No bare `PermissionError` raises remain in `src/promptgrimoire/db/`

| Aspect | Value |
|--------|-------|
| Test type | Unit (structural guard) |
| Test file | `tests/unit/test_exception_taxonomy.py` |
| Strategy | Run `sg run -p 'raise PermissionError($$$)' -l py src/promptgrimoire/db/` via subprocess and assert zero matches. Guard test that prevents regression. |

---

## AC2: get_session() Exception Triage

### AC2.1 — `BusinessLogicError` inside `get_session()` rolls back, warns, re-raises

| Aspect | Value |
|--------|-------|
| Test type | Unit |
| Test file | `tests/unit/test_db_engine.py` |
| Strategy | Patch `promptgrimoire.db.engine.logger`. Use mock session factory. Raise `BusinessLogicError` inside `async with get_session()`. Assert: (1) `session.rollback()` called, (2) `logger.warning()` called, (3) `logger.exception()` NOT called, (4) exception propagates to caller. |

### AC2.2 — Unexpected `Exception` inside `get_session()` rolls back, errors, re-raises

| Aspect | Value |
|--------|-------|
| Test type | Unit |
| Test file | `tests/unit/test_db_engine.py` |
| Strategy | Same setup as AC2.1 but raise `RuntimeError`. Assert: (1) `session.rollback()` called, (2) `logger.exception()` called (ERROR level), (3) exception propagates. |

### AC2.3 — Business-exception branch uses distinct event name

| Aspect | Value |
|--------|-------|
| Test type | Unit |
| Test file | `tests/unit/test_db_engine.py` |
| Strategy | Assert `logger.warning()` called with first positional arg `"Business logic error, rolling back transaction"`. Assert this differs from the generic branch's `"Database session error, rolling back transaction"`. |

### AC2.4 — Both branches include `exc_class` field

| Aspect | Value |
|--------|-------|
| Test type | Unit |
| Test file | `tests/unit/test_db_engine.py` |
| Strategy | For BusinessLogicError branch: assert `logger.warning()` kwargs include `exc_class="BusinessLogicError"`. For Exception branch: assert `logger.exception()` kwargs include `exc_class="RuntimeError"`. |

### AC2.5 — `BusinessLogicError` does NOT trigger Discord webhook

| Aspect | Value |
|--------|-------|
| Test type | Unit + Human |
| Test file | `tests/unit/test_db_engine.py` |
| Strategy | Unit: AC2.1 verifies `logger.warning()` (not `logger.exception()`/`logger.error()`). WARNING level does not trigger Discord per `logging_discord.py:110-112`. Human: production verification (see HV1). |

### AC2.6 — `grant_share()` with sharing disabled produces correct triage

| Aspect | Value |
|--------|-------|
| Test type | Integration |
| Test file | `tests/integration/test_business_exception_triage.py` |
| Strategy | Real DB: create user, workspace, set `sharing_allowed=False`. Call `grant_share()`. Assert: (1) raises `SharePermissionError`, (2) log contains `"Business logic error"` at WARNING, (3) no `"Database session error"` event. |

### AC2.7 — `delete_workspace()` by non-owner produces correct triage

| Aspect | Value |
|--------|-------|
| Test type | Integration |
| Test file | `tests/integration/test_business_exception_triage.py` |
| Strategy | Real DB: create owner, workspace, non-owner. Call `delete_workspace()` as non-owner. Assert: (1) raises `OwnershipError`, (2) log contains `"Business logic error"` at WARNING, (3) no `"Database session error"`. |

---

## AC3: Share Button Visibility

### AC3.1 — Button rendered when `allow_sharing=True` and `can_manage_sharing=True`

| Aspect | Value |
|--------|-------|
| Test type | Unit |
| Test file | `tests/unit/test_sharing_button_visibility.py` |
| Strategy | Evaluate `(allow_sharing or viewer_is_privileged) and can_manage_sharing` with `allow_sharing=True, can_manage_sharing=True, viewer_is_privileged=False`. Assert True. |

### AC3.2 — Button NOT rendered when `allow_sharing=False` and non-staff

| Aspect | Value |
|--------|-------|
| Test type | Unit |
| Test file | `tests/unit/test_sharing_button_visibility.py` |
| Strategy | Evaluate with `allow_sharing=False, can_manage_sharing=True, viewer_is_privileged=False`. Assert False. |

### AC3.3 — Button rendered for staff even when `allow_sharing=False`

| Aspect | Value |
|--------|-------|
| Test type | Unit |
| Test file | `tests/unit/test_sharing_button_visibility.py` |
| Strategy | Evaluate with `allow_sharing=False, can_manage_sharing=True, viewer_is_privileged=True`. Assert True (staff bypass). |

### AC3.4 — "Share with class" toggle still gated correctly (regression guard)

| Aspect | Value |
|--------|-------|
| Test type | Unit |
| Test file | `tests/unit/test_sharing_button_visibility.py` |
| Strategy | Evaluate `allow_sharing and can_manage_sharing` with `allow_sharing=False, viewer_is_privileged=True`. Assert False — staff bypass does NOT apply to class toggle. Structural guard via ast-grep verifies exact expression at line 68. |

---

## AC4: Loose Workspace Sharing Default

### AC4.1 — `PlacementContext(placement_type="loose").allow_sharing` is `True`

| Aspect | Value |
|--------|-------|
| Test type | Unit |
| Test file | `tests/integration/test_workspace_placement.py` |
| Strategy | Construct `PlacementContext(placement_type="loose")`. Assert `ctx.allow_sharing is True`. |

### AC4.2 — `get_placement_context()` for loose workspace returns `allow_sharing=True`

| Aspect | Value |
|--------|-------|
| Test type | Integration |
| Test file | `tests/integration/test_workspace_placement.py` |
| Strategy | Create workspace with no activity/course in real DB. Call `get_placement_context()`. Assert `result.allow_sharing is True`. |

### AC4.3 — Activity-placed workspace unaffected

| Aspect | Value |
|--------|-------|
| Test type | Integration |
| Test file | `tests/integration/test_workspace_placement.py` |
| Strategy | Regression guard: course with `default_allow_sharing=False`, activity with `allow_sharing=None`. Assert `get_placement_context()` returns `allow_sharing=False`. |

### AC4.4 — Course-placed workspace unaffected

| Aspect | Value |
|--------|-------|
| Test type | Integration |
| Test file | `tests/integration/test_workspace_placement.py` |
| Strategy | Regression guard: course with `default_allow_sharing=False`, workspace placed under course. Assert `get_placement_context()` returns `allow_sharing=False`. |

---

## Human Verification

### HV1: Discord webhook does NOT fire for business logic exceptions (AC2.5 production)

| Aspect | Value |
|--------|-------|
| Criteria | AC2.5 |
| Justification | Unit test verifies WARNING log level. Full production path (structlog processors → Discord HTTP webhook) needs production verification. |
| Verification | Deploy. Trigger sharing policy violation as non-staff user. Check Discord: no alert. Check logs: WARNING event with `exc_class=SharePermissionError`. |

### HV2: Share button visibility in live UI (AC3.1, AC3.2, AC3.3)

| Aspect | Value |
|--------|-------|
| Criteria | AC3.1, AC3.2, AC3.3 |
| Justification | Automated tests verify boolean logic. Live rendering depends on NiceGUI runtime. |
| Verification | (1) Non-staff user, workspace with `allow_sharing=False`: button absent. (2) Staff user, same workspace: button present. (3) Non-staff user, workspace with `allow_sharing=True`: button present. |

### HV3: Loose workspace sharing works end-to-end (AC4.1, AC4.2)

| Aspect | Value |
|--------|-------|
| Criteria | AC4.1, AC4.2 |
| Justification | Integration tests verify `get_placement_context()` default. Full UI flow (workspace creation → header → share button → share grant) not covered by E2E tests. |
| Verification | Create loose workspace. Navigate to it. Share button visible. Share with another user succeeds. |

---

## Test File Summary

| Test file | Lane | Phase | Criteria |
|-----------|------|-------|----------|
| `tests/unit/test_exception_taxonomy.py` | Unit | 1 | AC1.1-AC1.8 |
| `tests/unit/test_sharing_controls.py` | Unit | 1 | AC1.2 (behavioural) |
| `tests/unit/test_delete_guards.py` | Unit | 1 | AC1.3 (behavioural) |
| `tests/unit/test_tag_crud.py` | Unit | 1 | AC1.4 (behavioural) |
| `tests/unit/test_tag_management.py` | Unit | 1 | AC1.4 (behavioural) |
| `tests/unit/test_db_engine.py` | Unit | 2 | AC2.1-AC2.5 |
| `tests/integration/test_business_exception_triage.py` | Integration | 2 | AC2.6, AC2.7 |
| `tests/unit/test_sharing_button_visibility.py` | Unit | 3 | AC3.1-AC3.4 |
| `tests/integration/test_workspace_placement.py` | Integration | 4 | AC4.1-AC4.4 |

## Coverage Matrix

| AC | Automated | Human | Notes |
|----|-----------|-------|-------|
| AC1.1 | `test_exception_taxonomy.py` | -- | isinstance for all 10 |
| AC1.2 | `test_exception_taxonomy.py` + `test_sharing_controls.py` | -- | Structural + behavioural |
| AC1.3 | `test_exception_taxonomy.py` + `test_delete_guards.py` | -- | Structural + behavioural |
| AC1.4 | `test_exception_taxonomy.py` + `test_tag_crud.py` + `test_tag_management.py` | -- | Structural + behavioural |
| AC1.5 | `test_exception_taxonomy.py` | -- | `str()` preservation |
| AC1.6 | `test_exception_taxonomy.py` | -- | Not ValueError |
| AC1.7 | `test_exception_taxonomy.py` | -- | Import + `__all__` |
| AC1.8 | `test_exception_taxonomy.py` | -- | ast-grep guard |
| AC2.1 | `test_db_engine.py` | -- | Mock session |
| AC2.2 | `test_db_engine.py` | -- | Mock session |
| AC2.3 | `test_db_engine.py` | -- | Event name |
| AC2.4 | `test_db_engine.py` | -- | `exc_class` kwarg |
| AC2.5 | `test_db_engine.py` | HV1 | Log level + production |
| AC2.6 | `test_business_exception_triage.py` | -- | Real DB + log |
| AC2.7 | `test_business_exception_triage.py` | -- | Real DB + log |
| AC3.1 | `test_sharing_button_visibility.py` | HV2 | Boolean + live UI |
| AC3.2 | `test_sharing_button_visibility.py` | HV2 | Boolean + live UI |
| AC3.3 | `test_sharing_button_visibility.py` | HV2 | Boolean + live UI |
| AC3.4 | `test_sharing_button_visibility.py` | -- | Regression guard |
| AC4.1 | `test_workspace_placement.py` | HV3 | Dataclass default |
| AC4.2 | `test_workspace_placement.py` | HV3 | Integration + live UI |
| AC4.3 | `test_workspace_placement.py` | -- | Regression guard |
| AC4.4 | `test_workspace_placement.py` | -- | Regression guard |
