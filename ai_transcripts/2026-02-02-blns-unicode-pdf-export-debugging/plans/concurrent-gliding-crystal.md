# Plan: Configure Redirect URLs for Tailscale Funnel

## Summary

Configure Stytch authentication to use the Tailscale Funnel URL `https://sillytavern.tail0cc7cb.ts.net/` for OAuth/magic link callbacks.

## Changes Required

### 1. Environment Variable (`.env`)

Update `BASE_URL` to the Tailscale Funnel URL:

```env
BASE_URL=https://sillytavern.tail0cc7cb.ts.net
```

**No trailing slash** - the code appends paths like `/auth/callback`.

### 2. Stytch Dashboard Configuration

You'll need to add the new redirect URLs to your Stytch project's allowed list:

1. Go to [Stytch Dashboard](https://stytch.com/dashboard) → Your B2B Project → **Redirect URLs**
2. Add these URLs to the allowed list:
   - `https://sillytavern.tail0cc7cb.ts.net/auth/callback` (magic links)
   - `https://sillytavern.tail0cc7cb.ts.net/auth/sso/callback` (SSO)
   - `https://sillytavern.tail0cc7cb.ts.net/auth/oauth/callback` (GitHub OAuth)

### 3. GitHub OAuth (if using)

If you're using GitHub OAuth, update the callback URL in your GitHub OAuth App settings:
- Go to GitHub → Settings → Developer settings → OAuth Apps → Your App
- Update "Authorization callback URL" to: `https://sillytavern.tail0cc7cb.ts.net/auth/oauth/callback`

## No Code Changes Needed

The codebase already uses `BASE_URL` dynamically for all callback URLs:
- [config.py:102-110](src/promptgrimoire/auth/config.py#L102-L110) - generates callback URLs from `base_url`
- [auth.py:118](src/promptgrimoire/pages/auth.py#L118) - magic link callback
- [auth.py:188](src/promptgrimoire/pages/auth.py#L188) - OAuth callback

## Verification

1. Set `BASE_URL=https://sillytavern.tail0cc7cb.ts.net` in `.env`
2. Ensure Tailscale Funnel is running: `tailscale funnel 8080`
3. Start the app: `uv run python -m promptgrimoire`
4. Navigate to `https://sillytavern.tail0cc7cb.ts.net/login`
5. Test magic link login - callback should redirect to the Tailscale URL
