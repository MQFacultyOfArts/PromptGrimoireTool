# Plan: Block Vulnerability Scanners - Immediate Drop + Ban

## Problem

The logs show **massive bot traffic** from vulnerability scanners probing for:

- Cisco VPN exploits (`/+CSCOT+/*`, `/+CSCOE+/*`) - 304 hits each
- WordPress backdoors (`/wp-*/*.php`)
- PHPUnit RCE exploits (`/vendor/phpunit/*/eval-stdin.php`)
- PHP shells (`xleet.php`, `fierzashell.php`, `bypass.php`)
- Path traversal attacks (`/cgi-bin/../../bin/sh`)
- `.git/config`, `.env` exposure

Currently, these requests hit the `AuthMiddleware` which:

1. Logs "Unauthenticated request, redirecting to login"
2. Returns a 302 redirect to `/login`

This creates log spam and unnecessary processing.

## Solution

Add an **immediate drop + IP ban** for known attack paths. Any request to a scanner path:

1. Gets IP immediately added to fastapi-guard's blacklist
2. Connection is closed without response (tarpit)
3. All future requests from that IP get blocked

## Implementation

### 1. Add attack patterns to [security_config.py](app/core/security_config.py)

```python
# Paths that indicate bot/scanner traffic - immediate ban
SCANNER_PATH_PREFIXES: list[str] = [
    "/+CSCOT+",  # Cisco VPN exploits
    "/+CSCOE+",
    "/+CSCOL+",
    "/wp-",       # WordPress probes
    "/cgi-bin/",
    "/vendor/phpunit",
    "/phpunit/",
    "/.git/",
    "/.env",
    "/.well-known/fierzashell",
    "/.trash",
]

SCANNER_PATH_SUFFIXES: list[str] = [
    ".php",       # Any .php request (we don't use PHP)
]

SCANNER_EXACT_PATHS: set[str] = {
    "/admin.php",
    "/xmlrpc.php",
}
```

### 2. Modify [security.py](app/middleware/security.py)

Add IP banning logic to `custom_security_check()`:

```python
from starlette.responses import Response

# In-memory ban list (fastapi-guard may provide this, or use Redis)
_banned_ips: set[str] = set()

def _get_client_ip(request: Request) -> str:
    """Extract client IP, considering X-Forwarded-For behind proxy."""
    # Check X-Forwarded-For first (if behind reverse proxy)
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    # Fall back to direct client IP
    if request.client:
        return request.client.host
    return "unknown"

def _is_scanner_path(path: str) -> bool:
    """Check if path matches known vulnerability scanner patterns."""
    path_lower = path.lower()

    for prefix in SCANNER_PATH_PREFIXES:
        if path_lower.startswith(prefix.lower()):
            return True

    for suffix in SCANNER_PATH_SUFFIXES:
        if path_lower.endswith(suffix.lower()):
            return True

    return path in SCANNER_EXACT_PATHS

async def custom_security_check(request: Request) -> Optional[Response]:
    path = request.url.path
    client_ip = _get_client_ip(request)

    # Check if IP is already banned
    if client_ip in _banned_ips:
        logfire.debug("Banned IP rejected", ip=client_ip, path=path)
        # Return empty response - effectively drops connection
        return Response(status_code=444)  # nginx-style "no response"

    # Always allow NiceGUI internal routes
    if path.startswith("/_nicegui"):
        return None

    # Allow static assets
    if path.startswith("/assets"):
        return None

    # Check for scanner paths - ban and drop
    if _is_scanner_path(path):
        _banned_ips.add(client_ip)
        logfire.warning(
            "Scanner detected - IP banned",
            ip=client_ip,
            path=path,
            banned_count=len(_banned_ips),
        )
        # Drop connection without response
        return Response(status_code=444)

    return None
```

### 3. Add robots.txt and favicon.ico routes to [main.py](app/main.py)

```python
from fastapi.responses import PlainTextResponse, Response

@app.get("/robots.txt")
async def robots_txt():
    """Serve robots.txt to guide crawlers."""
    content = """User-agent: *
Disallow: /admin
Disallow: /dashboard
Disallow: /lesson
Allow: /
"""
    return PlainTextResponse(content)

@app.get("/favicon.ico")
async def favicon():
    """Return 404 for favicon."""
    return Response(status_code=404)
```

### 4. Optional: Persist bans across restarts

If you want bans to persist across server restarts, we can:

- Write banned IPs to a file on disk
- Use Redis (already configured in security_config.py)
- Store in database

For now, in-memory is fine - bans reset on restart but scanners get re-banned immediately.

## Files to Modify

1. [app/core/security_config.py](app/core/security_config.py) - Add scanner path patterns
2. [app/middleware/security.py](app/middleware/security.py) - Add IP banning + drop logic
3. [app/main.py](app/main.py) - Add robots.txt and favicon.ico routes

## Verification

1. Start the server
2. Test legitimate paths still work: `/`, `/login`, `/dashboard`
3. Test scanner paths get dropped (connection reset):

   ```bash
   curl -v http://localhost:8080/wp-admin.php
   # Should get connection reset or empty response

   # Second request from same IP should also be blocked
   curl -v http://localhost:8080/
   # Should also get blocked (IP is now banned)
   ```

4. Check logs show "Scanner detected - IP banned" at WARNING level
5. Monitor Logfire for reduced "Unauthenticated request" volume
