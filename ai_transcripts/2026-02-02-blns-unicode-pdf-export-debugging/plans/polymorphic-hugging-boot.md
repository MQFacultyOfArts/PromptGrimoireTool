# Plan: Meeting Recorder Improvements

## Issues to Address

1. **Ollama dependency blocks the app** - When ollama isn't running, an error prevents transcription from working
2. **Many old test session folders** - 17 session folders cluttering `meeting_transcripts/`
3. **WAV vs Opus** - Already fixed in recent code; old sessions have WAV, new sessions correctly save Opus

## Root Cause Analysis

The app currently has `cleanup.enabled = True` by default in [config.py](src/meeting_transcriber/config.py). Even though the cleanup code has error handling that gracefully returns original text on failure, the user is seeing errors that make them think transcription isn't working.

The actual error is likely just the printed message `"Ollama cleanup error: ..."` which appears during processing, not a blocking failure.

## Proposed Solution

### 1. Disable Ollama cleanup by default

Change the default in `CleanupConfig` to `enabled: bool = False` instead of `True`.

**File:** [src/meeting_transcriber/config.py:77](src/meeting_transcriber/config.py#L77)

```python
# Change from:
enabled: bool = True
# To:
enabled: bool = False
```

This makes the app work out of the box without requiring ollama. Users who want cleanup can enable it via configuration.

### 2. Organize session folders by hour

Group the 17+ session folders by hour into consolidated directories:

```
meeting_transcripts/
├── 2026-01-12_14h/   # 10 sessions from 14:34-14:59
├── 2026-01-12_15h/   # 5 sessions from 15:07-15:22
├── 2026-01-13_10h/   # 1 session from 10:47
└── 2026-01-13_13h/   # 2 sessions from 13:30
```

Each session folder moves into its corresponding hour folder, preserving original names.

### 3. WAV files (No action needed)

The opus saving is already working correctly. The old WAV files are from before the streaming writer was implemented. No code changes needed - this is already fixed.

## Verification

1. Run `uv run python -m meeting_transcriber` without ollama running
2. Start a recording, pause, and verify transcription works without errors
3. Confirm audio is saved as `.opus` file
