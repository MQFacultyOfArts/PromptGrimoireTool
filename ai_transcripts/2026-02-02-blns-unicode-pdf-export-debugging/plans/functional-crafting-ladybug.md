# Code Complexity Reduction Opportunities

## Status: EXPLORATION IN PROGRESS

Exploring opportunities to reduce code complexity across the codebase.

## Completed Exploration

### Duplication Analysis (Complete)

Found significant duplication patterns:

#### High Priority

1. **Database Session Wrapper Pattern** (~80 lines savings)
   - Files: `db/courses.py`, `db/users.py`, `db/weeks.py`, `db/annotation_state.py`
   - Pattern: `async with get_session() as session: result = await session.exec(select(...))`
   - Solution: Create generic `async def get_first_by(model_class, **filters)` helper

2. **Auth Callback Handlers** (~150 lines savings)
   - File: `pages/auth.py` lines 341-491
   - Three nearly identical handlers: `magic_link_callback`, `sso_callback`, `oauth_callback`
   - Solution: Create `async def _handle_auth_callback(auth_method, token, auth_client)` wrapper

3. **Flush + Refresh Pattern** (~50 lines savings)
   - Files: All db/*.py modules
   - Pattern: `session.add(obj); await session.flush(); await session.refresh(obj); return obj`
   - Solution: Create `async def persist_and_return(session, obj)` utility

#### Medium Priority

4. **Config Checks** (~20 lines)
   - Pattern: `os.environ.get("AUTH_MOCK") == "true"` and `os.environ.get("DATABASE_URL")`
   - Solution: `is_auth_mock()` and `is_database_configured()` utilities

5. **Session Retrieval** (~15 lines)
   - Duplicated `_get_session_user()` in `pages/auth.py` and `pages/courses.py`
   - Solution: Consolidate to shared utility

6. **Entity Not-Found Check** (~35 lines)
   - Pattern: `obj = await session.get(Model, id); if not obj: return None`
   - Solution: Could be part of generic DB helpers

### Pending Exploration

- [ ] Source file complexity analysis (large files, complex functions)
- [ ] Test code complexity beyond E2E

## Next Steps

1. Complete exploration of source file complexity
2. Complete exploration of test code patterns
3. Prioritize and select specific refactoring targets
4. Create implementation plan

## Estimated Total Savings

~420 lines of code through consolidation and abstraction.
