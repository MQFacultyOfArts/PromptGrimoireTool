# Code Review: PromptGrimoire (Commits 6db0a3d → 92e873d)

**Review Date:** 2026-01-21
**Reviewer:** Claude Opus 4.5
**Scope:** Spike 4 (SillyTavern Roleplay) + Spike 5 (Database & Auth)
**Commits Reviewed:** 15 commits since last code review

---

## 1. Executive Summary

This review covers two major spikes merged since the last code review:

- **Spike 4:** SillyTavern roleplay import with Claude API integration (7,006 insertions across 53 files)
- **Spike 5:** Stytch B2B authentication + PostgreSQL async database (in progress)

**Overall Assessment:** The codebase shows good architectural patterns and solid async/await usage. However, there are **7 critical security vulnerabilities** that must be fixed before any production deployment, plus several high-priority issues affecting data integrity and test quality.

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 7 | Must fix before merge |
| HIGH | 12 | Must fix before production |
| MEDIUM | 15 | Fix in next sprint |
| LOW | 6 | Nice to have |

---

## MANDATORY: No Quick Hacks

**Quick hacks are absolutely forbidden.** Every fix must be a proper solution:

- No `# type: ignore` without documented justification
- No `time.sleep()` or arbitrary waits to "fix" race conditions
- No global mutable state as a workaround for proper dependency injection
- No suppressing exceptions without logging and proper handling
- No "temporary" workarounds that bypass security checks
- No commented-out code left "just in case"

If a proper fix requires significant refactoring, that refactoring must be done. The codebase must remain maintainable and correct, not just "working for now."

---

## Race Condition Audit Checklist

All fixes must be reviewed against these race condition patterns:

### Async/Await Race Conditions
- [ ] **State mutations during await:** Any `await` can yield control. Mutable state accessed before and after an `await` may have changed.
- [ ] **Concurrent page loads:** Multiple users hitting the same endpoint simultaneously must not share state.
- [ ] **Stream consumption:** Async generators must handle consumer disconnection gracefully.

### Module-Level State
- [ ] **Import-time initialization:** Code that runs at import time must be thread-safe.
- [ ] **Global singletons:** Any module-level state must use proper locking or be truly immutable.
- [ ] **sys.modules manipulation:** Never modify sys.modules without locks.

### Database Transactions
- [ ] **Read-modify-write:** SELECT followed by UPDATE must use proper locking or optimistic concurrency.
- [ ] **Session lifecycle:** Async sessions must not be shared across await boundaries without explicit management.
- [ ] **Connection pool exhaustion:** What happens when all connections are in use?

### UI State
- [ ] **Optimistic updates:** UI updated before backend confirms must handle rollback.
- [ ] **Multiple tabs:** Same user with multiple tabs must not corrupt shared state.
- [ ] **Page refresh mid-operation:** What happens if user refreshes during an async operation?

---

## 2. Critical Issues (Must Fix Before Merge)

### CRIT-1: Path Traversal in Log Viewer
**File:** [logviewer.py:118-121](src/promptgrimoire/pages/logviewer.py#L118-L121)

```python
def on_select(e) -> None:
    path = Path(e.value)  # UNSAFE: No validation
    state["selected_path"] = path
    header, turns = parse_log_file(path)
```

**Risk:** Attacker can read arbitrary files (`../../../etc/passwd`)

**Fix:**
```python
def on_select(e) -> None:
    requested_path = Path(e.value).resolve()
    safe_base = LOG_DIR.resolve()
    if not str(requested_path).startswith(str(safe_base) + os.sep):
        ui.notify("Invalid path", type="negative")
        return
    state["selected_path"] = requested_path
```

---

### CRIT-2: Session Storage Auth Bypass
**File:** [auth.py:25-48](src/promptgrimoire/pages/auth.py#L25-L48)

```python
def _get_session_user() -> dict | None:
    return app.storage.user.get("auth_user")  # Client-side storage!

def _set_session_user(...) -> None:
    app.storage.user["auth_user"] = {...}  # Can be forged via DevTools
```

**Risk:** Complete auth bypass - attackers can impersonate any user including admins by modifying browser storage.

**Fix:** Implement server-side session validation:
1. Store only a session ID client-side
2. Validate session against server-side store (Redis/database) on every protected request
3. Never trust client-side session data for authorization decisions

---

### CRIT-3: No Input Validation on Auth Tokens
**File:** [auth.py:56-66](src/promptgrimoire/pages/auth.py#L56-L66)

```python
def _get_query_param(name: str) -> str | None:
    request: Request = ui.context.client.request
    return request.query_params.get(name)  # No validation
```

**Risk:** Token injection, URL parameter pollution

**Fix:**
```python
import re

def _validate_token(token: str) -> bool:
    if not token or len(token) > 1000:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', token))
```

---

### ~~CRIT-4: URL Injection in SSO Start~~ ✅ FIXED
**File:** [client.py:231-255](src/promptgrimoire/auth/client.py#L231-L255)
**Fixed in:** Commit fbc45b8

```python
# BEFORE (vulnerable):
redirect_url = f"{base_url}/v1/public/sso/start?connection_id={connection_id}"

# AFTER (fixed):
params = {"connection_id": connection_id, "public_token": public_token}
redirect_url = f"{base_url}/v1/public/sso/start?{urlencode(params)}"
```

**Preventive measure added:** `tests/unit/test_security_patterns.py` now scans for unsafe f-string URL construction and fails the build if found.

---

### CRIT-5: Unrestricted JSON Parsing - DoS
**File:** [sillytavern.py:30-33](src/promptgrimoire/parsers/sillytavern.py#L30-L33)

```python
raw = json.loads(path.read_text(encoding="utf-8"))  # No size limit
```

**Risk:** Memory exhaustion via large files, deeply nested structures, or billion-laughs-style attacks

**Fix:**
```python
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

file_size = path.stat().st_size
if file_size > MAX_FILE_SIZE:
    raise ValueError(f"File exceeds max size: {file_size}")
```

---

### CRIT-6: No File Upload Size Limit
**File:** [roleplay.py:155-162](src/promptgrimoire/pages/roleplay.py#L155-L162)

```python
async def handle_upload(e) -> None:
    content = await e.file.read()  # No size limit!
    tmp_path = Path(f"/tmp/pg_upload_{e.file.name}")
    tmp_path.write_bytes(content)
```

**Risk:** Disk/memory exhaustion via multi-GB uploads

**Fix:**
```python
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB

content = await e.file.read()
if len(content) > MAX_UPLOAD_SIZE:
    ui.notify("File too large (max 10MB)", type="negative")
    return
```

---

### CRIT-7: Module-Level Engine State Race Condition
**File:** [engine.py:75, 88](src/promptgrimoire/db/engine.py#L75)

```python
sys.modules[__name__]._engine = _state.engine  # type: ignore
```

**Risk:** Race condition during concurrent initialization, potential data corruption

**Fix:** Use `threading.Lock` for thread-safe state access or implement proper singleton pattern.

---

## 3. High Priority Issues

### HIGH-1: XSS via Reasoning Trace
**File:** [logviewer.py:66-69](src/promptgrimoire/pages/logviewer.py#L66-L69)

LLM-generated reasoning rendered as markdown without explicit sanitization.

**Fix:** Render as preformatted text: `ui.label(extra["reasoning"]).classes("font-mono")`

---

### HIGH-2: No Session Expiration Validation
**File:** [auth.py:302-309](src/promptgrimoire/pages/auth.py#L302-L309)

Protected pages never validate that session tokens are still valid with Stytch.

**Fix:** Add `auth_client.validate_session(token)` check on protected routes.

---

### HIGH-3: Missing Lorebook Entry Validation
**File:** [sillytavern.py:69-98](src/promptgrimoire/parsers/sillytavern.py#L69-L98)

No validation on `keys` list size, `content` length, or `scan_depth` bounds.

---

### HIGH-4: Stream Response Not Cleaned Up on Error
**File:** [client.py:129-137](src/promptgrimoire/llm/client.py#L129-L137)

If streaming fails mid-response, partial data may not be logged for audit.

---

### HIGH-5: Race Condition in Chat Message Rendering
**File:** [roleplay.py:67-103](src/promptgrimoire/pages/roleplay.py#L67-L103)

Turn added to session before UI confirms render - can diverge on page refresh.

---

### HIGH-6: Silent Failure on Missing Auth Credentials
**File:** [config.py:56-71](src/promptgrimoire/auth/config.py#L56-L71)

Mock mode uses hardcoded `"mock-*"` defaults without warning - could run mocked auth in production.

---

### HIGH-7: Session Auto-Commit Without Error Logging
**File:** [engine.py:111-117](src/promptgrimoire/db/engine.py#L111-L117)

Transaction failures rolled back without logging context.

---

### HIGH-8: Missing Connection Pool Exhaustion Handling
**File:** [engine.py:60-66](src/promptgrimoire/db/engine.py#L60-L66)

No `pool_recycle` or `connect_timeout` configured.

---

### HIGH-9: No Foreign Key Cascade Delete
**File:** [models.py](src/promptgrimoire/db/models.py) + migrations

FK constraints defined but no cascade delete - orphaned records possible.

---

### HIGH-10: Missing User Name Validation
**File:** [roleplay.py:164, 198-200](src/promptgrimoire/pages/roleplay.py#L164)

User name has no length check - potential prompt injection via `{{user}}` substitution.

---

### HIGH-11: Arbitrary Waits in E2E Tests
**File:** [test_two_tab_sync.py:111, 159](tests/e2e/test_two_tab_sync.py#L111)

`wait_for_timeout(200)` causes flaky tests. Use Playwright's `expect()` with auto-retry.

---

### HIGH-12: Weak Assertions in Tests
**File:** [test_example.py:19-25](tests/unit/test_example.py#L19-L25)

Version format test uses `>= 2` which allows invalid formats.

---

## 4. Specific Code Fixes

### Before (CRIT-1):
```python
def on_select(e) -> None:
    path = Path(e.value)
    state["selected_path"] = path
```

### After (CRIT-1):
```python
def on_select(e) -> None:
    requested_path = Path(e.value).resolve()
    safe_base = LOG_DIR.resolve()
    if not str(requested_path).startswith(str(safe_base) + os.sep):
        logger.warning("Path traversal attempt blocked: %s", e.value)
        ui.notify("Invalid log file path", type="negative")
        return
    state["selected_path"] = requested_path
```

### Before (CRIT-5):
```python
raw = json.loads(path.read_text(encoding="utf-8"))
```

### After (CRIT-5):
```python
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

file_size = path.stat().st_size
if file_size > MAX_FILE_SIZE:
    raise ValueError(f"Character card exceeds maximum size ({file_size} > {MAX_FILE_SIZE})")

try:
    raw = json.loads(path.read_text(encoding="utf-8"))
except json.JSONDecodeError as e:
    raise ValueError(f"Invalid JSON in {path}: {e}") from e
```

---

## 5. Checklist (Updated with User Decisions)

### Before Merge (Blocking)
- [ ] CRIT-1: Add path traversal protection → resolve() + startswith(LOG_DIR) check
- [ ] CRIT-2: Add Stytch session validation on protected routes (app.storage.user IS server-side per NiceGUI docs)
- [ ] CRIT-3: Add basic token validation (length < 1000 chars) before Stytch API calls
- [x] CRIT-4: Use urlencode() in get_sso_start_url ✅ Fixed in fbc45b8
- [ ] CRIT-5: Add 100MB file size limit to parser
- [ ] CRIT-6: Add 100MB upload size limit to roleplay page
- [x] CRIT-7: Fix module-level state race condition ✅ Fixed in a13a3f0 (dataclass, pool_recycle, timeouts)

### Before Production
- [ ] HIGH-1: Write automated test verifying ui.markdown() escapes <script> tags; fix logviewer.py if unsafe
- [ ] HIGH-2: (Merged into CRIT-2 - Stytch session validation)
- [x] HIGH-3: No limits needed - character cards are trusted content ✅
- [ ] HIGH-4: Add partial turn to session with error metadata AND log to separate error file
- [ ] HIGH-5: Defer until CRDT implementation - will need to coordinate session model updates with CRDT broadcast for multi-user collaborative roleplay
- [ ] HIGH-6: AUTH_MOCK=true should require valid Stytch TEST realm credentials (project_id/secret must point to test environment, not production). Remove hardcoded mock-* defaults.
- [x] HIGH-7: Add transaction error logging ✅ Fixed in a13a3f0
- [x] HIGH-8: Configure pool_recycle and timeouts ✅ Fixed in a13a3f0
- [x] HIGH-9: Cascade delete already implemented via _cascade_fk_column helper ✅
- [x] HIGH-10: No validation needed - Stytch has no constraints, user controls their own session name ✅
- [x] HIGH-11: Already uses Playwright expect() with auto-retry throughout ✅
- [x] HIGH-12: Already fixed - test requires exactly 3 numeric parts ✅

---

## 6. Verification Steps

After fixes are applied:

1. **Path Traversal (CRIT-1):**
   ```bash
   # Should fail gracefully, not expose /etc/passwd
   curl "http://localhost:8080/logs" -d "file=../../../etc/passwd"
   ```

2. **Session Bypass (CRIT-2):**
   ```javascript
   // In browser console on /protected - should redirect to /login
   localStorage.setItem('nicegui-storage', JSON.stringify({auth_user: {email: 'attacker@evil.com', roles: ['admin']}}));
   location.reload();
   ```

3. **Upload Size (CRIT-6):**
   ```bash
   # Create 20MB file, should be rejected
   dd if=/dev/zero of=large.json bs=1M count=20
   # Upload via UI - should show "File too large" error
   ```

4. **Run full test suite:**
   ```bash
   uv run pytest -v
   uv run playwright test
   uvx ty check
   ```

---

## 7. Notes for Future Work

1. **Authentication Architecture:** The current client-side session storage should be replaced with a server-side session store (Redis recommended) before the Session 1 launch.

2. **Rate Limiting:** No rate limiting on auth endpoints. Add before public deployment.

3. **HTTPS:** No HTTPS enforcement in app code. Configure via reverse proxy (nginx).

4. **CSRF Protection:** State-changing operations lack CSRF tokens. Consider NiceGUI's built-in CSRF support.

5. **Multi-User Testing:** E2E tests only verify happy paths. Add race condition tests for concurrent edits, session timeouts, and cascade deletes.

6. **Connection Pooling:** Consider sharing Anthropic client instance across sessions to reduce connection overhead.

---

## 8. Automation: Stop Hook for Code Review Reminder

Add a `Stop` hook to `.claude/settings.json` that reminds about security review when code changes were made:

**File to modify:** `.claude/settings.json`

```json
{
  "hooks": {
    "PostToolUse": [
      // ... existing python_lint.py hook ...
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "If Write or Edit tools were used this session to modify Python files, remind the user to run /security-review before committing. Keep the reminder brief (one line)."
          }
        ]
      }
    ]
  }
}
```

This ensures future Claude sessions get a nudge to run security review after making code changes.

---

## 9. Implementation Plan Summary

### Remaining Work (7 items)

**Before Merge (4 items):**
1. **CRIT-1** - `src/promptgrimoire/pages/logviewer.py:118-121`
   - Add `resolve() + startswith(LOG_DIR)` path validation

2. **CRIT-2** - `src/promptgrimoire/pages/auth.py` (protected routes)
   - Add Stytch `authenticate_session` call on `/protected` page

3. **CRIT-3** - `src/promptgrimoire/pages/auth.py:56-66`
   - Add token length validation (<1000 chars) in callback handlers

4. **CRIT-5 + CRIT-6** - Parser and upload size limits
   - `src/promptgrimoire/parsers/sillytavern.py:30`: Add 100MB file size check
   - `src/promptgrimoire/pages/roleplay.py:158`: Add 100MB upload size check

**Before Production (3 items):**
5. **HIGH-1** - XSS test for markdown
   - Create `tests/unit/test_markdown_sanitization.py`
   - Test that `<script>` tags are escaped by NiceGUI's `ui.markdown()`

6. **HIGH-4** - Stream error handling
   - `src/promptgrimoire/llm/client.py:185-219`: Wrap in try/finally
   - Add partial turn to session with `metadata["error"]` and `metadata["partial"]=True`
   - Also log to separate error file

7. **HIGH-6** - Auth mock credentials
   - `src/promptgrimoire/auth/config.py:59-71`: Remove hardcoded `mock-*` defaults
   - Require actual Stytch TEST realm credentials when `AUTH_MOCK=true`

**Deferred:**
- HIGH-5: Will be addressed during CRDT multi-user implementation

---

## Absolute Path to This Document

`/home/brian/.claude/plans/iterative-baking-crane.md`

---

*Code review prepared following the template in [prompts/CODE_REVIEW.md](prompts/CODE_REVIEW.md)*
