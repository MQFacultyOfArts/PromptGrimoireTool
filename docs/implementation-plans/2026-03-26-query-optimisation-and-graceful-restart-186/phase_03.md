# Query Optimisation and Graceful Restart — Phase 3

**Goal:** Enable the deploy script to tell all connected clients to save state and navigate away before the server is killed, achieving zero data loss on restart.

**Architecture:** Two new admin API routes (`POST /api/pre-restart` and `GET /api/connection-count`) orchestrate a client-side flush-and-navigate sequence. The flush iterates `_workspace_presence` to extract Milkdown content and persist CRDT state. Navigation targets ALL connected clients via `Client.instances`. Auth uses the existing Bearer token pattern.

**Tech Stack:** NiceGUI `Client.instances`, `client.run_javascript()`, pydantic-settings `SecretStr`, Starlette `Route`

**Scope:** Phase 3 of 6 from original design

**Codebase verified:** 2026-03-26

---

## Acceptance Criteria Coverage

This phase implements and tests:

### query-optimisation-and-graceful-restart-186.AC2: Pre-restart flush
- **query-optimisation-and-graceful-restart-186.AC2.1 Success:** `POST /api/pre-restart` triggers CRDT flush on all connected clients
- **query-optimisation-and-graceful-restart-186.AC2.2 Success:** Clients navigate to `/restarting?return=<url>` after flush completes
- **query-optimisation-and-graceful-restart-186.AC2.3 Failure:** Non-admin `POST /api/pre-restart` returns 403
- **query-optimisation-and-graceful-restart-186.AC2.4 Edge:** Mid-edit Milkdown content is saved to CRDT before flush

---

## Implementation Tasks

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add `PRE_RESTART_TOKEN` to config

**Verifies:** None (infrastructure)

**Files:**
- Modify: `src/promptgrimoire/config.py` (add field to `AdminConfig`)

**Implementation:**

Add `pre_restart_token: SecretStr = SecretStr("")` to `AdminConfig` alongside the existing `admin_api_secret` field. The env var will be `ADMIN__PRE_RESTART_TOKEN`.

```python
class AdminConfig(BaseModel):
    """Admin API configuration."""

    admin_api_secret: SecretStr = SecretStr("")
    pre_restart_token: SecretStr = SecretStr("")
```

**Verification:**
Run: `uvx ty@0.0.24 check`
Expected: No type errors

**Commit:** `feat: add PRE_RESTART_TOKEN config for graceful restart (#355)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement pre-restart and connection-count endpoints

**Verifies:** query-optimisation-and-graceful-restart-186.AC2.1, query-optimisation-and-graceful-restart-186.AC2.2, query-optimisation-and-graceful-restart-186.AC2.3, query-optimisation-and-graceful-restart-186.AC2.4

**Files:**
- Modify: `src/promptgrimoire/__init__.py` (add route registration near existing admin routes)
- Create: `src/promptgrimoire/pages/restart.py` (pre-restart handler logic)

**Implementation:**

Create `src/promptgrimoire/pages/restart.py` with two async handler functions:

**`pre_restart_handler(request)`:**
1. Validate Bearer token from `Authorization` header against `get_settings().admin.pre_restart_token` using `hmac.compare_digest()`. Return 403 `JSONResponse` if missing/invalid. Follow the exact pattern from `__init__.py:304-346` (kick handler auth).
2. Capture initial client count: `len([c for c in Client.instances.values() if c.has_socket_connection])`.
3. **Flush Milkdown content:** Iterate `_workspace_presence` (import from `pages/annotation/__init__`). For each workspace_id and its client dict, for each `_RemotePresence` with `has_milkdown_editor=True`:
   - Extract markdown: `md = await presence.nicegui_client.run_javascript("window._getMilkdownMarkdown()", timeout=3.0)`
   - Get the workspace's CRDT doc: `crdt_doc = await _workspace_registry.get_or_create_for_workspace(UUID(workspace_id))` (import `_workspace_registry` from `pages/annotation/__init__`)
   - Write to CRDT (same pattern as `pages/annotation/respond.py:382-391`):
     ```python
     text_field = crdt_doc.response_draft_markdown
     current = str(text_field)
     if current != md:
         with crdt_doc.doc.transaction():
             current_len = len(text_field)
             if current_len > 0:
                 del text_field[:current_len]
             if md:
                 text_field += md
     ```
   - Wrap each client call in try/except (tolerates stale/disconnected clients, log warning and continue)
4. **Persist CRDT:** Call `await get_persistence_manager().persist_all_dirty_workspaces()`.
5. **Navigate ALL clients:** Iterate `Client.instances.values()`, filter by `has_socket_connection`. For each, call `await client.run_javascript('window.location.href = "/restarting?return=" + encodeURIComponent(location.href)', timeout=2.0)` in try/except (same pattern as ban-disconnect in `auth/client_registry.py:51-68`).
6. Return `JSONResponse({"initial_count": initial_count})`.

**`connection_count_handler(request)`:**
1. Validate Bearer token (same as above).
2. Return `JSONResponse({"count": len([c for c in Client.instances.values() if c.has_socket_connection])})`.

**Route registration in `__init__.py`:**
Add near the existing admin routes (after healthz/kick):
```python
from promptgrimoire.pages.restart import pre_restart_handler, connection_count_handler
app.routes.insert(0, Route("/api/pre-restart", pre_restart_handler, methods=["POST"]))
app.routes.insert(0, Route("/api/connection-count", connection_count_handler, methods=["GET"]))
```

**Important implementation notes:**
- Use `client.run_javascript()` per iterated client (NOT `ui.run_javascript()` which runs in the current context) — matches the ban-disconnect pattern in `auth/client_registry.py:51-68`
- Existing callers of `_getMilkdownMarkdown` use `ui.run_javascript()` — the pre-restart handler uses `client.run_javascript()` instead because it iterates all clients, not the current one
- The CRDT write path is documented in `pages/annotation/respond.py:382-391` (`_sync_markdown_to_crdt`). The key difference: `_sync_markdown_to_crdt` uses `ui.run_javascript()` (current context) while pre-restart uses `client.run_javascript()` (specific client)
- `_workspace_registry` at `pages/annotation/__init__.py:93` provides `get_or_create_for_workspace(workspace_id)` to get the CRDT doc for a workspace
- `_workspace_presence` keys are workspace_id strings; the CRDT doc lookup needs `UUID(workspace_id)`

**Testing:**

Tests must verify each AC listed above. This is best tested as an integration test that exercises the handler functions directly with mocked NiceGUI Client objects:

- **AC2.3:** Call `pre_restart_handler` with no token, wrong token — assert 403 response
- **AC2.1:** Call with correct token and mocked `_workspace_presence` containing clients with `has_milkdown_editor=True` — verify `run_javascript("window._getMilkdownMarkdown()")` was awaited and `persist_all_dirty_workspaces()` was called
- **AC2.2:** Verify `run_javascript('window.location.href = "/restarting?..."')` was called on all clients
- **AC2.4:** Verify the Milkdown extraction happens BEFORE the persist call (ordering)

Follow integration test patterns. Since this involves NiceGUI Client mocking, use `unittest.mock.AsyncMock` for `client.run_javascript`.

Test file: `tests/integration/test_pre_restart.py`

Reference: `auth/client_registry.py:51-68` for the client iteration pattern, `__init__.py:304-346` for token validation pattern, `crdt/persistence.py:166-170` for `persist_all_dirty_workspaces()`.

**Verification:**
Run: `uv run grimoire test run tests/integration/test_pre_restart.py`
Expected: All tests pass

Run: `uv run grimoire test all`
Expected: No regressions

**Commit:** `feat: add pre-restart endpoint and connection-count API (#355)`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

---

## Complexipy Check

After completing this phase, run:
```bash
uv run complexipy src/promptgrimoire/pages/restart.py src/promptgrimoire/__init__.py src/promptgrimoire/config.py --max-complexity-allowed 15
```

The pre-restart handler has moderate complexity (token validation + iteration + JS calls + CRDT write + navigation). Flag if approaching threshold.

## UAT Steps

1. [ ] Start the app: `uv run run.py`
2. [ ] Set `ADMIN__PRE_RESTART_TOKEN=test-token` in `.env`
3. [ ] Call without token: `curl -sf -X POST http://localhost:8080/api/pre-restart` — verify 403
4. [ ] Call with wrong token: `curl -sf -X POST -H "Authorization: Bearer wrong" http://localhost:8080/api/pre-restart` — verify 403
5. [ ] Open annotation page in browser, type in Respond editor
6. [ ] Call with correct token: `curl -sf -X POST -H "Authorization: Bearer test-token" http://localhost:8080/api/pre-restart` — verify 200 with `{"initial_count": N}`
7. [ ] Verify: browser tab navigated to `/restarting?return=<original-url>`
8. [ ] Call: `curl -sf -H "Authorization: Bearer test-token" http://localhost:8080/api/connection-count` — verify count is lower

## Evidence Required
- [ ] `uv run grimoire test run tests/integration/test_pre_restart.py` output showing green
- [ ] curl output showing 403 for bad token, 200 for good token
- [ ] Browser screenshot showing navigation to `/restarting`
