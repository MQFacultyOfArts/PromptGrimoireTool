---
source: https://stytch.com/docs/api/webauthn
fetched: 2025-01-14
summary: Stytch Passkeys/WebAuthn registration and authentication
---

# Stytch Passkeys (WebAuthn)

Passkeys provide passwordless authentication using device biometrics or security keys.

## Overview

Passkeys require a two-step flow:
1. **Start** - Get credential options from Stytch
2. **Complete** - Send browser's credential response to Stytch

## Registration Flow

### 1. Start Registration

```python
from stytch import Client

client = Client(
    project_id="your-project-id",
    secret="your-secret",
)

# User must already exist (create via magic link first)
resp = client.webauthn.register_start(
    user_id="user-test-xxx",
    domain="yourapp.com",
    return_passkey_credential_options=True,  # Optimize for passkeys
    authenticator_type="platform",  # or "cross-platform" for security keys
)

# Send this to browser
public_key_options = resp.public_key_credential_creation_options
```

### 2. Browser Creates Credential

```javascript
// Use webauthn-json library for easier handling
import { create } from '@github/webauthn-json';

async function registerPasskey(publicKeyOptions) {
    // Parse the options from server
    const options = JSON.parse(publicKeyOptions);

    // Browser prompts user for biometric/PIN
    const credential = await create({ publicKey: options });

    // Send credential back to server
    return JSON.stringify(credential);
}
```

### 3. Complete Registration

```python
resp = client.webauthn.register(
    user_id="user-test-xxx",
    public_key_credential=credential_json,  # From browser
    session_duration_minutes=60 * 24 * 7,
)

print(resp.webauthn_registration_id)
print(resp.session_token)
```

## Authentication Flow

### 1. Start Authentication

```python
resp = client.webauthn.authenticate_start(
    domain="yourapp.com",
    return_passkey_credential_options=True,
    # user_id is optional - if omitted, allows any registered passkey
)

public_key_options = resp.public_key_credential_request_options
```

### 2. Browser Gets Credential

```javascript
import { get } from '@github/webauthn-json';

async function authenticatePasskey(publicKeyOptions) {
    const options = JSON.parse(publicKeyOptions);

    // Browser prompts user for biometric/PIN
    const credential = await get({ publicKey: options });

    return JSON.stringify(credential);
}
```

### 3. Complete Authentication

```python
resp = client.webauthn.authenticate(
    public_key_credential=credential_json,
    session_duration_minutes=60 * 24 * 7,
)

print(resp.user_id)
print(resp.session_token)
```

## NiceGUI Integration

### Complete Example

```python
from nicegui import app, ui
from stytch import Client
import os
import json

client = Client(
    project_id=os.getenv("STYTCH_PROJECT_ID"),
    secret=os.getenv("STYTCH_SECRET"),
)

DOMAIN = os.getenv("DOMAIN", "localhost")

# Add webauthn-json library
ui.add_head_html('''
<script src="https://unpkg.com/@github/webauthn-json@2.1.1/dist/esm/webauthn-json.browser-ponyfill.js"></script>
''')

@ui.page('/register-passkey')
async def register_passkey_page():
    user_id = app.storage.user.get('user_id')
    if not user_id:
        ui.navigate.to('/login')
        return

    async def start_registration():
        try:
            resp = await client.webauthn.register_start_async(
                user_id=user_id,
                domain=DOMAIN,
                return_passkey_credential_options=True,
            )

            # Send options to browser and get credential
            credential = await ui.run_javascript(f'''
                const options = JSON.parse('{resp.public_key_credential_creation_options}');
                const credential = await webauthnJSON.create({{ publicKey: options }});
                return JSON.stringify(credential);
            ''')

            # Complete registration
            resp2 = await client.webauthn.register_async(
                user_id=user_id,
                public_key_credential=credential,
                session_duration_minutes=60 * 24 * 7,
            )

            app.storage.user['session_token'] = resp2.session_token
            ui.notify('Passkey registered!', type='positive')

        except Exception as e:
            ui.notify(f'Error: {e}', type='negative')

    ui.label('Register a Passkey').classes('text-h5')
    ui.button('Register Passkey', on_click=start_registration)


@ui.page('/passkey-login')
async def passkey_login_page():
    async def authenticate():
        try:
            # Start authentication
            resp = await client.webauthn.authenticate_start_async(
                domain=DOMAIN,
                return_passkey_credential_options=True,
            )

            # Get credential from browser
            credential = await ui.run_javascript(f'''
                const options = JSON.parse('{resp.public_key_credential_request_options}');
                const credential = await webauthnJSON.get({{ publicKey: options }});
                return JSON.stringify(credential);
            ''')

            # Complete authentication
            resp2 = await client.webauthn.authenticate_async(
                public_key_credential=credential,
                session_duration_minutes=60 * 24 * 7,
            )

            app.storage.user['user_id'] = resp2.user_id
            app.storage.user['session_token'] = resp2.session_token
            ui.notify('Login successful!', type='positive')
            ui.navigate.to('/dashboard')

        except Exception as e:
            ui.notify(f'Error: {e}', type='negative')

    ui.label('Login with Passkey').classes('text-h5')
    ui.button('Use Passkey', on_click=authenticate)


ui.run()
```

### JavaScript Helper (Inline)

```python
ui.add_head_html('''
<script type="module">
import { create, get } from 'https://unpkg.com/@github/webauthn-json@2.1.1/dist/esm/webauthn-json.js';

window.registerPasskey = async function(optionsJson) {
    const options = JSON.parse(optionsJson);
    const credential = await create({ publicKey: options });
    return JSON.stringify(credential);
};

window.authenticatePasskey = async function(optionsJson) {
    const options = JSON.parse(optionsJson);
    const credential = await get({ publicKey: options });
    return JSON.stringify(credential);
};
</script>
''')
```

## Authenticator Types

| Type | Description | Example |
|------|-------------|---------|
| `platform` | Built-in device authenticator | Face ID, Touch ID, Windows Hello |
| `cross-platform` | External authenticator | YubiKey, security key |
| (omit) | Allow both types | User chooses |

## Error Handling

Common errors:

| Error | Meaning |
|-------|---------|
| `invalid_domain` | Domain doesn't match registration |
| `no_pending_webauthn_registration` | Start wasn't called or expired |
| `invalid_public_key_credential` | Browser response malformed |
| `duplicate_webauthn_registration` | Credential already registered |

```python
from stytch.core.response_base import StytchError

try:
    resp = await client.webauthn.authenticate_async(
        public_key_credential=credential,
    )
except StytchError as e:
    if e.details.error_type == "webauthn_registration_not_found":
        # No passkey registered for this user
        pass
```

## Flow: Magic Link + Passkey Registration

Recommended onboarding:

1. User signs up via magic link
2. After first login, prompt to register passkey
3. Future logins can use passkey (faster) or magic link (fallback)

```python
@ui.page('/dashboard')
async def dashboard():
    user_id = app.storage.user.get('user_id')

    # Check if user has passkey registered
    user = await get_user(user_id)
    has_passkey = len(user.webauthn_registrations) > 0

    if not has_passkey:
        with ui.dialog() as dialog, ui.card():
            ui.label('Register a passkey for faster logins?')
            ui.button('Yes', on_click=lambda: ui.navigate.to('/register-passkey'))
            ui.button('Later', on_click=dialog.close)
        dialog.open()
```

## Security Notes

- Passkeys are phishing-resistant (bound to domain)
- Private keys never leave the device
- User verification (biometric/PIN) required
- Works across devices with cloud sync (Apple, Google, Microsoft)
