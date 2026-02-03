# Fix: NiceGUI WebSocket Pending State

## Problem
NiceGUI WebSocket connections (`/_nicegui_ws/socket.io/...`) stay in "pending" state. Clicks do nothing because the WebSocket never connects.

## Root Cause
`BaseHTTPMiddleware` (used by `AuthMiddleware`) cannot handle WebSocket upgrade requests. It only handles HTTP request/response cycles. When a WebSocket upgrade comes in, the middleware chokes before `dispatch()` is even called.

Likely triggered by recent dependency update (`uv sync` pulled `sse_starlette` 3.0.3 → 3.2.0).

## Fix
Add `__call__` override to `AuthMiddleware` to bypass WebSocket requests at the ASGI level, before `BaseHTTPMiddleware` tries to process them.

**Security note:** This is safe because:
- NiceGUI validates WebSocket connections via `client_id` (UUID generated server-side when authenticated page loads)
- Invalid/guessed `client_id` values are rejected at handshake
- The auth already happened when the HTTP page request loaded

## File to Modify
- `app/middleware/auth.py`

## Change
Add this method to `AuthMiddleware` class (before `dispatch`):

```python
async def __call__(self, scope, receive, send):
    # WebSocket requests bypass auth middleware entirely
    # (NiceGUI validates via client_id token from authenticated page load)
    if scope["type"] == "websocket":
        await self.app(scope, receive, send)
        return
    await super().__call__(scope, receive, send)
```

## Verification
1. Run `uv run examples/example9_audio_pipeline/main.py`
2. Access via Tailscale: `https://sillytavern.tail0cc7cb.ts.net/`
3. Check browser Network tab → WS filter → should show "101 Switching Protocols" (not "pending")
4. Click buttons → should respond immediately
