# Fix pytest security middleware test failures

## Problem

3 tests in `tests/security/test_security_middleware.py` are failing due to environment variable interference:

1. **`test_default_values`** (line 176) - Creates `SecuritySettings()` which reads `SECURITY_ENABLED` from environment
2. **`test_microphone_not_blocked_in_permissions_policy`** (line 227) - Doesn't mock `security_settings`, so middleware setup returns early when `SECURITY_ENABLED=false`
3. **`test_camera_and_geolocation_still_blocked`** (line 270) - Same issue as #2

## Root Cause

The tests don't isolate themselves from environment variables. When `SECURITY_ENABLED=false` is in the environment, the tests fail because:
- `SecuritySettings()` uses Pydantic's env var loading
- `setup_security_middleware()` returns early when disabled

## Solution

### Fix 1: `test_default_values` (line 173)

Convert to a method that accepts pytest's `monkeypatch` fixture and clear security-related env vars:

```python
def test_default_values(self, monkeypatch):
    """Default values should be sensible for development."""
    # Clear security env vars so we test actual defaults
    for key in list(os.environ.keys()):
        if key.startswith(('SECURITY_', 'RATE_LIMIT', 'AUTO_BAN', 'ENFORCE_', 'ENABLE_', 'PASSIVE_')):
            monkeypatch.delenv(key, raising=False)

    settings = SecuritySettings()
    assert settings.SECURITY_ENABLED is True
    # ... rest unchanged
```

Also add `import os` at the top of the file.

### Fix 2 & 3: `test_microphone_not_blocked_in_permissions_policy` (line 227) and `test_camera_and_geolocation_still_blocked` (line 270)

Wrap the `setup_security_middleware` call with a mock of `security_settings.SECURITY_ENABLED = True`:

```python
with patch.object(app, "add_middleware", side_effect=capture_add_middleware):
    with patch("app.middleware.security.security_settings") as mock_settings:
        mock_settings.SECURITY_ENABLED = True
        from app.middleware.security import setup_security_middleware
        setup_security_middleware(app)
```

## File to Modify

- [tests/security/test_security_middleware.py](tests/security/test_security_middleware.py)

## Verification

```bash
uv run pytest tests/security/test_security_middleware.py::TestSecuritySettings::test_default_values tests/security/test_security_middleware.py::TestSecurityHeaders -v
```

Then full suite:
```bash
uv run pytest
```
