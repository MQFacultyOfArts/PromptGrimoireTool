# Plan: Minimal Proof of Concept - Read Inbox Subject

## Goal

Verify we can authenticate to your org's Microsoft Graph API and read email - before building the full "send and archive" tool.

## The Authentication Challenge

You mentioned you can't create Azure AD app registrations. Good news: there's a workaround.

**Microsoft's pre-registered app:** The Microsoft Graph PowerShell SDK uses a pre-registered enterprise app (`14d82eec-204b-4c2f-b7e8-296a70dab67e` / "Microsoft Graph Command Line Tools"). If your org uses Graph PowerShell at all, this app likely already exists in your tenant and we can use it from Python.

## Phase 1: Minimal PoC

### Step 1: Add dependencies to pyproject.toml

```toml
dependencies = [
    "msgraph-sdk>=1.0.0",
    "azure-identity>=1.15.0",
]
```

### Step 2: Create minimal test script

A simple script that:
1. Uses DeviceCodeCredential with Microsoft's pre-registered app ID
2. Attempts to fetch the single most recent message from inbox
3. Prints the subject line (or the error if blocked)

### Step 3: Run and observe

```bash
uv sync
uv run python main.py
```

**Possible outcomes:**

1. **Success** - You see a device code prompt, authenticate in browser, and see your latest email subject. We proceed to build the full tool.

2. **AADSTS50105** - Your org has blocked the Graph CLI app for non-assigned users. You'd need IT to either:
   - Assign you access to the existing app, OR
   - Create a custom app registration for you

3. **Consent required** - The Mail.Read scope needs admin consent. IT would need to grant it.

4. **App doesn't exist** - The enterprise app isn't in your tenant. An admin running `Connect-MgGraph` once would create it.

## Files to Modify

- [pyproject.toml](pyproject.toml) - Add dependencies
- [main.py](main.py) - Replace stub with PoC code

## Verification

Success looks like:
```
To sign in, use a web browser to open https://microsoft.com/devicelogin and enter code XXXXXXX
Most recent email: Re: Weekly sync meeting
```

## Next Steps After PoC

If auth works, we'll extend to:
1. Query for replied-to emails (PidTagLastVerbExecuted = 102)
2. Move them to Archive folder
3. Add CLI flags (--dry-run, -v, etc.)
