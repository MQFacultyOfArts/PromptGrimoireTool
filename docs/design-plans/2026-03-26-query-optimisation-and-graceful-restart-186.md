# Query Optimisation and Graceful Restart Design

**GitHub Issue:** #186, #432, #355

## Summary

PromptGrimoire's annotation page loads all documents for a workspace on every page visit, but the current query fetches the full `content` column for every document — an unbounded text field averaging 14KB and reaching 1MB. Most callers (the tab bar, the document list, the management dialog) only need metadata such as title and ordering; they never inspect the body. Phase A introduces `list_document_headers()`, a thin wrapper around the existing list query that uses SQLAlchemy's `defer()` to suppress the `content` column unless explicitly requested. Export paths, which need the full body, are left unchanged.

Phase B addresses a separate operational problem: when the server is restarted to deploy new code, any user who is actively editing a document may lose in-flight CRDT state that has not yet been persisted. The fix is a pre-restart handshake: the deploy script calls a new admin endpoint (`POST /api/pre-restart`) before killing the process. The server responds by pushing a flush-and-navigate command to every connected client. Clients save their dirty CRDT state, transition to a holding page (`/restarting`), and close their WebSocket connections. The holding page polls `/healthz` and, once the server is back, waits a random 1–5 second interval before redirecting users back to where they were. The deploy script waits until connection count drops to near zero, then proceeds with `systemctl restart`. The net effect is zero data loss and no user-visible interruption beyond a brief "updating" screen.

## Definition of Done

1. `list_document_headers()` exists in `workspace_documents.py`, excludes `content` via `defer()`. Returns `WorkspaceDocument`.
2. All non-export callers (`workspace.py`, `tab_bar.py` ×2, `document_management.py`) use `list_document_headers()`.
3. `POST /api/pre-restart` triggers all connected clients to flush CRDT state, navigate to `/restarting`, and WebSockets drain before server kill.
4. `/restarting` page polls `/healthz`, waits 1–5s jitter, redirects to return URL.
5. `deploy/restart.sh` calls pre-restart, waits for 95% drain + 2s, then restarts.

## Acceptance Criteria

### query-optimisation-and-graceful-restart-186.AC1: Query optimisation
- **AC1.1 Success:** `list_document_headers()` returns documents with all metadata columns; no `content` column transferred
- **AC1.2 Success:** Page load callers (`workspace.py`, `tab_bar.py` ×2) use `list_document_headers()`
- **AC1.3 Failure:** Accessing `.content` on a headers-only object raises `DetachedInstanceError`
- **AC1.4 Success:** Export callers (`pdf_export.py`, `cli/export.py`) still receive full `content`

### query-optimisation-and-graceful-restart-186.AC2: Pre-restart flush
- **AC2.1 Success:** `POST /api/pre-restart` triggers CRDT flush on all connected clients
- **AC2.2 Success:** Clients navigate to `/restarting?return=<url>` after flush completes
- **AC2.3 Failure:** Non-admin `POST /api/pre-restart` returns 403
- **AC2.4 Edge:** Mid-edit Milkdown content is saved to CRDT before flush

### query-optimisation-and-graceful-restart-186.AC3: Restarting page
- **AC3.1 Success:** `/restarting` polls `/healthz`, redirects to return URL on 200
- **AC3.2 Success:** Redirect includes 1–5s random jitter to prevent thundering herd
- **AC3.3 Failure:** Missing `return` param redirects to `/` (home)

### query-optimisation-and-graceful-restart-186.AC4: Deploy script
- **AC4.1 Success:** `restart.sh` calls pre-restart, waits for ≤5% connections + 2s
- **AC4.2 Edge:** Timeout after configurable seconds proceeds with restart (don't hang forever)
- **AC4.3 Success:** No HAProxy drain step in the deploy sequence

## Glossary

- **CRDT (Conflict-free Replicated Data Type)**: A data structure (here, `pycrdt` / Y.js) that lets multiple clients edit the same document simultaneously and merge changes without conflicts. The canonical copy lives in the database; clients hold an in-memory replica that must be persisted before the server shuts down.
- **`defer()`**: A SQLAlchemy ORM directive that excludes a mapped column from the `SELECT` statement. On detached objects (returned after session close) accessing a deferred column raises `DetachedInstanceError`.
- **`DetachedInstanceError`**: A SQLAlchemy exception raised when code tries to access a lazy-loaded attribute on an ORM object after its database session has closed. Used here as a deliberate enforcement mechanism.
- **Milkdown**: The rich-text WYSIWYG editor component used for the "Respond" tab. The flush sequence must extract its content and write it to the CRDT before the WebSocket is closed.
- **NiceGUI**: The Python web UI framework. Maintains a server-side object graph per connected browser tab and exposes `app.clients` for iterating all active connections.
- **`PersistenceManager`**: Internal component that tracks which workspaces have dirty CRDT state and flushes them to PostgreSQL on demand or after a debounce interval.
- **`page_route` decorator**: PromptGrimoire wrapper around `@ui.page` that enforces auth and ban checks. The `/restarting` page bypasses it (using `@ui.page` directly) so it is reachable regardless of authentication state.
- **Thundering herd**: A failure mode where many clients reconnect simultaneously after a restart, overwhelming the event loop. Mitigated by random 1–5s jitter before redirecting.
- **HAProxy drain**: The previous deploy strategy: HAProxy stops accepting new connections and waits for existing ones to close. Ineffective for WebSocket connections, which are long-lived.
- **`/healthz`**: Lightweight HTTP endpoint returning 200 when the server is ready. Used by `/restarting` to detect when the server is back.
- **xfail**: A pytest marker meaning "expected failure" — the test documents a known regression (#377) rather than suppressing it.
- **`before_cursor_execute` event**: SQLAlchemy engine event that fires before each SQL statement. Used in regression tests to count queries without mocking.
- **`workspace_document`**: The database table (and `WorkspaceDocument` SQLModel class) storing per-document content. The `content` column is the large field being deferred.

## Architecture

Two independent concerns that share annotation page plumbing:

**Phase A — Query optimisation (#432 P0):** Reduce per-page-load data transfer by not fetching the `content` column (unbounded `Text`, avg 14KB, up to 1MB) from `workspace_document` when callers only need metadata. A new `list_document_headers()` function uses SQLAlchemy `defer(WorkspaceDocument.content)` to exclude the column. The manage-documents dialog additionally changes to lazy-load content per-document when the user clicks Edit, instead of bulk-fetching all content up front.

**Phase B — Graceful restart (#355):** A pre-restart endpoint tells connected clients to save in-flight state and navigate away before the server is killed. The sequence: deploy script calls `POST /api/pre-restart` → server pushes flush + navigate to each client → clients persist dirty CRDT, show spinner, navigate to `/restarting?return=<url>` → WebSockets close as a side effect → deploy script polls connection count until ≤5% remain + 2s → `systemctl restart` → server comes back → `/restarting` page detects `/healthz` 200 → waits 1–5s random jitter → redirects to return URL.

The two compound: Phase A reduces the data each page load transfers; Phase B ensures restarts don't lose in-flight data. Both touch the annotation page lifecycle.

## Existing Patterns

**DB query layer** (`src/promptgrimoire/db/`): All query functions follow the pattern `async with get_session() as session: ... return list(result.all())`. Returned objects are detached from the session. `list_document_headers()` follows this exact pattern with an added `.options(defer(...))`.

**SQLAlchemy deferred columns:** Not currently used anywhere in the project. This design introduces `defer()` for the first time. The pattern is standard SQLAlchemy — no custom machinery.

**Shutdown hooks** (`src/promptgrimoire/__init__.py:396`): `app.on_shutdown` already cancels background workers and calls `persist_all_dirty_workspaces()`. The pre-restart endpoint builds on this by triggering client-side drain BEFORE the shutdown hook runs.

**Page routes** (`src/promptgrimoire/pages/registry.py`): `@page_route` decorator handles auth checks and ban guards. The `/restarting` page uses `@ui.page` directly (like `/banned`) since it must be accessible to all users regardless of auth state.

**Deploy script** (`deploy/restart.sh`): Currently does tests → HAProxy drain → maint → restart → healthz → ready. The drain step is ineffective for WebSocket connections. This design replaces it with application-level drain.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: `list_document_headers()` and caller migration

**Goal:** Eliminate unnecessary `content` column transfer on page load and document management dialog.

**Components:**
- `list_document_headers()` in `src/promptgrimoire/db/workspace_documents.py` — identical to `list_documents()` but with `.options(defer(WorkspaceDocument.content))`
- Caller updates in `src/promptgrimoire/pages/annotation/workspace.py`, `src/promptgrimoire/pages/annotation/tab_bar.py`, `src/promptgrimoire/pages/annotation/document_management.py`
- `document_management.py` edit dialog — fetch single doc via `get_document(doc.id)` before opening WYSIWYG editor
- `tab_bar.py:648` (`document_container()`) — use headers for list, fetch full doc for `docs[0]` only via `get_document()`

**Dependencies:** None (first phase)

**Done when:** Page load and document management dialog no longer transfer `content` for documents that don't need it. Accessing `.content` on a headers-only object raises `DetachedInstanceError`. Export paths unchanged.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Query efficiency regression tests

**Goal:** Prevent reintroduction of redundant queries with measurable guards.

**Components:**
- `tests/integration/test_query_efficiency.py` — new file with SQLAlchemy `before_cursor_execute` event listener for query counting
- Test: `list_document_headers()` excludes content (unit-level, verify `DetachedInstanceError`)
- Test: page load document query count (pass — we fixed it)
- Test: page load workspace fetch count (xfail, reason="#377 Phase 1")
- Test: placement context query count (xfail, reason="#377 Phase 1")

**Dependencies:** Phase 1

**Done when:** Tests pass (or xfail where documented). Query counting fixture is reusable for future efficiency tests.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Pre-restart endpoint and client flush

**Goal:** Server can tell all connected clients to save state and navigate away.

**Components:**
- `POST /api/pre-restart` route in `src/promptgrimoire/pages/` — admin-only (pre-shared token from `PRE_RESTART_TOKEN` env var), returns `{"initial_count": N}` for deploy script baseline
- `GET /api/connection-count` — returns current connected client count for deploy script polling
- Flush logic iterates `_workspace_presence` (already maps workspace → client with `nicegui_client` and `has_milkdown_editor` flag). For each Milkdown client: `client.run_javascript("window._getMilkdownMarkdown()")` → write to CRDT. Then `persist_all_dirty_workspaces()`. Then navigate each client via `client.run_javascript('window.location.href = "/restarting?return=" + encodeURIComponent(location.href)')`.
- Uses `client.run_javascript()` per iterated client (not `ui.run_javascript()`) — matches the ban-disconnect pattern in `auth/client_registry.py`

**Dependencies:** None (independent of Phase 1–2)

**Done when:** Calling the endpoint causes all connected clients to flush and navigate away. WebSocket connection count drops to near zero.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: `/restarting` page with auto-redirect

**Goal:** Users see a holding page during restart that auto-redirects when the server is back.

**Components:**
- `/restarting` page in `src/promptgrimoire/pages/` — uses `@ui.page` (not `page_route`), shows "Server updating, please wait..." message
- Client-side JS: polls `/healthz` every 2s, on 200 → wait random 1–5s jitter → `location.href = returnUrl`
- Query param: `return=<encoded_url>` for redirect target

**Dependencies:** Phase 3 (endpoint navigates to this page)

**Done when:** Page renders, polls healthz, redirects after jitter. Users land back on their workspace.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Deploy script integration

**Goal:** `restart.sh` uses application-level drain instead of HAProxy drain.

**Components:**
- `deploy/restart.sh` — sequence: tests → `POST /api/pre-restart` (get initial count) → HAProxy drain (block new arrivals) → poll `GET /api/connection-count` until ≤5% of initial + 2s grace → `systemctl restart` → healthz → HAProxy ready
- Auth: pre-shared token from `PRE_RESTART_TOKEN` env var, passed as `Authorization: Bearer $token`
- Timeout: configurable max wait (default 30s) before proceeding with restart regardless (don't hang forever on unresponsive clients)

**Dependencies:** Phases 3–4

**Done when:** Full deploy cycle works with zero data loss for connected users. Late-arriving users during drain window are blocked by HAProxy.
<!-- END_PHASE_5 -->

## Additional Considerations

**Thundering herd:** The 1–5s random jitter on client reload prevents 200 simultaneous page loads when the server comes back. Without jitter, the first restart under load would immediately re-saturate the event loop.

**Auth for pre-restart endpoint:** Pre-shared token from `PRE_RESTART_TOKEN` env var. The deploy script runs on the same server, so `curl -H "Authorization: Bearer $token"` is sufficient. No session cookie needed.

**Milkdown editor flush:** The `_workspace_presence` registry (in `pages/annotation/__init__.py`) already tracks which clients have Milkdown editors (`has_milkdown_editor` flag) and holds `nicegui_client` references. The pre-restart handler iterates this registry, calls `client.run_javascript("window._getMilkdownMarkdown()")` per Milkdown client, writes the result to the workspace's CRDT doc, then calls `persist_all_dirty_workspaces()`. This uses `client.run_javascript()` (not `ui.run_javascript()`) — the same per-client JS execution pattern as the ban-disconnect flow in `auth/client_registry.py`.

**Late arrivals during drain:** HAProxy drain is kept (blocks new HTTP connections) alongside application-level drain (flushes existing WebSocket clients). Sequence: pre-restart → HAProxy drain → poll until drained → restart. New users arriving after pre-restart but before HAProxy drain get the navigate signal; users arriving after HAProxy drain get a 503 maintenance page.

**Partial drain:** The 95% threshold handles unresponsive or stale WebSocket connections. Configurable timeout (default 30s) prevents the deploy script from hanging indefinitely.
