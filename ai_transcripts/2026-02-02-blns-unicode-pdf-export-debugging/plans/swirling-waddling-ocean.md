# Plan: GitHub Issue #45 - Replay Button After Page Refresh

## Problem
After page refresh, assistant messages from history are displayed using `StreamingMessage` (text-only). Users cannot replay teacher audio because:
1. Audio is not persisted - only held in memory during live streaming
2. `display_history()` creates `StreamingMessage` objects with no audio capability

## Solution
Add on-demand TTS: when user clicks replay on a history message, regenerate the audio via ElevenLabs and play it.

---

## Implementation Steps

### Step 1: Add `/api/audio/speak` Endpoint

**File:** [audio.py](app/routers/audio.py)

Add a POST endpoint that takes text and streams TTS audio:

```python
from pydantic import BaseModel

class SpeakRequest(BaseModel):
    text: str

@router.post("/speak")
async def speak_text(request: SpeakRequest):
    """Generate TTS audio on-demand for replay."""
    # Use TTSService.text_to_audio_stream(request.text)
    # Return StreamingResponse with audio/mpeg
```

### Step 2: Create `HistoryMessageComponent`

**File:** [history_message.py](app/ui/components/conversation/history_message.py) (new)

A simple assistant message with replay button:
- Same styling as `StreamingMessage` (ocean-blue background, koala icon)
- Shows text content
- Replay button (koala icon) always visible
- On click: call `/api/audio/speak`, play streamed audio

### Step 3: Update `display_history()`

**File:** [message_display.py:457-460](app/ui/components/conversation/message_display.py#L457-L460)

Change from:
```python
self.add_message("assistant", content)
```

To use new `HistoryMessageComponent` that includes replay capability.

---

## Files to Modify

| File | Change |
|------|--------|
| [audio.py](app/routers/audio.py) | Add `POST /api/audio/speak` endpoint |
| [history_message.py](app/ui/components/conversation/history_message.py) | Create new component (new file) |
| [message_display.py](app/ui/components/conversation/message_display.py) | Use `HistoryMessageComponent` in `display_history()` |

## Verification

1. Start a lesson session and have the AI teacher speak
2. Refresh the page
3. Verify replay button appears on all assistant messages
4. Click replay and verify audio plays
5. Test multiple replays work correctly
