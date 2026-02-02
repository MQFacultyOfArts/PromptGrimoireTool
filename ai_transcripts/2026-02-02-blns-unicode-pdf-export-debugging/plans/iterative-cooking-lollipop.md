# AAF-Stytch SSO Integration - Debugging Report

## Authentication Flow Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Your App      │     │     Stytch      │     │      AAF        │     │   Your App      │
│ localhost:8080  │     │  test.stytch.com│     │central.test.aaf │     │ /auth/sso/callback│
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │                       │
         │ 1. Click "Login AAF"  │                       │                       │
         │──────────────────────>│                       │                       │
         │                       │                       │                       │
         │ 2. 307 Redirect       │                       │                       │
         │<──────────────────────│                       │                       │
         │                       │                       │                       │
         │ 3. /oidc/authorize    │                       │                       │
         │───────────────────────────────────────────────>                       │
         │                       │                       │                       │
         │ 4. ❌ 400 Invalid Client                      │                       │
         │<───────────────────────────────────────────────                       │
         │                       │                       │                       │
```

## Current Status: BLOCKED at Step 4

**Error:** `400 Invalid Client` from AAF's `/oidc/authorize` endpoint

---

## Configuration Summary

### AAF Test Federation (central.test.aaf.edu.au)

| Setting | Value | Status |
|---------|-------|--------|
| App Name | MQ Prompt Grimoire | ✅ |
| Client ID | `405de14a-cab8-409c-bc7a-0728ece19452` | ✅ |
| Client Secret | (regenerated today) | ✅ Set |
| Status | Active | ✅ |
| Protocol | OpenID Connect | ✅ |
| URL | `https://sillytavern.tail0cc7cb.ts.net/` | ✅ Updated |
| Redirect URI | `https://test.stytch.com/v1/b2b/sso/callback/oidc-connection-test-f88ae402-f612-4417-bd4f-b5ca8bb17725` | ✅ |
| Scopes | `eduperson_affiliation`, `email`, `profile` | ✅ |

### Stytch Dashboard (Organization → SSO Connection)

| Setting | Value | Status |
|---------|-------|--------|
| Connection ID | `oidc-connection-test-f88ae402-f612-4417-bd4f-b5ca8bb17725` | ✅ |
| Client ID | `405de14a-cab8-409c-bc7a-0728ece19452` | ✅ Matches AAF |
| Client Secret | (set to match AAF) | ✅ Updated |
| Issuer URL | `https://central.test.aaf.edu.au` | ✅ |
| Identity Provider | Custom OIDC | ✅ |
| Custom Scopes | `openid profile email eduperson_affiliation` | ✅ |
| Redirect URL | `https://test.stytch.com/v1/b2b/sso/callback/oidc-connection-test-f88ae402-...` | ✅ |

### Your App (.env)

| Variable | Required | Status |
|----------|----------|--------|
| `STYTCH_PROJECT_ID` | Yes | ✅ Set |
| `STYTCH_SECRET` | Yes | ✅ Set |
| `STYTCH_PUBLIC_TOKEN` | Yes | ✅ Set (`public-token-test-61b9cb15-eb38-4e79-bae5-8f919f2dfecc`) |
| `STYTCH_SSO_CONNECTION_ID` | Yes | ✅ Set (`oidc-connection-test-f88ae402-...`) |
| `STYTCH_DEFAULT_ORG_ID` | Yes | ✅ Set |

---

## The Failing Request

**URL sent to AAF:**
```
https://central.test.aaf.edu.au/oidc/authorize
  ?client_id=405de14a-cab8-409c-bc7a-0728ece19452
  &nonce=6NYJKQRGub3-05RyU_5zBAxs6uERKPYrNocs3lP4j0hN
  &redirect_uri=https://test.stytch.com/v1/b2b/sso/callback/oidc-connection-test-f88ae402-f612-4417-bd4f-b5ca8bb17725
  &response_type=code
  &scope=openid+profile+email+eduperson_affiliation
  &state=6NYJKQRGub3-05RyU_5zBAxs6uERKPYrNocs3lP4j0hN
```

**AAF Response:**
```
302 Found → Location: https://central.test.aaf.edu.au/oidc/error?message=Invalid+Client&status=bad_request
```

---

## What We've Verified

- [x] Client ID matches between Stytch and AAF
- [x] AAF app status is "Active"
- [x] Redirect URI in AAF matches what Stytch sends
- [x] Client secret regenerated and updated in Stytch
- [x] Issuer URL correct (`https://central.test.aaf.edu.au`)
- [x] AAF OIDC discovery endpoint accessible
- [x] Scopes configured in AAF
- [x] URL field in AAF updated to HTTPS domain

---

## Root Cause: UNKNOWN

The error occurs at AAF's authorize endpoint, which does NOT use the client secret (that's only used at the token endpoint). At the authorize stage, AAF only validates:

1. `client_id` exists and is active
2. `redirect_uri` matches a registered URI for that client
3. `response_type` is supported
4. `scope` contains valid values

All of these appear correct based on our verification.

---

## Recommended Next Steps

### 1. Contact AAF Support

Email: support@aaf.edu.au

Include:
- Client ID: `405de14a-cab8-409c-bc7a-0728ece19452`
- Full authorize URL (above)
- Error: "Invalid Client" at `/oidc/authorize`
- Request they check server-side logs for the specific rejection reason

### 2. Verify No Caching Issues

- Try a different browser or incognito mode
- Clear cookies for `central.test.aaf.edu.au`
- Wait 2 hours (AAF mentions scope changes can take up to 2 hours)

### 3. Check for Hidden AAF Requirements

Ask AAF Support if test federation requires:
- Specific organization approval
- IP allowlisting
- Additional app activation steps not visible in the portal

### 4. Test AAF Directly (Bypass Stytch)

Create a minimal test to hit AAF directly from your browser:
```
https://central.test.aaf.edu.au/oidc/authorize?client_id=405de14a-cab8-409c-bc7a-0728ece19452&redirect_uri=https://test.stytch.com/v1/b2b/sso/callback/oidc-connection-test-f88ae402-f612-4417-bd4f-b5ca8bb17725&response_type=code&scope=openid&nonce=test123&state=test123
```

If this also fails, the issue is definitely AAF-side configuration.

---

## Files Involved (No Code Changes Needed for AAF)

The AAF SSO code is correct. That issue is a configuration problem between AAF and Stytch.

| File | Purpose | Status |
|------|---------|--------|
| `src/promptgrimoire/auth/client.py:243-267` | SSO start URL generation | ✅ Correct |
| `src/promptgrimoire/auth/config.py` | Loads env vars | ✅ Correct |
| `src/promptgrimoire/pages/auth.py:140-173` | SSO login button | ✅ Correct |
| `.env` | Stytch credentials | ✅ Configured |

---

# GitHub OAuth - Bug Found & Fix Plan

## Problem Identified

Stytch B2B has **two OAuth flows**:

| Flow | Start URL | Authenticate | Returns |
|------|-----------|--------------|---------|
| **Discovery** | `/oauth/github/discovery/start` | `oauth.discovery.authenticate` | IST + org list |
| **Direct** | `/oauth/github/start?organization_id=X` | `oauth.authenticate` | Final session |

**Current code:** Uses Discovery flow start → Direct flow authenticate (MISMATCH!)

## Option A: Fix to use Discovery flow properly (more complex)

Discovery flow returns an **Intermediate Session Token** + list of organizations, NOT a final session:

```
1. GitHub OAuth → callback with token
2. Discovery Authenticate → intermediate_session_token + discovered_organizations[]
3. Exchange Intermediate Session (with org_id) → final session_token
```

## Option B: Switch to Direct OAuth flow (simpler, recommended)

Since we already know the `STYTCH_DEFAULT_ORG_ID`, use the Direct flow:

```
1. GitHub OAuth with org_id → callback with token
2. Direct Authenticate → final session (one step!)
```

## Implementation Plan (Option B - Direct Flow)

Since we have `STYTCH_DEFAULT_ORG_ID` configured, the simplest fix is to switch to the Direct OAuth flow.

### Step 1: Update `get_oauth_start_url` to use Direct flow

In `src/promptgrimoire/auth/client.py:275-300`, change from Discovery to Direct:

**Current:**
```python
def get_oauth_start_url(
    self,
    provider: str,
    public_token: str,
    discovery_redirect_url: str,
) -> OAuthStartResult:
    ...
    redirect_url = (
        f"{base_url}/v1/b2b/public/oauth/{provider}/discovery/start"
        f"?{urlencode(params)}"
    )
```

**Change to:**
```python
def get_oauth_start_url(
    self,
    provider: str,
    public_token: str,
    organization_id: str,
    login_redirect_url: str,
) -> OAuthStartResult:
    ...
    params = {
        "public_token": public_token,
        "organization_id": organization_id,
        "login_redirect_url": login_redirect_url,
        "signup_redirect_url": login_redirect_url,
    }
    redirect_url = (
        f"{base_url}/v1/b2b/public/oauth/{provider}/start"
        f"?{urlencode(params)}"
    )
```

### Step 2: Update the login page to pass organization_id

In `src/promptgrimoire/pages/auth.py:176-207`, update `start_github_oauth`:

```python
def start_github_oauth() -> None:
    auth_client = get_auth_client()
    config = get_config()

    if not config.public_token:
        ...

    if not config.default_org_id:
        logger.error("STYTCH_DEFAULT_ORG_ID not configured")
        ui.notify("GitHub login not configured", type="negative")
        return

    callback_url = f"{config.base_url}/auth/oauth/callback"

    result = auth_client.get_oauth_start_url(
        provider="github",
        public_token=config.public_token,
        organization_id=config.default_org_id,  # NEW
        login_redirect_url=callback_url,        # RENAMED
    )
```

### Step 3: Update protocol and mock

Update method signatures in:
- `src/promptgrimoire/auth/protocol.py`
- `src/promptgrimoire/auth/mock.py`

### Step 4: No change needed to `authenticate_oauth`

The existing `authenticate_oauth` method already uses the correct Direct flow endpoint:
```python
response = await self._client.oauth.authenticate_async(oauth_token=token)
```

This is correct for the Direct flow!

## Files to Modify

| File | Change |
|------|--------|
| `src/promptgrimoire/auth/client.py:275-300` | Change Discovery URL to Direct URL, update params |
| `src/promptgrimoire/auth/protocol.py` | Update `get_oauth_start_url` signature |
| `src/promptgrimoire/auth/mock.py` | Update mock to match new signature |
| `src/promptgrimoire/pages/auth.py:176-207` | Pass `organization_id` instead of discovery URL |

## Verification

1. Run the app: `uv run python -m promptgrimoire`
2. Click "Login with GitHub"
3. Authorize with GitHub
4. Should redirect back and complete login (instead of "OAuth auth failed")
5. Protected page should show user info
