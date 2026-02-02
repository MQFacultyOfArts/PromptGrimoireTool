# Plan: Fix GitHub Issue #46 - Text should appear even when TTS fails

## Problem Summary

Two related issues:
1. **Bug #46**: When ElevenLabs TTS fails (out of credits, API errors), AI response text doesn't appear
2. **Hiccup on longer messages**: Text "jumps" ahead of audio when isFinal arrives

## Root Cause Analysis

### Current Flow
```
Claude streams text → stream_callback → text_accumulator AND tts_queue
                                             ↓
                              ElevenLabs WebSocket → audio chunks + alignment data
                                             ↓
                              text_sync_service shows text char-by-char (synced to alignment timing)
                                             ↓
                              isFinal received → finish_message() → DUMPS all remaining text
                                             ↓
                              on_audio_complete() → message.complete()
                                             ↓
                              Browser still playing buffered audio...
                                             ↓
                              Browser "ended" event → on_audio_state_change("finished")
```

### Issue 1: TTS Failure
- TTS task runs fire-and-forget (`asyncio.create_task`)
- If WebSocket fails, exception is lost
- `text_obj.content` stays empty (bound to text_sync_service)
- `text_accumulator` has all text but never displayed

### Issue 2: Text Hiccup
- `finish_message()` called when isFinal received from ElevenLabs
- This dumps ALL remaining text immediately
- But browser still has buffered audio to play
- Text "jumps" ahead of audio playback

## Solution

### Core Principle
**Decouple text display completion from ElevenLabs isFinal. Instead:**
- Continue char-by-char sync while audio is playing
- Only dump remaining text when browser audio actually finishes ("ended" event)
- On TTS failure, show accumulated text immediately

### Changes Required

#### File 1: [app/ui/components/conversation/message_display.py](app/ui/components/conversation/message_display.py)

**Change A: Wrap TTS task with error handling (~line 276-280)**

```python
# CURRENT:
asyncio.create_task(
    tts_service.stream_text_to_audio(
        message_id, text_iterator(), on_audio_complete
    )
)

# NEW:
async def tts_with_fallback():
    nonlocal text_accumulator
    try:
        await tts_service.stream_text_to_audio(
            message_id, text_iterator(), on_audio_complete
        )
    except Exception as e:
        logfire.error("TTS streaming failed", error=str(e))
        # Show accumulated text directly (bypass text_obj binding)
        message.update_text(text_accumulator)
        message.complete()

asyncio.create_task(tts_with_fallback())
```

**Change B: Add callback for browser audio finish (~line 264-267)**

We need a new callback that gets called when browser audio ends (not when ElevenLabs sends isFinal).

```python
# CURRENT:
async def on_audio_complete() -> None:
    """Called when audio generation is complete (isFinal received)."""
    logfire.debug("Audio generation complete, marking message complete")
    message.complete()

# NEW - rename and add new callback:
async def on_tts_stream_complete() -> None:
    """Called when TTS WebSocket receives isFinal (audio generation done)."""
    logfire.debug("TTS stream complete (isFinal received)")
    # Don't dump text here - wait for browser to finish playing

async def on_browser_audio_ended() -> None:
    """Called when browser finishes playing audio."""
    logfire.debug("Browser audio ended, showing any remaining text")
    # Now it's safe to show all remaining text
    await text_sync_service.finish_message(message_id)
    message.complete()
```

**Change C: Wire up on_browser_audio_ended to audio state change**

The `on_audio_state_change` callback is already passed to `create_callbacks_for_response()`. We need to call `finish_message()` when state is "finished".

In [lesson.py](examples/example9_audio_pipeline/pages/lesson.py) at ~line 500-515, `handle_audio_state_change` is defined. We need to also trigger `finish_message()` here.

**Change D: Ensure text visible on completion (~line 315-324)**

```python
# CURRENT:
async def completion_callback() -> None:
    if tts_queue:
        tts_queue.put_nowait(None)
    else:
        message.complete()

# NEW:
async def completion_callback() -> None:
    if tts_queue:
        tts_queue.put_nowait(None)
        # Ensure text visible as fallback (text_sync will override if working)
        message.update_text(text_accumulator)
    else:
        message.complete()
```

#### File 2: [app/services/tts_websocket_service.py](app/services/tts_websocket_service.py)

**Change E: Don't call finish_message on isFinal (~line 285-296)**

```python
# CURRENT:
elif data.get("isFinal"):
    logfire.info("Received isFinal from TTS", ...)
    await self.text_sync_service.finish_message(message_id)  # REMOVE THIS
    if on_audio_complete:
        await on_audio_complete()

# NEW:
elif data.get("isFinal"):
    logfire.info("Received isFinal from TTS", ...)
    # Don't call finish_message here - let browser "ended" trigger it
    if on_audio_complete:
        await on_audio_complete()
```

#### File 3: [examples/example9_audio_pipeline/pages/lesson.py](examples/example9_audio_pipeline/pages/lesson.py)

**Change F: Call finish_message when browser audio ends (~line 500-515)**

```python
# CURRENT:
def handle_audio_state_change(state: str) -> None:
    if state == "playing":
        deck.set_state(KoalaState.SPEAKING)
    elif state == "finished":
        deck.set_state(KoalaState.READY)

# NEW - need async and finish_message call:
async def handle_audio_state_change(state: str, message_id: str) -> None:
    if state == "playing":
        deck.set_state(KoalaState.SPEAKING)
    elif state == "finished":
        deck.set_state(KoalaState.READY)
        # Now finish text display
        await text_sync_service.finish_message(message_id)
```

This requires passing `message_id` through the callback chain, which adds complexity.

### Alternative: Simpler Approach

Instead of wiring through the audio state change, we could:
1. Keep `finish_message()` on isFinal
2. But make `finish_message()` NOT dump text immediately
3. Instead, let the chunk processor continue naturally
4. Only dump remaining text after a delay (estimated remaining audio duration)

But this is harder to get right and timing-dependent.

## Recommended Implementation Order

1. **Change A + D**: Error handling + fallback text (fixes issue #46)
2. **Test**: Verify TTS failure shows text
3. **Change E + F**: Move finish_message to browser audio end (fixes hiccup)
4. **Test**: Verify no text jump on long messages

## Files Summary

| File | Changes | Purpose |
|------|---------|---------|
| [message_display.py](app/ui/components/conversation/message_display.py) | A, B, C, D | Error handling, callbacks, fallback |
| [tts_websocket_service.py](app/services/tts_websocket_service.py) | E | Remove early finish_message call |
| [lesson.py](examples/example9_audio_pipeline/pages/lesson.py) | F | Call finish_message on browser audio end |

## Verification Plan

1. **TTS working normally**: Text syncs with audio, no jump at end
2. **TTS init fails**: `ELEVENLABS_API_KEY=""` - text appears immediately
3. **TTS mid-stream failure**: Invalid API key - text appears when Claude finishes
4. **Long message**: Text continues smoothly until audio ends in browser
5. **Audio replay**: Replaying audio doesn't re-trigger text display
