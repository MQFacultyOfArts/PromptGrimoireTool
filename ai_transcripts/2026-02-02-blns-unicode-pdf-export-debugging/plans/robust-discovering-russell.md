# Fix: WebSocket connections blocked by fastapi-guard cloud provider blocking

## Problem
After commit `32154f2`, button clicks on `/` do nothing. WebSocket connections show "pending" status - they never complete.

## Root Cause
The security middleware has `BLOCK_CLOUD_PROVIDERS: str = "AWS,GCP"` enabled by default. fastapi-guard's cloud provider blocking runs **before** the `custom_request_check` function, so even though `custom_security_check` returns early for `/_nicegui*` paths, the blocking already happened.

When accessing via Tailscale Serve, the client IP appears as a Tailscale CGNAT IP (100.64.x.x range), which fastapi-guard may be incorrectly classifying or the blocking middleware interferes with WebSocket upgrade requests.

## Solution
Add `/_nicegui` paths to the whitelist config so fastapi-guard skips all checks for them, OR disable cloud provider blocking in development.

### Option A: Quick fix for development (recommended)
Add to `.env`:
```
BLOCK_CLOUD_PROVIDERS=
```

### Option B: Proper fix in code
Modify `app/middleware/security.py` to configure fastapi-guard with an `excluded_paths` setting (if supported) or ensure NiceGUI paths bypass all middleware checks.

## Files to modify
- `.env` (for Option A)
- `app/core/security_config.py` - change default to empty string for dev

## Verification
1. Restart the server
2. Access via Tailscale Serve
3. Click "Go to Dashboard" or "Admin Panel" - buttons should work
4. Check DevTools Network tab - WebSocket should connect (not pending)
