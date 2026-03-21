---
source: https://github.com/stytchauth/stytch-python (source inspection)
fetched: 2026-03-18
library: stytch
summary: aiohttp session lifecycle in the Stytch Python SDK — lazy creation, external session injection, GC-based cleanup
---

# Stytch Python SDK: Async Session Management

## How the SDK creates aiohttp sessions

`B2BClient.__init__` accepts an optional `async_session: aiohttp.ClientSession`
parameter. This is passed down to `AsyncClient` in `stytch.core.http.client`.

### AsyncClient session lifecycle

```python
class AsyncClient(ClientBase):
    def __init__(self, project_id, secret, session=None):
        self.auth = aiohttp.BasicAuth(project_id, secret)
        self._external_session = session is not None
        self.__session = session

    @property
    def _session(self) -> aiohttp.ClientSession:
        # Lazy creation: session created on first HTTP request
        if self.__session is None:
            self.__session = aiohttp.ClientSession()
        return self.__session

    def __del__(self) -> None:
        # Skip cleanup if caller owns the session
        if self._external_session or self.__session is None:
            return
        # GC-triggered cleanup — fragile
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._session.close())
            else:
                loop.run_until_complete(self._session.close())
        except Exception:
            pass
```

### Key behaviours

1. **Lazy creation:** Session is not created until the first async HTTP call.
2. **External session:** If you pass `async_session=my_session`, the SDK sets
   `_external_session = True` and skips closing it in `__del__`. You own the
   lifecycle.
3. **GC cleanup:** When the SDK owns the session, `__del__` tries to close it.
   This relies on the event loop being available during garbage collection —
   unreliable in async applications where GC may run after the loop closes.

## The leak pattern

Each `B2BClient()` instantiation creates a new `AsyncClient` with a new
`aiohttp.ClientSession`. If `get_auth_client()` creates a fresh client per
request, sessions accumulate and are only cleaned up by GC — producing
"Unclosed client session" warnings/errors.

## Mitigation

### Option 1: Singleton client (implemented for #378)

Cache the `B2BClient` instance so only one `aiohttp.ClientSession` exists:

```python
_client_instance: AuthClientProtocol | None = None

def get_auth_client() -> AuthClientProtocol:
    global _client_instance
    if _client_instance is not None:
        return _client_instance
    # ... create and cache ...
```

### Option 2: External session with explicit close (not implemented)

Pass a managed `aiohttp.ClientSession` and close it on app shutdown:

```python
session = aiohttp.ClientSession()
client = B2BClient(
    project_id=..., secret=..., async_session=session
)

# On shutdown:
await session.close()
```

This is cleaner but requires NiceGUI shutdown hook integration.

## SDK version notes

- No official `close()` method on `B2BClient`
- No context manager support (`async with`)
- The `async_session` parameter is undocumented in official Stytch docs
  but present in the SDK source since at least v6 (2023)
