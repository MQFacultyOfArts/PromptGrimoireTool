# Plan: Fix Logfire Scrubbing to Debug ElevenLabs TTS Error

## Problem Summary

When ElevenLabs TTS streaming fails (after receiving only 1 audio chunk), the error message is being scrubbed by Logfire because it contains "API key". We need to see the actual error to debug the TTS streaming issue.

**Current logs show:**
```
"error": "[Scrubbed due to 'API key']"
"logfire.scrubbed": [{"path": ["attributes", "error"], "matched_substring": "API key"}]
```

Despite `scrubbing=False` being set in the code, Logfire is still scrubbing "API key" patterns.

## Root Cause

The `logfire.configure()` is being called multiple times with separate parameters:
```python
logfire.configure(send_to_logfire="if-token-present")  # line 25
logfire.instrument_pydantic_ai()                        # line 26
logfire.configure(scrubbing=False)                      # line 27
logfire.configure(console=...)                          # line 28
```

When `configure()` is called multiple times, later calls may not preserve settings from earlier calls. The `scrubbing=False` setting may be getting reset or not properly applied.

## Solution

Consolidate all `logfire.configure()` calls into a single call with all parameters:

```python
logfire.configure(
    send_to_logfire="if-token-present",
    scrubbing=False,
    console=logfire.ConsoleOptions(verbose=True, min_log_level="debug")
)
logfire.instrument_pydantic_ai()
```

## Files to Modify

1. **[app/main.py](app/main.py)** (lines 25-28)
2. **[examples/example9_audio_pipeline/main.py](examples/example9_audio_pipeline/main.py)** (lines 32-35)

## Changes

### app/main.py

**Before:**
```python
# Initialize logging
logfire.configure(send_to_logfire="if-token-present")
logfire.instrument_pydantic_ai()
logfire.configure(scrubbing=False)
logfire.configure(console=logfire.ConsoleOptions(verbose=True, min_log_level="debug"))
```

**After:**
```python
# Initialize logging
logfire.configure(
    send_to_logfire="if-token-present",
    scrubbing=False,
    console=logfire.ConsoleOptions(verbose=True, min_log_level="debug")
)
logfire.instrument_pydantic_ai()
```

### examples/example9_audio_pipeline/main.py

Same change at lines 32-35.

## Verification

1. Restart the server
2. Trigger TTS streaming (send a message that generates a teacher response)
3. Check Logfire logs - the error message should now show the actual ElevenLabs error instead of `[Scrubbed due to 'API key']`
4. The actual error message will help identify the root cause of the TTS streaming failure

## Expected Outcome

After this change, we'll be able to see the actual error message from ElevenLabs, which will help debug why only 1 audio chunk is being received before streaming fails.

## Sources

- [Logfire Scrubbing Documentation](https://logfire.pydantic.dev/docs/how-to-guides/scrubbing/)
- [Logfire API Reference](https://logfire.pydantic.dev/docs/reference/api/logfire/)
